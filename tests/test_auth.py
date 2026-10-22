import importlib
from datetime import timedelta

import mongomock
import pytest
from pymongo.errors import ConnectionFailure
from werkzeug.security import check_password_hash

from users_svc import create_app
from users_svc.Objects.UserStatus import UserStatus


PASSWORD = "a long test password"
ACCOUNT = {"username": "student_one", "email": "student@example.com", "password": PASSWORD}


@pytest.fixture
def app(monkeypatch):
    module = importlib.import_module("users_svc.users_dao.MongoUsersDAO")
    monkeypatch.setattr(module, "MongoClient", mongomock.MongoClient)
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost")
    return create_app({
        "TESTING": True, "SECRET_KEY": "test-secret-" * 4,
        "SESSION_COOKIE_SECURE": False,
    })


@pytest.fixture
def client(app):
    return app.test_client()


def post(client, path, data):
    token = client.get("/auth/csrf").json["csrf_token"]
    return client.post(path, json=data, headers={"X-CSRFToken": token})


def signup(client, **overrides):
    return post(client, "/auth/signup", {**ACCOUNT, **overrides})


def login(client, **overrides):
    return post(client, "/auth/login", {
        "email": ACCOUNT["email"], "password": PASSWORD, **overrides,
    })


def test_signup_hashes_password_and_preserves_identity(app, client):
    response = signup(client, roles=["tutor"], status="active")
    assert response.status_code == 201
    user = response.json["user"]
    assert user["roles"] == ["student"]
    assert user["status"] == "active"
    assert "password" not in user and "passhash" not in user
    dao = app.extensions["users_dao"]
    stored = dao.collection.find_one({"id": user["id"]})
    assert stored["passhash"].startswith("scrypt:")
    assert check_password_hash(stored["passhash"], PASSWORD)
    assert "password" not in stored
    assert str(dao.get_user(user["id"]).id) == user["id"]
    assert client.get("/users/me").status_code == 401


def test_same_password_has_distinct_salted_hashes(app, client):
    signup(client)
    signup(client, username="another", email="another@example.com")
    hashes = [doc["passhash"] for doc in app.extensions["users_dao"].collection.find()]
    assert len(hashes) == 2 and hashes[0] != hashes[1]


@pytest.mark.parametrize("overrides", [
    {"username": "STUDENT_ONE", "email": "other@example.com"},
    {"username": "other", "email": " STUDENT@EXAMPLE.COM "},
])
def test_duplicate_accounts_rejected(client, overrides):
    assert signup(client).status_code == 201
    assert signup(client, **overrides).status_code == 409


@pytest.mark.parametrize("field,value", [
    ("username", None), ("username", "x"), ("username", "bad name"),
    ("email", "invalid"), ("email", []), ("password", "short"),
    ("password", "x" * 129), ("password", None),
])
def test_signup_validation(client, field, value):
    assert signup(client, **{field: value}).status_code == 400


def test_login_me_and_logout(client):
    user = signup(client).json["user"]
    response = login(client, email=" STUDENT@EXAMPLE.COM ")
    assert response.status_code == 200
    assert response.json["user"] == user
    assert client.get("/users/me").json["user"] == user
    # Login rotates the CSRF token; use the returned token for logout.
    logout = client.post("/auth/logout", headers={"X-CSRFToken": response.json["csrf_token"]})
    assert logout.status_code == 200
    assert client.get("/users/me").status_code == 401


@pytest.mark.parametrize("overrides", [
    {"password": "wrong password"}, {"email": "unknown@example.com"},
    {"email": "invalid"}, {"password": None},
])
def test_login_failure_is_generic(client, overrides):
    signup(client)
    response = login(client, **overrides)
    assert response.status_code == 401
    assert response.json == {"error": "Invalid email or password."}
    assert client.get("/users/me").status_code == 401


@pytest.mark.parametrize("status", list(UserStatus)[1:])
def test_inactive_users_cannot_login(app, client, status):
    user = signup(client).json["user"]
    app.extensions["users_service"].change_status(user["id"], status)
    assert login(client).status_code == 401


def test_suspension_blocks_existing_session(app, client):
    user = signup(client).json["user"]
    login(client)
    app.extensions["users_service"].change_status(user["id"], UserStatus.SUSPENDED)
    assert client.get("/users/me").status_code == 401


@pytest.mark.parametrize("path", ["/auth/signup", "/auth/login", "/auth/logout"])
def test_csrf_required(client, path):
    assert client.post(path, json=ACCOUNT).status_code == 400
    assert client.post(path, json=ACCOUNT, headers={"X-CSRFToken": "invalid"}).status_code == 400


def test_csrf_token_cannot_be_used_with_another_session(app, client):
    token = client.get("/auth/csrf").json["csrf_token"]
    other = app.test_client()
    assert other.post("/auth/signup", json=ACCOUNT, headers={"X-CSRFToken": token}).status_code == 400


def test_invalid_json(client):
    assert post(client, "/auth/signup", []).status_code == 400
    assert post(client, "/auth/login", []).status_code == 400


def test_secure_cookie_configuration(app):
    app.config["SESSION_COOKIE_SECURE"] = True
    response = app.test_client().get("/auth/csrf", base_url="https://localhost")
    cookie = response.headers["Set-Cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_session_expiry(app, client):
    signup(client)
    login(client)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=-1)
    assert client.get("/users/me").status_code == 401


def test_tampered_cookie_rejected(app, client):
    signup(client)
    login(client)
    cookie = client.get_cookie(app.config["SESSION_COOKIE_NAME"])
    client.set_cookie(cookie.key, cookie.value + "tampered")
    assert client.get("/users/me").status_code == 401


def test_database_error_does_not_leak_details(app, client, monkeypatch):
    def fail(*args, **kwargs):
        raise ConnectionFailure("private connection details")
    monkeypatch.setattr(app.extensions["users_dao"], "get_user_by_email", fail)
    response = login(client)
    assert response.status_code == 503
    assert response.json == {"error": "User service temporarily unavailable."}


def test_secret_required(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()
