from enum import Enum

class SessionStatus(Enum):
    BOOKED = "booked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"