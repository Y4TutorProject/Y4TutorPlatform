import uuid

from flask_login import UserMixin

from users_svc.Objects.LearningTeachingStyles import LearningTeachingStyles

from .Role import Role
from .UserStatus import UserStatus


class User(UserMixin):
    def __init__(self, username, passhash, email, college_id=None, user_id=None,
                 status=UserStatus.ACTIVE, roles=None, preferences=None, email_verified=True,
                 preferences_completed=False, username_completed=True):
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
            preferences (dict | None): LearningTeachingStyles enum or lowercase string keys
                mapped to integer scores from 0 to 10. Missing scores default to zero.
            email_verified (bool): Whether email ownership is verified. Defaults
                to True for compatibility with existing accounts.
            preferences_completed (bool): Whether preference onboarding is complete.
            username_completed (bool): Whether the user has chosen their username.

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
        self.preferences = {pref: 0 for pref in LearningTeachingStyles}
        if preferences is not None:
            self.set_learning_preferences(preferences)
        self.email_verified = email_verified
        self.preferences_completed = preferences_completed
        self.username_completed = username_completed

    def set_learning_preferences(self, preferences):
        """Update supplied scores, preserving unspecified preferences.

        Accept LearningTeachingStyles members or their lowercase string values as keys.
        Raise ValueError for unknown keys or scores outside the integer range 0–10,
        leaving all scores unchanged if validation fails.
        """
        if not isinstance(preferences, dict):
            raise ValueError("Preferences must be a dictionary of scores.")
        updates = {}
        for key, score in preferences.items():
            try:
                preference = LearningTeachingStyles(key)
            except (ValueError, TypeError):
                raise ValueError(f"Unknown learning preference: {key!r}.") from None
            if type(score) is not int or not 0 <= score <= 10:
                raise ValueError("Preference scores must be integers from 0 to 10.")
            updates[preference] = score
        self.preferences.update(updates)

    @property
    def is_active(self):
        """Return whether the account is active and its email is verified.

        Returns:
            bool: True for an active account with a verified email.
        """
        return self.status == UserStatus.ACTIVE and self.email_verified

    def to_profile_dict(self):
        """Return general details safe to show other users; excludes email and status.

        Returns:
            dict: JSON-compatible profile for display to other users.
        """
        return {
            "id": str(self.id), "username": self.username,
            "college_id": str(self.college) if self.college else None,
            "roles": [role.value for role in self.roles],
            "preferences": {pref.value: score for pref, score in self.preferences.items()},
        }

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
            "preferences": {pref.value: score for pref, score in self.preferences.items()},
            "preferences_completed": self.preferences_completed,
            "username_completed": self.username_completed,
        }
