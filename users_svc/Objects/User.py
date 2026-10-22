import uuid

from flask_login import UserMixin

from .Role import Role
from .UserStatus import UserStatus


class User(UserMixin):
    def __init__(self, username, passhash, email, college_id=None, user_id=None,
                 status=UserStatus.ACTIVE, roles=None):
        self.id = uuid.UUID(str(user_id)) if user_id else uuid.uuid4()
        self.username = username
        self.passhash = passhash
        self.email = email
        self.college = uuid.UUID(str(college_id)) if college_id else None
        self.status = UserStatus(status)
        self.roles = [Role(role) for role in roles] if roles is not None else [Role.STUDENT]

    @property
    def is_active(self):
        return self.status == UserStatus.ACTIVE

    def to_public_dict(self):
        return {
            "id": str(self.id), "username": self.username, "email": self.email,
            "college_id": str(self.college) if self.college else None,
            "status": self.status.value, "roles": [role.value for role in self.roles],
        }
