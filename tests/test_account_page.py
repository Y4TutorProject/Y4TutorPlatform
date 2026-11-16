import json
from io import BytesIO

import pytest

from dashboard_svc.app import create_app


@pytest.mark.parametrize("completed", [False, True])
def test_account_renders_identity_and_preferences(monkeypatch, completed):
    app = create_app({"TESTING": True, "USERS_API_URL": "http://users.test"})
    client = app.test_client()
    client.set_cookie("tutor_session", "signed-session")
    user = {
        "username": "student<001>", "email": "student@example.test",
        "roles": ["student"], "email_verified": True,
        "preferences_completed": completed,
    }
    monkeypatch.setattr(app.extensions["users_opener"], "open",
                        lambda *args, **kwargs: BytesIO(json.dumps({"user": user}).encode()))

    response = client.get("/account")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'id="account-username">student&lt;001&gt;</dd>' in html
    assert 'id="account-email">student@example.test</dd>' in html
    assert ('Edit' if completed else 'Set up') + ' your learning preferences</a>' in html
    assert 'href="/preferences"' in html
    assert "teaching preferences" not in html
    assert html.count('id="logout-button"') == 1
    assert html.count('id="account-logout-button"') == 1
    assert html.count('id="form-status"') == 1
    assert response.headers["Cache-Control"] == "no-store"


def test_account_requires_login():
    client = create_app({"TESTING": True}).test_client()
    response = client.get("/account")
    assert response.status_code == 302
    assert response.location == "/login"


def test_tutor_account_shows_only_learning_preferences(monkeypatch):
    app = create_app({"TESTING": True, "USERS_API_URL": "http://users.test"})
    client = app.test_client()
    client.set_cookie("tutor_session", "signed-session")
    user = {
        "username": "tutor", "email": "tutor@example.test",
        "roles": ["tutor"], "email_verified": True,
        "preferences_completed": True, "preferences": {"visual": 2},
        "teaching_preferences_completed": True, "teaching_preferences": {"visual": 8},
    }
    monkeypatch.setattr(app.extensions["users_opener"], "open",
                        lambda *args, **kwargs: BytesIO(json.dumps({"user": user}).encode()))

    response = client.get("/account")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert '<h2 id="preferences-title">Learning preferences</h2>' in html
    assert "teaching preferences" not in html
    assert '<span>2<span class="profile-score-max"> / 10</span></span>' in html
    assert "Edit your learning preferences" in html


def test_account_learning_preferences_remain_consistent_between_roles(monkeypatch):
    app = create_app({
        "TESTING": True, "SECRET_KEY": "test-key", "WTF_CSRF_ENABLED": False,
        "USERS_API_URL": "http://users.test",
    })
    client = app.test_client()
    client.set_cookie("tutor_session", "signed-session")
    user = {
        "username": "both", "email": "both@example.test",
        "roles": ["student", "tutor"], "email_verified": True,
        "preferences_completed": True, "preferences": {"visual": 2},
        "teaching_preferences_completed": True, "teaching_preferences": {"visual": 8},
    }
    monkeypatch.setattr(app.extensions["users_opener"], "open",
                        lambda *args, **kwargs: BytesIO(json.dumps({"user": user}).encode()))

    for role in ["tutor", "student", "tutor"]:
        kind, score = "learning", 2
        assert client.post(f"/dashboard/switch/{role}").status_code == 302
        response = client.get("/account")
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert f'<h2 id="preferences-title">{kind.capitalize()} preferences</h2>' in html
        url = "/preferences"
        assert "teaching preferences" not in html
        assert f'href="{url}">Edit your {kind} preferences</a>' in html
        assert f'<span>{score}<span class="profile-score-max"> / 10</span></span>' in html
