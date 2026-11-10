import importlib
from datetime import timedelta

import mongomock
import pytest
from pymongo.errors import ConnectionFailure
from werkzeug.security import check_password_hash

from registration_svc import create_app as create_registration_app
from users_svc import create_app
from users_svc.Objects.UserStatus import UserStatus
from support import MemoryMailer, ExampleColleges, COLLEGE_ID, verify_latest


PASSWORD = "a long test password"
ACCOUNT = {"username": "student_one", "email": "student@example.com", "password": PASSWORD, "college_id": COLLEGE_ID}


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


@pytest.fixture
def registration_app(app):
    mailer = MemoryMailer()
    registration = create_registration_app({
        "TESTING": True, "SECRET_KEY": "registration-test-secret-" * 2,
        "SESSION_COOKIE_SECURE": False,
    }, dao=app.extensions["users_dao"], college_client=ExampleColleges(), mailer=mailer)
    registration.extensions["test_mailer"] = mailer
    return registration


@pytest.fixture
def registration_client(registration_app):
    return registration_app.test_client()


@pytest.fixture
def signup(registration_client, registration_app):
    def register(**overrides):
        response = post(registration_client, "/auth/signup", {**ACCOUNT, **overrides})
        if response.status_code == 201:
            assert verify_latest(registration_client, registration_app.extensions["test_mailer"]).status_code == 200
        return response
    return register


def login(client, **overrides):
    return post(client, "/auth/login", {
        "email": ACCOUNT["email"], "password": PASSWORD, **overrides,
    })


def test_signup_hashes_password_and_preserves_identity(app, client, signup):
    response = signup(roles=["tutor"], status="active")
    assert response.status_code == 201
    user = response.json["user"]
    assert user["roles"] == ["student"]
    assert user["username_completed"] is True
    assert user["status"] == "pending_verification"
    assert "password" not in user and "passhash" not in user
    dao = app.extensions["users_dao"]
    stored = dao.collection.find_one({"id": user["id"]})
    assert stored["passhash"].startswith("scrypt:")
    assert check_password_hash(stored["passhash"], PASSWORD)
    assert "password" not in stored
    assert str(dao.get_user(user["id"]).id) == user["id"]
    assert client.get("/users/me").status_code == 401


def test_same_password_has_distinct_salted_hashes(app, client, signup):
    signup()
    signup(username="another", email="another@example.com")
    hashes = [doc["passhash"] for doc in app.extensions["users_dao"].collection.find()]
    assert len(hashes) == 2 and hashes[0] != hashes[1]


def test_signup_without_username_generates_one(registration_client, registration_app, client):
    data = {"email": ACCOUNT["email"], "password": PASSWORD, "college_id": COLLEGE_ID}
    response = post(registration_client, "/auth/signup", data)
    assert response.status_code == 201
    user = response.json["user"]
    assert user["username"].startswith("user_")
    assert user["username_completed"] is False
    assert user["roles"] == ["student"]
    assert user["college_id"] == COLLEGE_ID
    assert login(client).status_code == 401
    assert verify_latest(registration_client, registration_app.extensions["test_mailer"]).status_code == 200
    assert login(client).status_code == 200


@pytest.mark.parametrize("account_type", ["tutor", "admin", "", None, [], {}])
def test_signup_cannot_choose_account_type(signup, account_type):
    response = signup(account_type=account_type)
    assert response.status_code == 400


@pytest.mark.parametrize("overrides", [
    {"username": "STUDENT_ONE", "email": "other@example.com"},
    {"username": "other", "email": " STUDENT@EXAMPLE.COM "},
])
def test_duplicate_accounts_rejected(client, overrides, signup):
    assert signup().status_code == 201
    assert signup(**overrides).status_code == 409


@pytest.mark.parametrize("field,value", [
    ("username", None), ("username", "x"), ("username", "bad name"),
    ("email", "invalid"), ("email", []), ("password", "short"),
    ("password", "x" * 129), ("password", None),
])
def test_signup_validation(client, field, value, signup):
    assert signup(**{field: value}).status_code == 400


def test_login_me_and_logout(client, signup):
    user = signup().json["user"]
    user.update(status="active", email_verified=True)
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
def test_login_failure_is_generic(client, overrides, signup):
    signup()
    response = login(client, **overrides)
    assert response.status_code == 401
    assert response.json == {"error": "Invalid email or password."}
    assert client.get("/users/me").status_code == 401


@pytest.mark.parametrize("status", list(UserStatus)[1:])
def test_inactive_users_cannot_login(app, client, status, signup):
    user = signup().json["user"]
    app.extensions["users_service"].change_status(user["id"], status)
    assert login(client).status_code == 401


def test_suspension_blocks_existing_session(app, client, signup):
    user = signup().json["user"]
    login(client)
    app.extensions["users_service"].change_status(user["id"], UserStatus.SUSPENDED)
    assert client.get("/users/me").status_code == 401


@pytest.mark.parametrize("path", ["/auth/login", "/auth/logout"])
def test_csrf_required(client, path):
    assert client.post(path, json=ACCOUNT).status_code == 400
    assert client.post(path, json=ACCOUNT, headers={"X-CSRFToken": "invalid"}).status_code == 400


def test_csrf_token_cannot_be_used_with_another_session(registration_app, registration_client):
    token = registration_client.get("/auth/csrf").json["csrf_token"]
    other = registration_app.test_client()
    assert other.post("/auth/signup", json=ACCOUNT, headers={"X-CSRFToken": token}).status_code == 400


def test_invalid_json(client, registration_client):
    assert post(registration_client, "/auth/signup", []).status_code == 400
    assert post(client, "/auth/login", []).status_code == 400


def test_secure_cookie_configuration(app):
    app.config["SESSION_COOKIE_SECURE"] = True
    response = app.test_client().get("/auth/csrf", base_url="https://localhost")
    cookie = response.headers["Set-Cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_preference_onboarding_and_later_edits(app, client, signup):
    user = signup(preferences_completed=True).json["user"]
    assert user["preferences_completed"] is False
    assert login(client).json["user"]["preferences_completed"] is False
    scores = {"visual": 10, "auditory": 0, "reading_writing": 4, "kinesthetic": 8}
    response = post(client, "/users/me/preferences", {"preferences": scores})
    assert response.status_code == 200
    assert response.json["user"]["preferences_completed"] is True
    assert response.json["user"]["preferences"] == scores
    scores["visual"] = 2
    assert post(client, "/users/me/preferences", {"preferences": scores}).status_code == 200
    assert client.get("/users/me").json["user"]["preferences"] == scores
    assert app.extensions["users_dao"].get_user(user["id"]).preferences_completed is True


@pytest.mark.parametrize("preferences", [None, {}, {"visual": 5}, {
    "visual": 11, "auditory": 0, "reading_writing": 4, "kinesthetic": 8,
}])
def test_invalid_onboarding_does_not_complete_or_save(client, signup, preferences):
    signup()
    login(client)
    response = post(client, "/users/me/preferences", {"preferences": preferences})
    assert response.status_code == 400
    user = client.get("/users/me").json["user"]
    assert user["preferences_completed"] is False
    assert all(score == 0 for score in user["preferences"].values())


def test_preferences_require_session_and_csrf(client, signup):
    assert post(client, "/users/me/preferences", {}).status_code == 401
    signup()
    login(client)
    assert client.post("/users/me/preferences", json={}).status_code == 400


def test_preference_update_only_changes_current_account(app, client, signup):
    signup()
    other = signup(username="other_student", email="other@example.com").json["user"]
    login(client)
    scores = {pref: 7 for pref in ("visual", "auditory", "reading_writing", "kinesthetic")}
    response = post(client, "/users/me/preferences", {"preferences": scores, "user_id": other["id"]})
    assert response.status_code == 200
    unchanged = app.extensions["users_dao"].get_user(other["id"])
    assert unchanged.preferences_completed is False
    assert all(score == 0 for score in unchanged.preferences.values())


def test_session_expiry(app, client, signup):
    signup()
    login(client)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=-1)
    assert client.get("/users/me").status_code == 401


def test_tampered_cookie_rejected(app, client, signup):
    signup()
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


def test_signup_only_available_in_registration(client, registration_client):
    assert post(client, "/auth/signup", ACCOUNT).status_code == 404
    assert post(registration_client, "/auth/signup", ACCOUNT).status_code == 201


def test_registration_csrf_required(registration_client):
    assert registration_client.post("/auth/signup", json=ACCOUNT).status_code == 400
    assert registration_client.post(
        "/auth/signup", json=ACCOUNT, headers={"X-CSRFToken": "invalid"},
    ).status_code == 400


def test_registration_database_error(registration_app, signup, monkeypatch):
    def fail(*args, **kwargs):
        raise ConnectionFailure("private connection details")
    monkeypatch.setattr(registration_app.extensions["users_dao"], "add_user", fail)
    response = signup()
    assert response.status_code == 503
    assert response.json == {"error": "Registration service temporarily unavailable."}


def test_registration_secret_required(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_registration_app()


def test_student_signup_requires_college(registration_client):
    for value in [None, ""]:
        response = post(registration_client, "/auth/signup", {**ACCOUNT, "college_id": value})
        assert response.status_code == 400


def test_student_email_must_match_college_domain(registration_client):
    response = post(registration_client, "/auth/signup", {**ACCOUNT, "email": "student@unrelated.test"})
    assert response.status_code == 400


def test_pending_email_cannot_login_and_is_not_returned_as_token(app, client, registration_app, registration_client):
    response = post(registration_client, "/auth/signup", ACCOUNT)
    assert response.status_code == 201
    assert response.json["user"]["email_verified"] is False
    assert "token" not in response.json
    assert login(client).status_code == 401
    record = app.extensions["users_dao"].collection.find_one({"email": ACCOUNT["email"]})
    assert len(record["verification_hash"]) == 64
    assert verify_latest(registration_client, registration_app.extensions["test_mailer"]).status_code == 200
    assert login(client).status_code == 200


def test_email_verification_token_is_single_use(registration_app, registration_client):
    post(registration_client, "/auth/signup", ACCOUNT)
    mailer = registration_app.extensions["test_mailer"]
    assert verify_latest(registration_client, mailer).status_code == 200
    assert verify_latest(registration_client, mailer).status_code == 400


def test_email_verification_token_expires(registration_app, registration_client, client):
    post(registration_client, "/auth/signup", ACCOUNT)
    registration_app.extensions["email_verification"].max_age = -1
    assert verify_latest(registration_client, registration_app.extensions["test_mailer"]).status_code == 400
    assert login(client).status_code == 401


def test_invalid_verification_token_does_not_activate_account(registration_client, client):
    post(registration_client, "/auth/signup", ACCOUNT)
    assert post(registration_client, "/auth/verify-email", {"token": "forged"}).status_code == 400
    assert login(client).status_code == 401


def test_college_admin_creates_account_without_selecting_college(registration_client, registration_app):
    response = post(registration_client, "/auth/signup", {
        "email": "administrator@college.test", "password": PASSWORD,
        "account_type": "college_admin", "roles": ["super_admin"], "email_verified": True,
    })
    assert response.status_code == 201
    assert response.json["user"]["roles"] == ["college_admin"]
    assert response.json["user"]["college_id"] is None
    assert response.json["user"]["email_verified"] is False
    assert verify_latest(registration_client, registration_app.extensions["test_mailer"]).status_code == 200


def test_resend_verification_rotates_nonce_and_throttles(app, registration_app, registration_client):
    post(registration_client, "/auth/signup", ACCOUNT)
    mailer = registration_app.extensions["test_mailer"]
    original_link = mailer.messages[0]
    assert post(registration_client, "/auth/resend-verification", {"email": ACCOUNT["email"]}).status_code == 200
    assert len(mailer.messages) == 1
    app.extensions["users_dao"].collection.update_one({"email": ACCOUNT["email"]}, {"$set": {"verification_sent_at": 0}})
    post(registration_client, "/auth/resend-verification", {"email": ACCOUNT["email"]})
    assert len(mailer.messages) == 2
    newest = mailer.messages[-1]
    mailer.messages.append(original_link)
    assert verify_latest(registration_client, mailer).status_code == 400
    mailer.messages.append(newest)
    assert verify_latest(registration_client, mailer).status_code == 200


def test_smtp_failure_leaves_recoverable_pending_account(registration_app, registration_client, app, monkeypatch):
    from registration_svc.verification import MailDeliveryError
    mailer = registration_app.extensions["test_mailer"]
    original = mailer.send_verification
    def fail(*args):
        raise MailDeliveryError()
    monkeypatch.setattr(mailer, "send_verification", fail)
    assert post(registration_client, "/auth/signup", ACCOUNT).status_code == 503
    record = app.extensions["users_dao"].collection.find_one({"email": ACCOUNT["email"]})
    assert record["status"] == "pending_verification"
    monkeypatch.setattr(mailer, "send_verification", original)
    post(registration_client, "/auth/resend-verification", {"email": ACCOUNT["email"]})
    assert verify_latest(registration_client, mailer).status_code == 200


def test_signed_in_account_with_old_preferences_remains_accessible(app, client, signup):
    user = signup().json["user"]
    assert login(client).status_code == 200
    app.extensions["users_dao"].collection.update_one(
        {"id": user["id"]}, {"$set": {"preferences": {
            "visual": 8, "auditory": 3, "verbal": 7, "kinesthetic": 6, "logical": 9,
        }}},
    )
    response = client.get("/users/me")
    assert response.status_code == 200
    assert response.json["user"]["preferences"] == {
        "visual": 8, "auditory": 3, "reading_writing": 7, "kinesthetic": 6,
    }


@pytest.fixture
def deferred_username(app, client, signup):
    user = signup().json['user']
    app.extensions['users_dao'].collection.update_one({'id': user['id']}, {'$set': {'username_completed': False}})
    assert login(client).json['user']['username_completed'] is False
    return user


def test_first_login_username_is_normalized_and_persisted(app, client, deferred_username):
    response = post(client, '/users/me/username', {'username': ' My_Username ', 'user_id': 'another-user'})
    assert response.status_code == 200
    assert response.json['user']['username'] == 'my_username'
    assert response.json['user']['username_completed'] is True
    stored = app.extensions['users_dao'].get_user(deferred_username['id'])
    assert stored.username == 'my_username' and stored.username_completed is True
    assert post(client, '/users/me/username', {'username': 'my_username'}).status_code == 200
    assert post(client, '/users/me/username', {'username': 'another_name'}).status_code == 409
    assert client.get('/users/me').json['user']['username'] == 'my_username'


@pytest.mark.parametrize('username', [None, '', 'ab', 'bad name', 'a' * 31, 12, {'$ne': None}])
def test_first_login_rejects_invalid_username(app, client, deferred_username, username):
    response = post(client, '/users/me/username', {'username': username})
    assert response.status_code == 400
    assert app.extensions['users_dao'].get_user(deferred_username['id']).username_completed is False


def test_first_login_duplicate_username_keeps_onboarding_pending(app, client, signup, deferred_username):
    signup(username='taken_name', email='other@example.com')
    response = post(client, '/users/me/username', {'username': 'TAKEN_NAME'})
    assert response.status_code == 409
    assert app.extensions['users_dao'].get_user(deferred_username['id']).username_completed is False


def test_username_selection_requires_session_and_csrf(app, client, signup):
    assert post(client, '/users/me/username', {'username': 'new_name'}).status_code == 401
    signup()
    login(client)
    assert client.post('/users/me/username', json={'username': 'new_name'}).status_code == 400


@pytest.mark.parametrize('username,completed', [('user_' + 'a' * 20, False), ('chosen_name', True)])
def test_legacy_usernames_only_prompt_for_generated_names(app, client, signup, username, completed):
    user = signup(username=username).json['user']
    app.extensions['users_dao'].collection.update_one({'id': user['id']}, {'$unset': {'username_completed': ''}})
    assert login(client).json['user']['username_completed'] is completed


def test_view_other_users_profile_in_same_college(app, client, signup):
    signup()
    tutor = signup(username="tutor_one", email="tutor@example.com").json["user"]
    assert client.get(f"/users/{tutor['id']}").status_code == 401
    assert login(client).status_code == 200
    response = client.get(f"/users/{tutor['id']}")
    assert response.status_code == 200
    profile = response.json["user"]
    assert profile["id"] == tutor["id"] and profile["username"] == "tutor_one"
    assert set(profile) == {
        "id", "username", "college_id", "roles", "preferences",
        "teaching_preferences", "teaching_preferences_completed",
    }
    assert profile["teaching_preferences_completed"] is False


def test_view_user_profile_hides_unknown_inactive_and_other_college(app, client, signup):
    signup()
    other_college = signup(username="elsewhere", email="elsewhere@example.com").json["user"]
    inactive = signup(username="inactive", email="inactive@example.com").json["user"]
    dao = app.extensions["users_dao"]
    dao.collection.update_one({"id": other_college["id"]}, {"$set": {"college": "00000000-0000-4000-8000-000000000001"}})
    dao.collection.update_one({"id": inactive["id"]}, {"$set": {"status": "suspended"}})
    assert login(client).status_code == 200
    for target in (other_college["id"], inactive["id"], "not-a-uuid", "00000000-0000-4000-8000-000000000002"):
        assert client.get(f"/users/{target}").status_code == 404
