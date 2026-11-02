import uuid

from .CollegeStatus import CollegeStatus

class College:
    def __init__(self, college_id, college_name, domain=None, status=CollegeStatus.ACTIVE, admin_id=None):
        """Build a college with a UUID and enum status, defaulting to active.

        Args:
            college_id (str | uuid.UUID): College identifier to look up.
            college_name (str): College name.
            admin_id (str | None): Owning administrator UUID. Defaults to None.
            domain (str | None): College email domain. Defaults to None.
            status (CollegeStatus | str): Initial account status. Defaults to
                active.

        Raises:
            ValueError: An identifier or enum value is invalid.
        """
        self.college_id = uuid.UUID(str(college_id))
        self.college_name = college_name
        self.college_domain = domain
        self.status = CollegeStatus(status)
        self.admin_id = str(admin_id) if admin_id else None

    def to_dict(self):
        """Return college details with JSON-compatible identifiers and status.

        Returns:
            dict: College details with string UUID and status values.
        """
        return {
            "id": str(self.college_id), "name": self.college_name,
            "domain": self.college_domain, "status": self.status.value,
            "admin_id": self.admin_id,
        }
