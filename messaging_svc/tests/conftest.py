import io
import sys
import types
from pathlib import Path

import pytest
from gridfs.errors import NoFile

MESSAGING_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MESSAGING_DIR))

from models.Chat import Chat  # noqa: E402


class FakeMessagesDAO:
    """In-memory stand-in for MongoMessagesDAO covering the methods app.py uses."""

    def __init__(self):
        self.clear()

    def clear(self):
        self.chats = {}
        self.messages = {}
        self.files = {}

    def add_chat(self, chat):
        self.chats[str(chat.id)] = chat
        return True

    def update_chat(self, chat):
        if str(chat.id) not in self.chats:
            return False
        self.chats[str(chat.id)] = chat
        return True

    def get_chat(self, chat_id):
        return self.chats.get(str(chat_id))

    def get_chats_for_user(self, user_id):
        return [
            chat for chat in self.chats.values()
            if str(user_id) in {str(member) for member in chat.members}
        ]

    def add_message(self, message):
        self.messages[str(message.id)] = message
        return True

    def get_message(self, message_id):
        return self.messages.get(str(message_id))

    def get_messages(self, chat_id):
        return sorted(
            (m for m in self.messages.values() if str(m.chatId) == str(chat_id)),
            key=lambda m: m.timestamp,
        )

    def get_latest_message(self, chat_id):
        messages = self.get_messages(chat_id)
        return messages[-1] if messages else None

    def get_next_message_id(self):
        return str(max((int(i) for i in self.messages), default=0) + 1)

    def get_next_chat_id(self):
        return str(max((int(i) for i in self.chats), default=0) + 1)

    def delete_message(self, message_id):
        message = self.messages.pop(str(message_id), None)
        if message is not None and message.file_id:
            self.files.pop(message.file_id, None)
        return message is not None

    def save_file(self, file_stream, file_name, mime_type, file_size, chat_id, sender_id):
        file_id = f"file-{len(self.files) + 1}"
        self.files[file_id] = {
            "data": file_stream.read(),
            "file_name": file_name,
            "mime_type": mime_type,
        }
        return file_id

    def open_file(self, file_id):
        if file_id not in self.files:
            raise NoFile("file not found")
        return io.BytesIO(self.files[file_id]["data"])


FAKE_DAO = FakeMessagesDAO()

# app.py imports dataload at module load, which connects to Mongo. Replace it.
_dataload_stub = types.ModuleType("dataload")
_dataload_stub.dao = FAKE_DAO
_dataload_stub.get_last_read_message_id = lambda user_id, chat_id: None
_dataload_stub.mark_chat_read = lambda user_id, chat_id, message_id: None
sys.modules["dataload"] = _dataload_stub


@pytest.fixture
def dao():
    FAKE_DAO.clear()
    return FAKE_DAO


@pytest.fixture
def app(dao):
    import app as app_module

    return app_module.create_app({
        "TESTING": True,
        "SECRET_KEY": "x" * 32,
        "SESSION_COOKIE_SECURE": False,
    })


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login(client):
    def _login(user_id):
        with client.session_transaction() as session:
            session["user"] = user_id
            session["usernames"] = {"1": "alice", "2": "bob"}

    return _login


@pytest.fixture
def chat(dao):
    new_chat = Chat({
        "id": "c1",
        "members": ["1", "2"],
        "lastMessage": "",
        "updatedAt": "2026-01-01T00:00:00+00:00",
        "messageId": None,
    })
    dao.add_chat(new_chat)
    return new_chat


@pytest.fixture
def emitted(app, monkeypatch):
    """Records every socketio.emit call as (event, payload, room)."""
    calls = []
    socketio = app.extensions["socketio"]
    monkeypatch.setattr(
        socketio,
        "emit",
        lambda event, data, to=None: calls.append((event, data, to)),
    )
    return calls
