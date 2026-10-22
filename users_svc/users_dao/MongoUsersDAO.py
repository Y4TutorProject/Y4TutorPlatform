import os
import uuid

from pymongo import ASCENDING, MongoClient

from ..interfaces.users_interface import UsersDAO
from ..Objects.User import User


class MongoUsersDAO(UsersDAO):
    def __init__(self, uri=None, db_name=None, collection_name=None):
        self.client = MongoClient(
            uri or os.environ["MONGO_URI"], serverSelectionTimeoutMS=5000,
        )
        self.db = self.client[db_name or os.getenv("MONGO_DB_NAME", "users_db")]
        self.collection = self.db[collection_name or os.getenv("MONGO_COLLECTION_NAME", "users")]

    def connect_to_database(self):
        self.client.admin.command("ping")
        return True

    @staticmethod
    def _to_document(user):
        data = user.to_public_dict()
        data["college"] = data.pop("college_id")
        data["passhash"] = user.passhash
        return data

    @staticmethod
    def _from_document(data):
        if data is None:
            return None
        return User(
            username=data["username"], passhash=data["passhash"], email=data["email"],
            college_id=data.get("college"), user_id=data["id"],
            status=data["status"], roles=data["roles"],
        )

    def add_user(self, user):
        self.collection.insert_one(self._to_document(user))
        return True

    def update_user(self, user):
        result = self.collection.update_one(
            {"id": str(user.id)}, {"$set": self._to_document(user)},
        )
        return result.matched_count > 0

    def get_user(self, user_id):
        try:
            user_id = str(uuid.UUID(str(user_id)))
        except (ValueError, TypeError, AttributeError):
            return None
        return self._from_document(self.collection.find_one({"id": user_id}))

    def get_user_by_email(self, email):
        return self._from_document(self.collection.find_one({"email": email}))

    def setup_database(self):
        for field in ("id", "username", "email"):
            self.collection.create_index([(field, ASCENDING)], unique=True)
        return True
