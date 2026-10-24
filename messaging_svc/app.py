from email.mime import message

from flask import Flask, json, request, render_template, redirect, url_for, session
from flask_socketio import SocketIO, join_room, leave_room, send, emit
import random
from string import ascii_letters
from Y4TutorPlatform.messaging_svc.dataload import users, messages, chats, updateFiles
from Y4TutorPlatform.messaging_svc.models.Chat import Chat
from Y4TutorPlatform.messaging_svc.models.Message import Message
from Y4TutorPlatform.messaging_svc.models.User import User

app = Flask(__name__)
app.config["SECRET_KEY"] = "supersecretkey"
socketio = SocketIO(app)



        

@app.route('/mychats/<userId>')
def my_chats(userId:str):
    user = users.get(int(userId))
    if(user is None):
        return "User not found", 404
    session['user'] = int(userId)
    if user is not None:
        return render_template('chatsPage.html', user=user.id, name=user.name, chats = loadChats(user.id))

def loadChats(user: int):
    userChats = []
    for chat in sorted(chats.values(), reverse=True):
        if user not in chat.members:
            continue
        # get the member that is not this user
        other_user_id = next(
            member_id
            for member_id in chat.members
            if member_id != user
        )
        # get the name of the other user
        other_user = users.get(other_user_id)
        userChats.append({
            "chatId": chat.id,
            "otherUserId": other_user.id,
            "displayName": other_user.name,
            "lastMessage": chat.lastMessage,
            "timestamp": chat.updatedAt
        })
    return userChats


def loadChatMessages(chatId: str):
    # if it is not a valid chat id, return an empty list
    chatMessages = []
    for message in messages:
        if str(message.chatId) == chatId:
            chatMessages.append(message)
    # sort the messages by timestamp
    chatMessages.sort()
    return [{
        "messageId": message.id,
        "senderId": message.senderId,
        "message": message.message,
        "timestamp": message.timestamp
    } for message in chatMessages]


@app.route('/mychats/chat/<chatId>', methods=['GET'])
def getChatById(chatId:str): 
    chat_id = int(chatId)
    if chat_id not in chats:
        return [], 404
    messages = loadChatMessages(chatId)
    return json.dumps(messages), 200

# # handles message send on the backend and sends it to the room, also adds it to the room's message history
@socketio.on('message')
def handle_message(payload):
    chat_id = int(payload["chatId"])
    sender_id = int(payload["senderId"])
    # update the messages list with the new message
    # TODO: fix message id generation
    new_message = Message({
        "id": len(messages) + 1, 
        "chatId": chat_id,
        "senderId": sender_id,
        "message": payload["message"],
        "timestamp": payload["timestamp"]
    })
    messages.append(new_message)
    # update the chat's last message and updatedAt
    chat = chats.get(chat_id)
    if chat is not None:
        chat.lastMessage = payload["message"]
        chat.updatedAt = payload["timestamp"]
    updateFiles()
    
    emit("message", {
        "messageId": new_message.id,
        "senderId": new_message.senderId,
        "message": new_message.message,
        "timestamp": new_message.timestamp
    }, to=str(chat_id))


@socketio.on('connect')
def handle_connect():
    print("Client connected")

@socketio.on('disconnect')
def handle_disconnect():
    print("Client disconnected")

@socketio.on('join_chat')
def join_chat(data):
    userId = data.get('userId')
    chatId = data.get('chatId')
    if userId is None or chatId is None:
        return
    chat_id = int(chatId)
    if chat_id not in chats:
        leave_room(chatId)
        return
    join_room(str(chat_id))


@socketio.on('leave_chat')
def handle_leave(data):
    userId = data.get('userId')
    chatId = data.get('chatId')
    if userId is None or chatId is None:
        return
    leave_room(str(chatId))


if __name__ == "__main__":
    socketio.run(app, debug=True)

