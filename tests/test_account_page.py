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
    assert html.count('id="logout-button"') == 1
    assert html.count('id="form-status"') == 1
    assert response.headers["Cache-Control"] == "no-store"


def test_account_requires_login():
    client = create_app({"TESTING": True}).test_client()
    response = client.get("/account")
    assert response.status_code == 302
    assert response.location == "/login"
