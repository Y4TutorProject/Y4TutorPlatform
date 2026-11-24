import os
from pymongo import ASCENDING, MongoClient

from sessions_svc.models.Session import Session


class MongoSessionsDAO:
    """MongoDB access for tutoring sessions."""

    def __init__(self, uri=None, db_name=None, collection_name=None):
        self.client = MongoClient(
            uri or os.environ["MONGO_URI"],
            serverSelectionTimeoutMS=5000,
        )
        self.db = self.client[
            db_name or os.getenv("MONGO_DB_NAME", "sessions_db")
        ]
        self.sessions = self.db[
            collection_name or os.getenv("MONGO_COLLECTION_NAME", "sessions")
        ]

    def connect_to_database(self):
        self.client.admin.command("ping")
        return True

    def setup_database(self):
        self.sessions.create_index([("id", ASCENDING)], unique=True)

    def add_session(self, session) -> None:
        """Add a new session to the database."""
        self.sessions.insert_one(session.to_dict())

    def get_session(self, session_id):
        """Retrieve a session by its ID, or None if it doesn't exist."""
        data = self.sessions.find_one({"id": session_id})
        return Session(data) if data else None

    def update_session(self, session) -> None:
        """Update an existing session in the database."""
        self.sessions.update_one(
            {"id": session.id}, {"$set": session.to_dict()}
        )
