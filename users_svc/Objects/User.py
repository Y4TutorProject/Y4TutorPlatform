import uuid

from flask_login import UserMixin

from .Role import Role
from .UserStatus import UserStatus


class User(UserMixin):
    def __init__(self, username, passhash, email, college_id=None, user_id=None,
                 status=UserStatus.ACTIVE, roles=None, email_verified=True):
        """Build a user with UUID identifiers and enum values, defaulting to an active
        student.

        Args:
            username (str): Username used to identify the account.
            passhash (str): Previously generated password hash.
            email (str): Email address used to identify the account.
            college_id (str | uuid.UUID | None): Associated college identifier.
                Defaults to None.
            user_id (str | uuid.UUID | None): User identifier. Defaults to a newly
                generated UUID.
            status (UserStatus | str): Initial account status. Defaults to active.
            roles (list[Role | str] | None): User roles. Defaults to the student
                role.
            email_verified (bool): Whether email ownership is verified. Defaults
                to True for compatibility with existing accounts.

        Raises:
            ValueError: An identifier or enum value is invalid.
        """
        self.id = uuid.UUID(str(user_id)) if user_id else uuid.uuid4()
        self.username = username
        self.passhash = passhash
        self.email = email
        self.college = uuid.UUID(str(college_id)) if college_id else None
        self.status = UserStatus(status)
        self.roles = [Role(role) for role in roles] if roles is not None else [Role.STUDENT]
        self.email_verified = email_verified

    @property
    def is_active(self):
        """Return whether the account is active and its email is verified.

        Returns:
            bool: True for an active account with a verified email.
        """
        return self.status == UserStatus.ACTIVE and self.email_verified

    def to_public_dict(self):
        """Return JSON-compatible user details without the password hash.

        Returns:
            dict: JSON-compatible user details excluding the password hash.
        """
        return {
            "id": str(self.id), "username": self.username, "email": self.email,
            "college_id": str(self.college) if self.college else None,
            "status": self.status.value, "roles": [role.value for role in self.roles],
            "email_verified": self.email_verified,
        }
