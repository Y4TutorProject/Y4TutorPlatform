from abc import ABC, abstractmethod
from ..Objects.College import College

class CollegeDAO(ABC):
    @abstractmethod
    def list_active_colleges(self):
        """List active colleges in name order.

        Returns:
            list[College]: Colleges available during registration.
        """
        pass

    @abstractmethod
    def connect_to_database(self):
        """Check connectivity to the database.

        Returns:
            bool: True when the operation succeeds.
        """
        pass

    @abstractmethod
    def add_college(self, college):
        """Insert a new college into the data store.

        Args:
            college (College): College to store, update, or serialize.

        Returns:
            bool: True when the operation succeeds.
        """
        pass

    @abstractmethod
    def update_college(self, college):
        """Update an existing college and report whether a record matched.

        Args:
            college (College): College to store, update, or serialize.

        Returns:
            bool: True if a stored record matched the identifier; otherwise False.
        """
        pass

    @abstractmethod
    def get_college(self, college_id):
        """Return the college with the given ID, or None if not found.

        Args:
            college_id (str | uuid.UUID): College identifier to look up.

        Returns:
            College | None: Reconstructed record, or None if no record matches.
        """
        pass

    @abstractmethod
    def setup_database(self):
        """Create the indexes required for unique college identities.
        """
        pass

class CollegeInterface(ABC):
    @abstractmethod
    def list_active_colleges(self):
        """List colleges available during registration.

        Returns:
            list[College]: Active colleges in name order.
        """
        pass

    @abstractmethod
    def create_college(self, college: College, admin_id=None):
        """Persist a college and return the created college object.

        Args:
            college (College): College to store, update, or serialize.
            admin_id (str | None): Verified owner UUID supplied by the API.

        Returns:
            College: Persisted college object.
        """
        pass

    @abstractmethod
    def update_college(self, college: College):
        """Update an existing college and report whether a record matched.

        Args:
            college (College): College to store, update, or serialize.

        Returns:
            bool: True if a stored record matched the identifier; otherwise False.
        """
        pass
    
    @abstractmethod
    def get_college_by_id(self, college_id):
        """Return a college by ID, or None if not found.

        Args:
            college_id (str | uuid.UUID): College identifier to look up.

        Returns:
            College | None: Reconstructed record, or None if no record matches.
        """
        pass

    @abstractmethod
    def get_college_by_name(self, name):
        """Return a college by name, or None if not found.

        Args:
            name (str): Exact stored college name to look up.

        Returns:
            College | None: Reconstructed record, or None if no record matches.
        """
        pass
