from enum import StrEnum

class NotificationType(StrEnum):
    TUTOR_REQUEST_CREATED = "tutor_request_created"
    BOOKING_CREATED = "booking_created"
    LESSON_REMINDER = "lesson_reminder"