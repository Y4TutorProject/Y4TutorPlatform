from datetime import datetime, timedelta, timezone
import logging
import uuid

from cryptography.fernet import Fernet
from pymongo.errors import PyMongoError
import pytest

from lms_svc import create_app
from lms_svc.lms.interfaces import LMSImportError
from lms_svc.worker import run_due
from college_svc.Objects.College import College
from test_lms_import import integration
from test_college_auth import services


@pytest.fixture
def saved(integration):
    _, client, _, _, payload, path, headers, _ = integration
    sync = client.application.extensions["lms_sync"]
    now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    sync.clock = lambda: now
    response = client.put(path + "/connection", json=payload, headers=headers)
    assert response.status_code == 200
    college_id = path.split("/")[2]
    return integration, sync, college_id, now


def test_credentials_encrypted_and_connection_survives_restart(saved):
    data, sync, college_id, now = saved
    _, client, _, _, payload, path, headers, _ = data
    database = client.application.extensions["lms_database"]
    document = database.connections.find_one()
    assert payload["api_key"] not in str(document)
    assert sync.cipher.decrypt(document["encrypted_api_key"].encode()).decode() == payload["api_key"]
    response = client.get(path + "/connection", headers=headers)
    assert "api_key" not in response.text and "encrypted" not in response.text
    restarted = create_app(client.application.config, database=database, college_client=sync.colleges)
    restarted_sync = restarted.extensions["lms_sync"]
    restarted_sync.importer.allowed_hosts = sync.importer.allowed_hosts
    restarted_sync.clock = lambda: now
    run_due(restarted_sync, logging.getLogger("test"))
    connection = restarted_sync.connections.get(college_id)
    assert connection["last_success_at"] == now
    assert connection["counts"] == {"users": 1, "courses": 1, "modules": 1}
    assert connection["next_sync_at"] == datetime(2026, 11, 3, 2, tzinfo=timezone.utc)
    assert database.lms_imports.count_documents({}) == 1


def test_nightly_schedule_catchup_and_no_duplicate_run(saved, monkeypatch):
    _, sync, college_id, now = saved
    run_due(sync, logging.getLogger("test"))
    previous = sync.importer.store.collection.find_one()
    def fail(*args):
        raise AssertionError("Must not run before next night")
    original = sync.importer.import_catalog
    monkeypatch.setattr(sync.importer, "import_catalog", fail)
    run_due(sync, logging.getLogger("test"))
    assert sync.importer.store.collection.find_one() == previous
    monkeypatch.setattr(sync.importer, "import_catalog", original)
    # Restart after the nightly time: the persisted due job is picked up once.
    sync.clock = lambda: now + timedelta(days=2)
    run_due(sync, logging.getLogger("test"))
    assert sync.connections.get(college_id)["last_success_at"] == now + timedelta(days=2)


def test_failure_preserves_catalog_records_status_and_retries(saved, monkeypatch):
    data, sync, college_id, now = saved
    _, client, _, _, _, path, headers, _ = data
    assert client.post(path + "/sync", headers=headers).status_code == 200
    previous = sync.importer.store.collection.find_one()
    def fail(*args):
        raise LMSImportError("Private upstream error")
    monkeypatch.setattr(sync.importer, "import_catalog", fail)
    result = client.post(path + "/sync", headers=headers)
    assert result.status_code == 502
    connection = sync.connections.get(college_id)
    assert connection["last_success_at"] == now
    assert "Private" not in connection["last_error"]
    assert connection["next_sync_at"] == now + timedelta(minutes=15)
    assert "lease_id" not in connection
    assert sync.importer.store.collection.find_one() == previous


def test_worker_continues_to_next_college_after_failure(saved, monkeypatch):
    data, sync, college_id, now = saved
    _, _, dao, _, payload, _, _, _ = data
    second = College(uuid.uuid4(), "Second College", admin_id="second-admin")
    dao.add_college(second)
    second_id = str(second.college_id)
    sync.configure(second_id, "second-admin", payload)
    original = sync.importer.import_catalog
    def import_catalog(current_id, settings):
        if current_id == college_id:
            raise LMSImportError("Moodle unavailable")
        return original(current_id, settings)
    monkeypatch.setattr(sync.importer, "import_catalog", import_catalog)
    run_due(sync, logging.getLogger("test"))
    assert sync.connections.get(college_id)["last_error"]
    assert sync.connections.get(second_id)["last_success_at"] == now


def test_lease_blocks_overlap_and_configuration_and_recovers_after_crash(saved):
    data, sync, college_id, now = saved
    _, client, _, _, payload, path, headers, _ = data
    first = sync.connections.claim(college_id, now)
    assert first is not None
    assert sync.connections.claim(college_id, now, force=True) is None
    assert client.post(path + "/sync", headers=headers).status_code == 409
    assert client.put(path + "/connection", json=payload, headers=headers).status_code == 409
    second = sync.connections.claim(college_id, now + timedelta(minutes=21))
    assert second and second["lease_id"] != first["lease_id"]
    sync.connections.finish(first, {"last_error": "stale worker"})
    assert sync.connections.get(college_id)["lease_id"] == second["lease_id"]


def test_pause_keep_key_rotate_key_and_reenable(saved):
    data, sync, college_id, now = saved
    _, client, _, _, payload, path, headers, _ = data
    encrypted = sync.connections.get(college_id)["encrypted_api_key"]
    response = client.put(path + "/connection", json={**payload, "api_key": "", "enabled": False}, headers=headers)
    assert response.status_code == 200
    assert sync.connections.get(college_id)["encrypted_api_key"] == encrypted
    assert sync.connections.due(now) == []
    assert client.post(path + "/sync", headers=headers).status_code == 409
    response = client.put(path + "/connection", json={**payload, "api_key": "replacement-key"}, headers=headers)
    assert response.status_code == 200
    assert sync.connections.get(college_id)["encrypted_api_key"] != encrypted
    assert sync.connections.due(now) == [college_id]


def test_bad_encryption_key_is_reported_without_erasing_catalog(saved):
    _, sync, college_id, now = saved
    sync.cipher = Fernet(Fernet.generate_key())
    with pytest.raises(LMSImportError, match="cannot be decrypted"):
        sync.synchronize(college_id)
    assert sync.connections.get(college_id)["last_error"]


def test_schedule_tracks_dublin_daylight_saving(saved):
    _, sync, _, _ = saved
    summer = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    winter = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
    assert sync.next_night(summer) == datetime(2026, 7, 2, 1, tzinfo=timezone.utc)
    assert sync.next_night(winter) == datetime(2026, 11, 2, 2, tzinfo=timezone.utc)


def test_college_service_no_longer_has_lms_dependency(services):
    _, _, client, _, _, _, _ = services
    assert "lms_service" not in client.application.extensions
    assert client.get("/college").status_code == 200
    assert client.post(f"/college/{uuid.uuid4()}/lms/import", json={}).status_code == 404


def test_lms_database_failure_leaves_users_and_colleges_available(saved, services, monkeypatch):
    data, sync, _, _ = saved
    _, lms_client, _, _, _, path, headers, _ = data
    _, users, colleges, _, _, _, _ = services
    def unavailable(*args, **kwargs):
        raise PyMongoError("private database connection details")
    monkeypatch.setattr(sync.connections.collection, "find_one", unavailable)
    response = lms_client.get(path + "/connection", headers=headers)
    assert response.status_code == 503
    assert "private" not in response.text
    assert users.get("/users/me").status_code == 200
    assert colleges.get("/college").status_code == 200


@pytest.mark.parametrize("method,endpoint", [("get", "/connection"), ("put", "/connection"), ("post", "/sync")])
def test_saved_connection_endpoints_enforce_csrf_and_ownership(saved, method, endpoint):
    data, _, _, _ = saved
    _, client, dao, _, payload, path, headers, _ = data
    assert client.open(path + endpoint, method=method.upper(), json=payload).status_code == 400
    other = College(uuid.uuid4(), "Foreign College", admin_id="foreign-admin")
    dao.add_college(other)
    assert client.open(f"/college/{other.college_id}/lms" + endpoint,
                       method=method.upper(), json=payload, headers=headers).status_code == 403
