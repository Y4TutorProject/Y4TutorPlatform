import os
import re
import uuid

from pymongo import ASCENDING, MongoClient

from ..interfaces.users_interface import UsersDAO
from ..Objects.User import User


class MongoUsersDAO(UsersDAO):
    def __init__(self, uri=None, db_name=None, collection_name=None):
        """Configure the MongoDB client and collection from arguments or environment
        settings.

        Args:
            uri (str | None): MongoDB connection URI. Defaults to the MONGO_URI
                environment variable.
            db_name (str | None): Database name. Defaults to MONGO_DB_NAME or the
                service default.
            collection_name (str | None): Collection name. Defaults to
                MONGO_COLLECTION_NAME or the service default.

        Raises:
            KeyError: No URI is supplied and MONGO_URI is not set.
        """
        self.client = MongoClient(
            uri or os.environ["MONGO_URI"], serverSelectionTimeoutMS=5000,
        )
        self.db = self.client[db_name or os.getenv("MONGO_DB_NAME", "users_db")]
        self.collection = self.db[collection_name or os.getenv("MONGO_COLLECTION_NAME", "users")]

    def connect_to_database(self):
        """Check connectivity to the database.

        Returns:
            bool: True when the operation succeeds.

        Raises:
            PyMongoError: The database operation fails.
        """
        self.client.admin.command("ping")
        return True

    @staticmethod
    def _to_document(user):
        """Serialize a user for MongoDB, including the password hash and college field.

        Args:
            user (User): User to store or serialize.

        Returns:
            dict: MongoDB document including the password hash.
        """
        data = user.to_public_dict()
        data["college"] = data.pop("college_id")
        data["passhash"] = user.passhash
        return data

    @staticmethod
    def _from_document(data):
        """Rebuild a User from a MongoDB document, or return None for missing data.

        Args:
            data (dict | None): MongoDB document, or None when no record was found.

        Returns:
            User | None: Reconstructed record, or None if no record matches.
        """
        if data is None:
            return None
        preferences = data.get("preferences")
        if isinstance(preferences, dict):
            # Normalize stored scores from before LearningTeachingStyles.
            # Keep an explicit new-style score when both names are present.
            preferences = preferences.copy()
            if "verbal" in preferences:
                preferences.setdefault("reading_writing", preferences.pop("verbal"))
            preferences.pop("logical", None)
        return User(
            username=data["username"], passhash=data["passhash"], email=data["email"],
            college_id=data.get("college"), user_id=data["id"],
            status=data["status"], roles=data["roles"],
            email_verified=data.get("email_verified", True),
            preferences=preferences,
            preferences_completed=data.get("preferences_completed", True),
            username_completed=data.get("username_completed",
                                        re.fullmatch(r"user_[0-9a-f]{20}", data["username"]) is None),
        )

    def add_user(self, user):
        """Insert a new user into the data store.

        Args:
            user (User): User to store or serialize.

        Returns:
            bool: True when the operation succeeds.

        Raises:
            DuplicateKeyError: The operation conflicts with a unique index.
            PyMongoError: The database operation fails.
        """
        self.collection.insert_one(self._to_document(user))
        return True

    def update_user(self, user):
        """Update a user by ID and return whether a document matched.

        Args:
            user (User): User to store or serialize.

        Returns:
            bool: True if a stored record matched the identifier; otherwise False.

        Raises:
            DuplicateKeyError: The operation conflicts with a unique index.
            PyMongoError: The database operation fails.
        """
        result = self.collection.update_one(
            {"id": str(user.id)}, {"$set": self._to_document(user)},
        )
        return result.matched_count > 0

    def get_user(self, user_id):
        """Return a user by UUID, or None for an invalid or unknown ID.

        Args:
            user_id (str | uuid.UUID): User identifier to look up.

        Returns:
            User | None: Matching user, or None for an invalid or unknown
                identifier.

        Raises:
            PyMongoError: The database operation fails.
        """
        try:
            user_id = str(uuid.UUID(str(user_id)))
        except (ValueError, TypeError, AttributeError):
            return None
        return self._from_document(self.collection.find_one({"id": user_id}))

    def get_user_by_email(self, email):
        """Return the user with the supplied normalized email, or None if not found.

        Args:
            email (str): Email address used to identify the account.

        Returns:
            User | None: Matching user, or None if the email is not registered.

        Raises:
            PyMongoError: The database operation fails.
        """
        return self._from_document(self.collection.find_one({"email": email}))

    def list_college_users(self, college_id):
        return [{key: record[key] for key in ('id', 'username', 'email', 'roles')}
                for record in self.collection.find({
                    'college': college_id, 'status': 'active', 'email_verified': True,
                }).sort('username', 1)]

    def setup_database(self):
        """Create unique indexes on user ID, username, and email, then return True.

        Returns:
            bool: True after all required unique indexes are created.

        Raises:
            DuplicateKeyError: The operation conflicts with a unique index.
            PyMongoError: The database operation fails.
        """
        for field in ("id", "username", "email"):
            self.collection.create_index([(field, ASCENDING)], unique=True)
        return True

    def set_verification_token(self, user_id, token_hash):
        """Store a hashed verification nonce for a pending account.

        Args:
            user_id (str): Pending user UUID.
            token_hash (str): SHA-256 digest of the verification nonce.

        Returns:
            bool: Whether a pending account was updated.
        """
        result = self.collection.update_one(
            {"id": str(user_id), "status": "pending_verification", "email_verified": False},
            {"$set": {"verification_hash": token_hash}},
        )
        return result.matched_count == 1

    def verify_email(self, user_id, email, token_hash):
        """Activate a pending account by consuming its verification nonce once.

        Args:
            user_id (str): Pending account UUID.
            email (str): Email address bound to the verification token.
            token_hash (str): SHA-256 digest of the supplied nonce.

        Returns:
            User | None: Activated user, or None if the token cannot be consumed.
        """
        result = self.collection.update_one(
            {"id": str(user_id), "email": email, "status": "pending_verification",
             "email_verified": False, "verification_hash": token_hash},
            {"$set": {"status": "active", "email_verified": True},
             "$unset": {"verification_hash": ""}},
        )
        return self.get_user(user_id) if result.modified_count == 1 else None

    def assign_college(self, user_id, college_id):
        """Assign a college to an administrator without replacing membership.

        Args:
            user_id (str): College administrator UUID.
            college_id (str): College UUID owned by the administrator.

        Returns:
            bool: Whether membership was assigned or already matched.
        """
        result = self.collection.update_one(
            {"id": str(user_id), "roles": "college_admin", "college": {"$in": [None, college_id]}},
            {"$set": {"college": college_id}},
        )
        return result.matched_count == 1

    def set_username(self, user_id, previous_username, username):
        """Claim a username once; the unique index arbitrates concurrent claims."""
        result = self.collection.update_one(
            {"id": str(user_id), "username": previous_username, "username_completed": {"$ne": True}},
            {"$set": {"username": username, "username_completed": True}},
        )
        return result.matched_count == 1
    

    def list_tutors(self, college_id):
        """Return active, verified tutors belonging to a college.

        Args:
            college_id (str | None): College UUID to filter by.

        Returns:
            list[User]: Matching tutors sorted by username; empty if none.

        Raises:
            PyMongoError: The database operation fails.
        """
        if not college_id:
            return []
        cursor = self.collection.find({
            "roles": "tutor",
            "college": str(college_id),
            "status": "active",
            "email_verified": True,
        }).sort("username", ASCENDING)
        return [self._from_document(doc) for doc in cursor]
