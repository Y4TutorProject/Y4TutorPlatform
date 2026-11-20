import base64
import io
import os
import secrets

import pytest
from bson import ObjectId
from cryptography.exceptions import InvalidTag

# encrypt.py reads MESSAGING_KEY at import time, so set it before importing.
os.environ.setdefault("MESSAGING_KEY", base64.b64encode(secrets.token_bytes(32)).decode())

from messaging_svc.messages_dao.MongoMessagesDAO import MongoMessagesDAO  # noqa: E402


class FakeGridFSBucket:
    """Records the bytes GridFS would store, without connecting to Mongo."""

    def __init__(self):
        self.stored = {}

    def upload_from_stream(self, filename, source, metadata=None):
        file_id = ObjectId()
        self.stored[str(file_id)] = source.read()
        return file_id

    def open_download_stream(self, file_id):
        return io.BytesIO(self.stored[str(file_id)])


@pytest.fixture
def bucket_dao():
    dao = MongoMessagesDAO.__new__(MongoMessagesDAO)
    dao.file_bucket = FakeGridFSBucket()
    return dao


def test_saved_file_is_not_stored_as_plaintext(bucket_dao):
    content = b"%PDF-1.4 private tutoring notes"
    file_id = bucket_dao.save_file(io.BytesIO(content), "notes.pdf", "application/pdf", len(content), "c", "u")

    stored = bucket_dao.file_bucket.stored[file_id]
    assert content not in stored
    assert len(stored) == len(content) + 12 + 16  # nonce + AES-GCM tag


def test_open_file_returns_original_bytes(bucket_dao):
    content = b"%PDF-1.4 private tutoring notes"
    file_id = bucket_dao.save_file(io.BytesIO(content), "notes.pdf", "application/pdf", len(content), "c", "u")

    assert bucket_dao.open_file(file_id).read() == content


def test_tampered_file_is_rejected(bucket_dao):
    content = b"%PDF-1.4 private tutoring notes"
    file_id = bucket_dao.save_file(io.BytesIO(content), "notes.pdf", "application/pdf", len(content), "c", "u")
    blob = bytearray(bucket_dao.file_bucket.stored[file_id])
    blob[-1] ^= 0x01
    bucket_dao.file_bucket.stored[file_id] = bytes(blob)

    with pytest.raises(InvalidTag):
        bucket_dao.open_file(file_id)
