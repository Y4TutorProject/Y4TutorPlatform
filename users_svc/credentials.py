import re

from werkzeug.security import generate_password_hash


def normalize_email(email):
    """Validate and normalize an email address.

    Args:
        email (str): Email address used to identify the account.

    Returns:
        str: Validated email address with surrounding whitespace removed and
            case normalized.

    Raises:
        ValueError: The email is missing, exceeds 254 characters, or has an
            invalid format.
    """
    if not isinstance(email, str):
        raise ValueError("Email is required.")
    email = email.strip().casefold()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("A valid email address is required.")
    return email


def hash_password(password):
    """Return a salted scrypt hash of the supplied password.

    Args:
        password (str): Plaintext password to validate or hash.

    Returns:
        str: Salted scrypt password hash.
    """
    return generate_password_hash(password, method="scrypt")
