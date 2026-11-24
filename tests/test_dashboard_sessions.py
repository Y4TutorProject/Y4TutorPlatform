import json
from io import BytesIO

import pytest
import requests

from dashboard_svc.app import create_app

STUDENT = {"id": "student-1", "username": "student", "roles": ["student"], "email_verified": True}


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


@pytest.fixture
def frontend(monkeypatch):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-key",
        "WTF_CSRF_ENABLED": False,
        "USERS_API_URL": "http://users.test",
        "SESSIONS_API_URL": "http://sessions.test",
        "DASHBOARD_SHARED_SECRET": "secret",
    })
    monkeypatch.setattr(app.extensions["users_opener"], "open",
                        lambda *args, **kwargs: BytesIO(json.dumps({"user": STUDENT}).encode()))
    client = app.test_client()
    client.set_cookie("tutor_session", "signed-session")
    return client


class RecordedCalls(list):
    """Requests sent to the sessions service, answered from `replies`."""

    def __init__(self):
        super().__init__()
        self.replies = {}

    def __call__(self, method, path, payload=None):
        self.append((method, path, payload))
        return self.replies.get((method, path), FakeResponse(200, {"id": "s1", "status": "booked"}))


@pytest.fixture
def calls(monkeypatch):
    recorded = RecordedCalls()
    monkeypatch.setattr("routes.sessions.sessions_request", recorded)
    return recorded


def test_create_session_books_signed_in_student_with_tutor(frontend, calls):
    calls.replies[("POST", "/sessions")] = FakeResponse(201, {"id": "s1", "status": "booked"})

    response = frontend.post("/sessions", json={"tutor_id": "tutor-1", "module_id": "module-1"})

    assert response.status_code == 201
    assert response.json == {"id": "s1", "status": "booked"}
    method, path, payload = calls[0]
    assert (method, path) == ("POST", "/sessions")
    assert payload["studentId"] == "student-1"
    assert payload["tutorId"] == "tutor-1"
    assert payload["moduleId"] == "module-1"
    assert payload["price"] == 2500


def test_create_session_requires_tutor_and_module(frontend, calls):
    assert frontend.post("/sessions", json={"tutor_id": "tutor-1"}).status_code == 400
    assert calls == []


@pytest.mark.parametrize("action", ["complete", "cancel"])
def test_participant_can_finish_session(frontend, calls, action):
    calls.replies[("GET", "/sessions/s1")] = FakeResponse(
        200, {"id": "s1", "tutorId": "tutor-1", "studentId": "student-1", "status": "booked"})
    calls.replies[("POST", f"/sessions/s1/{action}")] = FakeResponse(200, {"id": "s1", "status": "done"})

    response = frontend.post(f"/sessions/s1/{action}")

    assert response.status_code == 200
    assert calls[-1][:2] == ("POST", f"/sessions/s1/{action}")


def test_non_participant_cannot_finish_session(frontend, calls):
    calls.replies[("GET", "/sessions/s1")] = FakeResponse(
        200, {"id": "s1", "tutorId": "tutor-1", "studentId": "someone-else", "status": "booked"})

    assert frontend.post("/sessions/s1/complete").status_code == 403
    assert len(calls) == 1


def test_sessions_service_errors_are_passed_on(frontend, calls):
    calls.replies[("GET", "/sessions/s1")] = FakeResponse(
        200, {"id": "s1", "tutorId": "tutor-1", "studentId": "student-1", "status": "completed"})
    calls.replies[("POST", "/sessions/s1/cancel")] = FakeResponse(409, {"error": "Session is already completed"})

    response = frontend.post("/sessions/s1/cancel")
    assert response.status_code == 409
    assert response.json["error"] == "Session is already completed"


def test_unknown_action_is_404(frontend, calls):
    assert frontend.post("/sessions/s1/delete").status_code == 404
    assert calls == []


def test_sessions_service_down_is_502(frontend, monkeypatch):
    def down(*args, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr("routes.sessions.sessions_request", down)
    response = frontend.post("/sessions", json={"tutor_id": "tutor-1", "module_id": "module-1"})
    assert response.status_code == 502


def test_student_dashboard_exposes_csrf_token_for_session_buttons(frontend, monkeypatch):
    app = frontend.application

    def upstream(request, timeout):
        if request.full_url.endswith("/users/me"):
            return BytesIO(json.dumps({"user": STUDENT}).encode())
        return BytesIO(json.dumps({"student": {"username": "student"}, "modules": []}).encode())

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    html = frontend.get("/dashboard").get_data(as_text=True)
    assert 'id="tutor-results"' in html
    assert 'data-csrf="' in html
