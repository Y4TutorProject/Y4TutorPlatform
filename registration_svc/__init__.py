import os

from flask import Flask, jsonify, request
from flask_wtf.csrf import CSRFError, CSRFProtect, generate_csrf
from pymongo.errors import DuplicateKeyError, PyMongoError

from users_svc.users_dao.MongoUsersDAO import MongoUsersDAO

from .implementations.registration_svc import RegistrationService
from .college_client import CollegeClient, CollegeServiceUnavailable
from .verification import EmailVerification, SMTPMailer, MailDeliveryError
from users_svc.credentials import normalize_email


def create_app(config=None, dao=None, college_client=None, mailer=None):
    """Create the registration API with CSRF protection and a user DAO.

    Args:
        config (dict | None): Flask configuration overrides. Defaults to None.
        dao (UsersDAO | None): Data access object. Defaults to MongoUsersDAO.
        college_client (CollegeClient | None): College lookup client. Defaults
            to a client using COLLEGE_API_URL.
        mailer (SMTPMailer | None): Verification sender. Defaults to SMTP.

    Returns:
        Flask: Configured application with its routes, services, and error
            handlers.

    Raises:
        RuntimeError: SECRET_KEY is missing or shorter than 32 characters.
        PyMongoError: The configured database cannot be reached or initialized.
    """
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY"),
        SESSION_COOKIE_NAME="registration_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true",
        MAX_CONTENT_LENGTH=16 * 1024,
        COLLEGE_API_URL=os.getenv("COLLEGE_API_URL", "http://college_svc:5000"),
        SMTP_HOST=os.getenv("SMTP_HOST", "mailpit"),
        SMTP_PORT=int(os.getenv("SMTP_PORT", "1025")),
        MAIL_FROM=os.getenv("MAIL_FROM", "noreply@tutorplatform.test"),
        PUBLIC_BASE_URL=os.getenv("PUBLIC_BASE_URL", "http://localhost:8080"),
        VERIFICATION_MAX_AGE=3600,
    )
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Set SECRET_KEY to a random secret of at least 32 characters.")

    if dao is None:
        dao = MongoUsersDAO()
    dao.connect_to_database()
    dao.setup_database()
    app.extensions["users_dao"] = dao
    app.extensions["registration_service"] = RegistrationService(
        dao, college_client or CollegeClient(app.config["COLLEGE_API_URL"]),
    )
    app.extensions["email_verification"] = EmailVerification(
        dao, mailer or SMTPMailer(app.config["SMTP_HOST"], app.config["SMTP_PORT"], app.config["MAIL_FROM"]),
        app.config["SECRET_KEY"], app.config["PUBLIC_BASE_URL"], app.config["VERIFICATION_MAX_AGE"],
    )
    CSRFProtect(app)

    @app.get("/auth/csrf")
    def csrf_token():
        """Return a CSRF token tied to the registration session.

        Returns:
            Response: JSON response containing the session-bound CSRF token.
        """
        return jsonify(csrf_token=generate_csrf())

    @app.post("/auth/signup")
    def signup():
        """Create a user from request JSON and return public details with status 201.

        Returns:
            tuple[Response, int]: Created record with status 201, or a validation or
                duplicate-record error.
        """
        try:
            user = app.extensions["registration_service"].register_user(
                request.get_json(silent=True),
            )
            app.extensions["email_verification"].send(user)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except DuplicateKeyError:
            return jsonify(error="Username or email is already registered."), 409
        return jsonify(user=user.to_public_dict(), message="Check your email to verify your account."), 201

    @app.post("/auth/verify-email")
    def verify_email():
        """Activate a pending account using its emailed token.

        Returns:
            Response | tuple[Response, int]: Verified account or token error.
        """
        data = request.get_json(silent=True)
        try:
            user = app.extensions["email_verification"].verify(data.get("token") if isinstance(data, dict) else None)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        return jsonify(user=user.to_public_dict(), message="Email verified. You can now sign in.")

    @app.post("/auth/resend-verification")
    def resend_verification():
        """Request verification mail without exposing account existence.

        Returns:
            Response | tuple[Response, int]: Generic confirmation or input error.
        """
        data = request.get_json(silent=True)
        try:
            email = normalize_email(data.get("email") if isinstance(data, dict) else None)
        except ValueError:
            return jsonify(error="Enter a valid email address."), 400
        app.extensions["email_verification"].resend(email)
        return jsonify(message="If this account needs verification, an email will be sent. Please wait one minute between requests.")

    @app.errorhandler(MailDeliveryError)
    def mail_unavailable(error):
        """Report an SMTP failure while retaining the pending account.

        Args:
            error (MailDeliveryError): Failed verification email delivery.

        Returns:
            tuple[Response, int]: Retryable delivery error with status 503.
        """
        return jsonify(error="Email delivery failed. Your account is pending. Use Resend verification when email is available."), 503

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        """Return a generic JSON 400 response for a rejected CSRF token.

        Args:
            error (CSRFError): CSRF validation error handled by Flask.

        Returns:
            tuple[Response, int]: JSON error response with status 400.
        """
        return jsonify(error="Missing, invalid, or expired CSRF token."), 400

    @app.errorhandler(CollegeServiceUnavailable)
    def college_unavailable(error):
        """Return an error when a selected college cannot be checked.

        Args:
            error (CollegeServiceUnavailable): Failed college lookup.

        Returns:
            tuple[Response, int]: Retryable JSON error with status 503.
        """
        return jsonify(error="College service temporarily unavailable. Please try again."), 503

    @app.errorhandler(PyMongoError)
    def database_error(error):
        """Log the database error type and return a generic JSON 503 response.

        Args:
            error (PyMongoError): Database error handled by Flask.

        Returns:
            tuple[Response, int]: Generic JSON error response with status 503.
        """
        app.logger.error("Registration database operation failed (%s).", type(error).__name__)
        return jsonify(error="Registration service temporarily unavailable."), 503

    @app.after_request
    def security_headers(response):
        """Prevent response caching and MIME-type sniffing.

        Args:
            response (Response): Outgoing Flask response to update.

        Returns:
            Response: Response with caching and content-sniffing protections
                applied.
        """
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return app
