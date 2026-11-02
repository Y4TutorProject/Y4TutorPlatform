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
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "default_secret_key")
socketio = SocketIO(app)


def _id(value):
    return str(value)


@app.route('/mychats/me', methods=['GET'])
def my_chats():
   user_data = request.get_json()
   if user_data is None:
       return jsonify({"error": "Missing user data"}), 400  
   user_id = user_data.get("userId") if user_data else None
   username = user_data.get("username") if user_data else None
   if user_id is None or username is None:
       return jsonify({"error": "Missing user information"}), 400
   return render_template(
        'chatsPage.html',
        user=user_id,
        name=username,
        chats=loadChats(user_id)
    )

def loadChats(user: str):
    user_id = _id(user)
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
        # get the name of the other user
        other_user = users.get(_id(other_user_id))
        latest_message = dao.get_latest_message(_id(chat.id))
        last_read_id = get_last_read_message_id(user_id, chat.id)
        userChats.append({
            "chatId": _id(chat.id),
            "otherUserId": other_user.id,
            "displayName": other_user.name if other_user else _id(other_user_id),
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
    chatMessages = dao.get_messages(chat_id)
    return [{
        "messageId": _id(message.id),
        "chatId": chat_id,
        "senderId": _id(message.senderId),
        "message": message.message,
        "timestamp": message.timestamp
    } for message in chatMessages]


@app.route('/mychats/chat/<chatId>', methods=['GET'])
def getChatById(chatId:str): 
    chat_id = _id(chatId)
    if dao.get_chat(chat_id) is None:
        return jsonify([]), 404
    return jsonify(loadChatMessages(chat_id))


@app.route('/mychats/chat/<chatId>/read', methods=['POST'])
def mark_chat_read_route(chatId: str):
    user_id = session.get("user")
    chat_id = _id(chatId)
    chat = dao.get_chat(chat_id)
    if user_id is None or chat is None:
        return jsonify({"error": "Chat not found"}), 404

    chat_messages = loadChatMessages(chat_id)
    if chat_messages:
        mark_chat_read(user_id, chat_id, chat_messages[-1]["messageId"])
    return jsonify({"success": True})

@socketio.on('message')
def handle_message(payload):
    if not payload or "chatId" not in payload or "senderId" not in payload:
        return

    chat_id = _id(payload["chatId"])
    sender_id = _id(payload["senderId"])
    chat = dao.get_chat(chat_id)
    # make sure both users are part of the current chat
    if chat is None or sender_id not in {_id(member_id) for member_id in chat.members}:
        return
    new_message = Message({
        "id": dao.get_next_message_id(),
        "chatId": chat_id,
        "senderId": sender_id,
        "message": payload["message"],
        "timestamp": payload["timestamp"]
    })
    dao.add_message(new_message)


    chat.lastMessage = payload["message"]
    chat.messageId = new_message.id
    chat.updatedAt = payload["timestamp"]
    if not dao.update_chat(chat):
        dao.delete_message(new_message.id)
        return

    out = {
        "messageId": _id(new_message.id),
        "chatId": chat_id,
        "senderId": _id(new_message.senderId),
        "message": new_message.message,
        "timestamp": new_message.timestamp
    }
    # TODO: Trigger the notification service
    for member_id in set(chat.members):
        socketio.emit("message", out, to=f"user:{_id(member_id)}")

@socketio.on('connect')
def handle_connect(auth):
    user_id = _id(auth.get("userId")) if auth and auth.get("userId") is not None else None
    if user_id is not None:
        if user_id in users:
            join_room(f"user:{user_id}")

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

@socketio.on('join_chat')
def handle_join_chat(data):
    chat_id = _id(data.get("chatId")) if data else None
    user_id = _id(data.get("userId")) if data and data.get("userId") is not None else None
    chat = dao.get_chat(chat_id) if chat_id is not None else None
    if chat and user_id in {_id(member_id) for member_id in chat.members}:
        join_room(f"user:{user_id}")

@socketio.on('leave_chat')
def handle_leave_chat(data):
    return


if __name__ == "__main__":
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True, host="0.0.0.0")
