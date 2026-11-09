"""Import orchestration independent of Moodle and MongoDB."""
from .providers import installed_providers
from .transport import PublicHTTPSOpener, validate_url
from .validation import validate_catalog


class LMSImportService:
    def __init__(self, store, allowed_hosts=(), providers=None, private_hosts=(), ca_file=None):
        self.private_hosts = {host.strip().lower() for host in private_hosts if host.strip()}
        self.ca_file = ca_file
        self.store = store
        self.allowed_hosts = {host.strip().lower() for host in allowed_hosts if host.strip()}
        self.providers = providers if providers is not None else installed_providers()

    def validate_source(self, data):
        if not isinstance(data, dict):
            raise ValueError("A JSON object is required.")
        provider = data.get("provider", next(iter(self.providers), None))
        if not isinstance(provider, str) or provider not in self.providers:
            raise ValueError("Unsupported LMS provider.")
        return provider, validate_url(data.get("base_url"), self.allowed_hosts, self.private_hosts)

    def import_catalog(self, college_id, data):
        provider, url = self.validate_source(data)
        key = data.get("api_key")
        if not isinstance(key, str) or not 1 <= len(key.strip()) <= 4096:
            raise ValueError("An API key is required.")
        mapping = data.get("mapping", "academic")
        self.providers[provider].validate_mapping(mapping)
        options = self.providers[provider].options_for_mapping(mapping, data.get('provider_options'))
        adapter = self.providers[provider].build(
            url, key.strip(), mapping, options,
            PublicHTTPSOpener(self.private_hosts, self.ca_file))
        catalog = adapter.fetch_catalog()
        canonical = catalog.get('canonical', False)
        catalog = validate_catalog({**catalog, 'mapping': mapping})
        return self.store.save(college_id, provider, url, {**catalog, 'mapping': mapping, 'canonical': canonical})

    def provider_configurations(self):
        return [{"id": name, "default_mapping": provider.mapping_modes[0], **provider.configuration()} for name, provider in self.providers.items()]

    def validate_options(self, provider, options, mapping="academic"):
        return self.providers[provider].options_for_mapping(mapping, options)

    def validate_mapping(self, provider, mapping):
        return self.providers[provider].validate_mapping(mapping)
