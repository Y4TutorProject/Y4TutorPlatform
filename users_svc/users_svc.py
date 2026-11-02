import secrets

from werkzeug.security import check_password_hash

from .credentials import hash_password, normalize_email
from .interfaces.users_interface import UsersInterface
from .Objects.UserStatus import UserStatus


class UsersService(UsersInterface):
    def __init__(self, dao):
        self.dao = dao
        # Check a hash even when the email is unknown.
        self._dummy_hash = hash_password(secrets.token_urlsafe(32))

    def log_in(self, email, password):
        email = normalize_email(email)
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
