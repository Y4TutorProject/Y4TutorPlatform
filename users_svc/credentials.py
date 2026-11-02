import re

from werkzeug.security import generate_password_hash


def normalize_email(email):
    if not isinstance(email, str):
        raise ValueError("Email is required.")
    email = email.strip().casefold()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("A valid email address is required.")
    return email


def hash_password(password):
    return generate_password_hash(password, method="scrypt")
