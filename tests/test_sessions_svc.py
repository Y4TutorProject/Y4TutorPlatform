import hashlib
import hmac
import json

import mongomock
import pytest
import requests

from sessions_svc import events_client
from sessions_svc.app import create_app
from sessions_svc.sessions_dao.MongoSessionsDAO import MongoSessionsDAO

SECRET = "dashboard-secret"

NEW_SESSION = {
    "tutorId": "tutor-1",
    "studentId": "student-1",
    "moduleId": "module-1",
    "startTime": "2026-12-01T10:00:00+00:00",
    "endTime": "2026-12-01T11:00:00+00:00",
    "price": 2500,
}


@pytest.fixture
def dao(monkeypatch):
    monkeypatch.setattr(
        "sessions_svc.sessions_dao.MongoSessionsDAO.MongoClient", mongomock.MongoClient,
    )
    return MongoSessionsDAO(uri="mongodb://localhost")


@pytest.fixture
def sent(monkeypatch):
    """Records (url, body) for every event POST instead of making real requests."""
    calls = []

    class Ok:
        def raise_for_status(self):
            pass

    def fake_post(url, data, headers, timeout):
        calls.append((url, json.loads(data), headers))
        return Ok()

    monkeypatch.setattr(events_client.requests, "post", fake_post)
    return calls


def make_client(dao, **config):
    return create_app({"TESTING": True, "DASHBOARD_SHARED_SECRET": SECRET, **config}, dao=dao).test_client()


@pytest.fixture
def client(dao):
    return make_client(dao)


def signed_post(client, path, payload=None):
    body = json.dumps(payload or {}).encode()
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post(path, data=body, headers={
        "Content-Type": "application/json", "X-Dashboard-Signature": signature,
    })


def signed_get(client, path):
    signature = hmac.new(SECRET.encode(), b"", hashlib.sha256).hexdigest()
    return client.get(path, headers={"X-Dashboard-Signature": signature})


def book(client):
    response = signed_post(client, "/sessions", NEW_SESSION)
    assert response.status_code == 201
    return response.json


# Signature check

def test_health_needs_no_signature(client):
    assert client.get("/health").status_code == 200


def test_requests_without_a_valid_signature_are_rejected(client):
    assert client.post("/sessions", json=NEW_SESSION).status_code == 401
    assert client.post("/sessions", json=NEW_SESSION,
                       headers={"X-Dashboard-Signature": "wrong"}).status_code == 401
    assert client.get("/sessions/any").status_code == 401


# Create and get

def test_create_session_is_booked_and_saved(client, dao):
    created = book(client)

    assert created["status"] == "booked"
    assert created["price"] == 2500
    saved = dao.get_session(created["id"])
    assert saved.tutorId == "tutor-1"
    assert dao.sessions.find_one({"id": created["id"]})["status"] == "booked"


def test_get_session(client):
    created = book(client)
    response = signed_get(client, f"/sessions/{created['id']}")
    assert response.status_code == 200
    assert response.json == created


def test_get_missing_session_is_404(client):
    assert signed_get(client, "/sessions/missing").status_code == 404


@pytest.mark.parametrize("changes", [
    {"tutorId": None},
    {"studentId": "tutor-1"},
    {"price": -1},
    {"price": 12.5},
    {"price": True},
])
def test_create_session_rejects_bad_input(client, changes):
    response = signed_post(client, "/sessions", {**NEW_SESSION, **changes})
    assert response.status_code == 400


# Complete and cancel

def test_complete_session(client, dao):
    created = book(client)
    response = signed_post(client, f"/sessions/{created['id']}/complete")
    assert response.status_code == 200
    assert response.json["status"] == "completed"
    assert dao.get_session(created["id"]).status.value == "completed"


def test_cancel_session(client, dao):
    created = book(client)
    response = signed_post(client, f"/sessions/{created['id']}/cancel")
    assert response.status_code == 200
    assert dao.get_session(created["id"]).status.value == "cancelled"


@pytest.mark.parametrize("first, second", [
    ("complete", "complete"), ("complete", "cancel"),
    ("cancel", "complete"), ("cancel", "cancel"),
])
def test_finished_session_cannot_change_again(client, first, second):
    created = book(client)
    signed_post(client, f"/sessions/{created['id']}/{first}")
    assert signed_post(client, f"/sessions/{created['id']}/{second}").status_code == 409


def test_finishing_a_missing_session_is_404(client):
    assert signed_post(client, "/sessions/missing/complete").status_code == 404


# Events

def test_no_events_sent_when_urls_are_not_set(client, sent):
    created = book(client)
    signed_post(client, f"/sessions/{created['id']}/complete")
    assert sent == []


def test_events_go_to_the_right_services(dao, sent):
    client = make_client(dao, EVENTS_SHARED_SECRET="events-secret",
                         REVIEWS_API_URL="http://reviews", PAYMENTS_API_URL="http://payments")

    first = book(client)
    signed_post(client, f"/sessions/{first['id']}/complete")
    second = book(client)
    signed_post(client, f"/sessions/{second['id']}/cancel")

    assert [(url, body["event"]) for url, body, _ in sent] == [
        ("http://payments/events/sessions", "session.booked"),
        ("http://reviews/events/sessions", "session.completed"),
        ("http://payments/events/sessions", "session.completed"),
        ("http://payments/events/sessions", "session.booked"),
        ("http://payments/events/sessions", "session.cancelled"),
    ]


def test_events_are_signed(dao, sent):
    client = make_client(dao, EVENTS_SHARED_SECRET="events-secret", PAYMENTS_API_URL="http://payments")
    book(client)

    _, body, headers = sent[0]
    raw = json.dumps(body, separators=(",", ":")).encode()
    expected = hmac.new(b"events-secret", raw, hashlib.sha256).hexdigest()
    assert headers["X-Sessions-Signature"] == expected


def test_failed_event_does_not_stop_the_update(dao, monkeypatch):
    def down(*args, **kwargs):
        raise requests.ConnectionError("payments is down")

    monkeypatch.setattr(events_client.requests, "post", down)
    client = make_client(dao, EVENTS_SHARED_SECRET="events-secret", PAYMENTS_API_URL="http://payments")

    created = book(client)
    response = signed_post(client, f"/sessions/{created['id']}/cancel")
    assert response.status_code == 200
    assert response.json["status"] == "cancelled"
