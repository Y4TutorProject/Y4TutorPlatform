import json
from Y4TutorPlatform.messaging_svc.models.User import User
from Y4TutorPlatform.messaging_svc.models.Chat import Chat
from Y4TutorPlatform.messaging_svc.models.Message import Message


users = {}
chats = {}
messages = []

usersDump = json.load(open('./data/users.json', 'r'))['users']
chatsDump = json.load(open('./data/chats.json', 'r'))['chats']
messagesDump = json.load(open('./data/messages.json', 'r'))['messages']

for user in usersDump:
    users[user['id']] = User(user)

for chat in chatsDump:
    chats[chat['id']] = Chat(chat)

for message in messagesDump:
    messages.append(Message(message))


def updateFiles():
    with open('./data/users.json', 'w') as f:
        json.dump({"users": [user.to_dict() for user in users.values()]}, f, indent=4)
    with open('./data/chats.json', 'w') as f:
        json.dump({"chats": [chat.to_dict() for chat in chats.values()]}, f, indent=4)
    with open('./data/messages.json', 'w') as f:
        json.dump({"messages": [message.to_dict() for message in messages]}, f, indent=4)
        