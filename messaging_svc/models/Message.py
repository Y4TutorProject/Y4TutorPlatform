# create message class based on message dict
class Message:

    def __init__(self, messageData: dict):
        self.id = messageData['id']
        self.chatId = messageData['chatId']
        self.senderId = messageData['senderId']
        self.message = messageData['message']
        self.timestamp = messageData['timestamp']

    # add a method that enables sorting messages by timestamp
    def __lt__(self, other):
        return self.timestamp < other.timestamp

    def __repr__(self):
        return f"Message(id={self.id}, chatId={self.chatId}, senderId={self.senderId}, message={self.message}, timestamp={self.timestamp})"

    def __str__(self):
        return f"Message(id={self.id}, chatId={self.chatId}, senderId={self.senderId}, message={self.message}, timestamp={self.timestamp})"

    def to_dict(self):
        return {
            "id": self.id,
            "chatId": self.chatId,
            "senderId": self.senderId,
            "message": self.message,
            "timestamp": self.timestamp
        }
        