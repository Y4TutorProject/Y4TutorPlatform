class Chat:
    def __init__(self, chatData:dict):
        self.id = chatData['id']
        self.members = chatData['members']
        self.lastMessage = chatData['lastMessage']
        self.updatedAt = chatData['updatedAt']
        self.messageId = chatData['messageId']
    

    def __lt__(self, other):
        return self.updatedAt < other.updatedAt

    def to_dict(self):
        return {
            "id": self.id,
            "members": self.members,
            "lastMessage": self.lastMessage,
            "messageId": self.messageId,
            "updatedAt": self.updatedAt
        }
