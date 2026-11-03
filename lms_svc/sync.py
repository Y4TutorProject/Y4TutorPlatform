"""Saved connections and nightly scheduling, independent of the HTTP process."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken

from .connections import SyncBusy
from .lms.interfaces import LMSImportError


class LMSSyncService:
    def __init__(self, importer, connections, encryption_key, college_client,
                 timezone_name="Europe/Dublin", sync_hour=2, clock=None):
        self.importer = importer
        self.connections = connections
        self.cipher = Fernet(encryption_key)
        self.colleges = college_client
        self.zone = ZoneInfo(timezone_name)
        self.hour = int(sync_hour)
        if not 0 <= self.hour <= 23:
            raise ValueError("LMS_SYNC_HOUR must be between 0 and 23.")
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def next_night(self, now):
        local = now.astimezone(self.zone)
        target = datetime.combine(local.date(), time(self.hour), self.zone)
        if target <= local:
            target = datetime.combine(local.date() + timedelta(days=1), time(self.hour), self.zone)
        return target.astimezone(timezone.utc)

    def public(self, connection):
        if connection is None:
            return None
        fields = ("provider", "base_url", "mapping", "enabled", "next_sync_at", "last_attempt_at", "last_success_at", "last_error", "counts")
        result = {key: connection[key] for key in fields if key in connection}
        for key, value in result.items():
            if isinstance(value, datetime):
                result[key] = value.astimezone(timezone.utc).isoformat()
        result.update(timezone=str(self.zone), sync_hour=self.hour)
        return result

    def configure(self, college_id, admin_id, data):
        provider, url = self.importer.validate_source(data)
        mapping = data.get("mapping", "academic")
        if mapping not in ("academic", "activities"):
            raise ValueError("Mapping must be academic or activities.")
        # Keep nightly jobs bounded; academic mapping is the college's supported model.
        if mapping != "academic":
            raise ValueError("Saved nightly connections use the academic mapping.")
        enabled = data.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("Enabled must be true or false.")
        old = self.connections.get(college_id)
        key = data.get("api_key")
        if key is None or key == "":
            if old is None or old["provider"] != provider or old["base_url"] != url or old["admin_id"] != admin_id:
                raise ValueError("An API key is required for a new connection.")
            encrypted = old["encrypted_api_key"]
        elif not isinstance(key, str) or not 1 <= len(key.strip()) <= 4096:
            raise ValueError("Enter a valid API key.")
        else:
            encrypted = self.cipher.encrypt(key.strip().encode()).decode()
        now = self.clock()
        fields = {
            "provider": provider, "base_url": url, "mapping": mapping, "enabled": enabled,
            "encrypted_api_key": encrypted, "admin_id": admin_id,
            "next_sync_at": now if enabled else self.next_night(now), "updated_at": now,
        }
        if old and (old["provider"], old["base_url"]) != (provider, url):
            fields.update(last_attempt_at=None, last_success_at=None, last_error=None, counts=None)
        return self.public(self.connections.save(college_id, fields, now))

    def synchronize(self, college_id, force=False):
        connection = self.connections.claim(college_id, self.clock(), force=force)
        if connection is None:
            raise SyncBusy("No enabled synchronization is due, or one is already running.")
        try:
            college = self.colleges.get_college(college_id)
            if college is None or college.get("admin_id") != connection["admin_id"]:
                raise LMSImportError("College is inactive or connection ownership has changed.")
            try:
                key = self.cipher.decrypt(connection["encrypted_api_key"].encode()).decode()
            except InvalidToken:
                raise LMSImportError("Saved credentials cannot be decrypted. Update the connection API key.") from None
            catalog = self.importer.import_catalog(college_id, {
                "provider": connection["provider"], "base_url": connection["base_url"],
                "mapping": connection["mapping"], "api_key": key,
            })
        except Exception:
            # No upstream exception text or credentials enter status/logs.
            now = self.clock()
            self.connections.finish(connection, {"last_attempt_at": now,
                "last_error": "Synchronization failed. Check service availability, connection credentials and permissions.",
                "next_sync_at": now + timedelta(minutes=15)})
            raise
        now = self.clock()
        counts = {kind: len(catalog[kind]) for kind in ("users", "courses", "modules")}
        self.connections.finish(connection, {"last_attempt_at": now, "last_success_at": now,
            "last_error": None, "counts": counts, "next_sync_at": self.next_night(now)})
        return self.public(self.connections.get(college_id))
