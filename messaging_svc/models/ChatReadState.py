class ChatReadState:
    def __init__(self, state_data: dict):
        self.id = str(state_data["id"])
        self.senderId = str(state_data["senderid"])
        self.chatId = str(state_data["chatid"])
        self.lastReadMessageId = str(state_data["lastreadmessageId"])

    def to_dict(self):
        return {
            "id": self.id,
            "senderid": self.senderId,
            "chatid": self.chatId,
            "lastreadmessageId": self.lastReadMessageId
        }
