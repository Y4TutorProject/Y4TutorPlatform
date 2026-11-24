from sessions_svc.objects.SessionStatus import SessionStatus

class Session:
    def __init__(self, sessionData: dict):
        self.id: str = sessionData['id']
        self.tutorId: str = sessionData['tutorId']
        self.studentId: str = sessionData['studentId']
        self.moduleId: str = sessionData['moduleId']
        self.startTime: str = sessionData['startTime']
        self.endTime: str = sessionData['endTime']
        self.status: SessionStatus = SessionStatus(sessionData['status'])
        self.price: int = sessionData['price'] ## price in cents

    def to_dict(self):
        return {
            "id": self.id,
            "tutorId": self.tutorId,
            "studentId": self.studentId,
            "moduleId": self.moduleId,
            "startTime": self.startTime,
            "endTime": self.endTime,
            "status": self.status.value,  # store the string, not the Enum
            "price": self.price,
        }
