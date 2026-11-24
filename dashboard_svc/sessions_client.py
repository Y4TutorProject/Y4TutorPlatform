import hashlib
import hmac
import json

import requests
from flask import current_app


def sessions_request(method, path, payload=None):
    """Send a dashboard-signed request to the sessions service."""
    body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(
        current_app.config["DASHBOARD_SHARED_SECRET"].encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return requests.request(
        method,
        current_app.config["SESSIONS_API_URL"].rstrip("/") + path,
        data=body if payload is not None else None,
        headers={
            "Content-Type": "application/json",
            "X-Dashboard-Signature": signature,
        },
        timeout=5,
    )
