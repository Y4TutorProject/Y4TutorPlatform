import os
from pymongo import ASCENDING, DESCENDING, MongoClient
from models.Chat import Chat
from models.Message import Message
from models.ChatReadState import ChatReadState


class MongoMessagesDAO:
    """MongoDB access for chats, messages, and per-user chat read state."""

    def __init__(
        self,
        uri=None,
        db_name=None,
        chat_collection_name=None,
        message_collection_name=None,
        read_state_collection_name=None,
    ):
        self.client = MongoClient(
            uri or os.environ["MONGO_URI"],
            serverSelectionTimeoutMS=5000,
        )
        self.db = self.client[
            db_name or os.getenv("MONGO_DB_NAME", "messaging_db")
        ]
        self.chats = self.db[
            chat_collection_name
            or os.getenv("MONGO_CHAT_COLLECTION_NAME", "chats")
        ]
        self.messages = self.db[
            message_collection_name
            or os.getenv(
                "MONGO_MESSAGE_COLLECTION_NAME",
                os.getenv("MONGO_COLLECTION_NAME", "messages"),
            )
        ]
        self.chat_read_states = self.db[
            read_state_collection_name
            or os.getenv("MONGO_READ_STATE_COLLECTION_NAME", "chatReadStates")
        ]

    def connect_to_database(self):
        self.client.admin.command("ping")
        return True

    def setup_database(self):
        self.chats.create_index([("id", ASCENDING)], unique=True)
        self.messages.create_index([("id", ASCENDING)], unique=True)
        self.messages.create_index(
            [("chatId", ASCENDING), ("timestamp", ASCENDING)]
        )
        self.chat_read_states.create_index([("id", ASCENDING)], unique=True)
        self.chat_read_states.create_index(
            [("senderid", ASCENDING), ("chatid", ASCENDING)],
            unique=True,
        )
        return True

    @staticmethod
    def _chat_to_document(chat):
        return chat.to_dict()

    @staticmethod
    def _message_to_document(message):
        return message.to_dict()

    @staticmethod
    def _read_state_to_document(
        state_id, sender_id, chat_id, last_read_message_id
    ):
        return {
            "id": state_id,
            "senderid": sender_id,
            "chatid": chat_id,
            "lastreadmessageId": last_read_message_id,
        }

    @staticmethod
    def _chat_from_document(data):
        return Chat(data) if data is not None else None

    @staticmethod
    def _message_from_document(data):
        return Message(data) if data is not None else None

    @staticmethod
    def _read_state_from_document(data):
        return ChatReadState(data) if data is not None else None

    def add_chat(self, chat):
        self.chats.insert_one(self._chat_to_document(chat))
        return True

    def update_chat(self, chat):
        result = self.chats.update_one(
            {"id": chat.id},
            {"$set": self._chat_to_document(chat)},
        )
        return result.matched_count > 0

    def get_chat(self, chat_id):
        return self._chat_from_document(self.chats.find_one({"id": chat_id}))

    def get_all_chats(self):
        return [
            self._chat_from_document(document)
            for document in self.chats.find().sort("updatedAt", DESCENDING)
        ]

    def get_chats_for_user(self, user_id):
        return [
            self._chat_from_document(document)
            for document in self.chats.find({"members": user_id}).sort(
                "updatedAt", DESCENDING
            )
        ]

    def add_message(self, message):
        self.messages.insert_one(self._message_to_document(message))
        return True

    def get_message(self, message_id):
        return self._message_from_document(
            self.messages.find_one({"id": message_id})
        )

    def get_messages(self, chat_id):
        return [
            self._message_from_document(document)
            for document in self.messages.find({"chatId": chat_id}).sort(
                "timestamp", ASCENDING
            )
        ]

    def get_latest_message(self, chat_id):
        return self._message_from_document(
            self.messages.find_one(
                {"chatId": chat_id},
                sort=[("timestamp", DESCENDING)],
            )
        )

    def get_next_chat_id(self):
        latest = self.chats.find_one(sort=[("id", DESCENDING)])
        return str(int(latest["id"]) + 1) if latest else "1"

    def get_next_message_id(self):
        latest = self.messages.find_one(sort=[("id", DESCENDING)])
        return str(int(latest["id"]) + 1) if latest else "1"

    def delete_message(self, message_id):
        result = self.messages.delete_one({"id": message_id})
        return result.deleted_count > 0

    def add_or_update_chat_read_state(
        self,
        state_id,
        sender_id,
        chat_id,
        last_read_message_id,
    ):
        document = self._read_state_to_document(
            state_id, sender_id, chat_id, last_read_message_id
        )
        self.chat_read_states.replace_one(
            {"senderid": sender_id, "chatid": chat_id},
            document,
            upsert=True,
        )
        return document

    def get_chat_read_state(self, sender_id, chat_id):
        return self.chat_read_states.find_one(
            {"senderid": sender_id, "chatid": chat_id},
            {"_id": 0},
        )

    def get_next_read_state_id(self):
        latest = self.chat_read_states.find_one(sort=[("id", DESCENDING)])
        return str(int(latest["id"]) + 1) if latest else "1"

    def get_chat_read_states(self, chat_id=None):
        query = {"chatid": chat_id} if chat_id is not None else {}
        return [
            self._read_state_from_document(document)
            for document in self.chat_read_states.find(query, {"_id": 0})
        ]
