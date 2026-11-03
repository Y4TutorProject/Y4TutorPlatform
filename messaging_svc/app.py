import hashlib
import hmac

from flask import Flask, jsonify, render_template, request, session
from flask_socketio import SocketIO, join_room
from dataload import (
    get_last_read_message_id,
    mark_chat_read,
    dao,
)
from models.Message import Message
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
app.config["DASHBOARD_SHARED_SECRET"] = os.environ.get(
    "DASHBOARD_SHARED_SECRET"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
)
if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
    raise RuntimeError("Set SECRET_KEY to a random secret of at least 32 characters.")
socketio = SocketIO(app)


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
    roles = user.get("roles")
    usernames = data.get("users", {})
    if (
        not isinstance(user_id, str)
        or not user_id.strip()
        or not isinstance(username, str)
        or not username.strip()
        or status != "active"
        or not isinstance(roles, list)
        or not roles
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


@app.route('/mychats/me', methods=['POST'])
def my_chats():
    if not _dashboard_request_is_trusted():
        return jsonify({"error": "Trusted dashboard authentication required"}), 401

    user_id, usernames = _user_context()
    if user_id is None:
        return jsonify({"error": "Expected user.id and user.username"}), 400

    session["user"] = user_id
    session["usernames"] = usernames
    return render_template(
        'chatsPage.html',
        user=user_id,
        name=usernames[user_id],
        chats=loadChats(user_id, usernames),
    )


def loadChats(user: str, usernames=None):
    user_id = _id(user)
    usernames = usernames or session.get("usernames", {})
    userChats = []
    for chat in dao.get_chats_for_user(user_id):
        if user_id not in {_id(member_id) for member_id in chat.members}:
            continue
        # get the member that is not this user
        other_user_id = next(
            member_id
            for member_id in chat.members
            if _id(member_id) != user_id
        )
        latest_message = dao.get_latest_message(_id(chat.id))
        last_read_id = get_last_read_message_id(user_id, chat.id)
        userChats.append({
            "chatId": _id(chat.id),
            "otherUserId": other_user_id,
            "displayName": usernames.get(_id(other_user_id), _id(other_user_id)),
            "lastMessage": chat.lastMessage,
            "timestamp": chat.updatedAt,
            "unread": (
                latest_message is not None
                and _id(latest_message.id) != last_read_id
                and _id(latest_message.senderId) != user_id
            )
        })
    return userChats


def loadChatMessages(chatId: str):
    chat_id = _id(chatId)
    usernames = session.get("usernames", {})
    chatMessages = dao.get_messages(chat_id)
    return [{
        "messageId": _id(message.id),
        "chatId": chat_id,
        "senderId": _id(message.senderId),
        "senderUsername": usernames.get(
            _id(message.senderId), _id(message.senderId)
        ),
        "message": message.message,
        "timestamp": message.timestamp
    } for message in chatMessages]


@app.route('/mychats/chat/<chatId>', methods=['GET'])
def getChatById(chatId:str): 
    chat_id = _id(chatId)
    chat = dao.get_chat(chat_id)
    user_id = session.get("user")
    if chat is None:
        return jsonify([]), 404
    if user_id not in {_id(member_id) for member_id in chat.members}:
        return jsonify({"error": "Chat not found"}), 404
    return jsonify(loadChatMessages(chat_id))


@app.route('/mychats/chat/<chatId>/read', methods=['POST'])
def mark_chat_read_route(chatId: str):
    user_id = session.get("user")
    chat_id = _id(chatId)
    chat = dao.get_chat(chat_id)
    if user_id is None or chat is None:
        return jsonify({"error": "Chat not found"}), 404
    if user_id not in {_id(member_id) for member_id in chat.members}:
        return jsonify({"error": "Chat not found"}), 404

    chat_messages = loadChatMessages(chat_id)
    if chat_messages:
        mark_chat_read(user_id, chat_id, chat_messages[-1]["messageId"])
    return jsonify({"success": True})

@socketio.on('message')
def handle_message(payload):
    if not isinstance(payload, dict):
        return
    if not all(field in payload for field in ("chatId", "senderId", "message", "timestamp")):
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
    # make sure both users are part of the current chat
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
        "timestamp": payload["timestamp"]
    })
    dao.add_message(new_message)


    chat.lastMessage = message_text
    chat.messageId = new_message.id
    chat.updatedAt = payload["timestamp"]
    if not dao.update_chat(chat):
        dao.delete_message(new_message.id)
        return

    out = {
        "messageId": _id(new_message.id),
        "chatId": chat_id,
        "senderId": _id(new_message.senderId),
        "senderUsername": session.get("usernames", {}).get(
            _id(new_message.senderId), _id(new_message.senderId)
        ),
        "message": new_message.message,
        "timestamp": new_message.timestamp
    }
    # TODO: Trigger the notification service
    for member_id in set(chat.members):
        socketio.emit("message", out, to=f"user:{_id(member_id)}")


@socketio.on('typing')
def handle_typing(payload):
    if not isinstance(payload, dict):
        return

    chat_id = _id(payload.get("chatId")) if payload.get("chatId") is not None else None
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


@socketio.on('connect')
def handle_connect(auth):
    user_id = _id(auth.get("userId")) if auth and auth.get("userId") is not None else None
    if user_id is not None and user_id == session.get("user"):
        join_room(f"user:{user_id}")

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

@socketio.on('join_chat')
def handle_join_chat(data):
    chat_id = _id(data.get("chatId")) if data else None
    user_id = _id(data.get("userId")) if data and data.get("userId") is not None else None
    chat = dao.get_chat(chat_id) if chat_id is not None else None
    if (
        chat
        and user_id == session.get("user")
        and user_id in {_id(member_id) for member_id in chat.members}
    ):
        join_room(f"user:{user_id}")

@socketio.on('leave_chat')
def handle_leave_chat(data):
    return


if __name__ == "__main__":
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True, host="0.0.0.0")
