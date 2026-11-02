from datetime import timedelta
from io import BytesIO
import uuid
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.error import URLError

import mongomock
import pytest

from college_svc import create_app as create_college_app
from college_svc.auth import AuthenticationError, UsersAuthClient
from college_svc.college_dao.MongoCollegeDAO import MongoCollegeDAO
from college_svc.Objects.College import College
from college_svc.Objects.CollegeStatus import CollegeStatus
from registration_svc.college_client import CollegeClient
from registration_svc import create_app as create_registration_app
from users_svc import create_app as create_users_app
from users_svc.Objects.UserStatus import UserStatus
from support import MemoryMailer, verify_latest


@pytest.fixture
def services(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost")
    monkeypatch.setattr("users_svc.users_dao.MongoUsersDAO.MongoClient", mongomock.MongoClient)
    monkeypatch.setattr("college_svc.college_dao.MongoCollegeDAO.MongoClient", mongomock.MongoClient)
    config = {"TESTING": True, "SECRET_KEY": "college-test-secret-" * 3, "SESSION_COOKIE_SECURE": False}
    users_app = create_users_app(config)
    users = users_app.test_client()
    mailer = MemoryMailer()
    registration = create_registration_app(config, dao=users_app.extensions["users_dao"], mailer=mailer).test_client()
    data = {"email": "creator@example.test", "password": "a long test password", "account_type": "college_admin"}
    token = registration.get("/auth/csrf").json["csrf_token"]
    user = registration.post("/auth/signup", json=data, headers={"X-CSRFToken": token}).json["user"]

    assert verify_latest(registration, mailer).status_code == 200

    def sign_in():
        token = users.get("/auth/csrf").json["csrf_token"]
        response = users.post("/auth/login", json=data, headers={"X-CSRFToken": token})
        assert response.status_code == 200
        return response.json["csrf_token"]

    auth = UsersAuthClient("http://users.invalid")

    def send_to_users(method, path, headers, data=None):
        # Exercise real session, active-user, and CSRF checks across both apps.
        with users_app.test_client(use_cookies=False) as upstream:
            response = upstream.open(path, method=method, headers=headers, json=data)
            return response.status_code, response.json

    monkeypatch.setattr(auth, "_request", send_to_users)
    dao = MongoCollegeDAO()
    college_app = create_college_app(config, dao=dao, auth_client=auth)
    colleges = college_app.test_client()
    monkeypatch.setattr(users_app.extensions["college_client"], "get_college",
        lambda college_id: (colleges.get(f"/college/{college_id}").json or {}).get("college"))

    def copy_session():
        cookie = users.get_cookie("tutor_session")
        colleges.set_cookie("tutor_session", cookie.value)

    return users_app, users, colleges, dao, sign_in, copy_session, user


def test_anonymous_create_rejected_without_writing(services):
    _, _, colleges, dao, *_ = services
    response = colleges.post("/college", json={"name": "Test College"}, headers={"X-User-ID": "forged"})
    assert response.status_code == 401
    assert response.json == {"error": "Authentication required."}
    assert dao.collection.count_documents({}) == 0


def test_signed_in_user_can_create_college(services):
    _, _, colleges, dao, sign_in, copy_session, _ = services
    token = sign_in()
    copy_session()
    response = colleges.post("/college", json={"name": "Test College", "domain": "college.test"}, headers={"X-CSRFToken": token})
    assert response.status_code == 201
    college = response.json["college"]
    assert college["name"] == "Test College" and college["status"] == "active"
    assert dao.get_college(college["id"]).to_dict() == college


@pytest.mark.parametrize("token", [None, "invalid"])
def test_authenticated_create_requires_csrf(services, token):
    _, _, colleges, dao, sign_in, copy_session, _ = services
    sign_in()
    copy_session()
    response = colleges.post("/college", json={"name": "Test College"}, headers={} if token is None else {"X-CSRFToken": token})
    assert response.status_code == 400
    assert dao.collection.count_documents({}) == 0


def test_forged_cookie_rejected(services):
    _, _, colleges, dao, *_ = services
    colleges.set_cookie("tutor_session", "forged")
    assert colleges.post("/college", json={"name": "Test College"}).status_code == 401
    assert dao.collection.count_documents({}) == 0


def test_expired_session_rejected(services):
    users_app, _, colleges, dao, sign_in, copy_session, _ = services
    token = sign_in()
    copy_session()
    users_app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=-1)
    assert colleges.post("/college", json={"name": "Test College"}, headers={"X-CSRFToken": token}).status_code == 401
    assert dao.collection.count_documents({}) == 0


def test_suspended_user_rejected(services):
    users_app, _, colleges, dao, sign_in, copy_session, user = services
    token = sign_in()
    copy_session()
    users_app.extensions["users_service"].change_status(user["id"], UserStatus.SUSPENDED)
    assert colleges.post("/college", json={"name": "Test College"}, headers={"X-CSRFToken": token}).status_code == 401
    assert dao.collection.count_documents({}) == 0


def test_logged_out_user_rejected(services):
    _, users, colleges, dao, sign_in, _, _ = services
    token = sign_in()
    users.post("/auth/logout", headers={"X-CSRFToken": token})
    cookie = users.get_cookie("tutor_session")
    colleges.set_cookie("tutor_session", cookie.value)
    assert colleges.post("/college", json={"name": "Test College"}).status_code == 401
    assert dao.collection.count_documents({}) == 0


def test_authentication_outage_prevents_writes(services, monkeypatch):
    _, _, colleges, dao, sign_in, copy_session, _ = services
    token = sign_in()
    copy_session()
    def unavailable(*args):
        raise AuthenticationError("Authentication service temporarily unavailable.", 503)
    monkeypatch.setattr(colleges.application.extensions["users_auth"], "_request", unavailable)
    assert colleges.post("/college", json={"name": "Test College"}, headers={"X-CSRFToken": token}).status_code == 503
    assert dao.collection.count_documents({}) == 0


def test_auth_client_handles_network_failure(monkeypatch):
    auth = UsersAuthClient("http://users.invalid")
    def unavailable(*args, **kwargs):
        raise URLError("private connection details")
    monkeypatch.setattr(auth.opener, "open", unavailable)
    with pytest.raises(AuthenticationError, match="Authentication service temporarily unavailable") as error:
        auth.verify("signed-cookie", "test-agent", "token")
    assert error.value.status == 503


def test_college_list_is_public_and_only_includes_active_colleges(services):
    _, _, colleges, dao, *_ = services
    assert colleges.get("/college").json == {"colleges": []}
    for name, status in [("Zulu College", "active"), ("Alpha College", "active"), ("Hidden College", "inactive")]:
        dao.add_college(College(uuid.uuid4(), name, status=status))
    response = colleges.get("/college")
    assert response.status_code == 200
    assert [college["name"] for college in response.json["colleges"]] == ["Alpha College", "Zulu College"]
    assert colleges.post("/college", json={"name": "Unauthorized"}).status_code == 401


@pytest.mark.parametrize("status", list(CollegeStatus))
def test_only_active_colleges_can_be_looked_up_for_signup(services, status):
    _, _, colleges, dao, *_ = services
    college = College(uuid.uuid4(), "Example College", status=status)
    dao.add_college(college)
    response = colleges.get(f"/college/{college.college_id}")
    assert response.status_code == (200 if status == CollegeStatus.ACTIVE else 404)
    assert colleges.get("/college/not-a-uuid").status_code == 404


@pytest.fixture
def college_registration(services, monkeypatch):
    users_app, users, colleges, college_dao, *_ = services
    active = College(uuid.uuid4(), "Active College", domain="example.test")
    inactive = College(uuid.uuid4(), "Inactive College", status=CollegeStatus.INACTIVE)
    college_dao.add_college(active)
    college_dao.add_college(inactive)
    college_client = CollegeClient("http://colleges.test")

    def read_college_api(url, timeout):
        response = colleges.get(urlsplit(url).path)
        if response.status_code != 200:
            raise HTTPError(url, response.status_code, "College API error", {}, None)
        return BytesIO(response.data)

    monkeypatch.setattr(college_client.opener, "open", read_college_api)
    mailer = MemoryMailer()
    registration = create_registration_app(
        {"TESTING": True, "SECRET_KEY": "registration-college-test-" * 2, "SESSION_COOKIE_SECURE": False},
        dao=users_app.extensions["users_dao"], college_client=college_client, mailer=mailer,
    ).test_client()

    def register(college_id):
        token = registration.get("/auth/csrf").json["csrf_token"]
        response = registration.post("/auth/signup", json={
            "email": "member@example.test", "password": "a long test password", "college_id": college_id,
        }, headers={"X-CSRFToken": token})
        if response.status_code == 201:
            assert verify_latest(registration, mailer).status_code == 200
        return response

    return register, active, inactive, users_app.extensions["users_dao"], users, college_client


def test_signup_saves_verified_college_and_login_returns_it(college_registration):
    register, active, _, dao, users, _ = college_registration
    response = register(str(active.college_id))
    assert response.status_code == 201
    user = response.json["user"]
    assert user["college_id"] == str(active.college_id)
    assert dao.collection.find_one({"id": user["id"]})["college"] == str(active.college_id)
    token = users.get("/auth/csrf").json["csrf_token"]
    login = users.post("/auth/login", json={"email": "member@example.test", "password": "a long test password"}, headers={"X-CSRFToken": token})
    assert login.status_code == 200
    assert login.json["user"]["college_id"] == str(active.college_id)


@pytest.mark.parametrize("college_id", ["invalid", [], {}, 0, False, str(uuid.uuid4())])
def test_signup_rejects_invalid_or_unknown_college(college_registration, college_id):
    register, _, _, dao, *_ = college_registration
    count = dao.collection.count_documents({})
    assert register(college_id).status_code == 400
    assert dao.collection.count_documents({}) == count


def test_signup_rejects_inactive_college(college_registration):
    register, _, inactive, dao, *_ = college_registration
    count = dao.collection.count_documents({})
    assert register(str(inactive.college_id)).status_code == 400
    assert dao.collection.count_documents({}) == count


def test_signup_does_not_save_when_college_service_is_unavailable(college_registration, monkeypatch):
    register, active, _, dao, _, college_client = college_registration
    def unavailable(*args, **kwargs):
        raise URLError("private database connection details")
    monkeypatch.setattr(college_client.opener, "open", unavailable)
    count = dao.collection.count_documents({})
    response = register(str(active.college_id))
    assert response.status_code == 503
    assert "private" not in response.json["error"]
    assert dao.collection.count_documents({}) == count


def test_student_cannot_register_college(services):
    users_app, _, colleges, dao, sign_in, copy_session, user = services
    token = sign_in()
    copy_session()
    users_app.extensions["users_dao"].collection.update_one({"id": user["id"]}, {"$set": {"roles": ["student"]}})
    response = colleges.post("/college", json={"name": "Blocked College", "domain": "student.example"}, headers={"X-CSRFToken": token})
    assert response.status_code == 403
    assert dao.collection.count_documents({}) == 0


def test_admin_onboarding_links_college_and_is_retryable(services):
    _, users, colleges, dao, sign_in, copy_session, user = services
    token = sign_in()
    copy_session()
    payload = {"name": "My College", "domain": "students.college.test", "admin_id": "forged"}
    first = colleges.post("/college", json=payload, headers={"X-CSRFToken": token})
    assert first.status_code == 201
    assert first.json["college"]["admin_id"] == user["id"]
    assert users.get("/users/me").json["user"]["college_id"] == first.json["college"]["id"]
    second = colleges.post("/college", json=payload, headers={"X-CSRFToken": token})
    assert second.status_code == 201
    assert dao.collection.count_documents({}) == 1
    assert colleges.post("/college", json={"name": "Another", "domain": "another.test"}, headers={"X-CSRFToken": token}).status_code == 400


@pytest.mark.parametrize("domain", [None, "", "@college.test", "https://college.test", "bad domain", "-bad.test"])
def test_college_registration_requires_valid_student_domain(services, domain):
    _, _, colleges, dao, sign_in, copy_session, _ = services
    token = sign_in()
    copy_session()
    response = colleges.post("/college", json={"name": "Example", "domain": domain}, headers={"X-CSRFToken": token})
    assert response.status_code == 400
    assert dao.collection.count_documents({}) == 0


def test_incomplete_admin_account_linking_can_be_retried(services, monkeypatch):
    _, users, colleges, dao, sign_in, copy_session, _ = services
    token = sign_in()
    copy_session()
    auth = colleges.application.extensions["users_auth"]
    original = auth.assign_college
    def unavailable(*args):
        raise AuthenticationError("Account service unavailable", 503)
    monkeypatch.setattr(auth, "assign_college", unavailable)
    payload = {"name": "Retry College", "domain": "students.retry.test"}
    assert colleges.post("/college", json=payload, headers={"X-CSRFToken": token}).status_code == 503
    assert dao.collection.count_documents({}) == 1
    assert users.get("/users/me").json["user"]["college_id"] is None
    monkeypatch.setattr(auth, "assign_college", original)
    assert colleges.post("/college", json=payload, headers={"X-CSRFToken": token}).status_code == 201
    assert dao.collection.count_documents({}) == 1
    assert users.get("/users/me").json["user"]["college_id"] is not None


def test_admin_cannot_claim_another_administrators_college(services):
    _, users, _, dao, sign_in, _, _ = services
    token = sign_in()
    college = College(uuid.uuid4(), "Someone Else's College", domain="other.test", admin_id=str(uuid.uuid4()))
    dao.add_college(college)
    response = users.post("/users/me/college", json={"college_id": str(college.college_id)}, headers={"X-CSRFToken": token})
    assert response.status_code == 403
    assert users.get("/users/me").json["user"]["college_id"] is None
