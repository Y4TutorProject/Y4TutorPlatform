"""A single atomic MongoDB replacement publishes each complete import."""
from datetime import datetime, timezone
from hashlib import sha256

from bson import BSON

from .interfaces import LMSImportError, LMSImportStore


class MongoLMSImportStore(LMSImportStore):
    def __init__(self, database):
        self.collection = database["lms_imports"]

    @staticmethod
    def _id(college_id, provider, source_url):
        return sha256(f"{college_id}\n{provider}\n{source_url}".encode()).hexdigest()

    def save(self, college_id, provider, source_url, catalog):
        document = {"_id": self._id(college_id, provider, source_url),
                    "college_id": str(college_id), "provider": provider, "base_url": source_url,
                    "imported_at": datetime.now(timezone.utc).isoformat(), **catalog}
        if len(BSON.encode(document)) > 8 * 1024 * 1024:
            raise LMSImportError("Catalog exceeds the import size limit; the previous import is unchanged.")
        self.collection.replace_one({"_id": document["_id"]}, document, upsert=True)
        return self._public(document)

    @staticmethod
    def _public(document):
        return {key: value for key, value in document.items() if key != "_id"}

    def get(self, college_id, provider, source_url):
        document = self.collection.find_one({"_id": self._id(college_id, provider, source_url)})
        return self._public(document) if document else None
