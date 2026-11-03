"""Import orchestration independent of Moodle and MongoDB."""
from .moodle import MoodleProvider
from .transport import PublicHTTPSOpener, validate_url
from .validation import validate_catalog


class LMSImportService:
    def __init__(self, store, allowed_hosts=(), providers=None, private_hosts=(), ca_file=None):
        self.private_hosts = {host.strip().lower() for host in private_hosts if host.strip()}
        self.ca_file = ca_file
        self.store = store
        self.allowed_hosts = {host.strip().lower() for host in allowed_hosts if host.strip()}
        self.providers = providers if providers is not None else {"moodle": MoodleProvider}

    def validate_source(self, data):
        if not isinstance(data, dict):
            raise ValueError("A JSON object is required.")
        provider = data.get("provider", "moodle")
        if not isinstance(provider, str) or provider not in self.providers:
            raise ValueError("Unsupported LMS provider.")
        return provider, validate_url(data.get("base_url"), self.allowed_hosts, self.private_hosts)

    def import_catalog(self, college_id, data):
        provider, url = self.validate_source(data)
        key = data.get("api_key")
        if not isinstance(key, str) or not 1 <= len(key.strip()) <= 4096:
            raise ValueError("An API key is required.")
        mapping = data.get("mapping", "academic")
        if mapping not in ("academic", "activities"):
            raise ValueError("Mapping must be academic or activities.")
        options = {}
        if self.providers[provider] is MoodleProvider and (self.private_hosts or self.ca_file):
            options["opener"] = PublicHTTPSOpener(self.private_hosts, self.ca_file)
        catalog = self.providers[provider](url, key.strip(), mapping=mapping, **options).fetch_catalog()
        catalog = validate_catalog({**catalog, "mapping": mapping})
        return self.store.save(college_id, provider, url, {**catalog, "mapping": mapping})
