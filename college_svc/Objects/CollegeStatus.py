from enum import Enum

class CollegeStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    MARKED_FOR_DELETION = "marked_for_deletion"