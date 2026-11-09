import hashlib
import hmac
import json

from flask import current_app, request


def messaging_post(client, path, payload):
    """POST a dashboard-signed JSON payload to the messaging service."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(
        current_app.config["DASHBOARD_SHARED_SECRET"].encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return client.post(
        current_app.config["MESSAGING_API_URL"].rstrip("/") + path,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Dashboard-Signature": signature,
        },
        timeout=5,
    )


def forward_messaging_cookie(response, client):
    """Copy the messaging service's session cookie onto the browser response."""
    cookie = client.cookies.get("messaging_session")
    if cookie:
        response.set_cookie(
            "messaging_session",
            cookie,
            httponly=True,
            secure=request.headers.get(
                "X-Forwarded-Proto", request.scheme
            ).lower() == "https",
            samesite="Lax",
        )
    return response
