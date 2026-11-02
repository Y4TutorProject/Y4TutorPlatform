import uuid
import re

from ..interfaces.college_interface import CollegeInterface
from ..Objects.College import College

class CollegeService(CollegeInterface):
    def __init__(self, dao):
        """Store the DAO used for college persistence and lookups.

        Args:
            dao (CollegeDAO): Data access object used by the service.
        """
        self.dao = dao

    def create_college(self, college: College, admin_id=None):
        """Save and return a College, accepting a model or a JSON-style dictionary.

        Dictionary input receives a generated UUID. Authentication is enforced
        by the API route before this method is called.

        Args:
            college (College | dict): College to store, update, or serialize.
            admin_id (str | None): Verified owner UUID supplied by the API.

        Returns:
            College: Persisted college object.

        Raises:
            ValueError: The input is not a College or dictionary, or a supplied
                field is invalid.
            DuplicateKeyError: The college ID or name already exists.
        """
        if isinstance(college, dict):
            name = college.get("name")
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
                raise ValueError("College name must contain 1–200 characters.")
            domain = college.get("domain")
            if not isinstance(domain, str):
                raise ValueError("Enter the student email domain, such as students.college.ie.")
            domain = domain.strip().lower()
            if len(domain) > 253 or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain):
                raise ValueError("Enter a valid student email domain without @ or a URL.")
            if admin_id:
                existing = self.dao.get_college_by_admin(admin_id)
                if existing:
                    if existing.college_name == name.strip() and existing.college_domain == domain:
                        return existing
                    raise ValueError("You have already registered a college.")
            college = College(uuid.uuid4(), name.strip(), domain=domain, admin_id=admin_id)
        elif not isinstance(college, College):
            raise ValueError("A JSON object is required.")
        self.dao.add_college(college)
        return college

    def update_college(self, college: College):
        """Persist a college and return whether an existing document matched.

        Args:
            college (College): College to store, update, or serialize.

        Returns:
            bool: True if a stored record matched the identifier; otherwise False.
        """
        return self.dao.update_college(college)

    def get_college_by_id(self, college_id):
        """Return a college by UUID, or None for an invalid or unknown ID.

        Args:
            college_id (str | uuid.UUID): College identifier to look up.

        Returns:
            College | None: Reconstructed record, or None if no record matches.
        """
        return self.dao.get_college(college_id)

    def get_college_by_name(self, name):
        """Return a college by its exact stored name, or None if not found.

        Args:
            name (str): Exact stored college name to look up.

        Returns:
            College | None: Reconstructed record, or None if no record matches.
        """
        return self.dao.get_college_by_name(name)

    def list_active_colleges(self):
        """Return colleges available for selection during signup.

        Returns:
            list[College]: Active colleges sorted by name.
        """
        return self.dao.list_active_colleges()

