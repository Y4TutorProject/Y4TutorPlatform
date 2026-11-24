"""Sends session events to reviews_svc and payments_svc (YGPT-155, YGPT-156).

Works like dashboard_svc/messaging_client.py: the JSON body is signed with a
shared secret so the receiving service knows it came from sessions_svc.

Neither service exists yet. If a URL isn't set, the event is logged and
skipped. A failed send never stops the session from being updated.
"""
import hashlib
import hmac
import json
import logging

import requests

logger = logging.getLogger(__name__)

SESSION_BOOKED = "session.booked"
SESSION_COMPLETED = "session.completed"
SESSION_CANCELLED = "session.cancelled"

# Which service needs to hear about which event.
EVENT_TARGETS = {
    SESSION_BOOKED: ["PAYMENTS_API_URL"],
    SESSION_COMPLETED: ["REVIEWS_API_URL", "PAYMENTS_API_URL"],
    SESSION_CANCELLED: ["PAYMENTS_API_URL"],
}


def send_event(config, event, session):
    """POST a signed event to every service that needs it."""
    secret = config.get("EVENTS_SHARED_SECRET")
    body = json.dumps(
        {"event": event, "session": session.to_dict()},
        separators=(",", ":"),
    ).encode("utf-8")

    for url_setting in EVENT_TARGETS[event]:
        base_url = config.get(url_setting)
        if not base_url or not secret:
            logger.info("%s not configured, skipped %s", url_setting, event)
            continue

        signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        try:
            response = requests.post(
                base_url.rstrip("/") + "/events/sessions",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Sessions-Signature": signature,
                },
                timeout=5,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.exception("Failed to send %s to %s", event, url_setting)
