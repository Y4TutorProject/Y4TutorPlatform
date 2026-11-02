import re
import secrets

from registration_svc.interfaces.registration_interface import RegistrationInterface
from users_svc.credentials import hash_password, normalize_email
from users_svc.Objects.User import User


class RegistrationService(RegistrationInterface):
    def __init__(self, dao):
        self.dao = dao

    def validate_user(self, user_data):
        if not isinstance(user_data, dict):
            raise ValueError("A JSON object is required.")
        # The signup screen only asks for email and password. Retain support for
        # explicit usernames from API clients while generating one when omitted.
        username = user_data.get("username", "user_" + secrets.token_hex(10))
        if not isinstance(username, str):
            raise ValueError("Username is required.")
        username = username.strip().casefold()
        if not re.fullmatch(r"[a-z0-9_]{3,30}", username):
            raise ValueError("Username must contain 3–30 letters, numbers, or underscores.")
        email = normalize_email(user_data.get("email"))
        password = user_data.get("password")
        if not isinstance(password, str) or not 9 <= len(password) <= 128:
            raise ValueError("Password must contain 9–128 characters.")
        return {"username": username, "email": email, "password": password}

    def register_user(self, user_data):
        data = self.validate_user(user_data)
        user = User(data["username"], hash_password(data["password"]), data["email"])
        self.dao.add_user(user)
        return user
