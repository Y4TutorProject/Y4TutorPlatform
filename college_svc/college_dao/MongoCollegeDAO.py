import os
import uuid

from pymongo import ASCENDING, MongoClient

from ..interfaces.college_interface import CollegeDAO
from ..Objects.College import College

class MongoCollegeDAO(CollegeDAO):
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
        self.db = self.client[db_name or os.getenv("MONGO_DB_NAME", "college_db")]
        self.collection = self.db[collection_name or os.getenv("MONGO_COLLECTION_NAME", "colleges")]

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
    def _to_document(college):
        """Serialize a college into a MongoDB document.

        Args:
            college (College): College to store, update, or serialize.

        Returns:
            dict: College details with string UUID and status values.
        """
        return {
            "id": str(college.college_id),
            "name": college.college_name,
            "domain": college.college_domain,
            "status": college.status.value,
            "admin_id": college.admin_id,
        }

    @staticmethod
    def _from_document(data):
        """Rebuild a College from a MongoDB document, or return None for missing data.

        Args:
            data (dict | None): MongoDB document, or None when no record was found.

        Returns:
            College | None: Reconstructed record, or None if no record matches.
        """
        if data is None:
            return None
        college = College(
            college_id=data["id"],
            college_name=data["name"],
            domain=data.get("domain"),
            status=data.get("status", "active"),
            admin_id=data.get("admin_id"),
        )
        return college

    def add_college(self, college):
        """Insert a new college into the data store.

        Args:
            college (College): College to store, update, or serialize.

        Returns:
            bool: True when the operation succeeds.

        Raises:
            DuplicateKeyError: The operation conflicts with a unique index.
            PyMongoError: The database operation fails.
        """
        self.collection.insert_one(self._to_document(college))
        return True

    def update_college(self, college):
        """Update a college by UUID and return whether a document matched.

        Args:
            college (College): College to store, update, or serialize.

        Returns:
            bool: True if a stored record matched the identifier; otherwise False.

        Raises:
            DuplicateKeyError: The operation conflicts with a unique index.
            PyMongoError: The database operation fails.
        """
        result = self.collection.update_one(
            {"id": str(college.college_id)}, {"$set": self._to_document(college)},
        )
        return result.matched_count > 0

    def get_college(self, college_id):
        """Return a college by UUID, or None for an invalid or unknown ID.

        Args:
            college_id (str | uuid.UUID): College identifier to look up.

        Returns:
            College | None: Reconstructed record, or None if no record matches.

        Raises:
            PyMongoError: The database operation fails.
        """
        try:
            college_id = str(uuid.UUID(str(college_id)))
        except (ValueError, TypeError, AttributeError):
            return None
        return self._from_document(self.collection.find_one({"id": college_id}))

    def get_college_by_name(self, name):
        """Return a college by its exact stored name, or None if not found.

        Args:
            name (str): Exact stored college name to look up.

        Returns:
            College | None: Reconstructed record, or None if no record matches.

        Raises:
            PyMongoError: The database operation fails.
        """
        return self._from_document(self.collection.find_one({"name": name}))

    def list_active_colleges(self):
        """Read active colleges from MongoDB in name order.

        Returns:
            list[College]: Colleges with active status.

        Raises:
            PyMongoError: The database query fails.
        """
        documents = self.collection.find({"status": "active"}).sort("name", ASCENDING)
        return [self._from_document(document) for document in documents]

    def setup_database(self):
        """Create unique indexes on college ID and name.

        Raises:
            DuplicateKeyError: The operation conflicts with a unique index.
            PyMongoError: The database operation fails.
        """
        for field in ("id", "name"):
            self.collection.create_index([(field, ASCENDING)], unique=True)
        self.collection.create_index("admin_id", unique=True,
            partialFilterExpression={"admin_id": {"$type": "string"}})

    def get_college_by_admin(self, admin_id):
        """Find a college by its owning administrator.

        Args:
            admin_id (str): Administrator UUID.

        Returns:
            College | None: Owned college, or None before college registration.
        """
        return self._from_document(self.collection.find_one({"admin_id": admin_id}))
