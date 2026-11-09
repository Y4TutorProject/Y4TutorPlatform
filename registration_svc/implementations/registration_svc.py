import secrets
import uuid

from registration_svc.interfaces.registration_interface import RegistrationInterface
from users_svc.credentials import hash_password, normalize_email, normalize_username
from users_svc.Objects.User import User
from users_svc.Objects.UserStatus import UserStatus


class RegistrationService(RegistrationInterface):
    def __init__(self, dao, college_client):
        """Store the DAO used to persist newly registered users.

        Args:
            dao (UsersDAO): Data access object used by the service.
            college_client (CollegeClient): Client for validating selected colleges.
        """
        self.dao = dao
        self.college_client = college_client

    def validate_user(self, user_data):
        """Validate and normalize signup fields.

        Generate a username when omitted. Students must select a college and use
        its student email domain. Administrators register a college later; raw
        role, status, and verification fields are ignored.

        Args:
            user_data (dict): Signup fields containing email, password, and
                an account_type and an optional username. Students require college_id.

        Returns:
            dict: Validated credentials, signup type, and student college UUID.

        Raises:
            ValueError: The body or signup fields are invalid.
            CollegeServiceUnavailable: A selected college cannot be verified.
        """
        if not isinstance(user_data, dict):
            raise ValueError("A JSON object is required.")
        # API clients may defer their username until the first sign-in.
        username_completed = "username" in user_data
        username = normalize_username(user_data.get("username", "user_" + secrets.token_hex(10)))
        email = normalize_email(user_data.get("email"))
        password = user_data.get("password")
        if not isinstance(password, str) or not 9 <= len(password) <= 128:
            raise ValueError("Password must contain 9–128 characters.")
        account_type = user_data.get("account_type", "student")
        if account_type not in ("student", "college_admin"):
            raise ValueError("Choose student signup or college administrator registration.")
        college_id = user_data.get("college_id")
        if account_type == "student":
            if college_id is None or college_id == "":
                raise ValueError("Select your college before signing up.")
            if not isinstance(college_id, str):
                raise ValueError("Select an available college.")
            try:
                college_id = str(uuid.UUID(college_id))
            except ValueError:
                raise ValueError("Select an available college.") from None
            college = self.college_client.get_college(college_id)
            if college is None:
                raise ValueError("Select an available college.")
            if not college.get("domain") or email.rsplit("@", 1)[1] != college["domain"].lower():
                raise ValueError("Use a student email address matching your college's email domain.")
        else:
            if college_id:
                raise ValueError("Administrators register their college after creating an account.")
            college_id = None
        return {"username": username, "email": email, "password": password,
                "college_id": college_id, "account_type": account_type,
                "username_completed": username_completed}

    def register_user(self, user_data):
        """Create a pending student or college-administrator account.

        Args:
            user_data (dict): Signup fields containing email, password, and
                an account_type and an optional username. Students require college_id.

        Returns:
            User: Account awaiting email verification, with a hashed password.

        Raises:
            ValueError: The body or signup fields are invalid.
            DuplicateKeyError: The username, email, or user ID already exists.
            CollegeServiceUnavailable: A selected college cannot be verified.
        """
        data = self.validate_user(user_data)
        user = User(data["username"], hash_password(data["password"]), data["email"],
                    college_id=data["college_id"], roles=[data["account_type"]],
                    status=UserStatus.PENDING_VERIFICATION, email_verified=False,
                    username_completed=data["username_completed"])
        self.dao.add_user(user)
        return user
