"""Durable encrypted connections and distributed synchronization leases."""
from abc import ABC, abstractmethod
from datetime import timedelta
from uuid import uuid4

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


class ConnectionStore(ABC):
    @abstractmethod
    def get(self, college_id):
        """Read a saved connection, including its encrypted credential."""

    @abstractmethod
    def save(self, college_id, fields, now):
        """Save configuration unless synchronization holds the lease."""

    @abstractmethod
    def claim(self, college_id, now, force=False):
        """Atomically lease an enabled connection, if due or forced."""

    @abstractmethod
    def finish(self, connection, fields):
        """Record the result and release only the caller's lease."""

    @abstractmethod
    def due(self, now):
        """List enabled college IDs with due synchronizations."""


class SyncBusy(Exception):
    """A synchronization is already running for this college."""


class MongoConnectionStore(ConnectionStore):
    def __init__(self, database):
        self.collection = database["connections"]
        self.collection.create_index([("enabled", 1), ("next_sync_at", 1)])

    def get(self, college_id):
        return self.collection.find_one({"_id": college_id})

    def save(self, college_id, fields, now):
        try:
            self.collection.update_one(
                {"_id": college_id, "$or": [{"locked_until": {"$lte": now}}, {"locked_until": {"$exists": False}}]},
                {"$set": fields}, upsert=True,
            )
        except DuplicateKeyError:
            raise SyncBusy("Synchronization is running. Try again shortly.") from None
        return self.get(college_id)

    def claim(self, college_id, now, force=False):
        query = {"_id": college_id, "enabled": True,
                 "$or": [{"locked_until": {"$lte": now}}, {"locked_until": {"$exists": False}}]}
        if not force:
            query["next_sync_at"] = {"$lte": now}
        return self.collection.find_one_and_update(
            query, {"$set": {"lease_id": str(uuid4()), "locked_until": now + timedelta(minutes=20)}},
            return_document=ReturnDocument.AFTER,
        )

    def finish(self, connection, fields):
        self.collection.update_one({"_id": connection["_id"], "lease_id": connection["lease_id"]},
                                   {"$set": fields, "$unset": {"lease_id": "", "locked_until": ""}})

    def due(self, now):
        return [row["_id"] for row in self.collection.find({"enabled": True, "next_sync_at": {"$lte": now}}, {"_id": 1})]
