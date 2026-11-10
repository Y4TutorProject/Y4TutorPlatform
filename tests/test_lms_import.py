from io import BytesIO
import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs

import pytest
import mongomock
from cryptography.fernet import Fernet
from lms_svc import create_app as create_lms_app
from lms_svc.auth import UsersAuthClient

from lms_svc.lms.interfaces import LMSImportError, LMSProvider
from lms_svc.lms.moodle import MoodleProvider
from college_svc.Objects.College import College
from test_college_auth import services  # Shared real-session integration fixture.


@pytest.fixture
def integration(services, monkeypatch):
    users_app, users, college_client, dao, sign_in, copy_session, user = services
    token = sign_in()
    copy_session()
    college = College(uuid.uuid4(), "Import College", admin_id=user["id"])
    dao.add_college(college)
    class Colleges:
        def get_manual_academic(self, college_id):
            response = college_client.get(f'/internal/college/{college_id}/manual-academic',
                headers={'X-College-Sync-Token': 'test-service-token'})
            assert response.status_code == 200
            return response.json['catalog']
        def get_college(self, college_id):
            college = dao.get_college(college_id)
            return college.to_dict() if college and college.status.value == "active" else None
        def save_catalog(self, college_id, provider, source_url, courses, modules):
            response = college_client.post(f"/internal/college/{college_id}/catalogs",
                json={"provider": provider, "base_url": source_url, "courses": courses, "modules": modules},
                headers={"X-College-Sync-Token": "test-service-token"})
            assert response.status_code == 200, response.json
            return response.json["catalog"]
        def get_catalog(self, college_id, catalog_id):
            response = college_client.get(f"/internal/college/{college_id}/catalogs/{catalog_id}",
                headers={"X-College-Sync-Token": "test-service-token"})
            assert response.status_code == 200
            return response.json["catalog"]
    database = mongomock.MongoClient(tz_aware=True).lms_db
    auth = UsersAuthClient("http://users.invalid")
    monkeypatch.setattr(auth, "_request", college_client.application.extensions["users_auth"]._request)
    app = create_lms_app({"TESTING": True, "LMS_ENCRYPTION_KEY": Fernet.generate_key()},
                         database=database, auth_client=auth,
                         college_client=Colleges())
    client = app.test_client()
    client.set_cookie("tutor_session", users.get_cookie("tutor_session").value)
    service = app.extensions["lms_service"]
    service.allowed_hosts = {"moodle.college.test"}
    responses = {
        "core_user_get_users": {"users": [{"id": 10, "email": "member@college.test", "firstname": "Member"}], "warnings": []},
        "core_course_get_courses": [{"id": 1}, {"id": 20, "fullname": "Databases", "shortname": "DB4", "categoryid": 30}],
        "core_course_get_categories": [{"id": 30, "name": "Computing", "parent": 0}],
        "core_enrol_get_users_courses": [{"id": 20}],
    }
    monkeypatch.setattr(MoodleProvider, "_call", lambda self, function, **kwargs: responses[function])
    payload = {"provider": "moodle", "base_url": "https://moodle.college.test", "api_key": "secret-test-token"}
    path = f"/college/{college.college_id}/lms"
    return users_app, client, dao, service, payload, path, {"X-CSRFToken": token}, responses


def test_import_mapping_retry_and_catalog(integration):
    users, client, dao, service, payload, path, headers, responses = integration
    account_count = users.extensions["users_dao"].collection.count_documents({})
    result = client.post(path + "/import", json=payload, headers=headers)
    assert result.status_code == 200
    assert result.json["counts"] == {"users": 1, "courses": 1, "modules": 1}
    result = client.get(path + "/catalog", query_string={"base_url": payload["base_url"]}, headers=headers)
    catalog = result.json["catalog"]
    assert catalog["modules"][0]["course_id"] == catalog["courses"][0]["id"]
    assert catalog["modules"][0]["name"] == "Databases"
    assert catalog["courses"][0]["name"] == "Computing"
    assert catalog["users"][0]["source_id"] == "10"
    assert result.headers["Cache-Control"] == "no-store"
    responses["core_user_get_users"]["users"] = []
    assert client.post(path + "/import", json=payload, headers=headers).json["counts"]["users"] == 0
    assert client.application.extensions["lms_database"].lms_imports.count_documents({}) == 1
    assert "secret-test-token" not in str(client.application.extensions["lms_database"].lms_imports.find_one())
    assert users.extensions["users_dao"].collection.count_documents({}) == account_count


def test_failed_fetch_preserves_previous_import(integration, monkeypatch):
    _, client, dao, _, payload, path, headers, _ = integration
    assert client.post(path + "/import", json=payload, headers=headers).status_code == 200
    previous = client.application.extensions["lms_database"].lms_imports.find_one()
    def fail(self, function, **kwargs):
        raise LMSImportError("Moodle unavailable.")
    monkeypatch.setattr(MoodleProvider, "_call", fail)
    assert client.post(path + "/import", json=payload, headers=headers).status_code == 502
    assert client.application.extensions["lms_database"].lms_imports.find_one() == previous


def test_builtin_guest_is_excluded_without_relaxing_real_user_validation(integration):
    _, client, _, _, payload, path, headers, responses = integration
    responses["core_user_get_users"]["users"].append({
        "id": 1, "username": "guest", "email": "root@localhost",
        "firstname": "Guest user", "lastname": " ",
    })
    response = client.post(path + "/import", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json["counts"]["users"] == 1
    collection = client.application.extensions["lms_database"].lms_imports
    previous = collection.find_one()
    assert all(user["source_id"] != "1" for user in previous["users"])
    responses["core_user_get_users"]["users"][0]["email"] = "root@localhost"
    assert client.post(path + "/import", json=payload, headers=headers).status_code == 502
    assert collection.find_one() == previous


def test_missing_programme_does_not_publish_detached_modules(integration):
    _, client, dao, _, payload, path, headers, responses = integration
    responses["core_course_get_categories"] = []
    assert client.post(path + "/import", json=payload, headers=headers).status_code == 502
    assert client.application.extensions["lms_database"].lms_imports.count_documents({}) == 0


def test_optional_activity_mapping(integration):
    _, client, _, _, payload, path, headers, responses = integration
    responses["core_course_get_contents"] = [{"modules": [{"id": 40, "name": "Quiz", "modname": "quiz"}]}]
    response = client.post(path + "/import", json={**payload, "mapping": "activities"}, headers=headers)
    assert response.status_code == 200
    assert response.json["mapping"] == "activities"
    catalog = client.get(path + "/catalog", query_string={"base_url": payload["base_url"]}, headers=headers).json["catalog"]
    assert any(c["id"] == catalog["modules"][0]["course_id"] for c in catalog["courses"])
    assert catalog["modules"][0]["name"] == "Quiz"


def test_unlisted_public_source_is_accepted_when_allowlist_is_empty(integration):
    _, client, _, service, payload, path, headers, _ = integration
    service.allowed_hosts = set()
    response = client.post(path + "/import", json={**payload, "base_url": "https://another.college.edu"}, headers=headers)
    assert response.status_code == 200


@pytest.mark.parametrize("bad_user", [{"id": True}, {"id": {"$ne": None}}, {"id": 3, "suspended": "false"}, {"id": 3, "firstname": {"nested": "payload"}}, {"id": 3, "email": "invalid"}])
def test_invalid_moodle_fields_do_not_replace_catalog(integration, bad_user):
    _, client, _, _, payload, path, headers, responses = integration
    assert client.post(path + "/import", json=payload, headers=headers).status_code == 200
    collection = client.application.extensions["lms_database"].lms_imports
    previous = collection.find_one()
    responses["core_user_get_users"]["users"] = [bad_user]
    assert client.post(path + "/import", json=payload, headers=headers).status_code == 502
    assert collection.find_one() == previous


@pytest.mark.parametrize("method", ["get", "post"])
def test_lms_requires_session_csrf_role_and_owner(integration, method):
    users, client, dao, _, payload, path, headers, _ = integration
    def send(url=path, extra_headers=headers):
        if method == "post":
            return client.post(url + "/import", json=payload, headers=extra_headers)
        return client.get(url + "/catalog", query_string={"base_url": payload["base_url"]}, headers=extra_headers)
    assert send(extra_headers={}).status_code == 400
    foreign = College(uuid.uuid4(), "Other College", admin_id="other-admin")
    dao.add_college(foreign)
    assert send(f"/college/{foreign.college_id}/lms").status_code == 403
    account = users.extensions["users_dao"].collection.find_one()
    users.extensions["users_dao"].collection.update_one({"id": account["id"]}, {"$set": {"roles": ["student"]}})
    assert send().status_code == 403
    client.delete_cookie("tutor_session")
    assert send().status_code == 401
    assert client.application.extensions["lms_database"].lms_imports.count_documents({}) == 0


@pytest.mark.parametrize("url", ["http://moodle.college.test", "https://localhost", "https://127.0.0.1", "https://moodle.college.test.evil.test", "https://key@moodle.college.test", "https://moodle.college.test:8443", "https://moodle.college.test?token=x", "https://moodle.college.test#fragment"])
def test_untrusted_sources_rejected_before_fetch(integration, url):
    _, client, dao, _, payload, path, headers, _ = integration
    assert client.post(path + "/import", json={**payload, "base_url": url}, headers=headers).status_code == 400
    assert client.application.extensions["lms_database"].lms_imports.count_documents({}) == 0


@pytest.mark.parametrize("result", [{"warnings": [{"message": "hidden"}], "users": []}, {"unexpected": []}, {"users": [{"id": 1}, {"id": 1}]}])
def test_incomplete_or_duplicate_response_does_not_save(integration, result):
    _, client, dao, _, payload, path, headers, responses = integration
    responses["core_user_get_users"] = result
    assert client.post(path + "/import", json=payload, headers=headers).status_code == 502
    assert client.application.extensions["lms_database"].lms_imports.count_documents({}) == 0


def test_add_provider_without_changing_import_or_storage(integration):
    _, client, dao, service, _, _, _, _ = integration
    class BlackboardStub(LMSProvider):
        def __init__(self, base_url, api_key, mapping):
            pass

        def fetch_catalog(self):
            return {"users": [], "courses": [], "modules": []}
    service.providers["blackboard"] = BlackboardStub
    college = College(uuid.uuid4(), "Blackboard College", admin_id="blackboard-admin")
    dao.add_college(college)
    result = service.import_catalog(str(college.college_id), {"provider": "blackboard", "base_url": "https://moodle.college.test", "api_key": "key"})
    assert result["provider"] == "blackboard"
    assert client.application.extensions["lms_database"].lms_imports.count_documents({}) == 1
    assert service.store.get("college-1", "blackboard", result["base_url"]) is None


def test_moodle_transport_uses_post_body_and_moodle_subpath():
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://moodle.college.test/moodle/webservice/rest/server.php"
            assert request.method == "POST"
            assert parse_qs(request.data.decode())["wstoken"] == ["private-key"]
            assert timeout == 15
            return BytesIO(b"[]")
    provider = MoodleProvider("https://moodle.college.test/moodle", "private-key", opener=Opener())
    assert provider._call("core_course_get_courses") == []


@pytest.mark.parametrize("failure", [URLError("private-key"), HTTPError("https://private-key", 302, "private-key", {}, None)])
def test_transport_errors_do_not_expose_credentials(failure):
    class Opener:
        def open(self, *args, **kwargs):
            raise failure
    with pytest.raises(LMSImportError) as error:
        MoodleProvider("https://moodle.college.test", "private-key", opener=Opener())._call("core_course_get_courses")
    assert "private-key" not in str(error.value)


def test_moodle_json_exception_is_sanitized():
    class Opener:
        def open(self, *args, **kwargs):
            return BytesIO(json.dumps({"exception": "error", "message": "private-key"}).encode())
    with pytest.raises(LMSImportError) as error:
        MoodleProvider("https://moodle.college.test", "private-key", opener=Opener())._call("core_course_get_courses")
    assert "private-key" not in str(error.value)


def test_enrolment_api_is_read_for_each_active_moodle_user(integration, monkeypatch):
    _, _, _, service, payload, path, _, responses = integration
    responses['core_user_get_users']['users'].append({'id': 11, 'email': 'paused@college.test', 'suspended': True})
    calls = []
    def read(self, function, **kwargs):
        calls.append((function, kwargs))
        return responses[function]
    monkeypatch.setattr(MoodleProvider, '_call', read)
    catalog = service.import_catalog(path.split('/')[2], payload)
    assert [(fn, args) for fn, args in calls if fn == 'core_enrol_get_users_courses'] == [
        ('core_enrol_get_users_courses', {'userid': 10, 'returnusercount': 0})]
    assert catalog['enrolments_available'] is True
    assert len(catalog['enrolments']) == 1


@pytest.mark.parametrize('enrolled', [[{'id': 999}], [{'id': 20}, {'id': 20}], [{'id': '20'}], {'warnings': []}])
def test_bad_enrolment_response_preserves_previous_import(integration, enrolled):
    _, _, _, service, payload, path, _, responses = integration
    college_id = path.split('/')[2]
    service.import_catalog(college_id, payload)
    previous = service.store.collection.find_one()
    responses['core_enrol_get_users_courses'] = enrolled
    with pytest.raises(LMSImportError):
        service.import_catalog(college_id, payload)
    assert service.store.collection.find_one() == previous
