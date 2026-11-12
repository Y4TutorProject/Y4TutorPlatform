import secrets

from werkzeug.security import check_password_hash

from users_svc.Objects.Role import Role

from .credentials import hash_password, normalize_email
from .interfaces.users_interface import UsersInterface
from .Objects.UserStatus import UserStatus
from .Objects.LearningTeachingStyles import LearningTeachingStyles

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

    def set_learning_preferences(self, user_uuid, preferences):
        """Validate and persist supplied learning preference scores.

        Supplying all four preferences also completes preference onboarding.

        Args:
            user_uuid (str | uuid.UUID): Identifier of the user to update.
            preferences (dict): LearningTeachingStyles members or lowercase string keys
                mapped to integer scores from 0 to 10. Other scores are preserved.

        Returns:
            User | None: Updated user, or None if no stored user matches.

        Raises:
            ValueError: A preference name or score is invalid.
        """
        user = self.dao.get_user(user_uuid)
        if user is None:
            return None
        user.set_learning_preferences(preferences)
        if {LearningTeachingStyles(key) for key in preferences} == set(LearningTeachingStyles):
            user.preferences_completed = True
        return user if self.dao.update_user(user) else None

    def set_teaching_preferences(self, user_uuid, preferences):
        """Validate and persist supplied teaching preference scores.

        Supplying all four preferences also completes preference onboarding.

        Args:
            user_uuid (str | uuid.UUID): Identifier of the user to update.
            preferences (dict): LearningTeachingStyles members or lowercase string keys
                mapped to integer scores from 0 to 10. Other scores are preserved.

        Returns:
            User | None: Updated user, or None if no stored user matches.

        Raises:
            ValueError: A preference name or score is invalid.
        """
        user = self.dao.get_user(user_uuid)
        if user is None:
            return None
        user.set_teaching_preferences(preferences)
        if {LearningTeachingStyles(key) for key in preferences} == set(LearningTeachingStyles):
            user.teaching_preferences_completed = True
        return user if self.dao.update_user(user) else None
    
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

    def update_role(self, user_uuid, role):
        """Update the role of the specified user."""
        user = self.dao.get_user(user_uuid)
        if user is None:
            return None
        if role not in [r.value for r in Role]:
            raise ValueError("Invalid role.")
        if role not in user.roles:
            user.roles.append(role)
        return user if self.dao.update_user(user) else None