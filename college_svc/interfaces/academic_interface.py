from abc import ABC, abstractmethod


class AcademicDAO(ABC):
    @abstractmethod
    def save_catalog(self, college_id, catalog_id, courses, modules):
        """Publish an immutable catalogue after storing all Course/Module objects."""

    @abstractmethod
    def get_catalog(self, college_id, catalog_id):
        """Read a college-scoped catalogue, or None if it does not exist."""


class AcademicInterface(ABC):
    @abstractmethod
    def import_catalog(self, college_id, data):
        """Validate source records and store the college's courses and modules."""

    @abstractmethod
    def get_catalog(self, college_id, catalog_id):
        """Return a published catalogue, or None."""
