from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests
from flask import Blueprint, abort, current_app, g, request

from sessions_client import sessions_request
from users_client import login_required


bp = Blueprint("sessions", __name__)

TEST_SESSION_PRICE = 2500  # €25.00 in cents


def _forward(response):
    """Return the sessions service's JSON and status code to the browser."""
    try:
        return response.json(), response.status_code
    except ValueError:
        abort(502, "Sessions service returned an invalid response")


@bp.post("/sessions")
@login_required
def create_session():
    """Book a test session between the signed-in student and a tutor, starting tomorrow."""
    data = request.get_json(silent=True) or {}
    tutor_id, module_id = data.get("tutor_id"), data.get("module_id")
    if not tutor_id or not module_id:
        abort(400, "tutor_id and module_id are required")

    start = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=1)
    try:
        response = sessions_request("POST", "/sessions", {
            "tutorId": tutor_id,
            "studentId": g.user["id"],
            "moduleId": module_id,
            "startTime": start.isoformat(),
            "endTime": (start + timedelta(hours=1)).isoformat(),
            "price": TEST_SESSION_PRICE,
        })
    except requests.RequestException as error:
        current_app.logger.warning("Session create failed (%s)", type(error).__name__)
        abort(502, "Sessions service is unavailable")
    return _forward(response)


@bp.post("/sessions/<session_id>/<action>")
@login_required
def finish_session(session_id, action):
    """Complete or cancel a session the signed-in user is part of."""
    if action not in ("complete", "cancel"):
        abort(404)
    path = f"/sessions/{quote(session_id, safe='')}"
    try:
        existing = sessions_request("GET", path)
        if existing.status_code != 200:
            return _forward(existing)
        session = existing.json()
        if g.user["id"] not in (session.get("tutorId"), session.get("studentId")):
            abort(403, "You are not part of this session")
        response = sessions_request("POST", f"{path}/{action}", {})
    except requests.RequestException as error:
        current_app.logger.warning("Session %s failed (%s)", action, type(error).__name__)
        abort(502, "Sessions service is unavailable")
    return _forward(response)
