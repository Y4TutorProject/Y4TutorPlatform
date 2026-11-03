"""The server must omit privileged settings from unauthorized responses."""
import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from users_frontend.app import create_app


@pytest.fixture
def frontend(monkeypatch):
    app = create_app({"TESTING": True, "USERS_API_URL": "http://users.test"})
    client = app.test_client()
    client.set_cookie("tutor_session", "signed-session")
    return app, client


def serve_user(monkeypatch, app, roles, college_id="college-id"):
    def authenticate(request, timeout):
        if request.full_url.endswith("/students/me"):
            raise HTTPError(request.full_url, 404, "No import", {}, None)
        assert request.full_url == "http://users.test/users/me"
        assert request.get_header("Cookie") == "tutor_session=signed-session"
        assert request.get_header("User-agent") == "original-browser"
        assert timeout == 5
        return BytesIO(json.dumps({"user": {
            "email_verified": True, "roles": roles, "college_id": college_id,
        }}).encode())
    monkeypatch.setattr(app.extensions["users_opener"], "open", authenticate)


@pytest.mark.parametrize("roles,college_id,allowed", [
    (["student"], "college-id", False),
    (["tutor"], "college-id", False),
    ([], "college-id", False),
    (["college_admin"], None, False),
    (["college_admin"], "college-id", True),
])
def test_settings_html_is_rendered_only_for_assigned_admin(frontend, monkeypatch, roles, college_id, allowed):
    app, client = frontend
    serve_user(monkeypatch, app, roles, college_id)
    response = client.get("/account", headers={"User-Agent": "original-browser", "X-Role": "college_admin"})
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for marker in ['id="lms-settings"', 'id="lms-form"', 'id="lms-key"', 'id="lms-sync-button"']:
        assert (marker in html) is allowed
    if allowed:
        assert 'data-college-id="college-id"' in html
        assert 'class="mt-4" hidden' not in html
    assert response.headers["Cache-Control"] == "no-store"


def test_anonymous_account_redirects_without_contacting_users(frontend, monkeypatch):
    app, client = frontend
    client.delete_cookie("tutor_session")
    def unexpected(*args, **kwargs):
        pytest.fail("Anonymous requests must not contact the users API")
    monkeypatch.setattr(app.extensions["users_opener"], "open", unexpected)
    response = client.get("/account")
    assert response.status_code == 302
    assert response.location == "/login"
    assert b'lms-settings' not in response.data


@pytest.mark.parametrize("failure,status", [
    (HTTPError("http://users.test", 401, "Invalid session", {}, None), 302),
    (HTTPError("http://users.test", 500, "Unavailable", {}, None), 503),
    (HTTPError("http://users.test", 302, "Redirect", {}, None), 503),
    (URLError("Unavailable"), 503),
    (ValueError("Invalid JSON"), 503),
])
def test_authentication_failure_never_returns_settings(frontend, monkeypatch, failure, status):
    app, client = frontend
    def unavailable(*args, **kwargs):
        raise failure
    monkeypatch.setattr(app.extensions["users_opener"], "open", unavailable)
    response = client.get("/account")
    assert response.status_code == status
    assert b'lms-settings' not in response.data
    assert response.headers["Cache-Control"] == "no-store"


def test_upstream_redirects_cannot_forward_session_cookie(frontend):
    app, _ = frontend
    handler = next(handler for handler in app.extensions["users_opener"].handlers
                   if hasattr(handler, "redirect_request"))
    assert handler.redirect_request(None, None, 302, "Redirect", {}, "https://other.test") is None


def test_student_moodle_information_is_rendered_and_escaped(frontend, monkeypatch):
    app, client = frontend
    def upstream(request, timeout):
        if request.full_url.endswith('/users/me'):
            data = {'user': {'roles': ['student'], 'college_id': 'college-id', 'email_verified': True,
                             'username': 'student', 'email': 'student@example.test'}}
        else:
            assert request.full_url.endswith('/students/me')
            assert request.get_header('Cookie') == 'tutor_session=signed-session'
            data = {'student': {'first_name': '<script>alert(1)</script>', 'last_name': 'Example',
                                'username': 'moodle-student', 'email': 'student@example.test'},
                    'college': {'name': 'Example College'}, 'imported_at': '2026-11-03T12:00:00Z',
                    'mapping': 'academic', 'enrolments_available': True, 'courses': [{'id': '1', 'source_id': '1', 'name': 'Computing'}],
                    'modules': [{'course_id': '1', 'name': 'Databases', 'code': 'DB4'}]}
        return BytesIO(json.dumps(data).encode())
    monkeypatch.setattr(app.extensions['users_opener'], 'open', upstream)
    response = client.get('/account')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'moodle-student' in html and 'Databases' in html and 'Computing' in html
    assert '&lt;script&gt;' in html and '<script>alert' not in html
    assert 'Your programmes and modules' in html
    assert 'id="lms-settings"' not in html
    assert 'id="account-details" hidden' not in html
