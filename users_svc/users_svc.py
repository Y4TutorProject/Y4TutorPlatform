import secrets

from werkzeug.security import check_password_hash

from .credentials import hash_password, normalize_email
from .interfaces.users_interface import UsersInterface
from .Objects.UserStatus import UserStatus


class UsersService(UsersInterface):
    def __init__(self, dao):
        """Store the DAO and prepare a dummy password hash for unknown-account checks.

        Args:
            dao (UsersDAO): Data access object used by the service.
        """
        self.dao = dao
        # Check a hash even when the email is unknown.
        self._dummy_hash = hash_password(secrets.token_urlsafe(32))

    def log_in(self, email, password):
        """Return the active user for valid credentials, or None on failure.

        Args:
            email (str): Email address used to identify the account.
            password (str): Plaintext password to validate or hash.

        Returns:
            User | None: Active user for valid credentials, or None when
                authentication fails.

        Raises:
            ValueError: The email cannot be normalized.
        """
        email = normalize_email(email)
        if not isinstance(password, str) or not 1 <= len(password) <= 128:
            return None
        user = self.dao.get_user_by_email(email)
        valid = check_password_hash(user.passhash if user else self._dummy_hash, password)
        return user if valid and user and user.is_active else None

    def change_status(self, user_uuid, new_status):
        """Save and return the user with the new status, or None if the ID is unknown.

        Args:
            user_uuid (str | uuid.UUID): Identifier of the user to update.
            new_status (UserStatus | str): Status to assign to the user.

        Returns:
            User | None: Updated user, or None if the identifier does not match a
                user.

        Raises:
            ValueError: The requested status is not a UserStatus value.
        """
        user = self.dao.get_user(user_uuid)
        if user:
            user.status = UserStatus(new_status)
            self.dao.update_user(user)
        return user
