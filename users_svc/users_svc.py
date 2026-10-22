import re
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

from .interfaces.users_interface import UsersInterface
from .Objects.User import User
from .Objects.UserStatus import UserStatus


class UsersService(UsersInterface):
    def __init__(self, dao):
        self.dao = dao
        # Check a hash even when the email is unknown.
        self._dummy_hash = self.hash_password(secrets.token_urlsafe(32))

    @staticmethod
    def normalize_email(email):
        if not isinstance(email, str):
            raise ValueError("Email is required.")
        email = email.strip().casefold()
        if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("A valid email address is required.")
        return email

    def sign_up(self, username, password, email, college_id=None):
        if not isinstance(username, str):
            raise ValueError("Username is required.")
        username = username.strip().casefold()
        if not re.fullmatch(r"[a-z0-9_]{3,30}", username):
            raise ValueError("Username must contain 3–30 letters, numbers, or underscores.")
        email = self.normalize_email(email)
        if not isinstance(password, str) or not 9 <= len(password) <= 128:
            raise ValueError("Password must contain 9–128 characters.")
        user = User(username, self.hash_password(password), email, college_id)
        self.dao.add_user(user)
        return user

    def log_in(self, email, password):
        email = self.normalize_email(email)
        if not isinstance(password, str) or not 1 <= len(password) <= 128:
            return None
        user = self.dao.get_user_by_email(email)
        valid = check_password_hash(user.passhash if user else self._dummy_hash, password)
        return user if valid and user and user.is_active else None

    def change_status(self, user_uuid, new_status):
        user = self.dao.get_user(user_uuid)
        if user:
            user.status = UserStatus(new_status)
            self.dao.update_user(user)
        return user

    def hash_password(self, password):
        return generate_password_hash(password, method="scrypt")
