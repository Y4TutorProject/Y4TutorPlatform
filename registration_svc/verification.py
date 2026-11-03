import hashlib
import secrets
import smtplib
import time
from email.message import EmailMessage
from urllib.parse import quote

from itsdangerous import BadData, URLSafeTimedSerializer


class MailDeliveryError(Exception):
    """Indicate that a verification email could not be sent."""


class SMTPMailer:
    def __init__(self, host, port, sender):
        """Configure the development SMTP connection.

        Args:
            host (str): SMTP server hostname.
            port (int): SMTP server port.
            sender (str): Verification email sender address.
        """
        self.host, self.port, self.sender = host, port, sender

    def send_verification(self, email, link):
        """Send an email ownership verification link through SMTP.

        Args:
            email (str): Recipient address.
            link (str): Verification URL containing an expiring signed token.

        Raises:
            MailDeliveryError: SMTP delivery fails.
        """
        message = EmailMessage()
        message["From"], message["To"] = self.sender, email
        message["Subject"] = "Verify your TutorPlatform email"
        message.set_content(f"Verify your email address to activate your account:\n\n{link}\n\n"
                            "This link expires in one hour and can only be used once.\n")
        try:
            with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            raise MailDeliveryError() from None


class EmailVerification:
    def __init__(self, dao, mailer, secret, public_url, max_age=3600):
        """Configure email verification and one-use token storage.

        Args:
            dao (MongoUsersDAO): User persistence object.
            mailer (SMTPMailer): Verification email sender.
            secret (str): Signing key for verification tokens.
            public_url (str): Public frontend base URL.
            max_age (int): Token lifetime in seconds. Defaults to 3600.
        """
        self.dao, self.mailer = dao, mailer
        self.serializer = URLSafeTimedSerializer(secret, salt="email-verification")
        self.public_url, self.max_age = public_url.rstrip("/"), max_age

    def send(self, user):
        """Issue a new one-use token and email its link to a pending user.

        Args:
            user (User): Account awaiting email verification.

        Raises:
            MailDeliveryError: The email cannot be delivered.
        """
        nonce = secrets.token_urlsafe(32)
        digest = hashlib.sha256(nonce.encode()).hexdigest()
        if not self.dao.set_verification_token(str(user.id), digest):
            return
        token = self.serializer.dumps({"id": str(user.id), "email": user.email, "nonce": nonce})
        self.mailer.send_verification(user.email, f"{self.public_url}/verify-email#token={quote(token)}")
        self.dao.collection.update_one({"id": str(user.id)}, {"$set": {"verification_sent_at": time.time()}})

    def verify(self, token):
        """Activate an account using a signed, expiring, single-use token.

        Args:
            token (str): Token from the verification email.

        Returns:
            User: Activated account.

        Raises:
            ValueError: The token is invalid, expired, or already consumed.
        """
        try:
            if not isinstance(token, str):
                raise ValueError()
            data = self.serializer.loads(token, max_age=self.max_age)
            digest = hashlib.sha256(data["nonce"].encode()).hexdigest()
            user = self.dao.verify_email(data["id"], data["email"], digest)
            if user is None:
                raise ValueError()
            return user
        except (BadData, KeyError, TypeError, AttributeError, ValueError):
            raise ValueError("This verification link is invalid, expired, or has already been used.") from None

    def resend(self, email):
        """Resend verification without disclosing whether an account exists.

        Args:
            email (str): Normalized email address requesting verification.

        Raises:
            MailDeliveryError: SMTP delivery fails for an eligible account.
        """
        user = self.dao.get_user_by_email(email)
        if user is None or user.status.value != "pending_verification":
            return
        record = self.dao.collection.find_one({"id": str(user.id)})
        if time.time() - record.get("verification_sent_at", 0) >= 60:
            self.send(user)
