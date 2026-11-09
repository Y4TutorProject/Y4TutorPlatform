"""Provider-independent contracts for college data imports."""
from abc import ABC, abstractmethod
from hashlib import sha256


class LMSProvider(ABC):
    label = "LMS"
    mapping_modes = ("academic",)

    @classmethod
    def configuration(cls):
        """Describe supported configuration fields for the admin UI."""
        return {"label": cls.label, "fields": []}

    @classmethod
    def validate_options(cls, options):
        if options not in (None, {}):
            raise ValueError("This provider does not support configuration options.")
        return {}

    @classmethod
    def validate_mapping(cls, mapping):
        if mapping not in cls.mapping_modes:
            raise ValueError('Unsupported mapping mode for this LMS provider.')
        return mapping

    @classmethod
    def options_for_mapping(cls, mapping, options):
        return cls.validate_options(options)

    @classmethod
    def build(cls, base_url, api_key, mapping, options, transport):
        """Construct an adapter; legacy adapters can retain their constructor."""
        cls.validate_options(options)
        return cls(base_url, api_key, mapping=mapping)

    @abstractmethod
    def fetch_catalog(self):
        """Return normalized users, courses, modules and optional enrolment links.

        Every record has a source_id. Relationships use these source IDs, never
        email addresses or locally assigned account IDs. Raise LMSImportError
        when any part of the fetch fails; never return a partial catalog.
        Modules use course_id, programme_id (source identifiers) and nullable
        integer year. Enrolments use user_source_id, target_source_id,
        target_type (module/course), and roles (student/lecturer). Legacy
        course_source_id remains accepted. Set enrolments_available only
        after a complete successful enrolment read, including an empty result.
        """


class LMSCatalogMapper(ABC):
    @abstractmethod
    def map_catalog(self, raw):
        """Map provider records to canonical courses, modules, years and roles."""


class LMSHTTPTransport(ABC):
    @abstractmethod
    def open(self, request, timeout):
        """Open a validated request and return a response context manager."""


class AcademicCatalogClient(ABC):
    @abstractmethod
    def save_catalog(self, college_id, provider, source_url, courses, modules):
        """Publish canonical academic records in the college service."""

    @abstractmethod
    def get_catalog(self, college_id, catalog_id):
        """Read a college-scoped immutable academic catalogue."""

    @abstractmethod
    def get_college(self, college_id):
        """Read an active college or return None."""


class LMSImportStore(ABC):
    @staticmethod
    def source_identity(college_id, provider, source_url):
        return sha256(f'{college_id}\n{provider}\n{source_url}'.encode()).hexdigest()

    @abstractmethod
    def save(self, college_id, provider, source_url, catalog):
        """Atomically publish a complete catalog for this college and source."""

    @abstractmethod
    def get(self, college_id, provider, source_url):
        """Return the last successful import, or None."""


class LMSImportError(Exception):
    """Public, credential-free error raised by a provider."""
