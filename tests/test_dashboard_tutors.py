import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from dashboard_svc.app import create_app


@pytest.fixture
def frontend(monkeypatch):
    app = create_app({
        "TESTING": True,
        "USERS_API_URL": "http://users.test",
        "LMS_API_URL": "http://lms.test",
    })
    client = app.test_client()
    client.set_cookie("tutor_session", "signed-session")
    return app, client


def json_response(data):
    return BytesIO(json.dumps(data).encode())


def test_student_dashboard_renders_sidebar_and_tutor_area(frontend, monkeypatch):
    app, client = frontend

    def upstream(request, timeout):
        if request.full_url.endswith("/users/me"):
            return json_response({"user": {"email_verified": True, "roles": ["student"]}})
        return json_response({
            "student": {"username": "student"},
            "modules": [{"id": "module-1", "display_name": "Web & SQL"}],
        })

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    response = client.get("/dashboard")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-module="module-1"' in html
    assert "Web &amp; SQL" in html
    assert 'id="tutor-results"' in html
    assert "student_dashboard.css" in html


@pytest.mark.parametrize("tutor_ids", [[], ["tutor-1", "tutor-2"]])
def test_get_tutors_returns_profiles(frontend, monkeypatch, tutor_ids):
    app, client = frontend
    requested = []

    def upstream(request, timeout):
        requested.append(request.full_url)
        assert request.get_header("Cookie") == "tutor_session=signed-session"
        assert request.get_header("User-agent") == "test-browser"
        assert timeout == 5
        if request.full_url == "http://users.test/users/me":
            return json_response({"user": {"email_verified": True}})
        if request.full_url == "http://lms.test/students/me/modules/module-1/tutors":
            return json_response({"tutor_ids": tutor_ids})
        tutor_id = request.full_url.removeprefix("http://users.test/users/")
        assert tutor_id in tutor_ids
        return json_response({"user": {
            "id": tutor_id, "username": tutor_id, "preferences": {"visual": 5},
        }})

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    response = client.get("/get_tutors?module_id=module-1", headers={"User-Agent": "test-browser"})

    assert response.status_code == 200
    assert response.json == {"tutors": [
        {"id": tutor_id, "username": tutor_id, "preferences": {"visual": 5}}
        for tutor_id in tutor_ids
    ]}
    assert requested == [
        "http://users.test/users/me",
        "http://lms.test/students/me/modules/module-1/tutors",
        *[f"http://users.test/users/{tutor_id}" for tutor_id in tutor_ids],
    ]


@pytest.mark.parametrize("payload", [{}, {"tutor_ids": "tutor-1"}, {"tutor_ids": [1]}])
def test_get_tutors_rejects_malformed_lms_response(frontend, monkeypatch, payload):
    app, client = frontend

    def upstream(request, timeout):
        if request.full_url.endswith("/users/me"):
            return json_response({"user": {"email_verified": True}})
        return json_response(payload)

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    assert client.get("/get_tutors?module_id=module-1").status_code == 502


@pytest.mark.parametrize("failure", [
    HTTPError("http://users.test", 404, "Not found", {}, None),
    URLError("unavailable"),
])
def test_get_tutors_reports_profile_lookup_failures(frontend, monkeypatch, failure):
    app, client = frontend

    def upstream(request, timeout):
        if request.full_url.endswith("/users/me"):
            return json_response({"user": {"email_verified": True}})
        if request.full_url.startswith("http://lms.test/"):
            return json_response({"tutor_ids": ["tutor-1"]})
        raise failure

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    assert client.get("/get_tutors?module_id=module-1").status_code == 502


def test_get_tutors_rejects_malformed_profile(frontend, monkeypatch):
    app, client = frontend

    def upstream(request, timeout):
        if request.full_url.endswith("/users/me"):
            return json_response({"user": {"email_verified": True}})
        if request.full_url.startswith("http://lms.test/"):
            return json_response({"tutor_ids": ["tutor-1"]})
        return json_response({"user": None})

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    assert client.get("/get_tutors?module_id=module-1").status_code == 502
