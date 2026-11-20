class Message:

    def __init__(self, messageData: dict):
        self.id = messageData['id']
        self.chatId = messageData['chatId']
        self.senderId = messageData['senderId']
        self.message = messageData['message']
        self.timestamp = messageData['timestamp']
        self.messageType = messageData.get('messageType', "text")
        # File-related attributes (optional)    
        self.file_id = messageData['file_id'] if 'file_id' in messageData else None
        self.file_name = messageData['file_name'] if 'file_name' in messageData else None
        self.mime_type = messageData['mime_type'] if 'mime_type' in messageData else None
        self.file_size = messageData['file_size'] if 'file_size' in messageData else None


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
            "timestamp": self.timestamp,
            "messageType": self.messageType,
            "file_id": self.file_id,
            "file_name": self.file_name,
            "mime_type": self.mime_type,
            "file_size": self.file_size
        }
        