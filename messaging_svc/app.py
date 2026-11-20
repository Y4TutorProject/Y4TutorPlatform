from asyncio.log import logger
from datetime import datetime, timezone
import hashlib
import hmac
import io
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_file, session
from flask_socketio import SocketIO, join_room
from gridfs.errors import NoFile
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.utils import secure_filename

from dataload import get_last_read_message_id, mark_chat_read, dao
from models.Chat import Chat
from models.Message import Message

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
ALLOWED_FILE_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/csv",
}


def create_app(config=None):
    shared = Path(os.environ.get(
        "FRONTEND_SHARED_PATH",
        Path(__file__).resolve().parent.parent / "frontend_shared",
    ))
    app = Flask(
        __name__,
        static_folder=str(shared / "static"),
        static_url_path="/dashboard/static",
    )
    app.jinja_loader = ChoiceLoader([
        app.jinja_loader,
        FileSystemLoader(shared / "templates"),
    ])
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DASHBOARD_SHARED_SECRET=os.environ.get("DASHBOARD_SHARED_SECRET"),
        MONGO_FILE_BUCKET_NAME=os.environ.get("MONGO_FILE_BUCKET_NAME"),        
        MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES + 64 * 1024,
        SESSION_COOKIE_NAME="messaging_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(
            os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
        ),
    )
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Set SECRET_KEY to a random secret of at least 32 characters.")

    socketio = SocketIO(app, cors_allowed_origins = os.getenv("SOCKETIO_CORS_ALLOWED_ORIGINS", "*"), logger=True, engineio_logger=True)
    app.extensions["socketio"] = socketio

    def _id(value):
        return str(value)

    def _dashboard_request_is_trusted():
        secret = app.config["DASHBOARD_SHARED_SECRET"]
        signature = request.headers.get("X-Dashboard-Signature")
        if not secret or not signature:
            return False

        body = request.get_data(cache=True)
        digest = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, digest)

    def _user_context():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("user"), dict):
            return None, None

        user = data["user"]
        user_id = user.get("id")
        username = user.get("username")
        status = user.get("status")
        usernames = data.get("users", {})
        if (
            not isinstance(user_id, str)
            or not user_id.strip()
            or not isinstance(username, str)
            or not username.strip()
            or status != "active"
            or not isinstance(usernames, dict)
        ):
            return None, None

        username_map = {
            _id(participant_id): participant_name
            for participant_id, participant_name in usernames.items()
            if isinstance(participant_name, str) and participant_name.strip()
        }
        username_map[_id(user_id)] = username
        return _id(user_id), username_map

    def load_chats(user: str, usernames=None):
        user_id = _id(user)
        usernames = usernames or session.get("usernames", {})
        user_chats = []
        for chat in dao.get_chats_for_user(user_id):
            if user_id not in {_id(member_id) for member_id in chat.members}:
                continue
            other_user_id = next(
                member_id
                for member_id in chat.members
                if _id(member_id) != user_id
            )
            latest_message = dao.get_latest_message(_id(chat.id))
            last_read_id = get_last_read_message_id(user_id, chat.id)
            user_chats.append({
                "chatId": _id(chat.id),
                "otherUserId": other_user_id,
                "displayName": usernames.get(
                    _id(other_user_id), _id(other_user_id)
                ),
                "lastMessage": chat.lastMessage,
                "timestamp": chat.updatedAt,
                "unread": (
                    latest_message is not None
                    and _id(latest_message.id) != last_read_id
                    and _id(latest_message.senderId) != user_id
                ),
            })
        return user_chats

    def _message_payload(message):
        usernames = session.get("usernames", {})
        sender_id = _id(message.senderId)
        payload = {
            "messageId": _id(message.id),
            "chatId": _id(message.chatId),
            "senderId": sender_id,
            "senderUsername": usernames.get(sender_id, sender_id),
            "message": message.message,
            "timestamp": message.timestamp,
            "messageType": message.messageType,
        }
        if message.messageType == "file":
            payload.update({
                "fileName": message.file_name,
                "mimeType": message.mime_type,
                "fileSize": message.file_size,
            })
        return payload

    def _emit_message(chat, payload):
        for member_id in set(chat.members):
            socketio.emit("message", payload, to=f"user:{_id(member_id)}")

    def load_chat_messages(chat_id: str):
        return [_message_payload(message) for message in dao.get_messages(_id(chat_id))]

    @app.route("/mychats/me", methods=["POST"])
    def my_chats():
        if not _dashboard_request_is_trusted():
            return jsonify({"error": "Trusted dashboard authentication required"}), 401
        user_id, usernames = _user_context()
        if user_id is None:
            return jsonify({"error": "Expected user.id and user.username"}), 400

        session["user"] = user_id
        session["usernames"] = usernames
        chats = load_chats(user_id, usernames)
        return jsonify({"chats": chats}), 200
        
 
    @app.route("/mychats/new", methods=["POST"])
    def new_chat():
        if not _dashboard_request_is_trusted():
            return jsonify({"error": "Trusted dashboard authentication required"}), 401
        user_id, usernames = _user_context()
        if user_id is None:
            return jsonify({"error": "Expected user.id and user.username"}), 400

        if not isinstance(usernames, dict):
            return jsonify({"error": "Expected usernames to be a dictionary"}), 400

        data = request.get_json(silent=True) or {}
        other_id = _id(data.get("otherUserId", ""))
        if not other_id or other_id == user_id or other_id not in usernames:
            return jsonify({"error": "A valid other user is required"}), 400

        # check if users have an existing chat
        for chat in dao.get_chats_for_user(user_id):
            if {_id(m) for m in chat.members} == {user_id, other_id}:
                return jsonify({"chatId": _id(chat.id)}), 200

        # user1:user2
        chat_id = ":".join(sorted([user_id, other_id]))
        if dao.get_chat(chat_id) is not None:
            return jsonify({"chatId": chat_id}), 200
        new_chat_obj = Chat({
            "id": dao.get_next_chat_id(),
            "members": [user_id, other_id],
            "lastMessage": "",
            "messageId": None,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        })
        dao.add_chat(new_chat_obj)
        return jsonify({"chatId": _id(new_chat_obj.id)}), 201

    
    @app.route("/mychats/chat/<chat_id>", methods=["GET"])
    def get_chat_by_id(chat_id: str):
        """
        Get the messages for a specific chat by its ID.
        """
        chat_id = _id(chat_id)
        chat = dao.get_chat(chat_id)
        user_id = session.get("user")
        if chat is None:
            return jsonify([]), 404
        if user_id not in {_id(member_id) for member_id in chat.members}:
            return jsonify({"error": "Chat not found"}), 404
        return jsonify(load_chat_messages(chat_id))

    @app.route("/mychats/chat/<chat_id>/read", methods=["POST"])
    def mark_chat_read_route(chat_id: str):
        user_id = session.get("user")
        chat_id = _id(chat_id)
        chat = dao.get_chat(chat_id)
        if user_id is None or chat is None:
            return jsonify({"error": "Chat not found"}), 404
        if user_id not in {_id(member_id) for member_id in chat.members}:
            return jsonify({"error": "Chat not found"}), 404

        chat_messages = load_chat_messages(chat_id)
        if chat_messages:
            mark_chat_read(user_id, chat_id, chat_messages[-1]["messageId"])
        return jsonify({"success": True})

    @app.route("/mychats/chat/<chat_id>/files", methods=["POST"])
    def upload_chat_file(chat_id: str):
        chat_id = _id(chat_id)
        user_id = session.get("user")
        chat = dao.get_chat(chat_id)
        if (
            user_id is None
            or chat is None
            or user_id not in {_id(member_id) for member_id in chat.members}
        ):
            return jsonify({"error": "Chat not found"}), 404

        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify({"error": "A file is required"}), 400
        if upload.mimetype not in ALLOWED_FILE_MIME_TYPES:
            return jsonify({"error": "File type not allowed"}), 415

        stream = upload.stream
        stream.seek(0, os.SEEK_END)
        file_size = stream.tell()
        stream.seek(0)
        if file_size > MAX_UPLOAD_BYTES:
            return jsonify({"error": f"File must be at most {MAX_UPLOAD_BYTES} bytes"}), 413
        if file_size == 0:
            return jsonify({"error": "File is empty"}), 400

        caption = (request.form.get("message") or "").strip()
        if len(caption) > 5000:
            return jsonify({"error": "Message is too long"}), 400

        file_name = secure_filename(upload.filename) or "file"
        file_id = dao.save_file(
            stream, file_name, upload.mimetype, file_size, chat_id, user_id
        )
        timestamp = datetime.now(timezone.utc).isoformat()
        new_message = Message({
            "id": dao.get_next_message_id(),
            "chatId": chat_id,
            "senderId": user_id,
            "message": caption,
            "timestamp": timestamp,
            "messageType": "file",
            "file_id": file_id,
            "file_name": file_name,
            "mime_type": upload.mimetype,
            "file_size": file_size,
        })
        dao.add_message(new_message)

        chat.lastMessage = caption or f"File: {file_name}"
        chat.messageId = new_message.id
        chat.updatedAt = timestamp
        if not dao.update_chat(chat):
            dao.delete_message(new_message.id)
            return jsonify({"error": "Could not save the file"}), 500

        out = _message_payload(new_message)
        _emit_message(chat, out)
        return jsonify(out), 201

    @app.route("/mychats/chat/<chat_id>/files/<message_id>", methods=["GET"])
    def download_chat_file(chat_id: str, message_id: str):
        """ handles downloading a file from a chat message."""
        chat_id = _id(chat_id)
        message_id = _id(message_id)
        user_id = session.get("user")
        chat = dao.get_chat(chat_id)
        if (
            user_id is None
            or chat is None
            or user_id not in {_id(member_id) for member_id in chat.members}
        ):
            return jsonify({"error": "Chat not found"}), 404

        message = dao.get_message(message_id)
        if (
            message is None
            or _id(message.chatId) != chat_id
            or message.messageType != "file"
            or not message.file_id
        ):
            return jsonify({"error": "File not found"}), 404

        try:
            grid_out = dao.open_file(message.file_id)
        except NoFile:
            return jsonify({"error": "File not found"}), 404

        return send_file(
            io.BytesIO(grid_out.read()),
            mimetype=message.mime_type or "application/octet-stream",
            as_attachment=True,
            download_name=message.file_name,
        )

    @socketio.on("message")
    def handle_message(payload):
        """Handle incoming chat messages.

        Validates the payload, checks chat membership, stores the message,
        updates the chat, and emits the message to all chat members.
        """
        if not isinstance(payload, dict):
            return
        if not all(
            field in payload
            for field in ("chatId", "senderId", "message", "timestamp")
        ):
            return

        chat_id = _id(payload["chatId"])
        sender_id = _id(payload["senderId"])
        message_text = payload["message"]
        if (
            not isinstance(message_text, str)
            or not message_text.strip()
            or len(message_text) > 5000
        ):
            return
        chat = dao.get_chat(chat_id)
        if (
            chat is None
            or sender_id != session.get("user")
            or sender_id not in {_id(member_id) for member_id in chat.members}
        ):
            return
        new_message = Message({
            "id": dao.get_next_message_id(),
            "chatId": chat_id,
            "senderId": sender_id,
            "message": message_text,
            "timestamp": payload["timestamp"],
            "messageType": "text",
        })
        dao.add_message(new_message)

        chat.lastMessage = message_text
        chat.messageId = new_message.id
        chat.updatedAt = payload["timestamp"]
        if not dao.update_chat(chat):
            dao.delete_message(new_message.id)
            return

        out = _message_payload(new_message)
        _emit_message(chat, out)
        return {"ok": True, "messageId": out["messageId"]}

    @socketio.on("typing")
    def handle_typing(payload):
        if not isinstance(payload, dict):
            return

        chat_id = (
            _id(payload.get("chatId"))
            if payload.get("chatId") is not None
            else None
        )
        user_id = session.get("user")
        is_typing = payload.get("isTyping")
        chat = dao.get_chat(chat_id) if chat_id is not None else None
        if (
            chat is None
            or user_id is None
            or not isinstance(is_typing, bool)
            or user_id not in {_id(member_id) for member_id in chat.members}
        ):
            return

        typing_update = {
            "chatId": chat_id,
            "senderId": _id(user_id),
            "senderUsername": session.get("usernames", {}).get(
                _id(user_id), _id(user_id)
            ),
            "isTyping": is_typing,
        }
        for member_id in set(chat.members):
            if _id(member_id) != _id(user_id):
                socketio.emit("typing", typing_update, to=f"user:{_id(member_id)}")

    @socketio.on("connect")
    def handle_connect(auth):
        user_id = (
            _id(auth.get("userId"))
            if auth and auth.get("userId") is not None
            else None
        )
        if user_id is None or user_id != session.get("user"):
            return False
        join_room(f"user:{user_id}")

    @socketio.on("disconnect")
    def handle_disconnect():
        print("Client disconnected")

    @socketio.on("join_chat")
    def handle_join_chat(data):
        chat_id = (
            _id(data.get("chatId"))
            if data and data.get("chatId") is not None
            else None
        )
        user_id = (
            _id(data.get("userId"))
            if data and data.get("userId") is not None
            else None
        )
        chat = dao.get_chat(chat_id) if chat_id is not None else None
        if (
            chat
            and user_id == session.get("user")
            and user_id in {_id(member_id) for member_id in chat.members}
        ):
            join_room(f"user:{user_id}")

    @socketio.on("leave_chat")
    def handle_leave_chat(data):
        return

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


if __name__ == "__main__":
    application = create_app()
    application.extensions["socketio"].run(
        application,
        debug=True,
        allow_unsafe_werkzeug=True,
        host="0.0.0.0",
    )
