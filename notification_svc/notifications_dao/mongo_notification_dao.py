from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING
from pymongo.collection import Collection

from ..Models.NotificationStore import NotificationStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_object_id(value: str) -> Optional[ObjectId]:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _serialize(doc: dict) -> dict:
    """Turn a Mongo document into a JSON-friendly dict."""
    out = dict(doc)
    out["id"] = str(out.pop("_id"))
    for key in ("created_at", "read_at"):
        if out.get(key):
            out[key] = out[key].isoformat()
    return out


class MongoNotificationDAO(NotificationStore):
    """MVP implementation backed by a MongoDB collection (PyMongo).

    Usage:
        client = MongoClient(MONGO_URI)
        dao = MongoNotificationDAO(client["tutoring"]["notifications"])
        dao.ensure_indexes()   # call once at startup
    """

    def __init__(self, collection: Collection):
        self.col = collection

    def ensure_indexes(self) -> None:
        self.col.create_index([("recipient_id", ASCENDING), ("created_at", DESCENDING)])
        # Unread count
        self.col.create_index([("recipient_id", ASCENDING), ("read_at", ASCENDING), ("created_at", DESCENDING)])

    def create_many(
        self,
        recipient_ids,
        type,
        title,
        body="",
        payload=None,
        actor_id=None,
    ):
        # One document per recipient.
        unique_ids = list(dict.fromkeys(str(r) for r in recipient_ids))
        if not unique_ids:
            return []

        now = _now()
        docs = [
            {
                "recipient_id": rid,
                "actor_id": str(actor_id) if actor_id else None,
                "type": type,
                "title": title,
                "body": body,
                "link": payload.get("link") if payload else None,
                "payload": payload or {},
                "read_at": None,
                "created_at": now,
            }
            for rid in unique_ids
        ]
        self.col.insert_many(docs)
        return [_serialize(d) for d in docs]

    def get(self, notification_id):
        oid = _to_object_id(notification_id)
        if oid is None:
            return None
        doc = self.col.find_one({"_id": oid})
        return _serialize(doc) if doc else None

    def list_for_user(self, user_id, unread_only=False, page=1, per_page=20):
        page = max(page, 1)
        query = {"recipient_id": str(user_id)}
        if unread_only:
            query["read_at"] = None  # matches null or missing

        total = self.col.count_documents(query)
        cursor = (
            self.col.find(query)
            .sort("created_at", DESCENDING)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
        return {
            "items": [_serialize(d) for d in cursor],
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_next": page * per_page < total,
        }

    def unread_count(self, user_id):
        return self.col.count_documents(
            {"recipient_id": str(user_id), "read_at": None}
        )

    def mark_read(self, notification_id, user_id):
        oid = _to_object_id(notification_id)
        if oid is None:
            return False
        # Scoped by recipient_id so a user can only mark their own.
        result = self.col.update_one(
            {"_id": oid, "recipient_id": str(user_id), "read_at": None},
            {"$set": {"read_at": _now()}},
        )
        return result.modified_count > 0

    def mark_all_read(self, user_id):
        result = self.col.update_many(
            {"recipient_id": str(user_id), "read_at": None},
            {"$set": {"read_at": _now()}},
        )
        return result.modified_count