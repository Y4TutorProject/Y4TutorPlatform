import json
from io import BytesIO

import pytest

from dashboard_svc.app import create_app


@pytest.fixture
def frontend(monkeypatch):
    app = create_app({"TESTING": True, "USERS_API_URL": "http://users.test"})
    client = app.test_client()
    client.set_cookie("tutor_session", "signed-session")

    def serve(user):
        monkeypatch.setattr(
            app.extensions["users_opener"], "open",
            lambda *args, **kwargs: BytesIO(json.dumps({"user": {
                "email_verified": True, "username": "someone", **user,
            }}).encode()))
    return client, serve


def test_learning_is_the_default_preference_page(frontend):
    client, serve = frontend
    serve({"roles": ["student"], "preferences_completed": True,
           "preferences": {"visual": 9}, "teaching_preferences": {"visual": 3}})
    html = client.get("/preferences").get_data(as_text=True)
    assert 'data-kind="learning"' in html
    assert 'value="9"' in html and 'value="3"' not in html
    assert "Edit your learning preferences" in html


def test_teaching_page_uses_teaching_scores(frontend):
    client, serve = frontend
    serve({"roles": ["tutor"], "teaching_preferences_completed": True,
           "preferences": {"visual": 9}, "teaching_preferences": {"visual": 3}})
    response = client.get("/preferences?type=teaching")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-kind="teaching"' in html and 'data-onboarding="false"' in html
    assert 'value="3"' in html and 'value="9"' not in html
    assert "Teaching with pictures" in html


@pytest.mark.parametrize("completed,expected", [(False, "true"), (True, "false")])
def test_learning_onboarding_follows_completion(frontend, completed, expected):
    client, serve = frontend
    serve({"roles": ["student"], "preferences_completed": completed})
    assert f'data-onboarding="{expected}"' in client.get("/preferences").get_data(as_text=True)


@pytest.mark.parametrize("completed,expected", [(False, "true"), (True, "false")])
def test_teaching_onboarding_follows_completion_for_tutors(frontend, completed, expected):
    client, serve = frontend
    serve({"roles": ["tutor"], "teaching_preferences_completed": completed})
    html = client.get("/preferences?type=teaching").get_data(as_text=True)
    assert f'data-onboarding="{expected}"' in html


def test_teaching_page_does_not_onboard_non_tutors(frontend):
    client, serve = frontend
    serve({"roles": ["student"], "teaching_preferences_completed": False})
    assert 'data-onboarding="false"' in client.get("/preferences?type=teaching").get_data(as_text=True)


def test_unknown_preference_type_is_not_found(frontend):
    client, serve = frontend
    serve({"roles": ["student"]})
    assert client.get("/preferences?type=other").status_code == 404


def test_tutor_without_teaching_preferences_is_sent_to_set_them(frontend):
    client, serve = frontend
    serve({"roles": ["tutor"], "teaching_preferences_completed": False})
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert response.location == "/preferences?type=teaching"


def test_tutor_with_teaching_preferences_reaches_the_dashboard(frontend):
    client, serve = frontend
    serve({"roles": ["tutor"], "teaching_preferences_completed": True})
    assert client.get("/dashboard").status_code == 200


def test_tutor_dashboard_shows_both_preference_sets(frontend):
    client, serve = frontend
    serve({"roles": ["tutor"], "teaching_preferences_completed": True,
           "preferences": {"visual": 9}, "teaching_preferences": {"visual": 3}})
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Your learning preferences" in html and "Your teaching preferences" in html
    assert 'href="/preferences?type=teaching"' in html
    assert "<dd>9 / 10</dd>" in html and "<dd>3 / 10</dd>" in html


@pytest.mark.parametrize("roles,shown", [(["student"], False), (["tutor"], True)])
def test_account_links_teaching_preferences_for_tutors_only(frontend, roles, shown):
    client, serve = frontend
    serve({"roles": roles, "email": "a@example.test"})
    html = client.get("/account").get_data(as_text=True)
    assert ('href="/preferences?type=teaching"' in html) is shown
