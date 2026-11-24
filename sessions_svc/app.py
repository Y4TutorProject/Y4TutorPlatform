import hashlib
import hmac
import os
import uuid

from flask import Flask, jsonify, request

from sessions_svc.events_client import (
    SESSION_BOOKED,
    SESSION_CANCELLED,
    SESSION_COMPLETED,
    send_event,
)
from sessions_svc.models.Session import Session
from sessions_svc.objects.SessionStatus import SessionStatus

REQUIRED_FIELDS = ["tutorId", "studentId", "moduleId", "startTime", "endTime", "price"]


def create_app(config=None, dao=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DASHBOARD_SHARED_SECRET=os.environ.get("DASHBOARD_SHARED_SECRET"),
        EVENTS_SHARED_SECRET=os.environ.get("EVENTS_SHARED_SECRET"),
        REVIEWS_API_URL=os.environ.get("REVIEWS_API_URL"),
        PAYMENTS_API_URL=os.environ.get("PAYMENTS_API_URL"),
    )
    if config:
        app.config.update(config)

    # Tests pass in a dao backed by mongomock; otherwise connect to the real database.
    if dao is None:
        from sessions_svc.sessions_dao.MongoSessionsDAO import MongoSessionsDAO
        dao = MongoSessionsDAO()
        dao.connect_to_database()
        dao.setup_database()

    def _dashboard_request_is_trusted():
        """Same check as messaging_svc: the dashboard signs the request body."""
        secret = app.config["DASHBOARD_SHARED_SECRET"]
        signature = request.headers.get("X-Dashboard-Signature")
        if not secret or not signature:
            return False
        digest = hmac.new(
            secret.encode("utf-8"), request.get_data(cache=True), hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, digest)

    @app.before_request
    def require_dashboard_signature():
        if request.endpoint == "health":
            return None
        if not _dashboard_request_is_trusted():
            return jsonify({"error": "Unauthorized"}), 401
        return None

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({'status': 'healthy'}), 200

    @app.route('/sessions', methods=['POST'])
    def create_session():
        """Create a booked session. YGPT-34 builds the real booking flow on top of this."""
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Expected a JSON object"}), 400

        missing = [field for field in REQUIRED_FIELDS if data.get(field) in (None, "")]
        if missing:
            return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400
        if data["tutorId"] == data["studentId"]:
            return jsonify({"error": "tutorId and studentId must be different"}), 400
        price = data["price"]
        if isinstance(price, bool) or not isinstance(price, int) or price < 0:
            return jsonify({"error": "price must be a whole number of cents, 0 or more"}), 400

        session = Session({
            "id": str(uuid.uuid4()),
            "tutorId": data["tutorId"],
            "studentId": data["studentId"],
            "moduleId": data["moduleId"],
            "startTime": data["startTime"],
            "endTime": data["endTime"],
            "status": SessionStatus.BOOKED.value,
            "price": price,
        })
        dao.add_session(session)
        send_event(app.config, SESSION_BOOKED, session)
        return jsonify(session.to_dict()), 201

    @app.route('/sessions/<session_id>', methods=['GET'])
    def get_session(session_id):
        session = dao.get_session(session_id)
        if session is None:
            return jsonify({"error": "Session not found"}), 404
        return jsonify(session.to_dict()), 200

    def _finish_session(session_id, new_status, event):
        """Move a booked session to completed or cancelled, then send the event."""
        session = dao.get_session(session_id)
        if session is None:
            return jsonify({"error": "Session not found"}), 404
        if session.status != SessionStatus.BOOKED:
            return jsonify({"error": f"Session is already {session.status.value}"}), 409

        session.status = new_status
        dao.update_session(session)
        send_event(app.config, event, session)
        return jsonify(session.to_dict()), 200

    @app.route('/sessions/<session_id>/complete', methods=['POST'])
    def complete_session(session_id):
        return _finish_session(session_id, SessionStatus.COMPLETED, SESSION_COMPLETED)

    @app.route('/sessions/<session_id>/cancel', methods=['POST'])
    def cancel_session(session_id):
        return _finish_session(session_id, SessionStatus.CANCELLED, SESSION_CANCELLED)

    return app
