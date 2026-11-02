"""Provider-independent contracts for college data imports."""
from abc import ABC, abstractmethod


class LMSProvider(ABC):
    @abstractmethod
    def fetch_catalog(self):
        """Return a dict containing normalized users, courses and modules lists.

        Every record has a source_id. Relationships use these source IDs, never
        email addresses or locally assigned account IDs. Raise LMSImportError
        when any part of the fetch fails; never return a partial catalog.
        """


class LMSImportStore(ABC):
    @abstractmethod
    def save(self, college_id, provider, source_url, catalog):
        """Atomically publish a complete catalog for this college and source."""

    @abstractmethod
    def get(self, college_id, provider, source_url):
        """Return the last successful import, or None."""


class LMSImportError(Exception):
    """Public, credential-free error raised by a provider."""
