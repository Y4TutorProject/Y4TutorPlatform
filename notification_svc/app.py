import hmac
import os
from urllib.parse import urlparse

from flask import Flask, jsonify, request
from pymongo import MongoClient

from notification_service import NotificationService
from notifications_dao.mongo_notification_dao import MongoNotificationDAO

app = Flask(__name__)


mongo_client = MongoClient(
    os.environ.get("MONGO_URI", "mongodb://localhost:27019"),
    serverSelectionTimeoutMS=5000,
)
database = mongo_client[os.environ.get("MONGO_DB_NAME", "notification_db")]
notification_store = MongoNotificationDAO(database["notifications"])
notification_store.ensure_indexes()
notification_service = NotificationService(notification_store)


def _authenticated_user_id():
    user_id = request.headers.get("X-User-ID", "").strip()
    return user_id or None


def _require_user(user_id):
    """Require that the authenticated user matches the given user_id.
    """
    authenticated_user_id = _authenticated_user_id()
    if authenticated_user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    if authenticated_user_id != str(user_id):
        return jsonify({"error": "User identity mismatch"}), 403
    return None


def _valid_link(link):
    """Validate that the link is a valid relative path.
    """
    if link is None:
        return True
    if not isinstance(link, str) or not link.startswith("/") or link.startswith("//"):
        return False
    return not urlparse(link).scheme and not urlparse(link).netloc


@app.post("/notifications")
def create_notifications():
    """Create a new notification.

    param recipient_ids: List of user IDs to receive the notification.
    param type: Notification type (string).
    param title: Notification title (string).
    param body: Notification body (string, optional).
    param payload: Additional data (object, optional).
    param actor_id: ID of the user who triggered the notification (string, optional).

    Returns:
        201 Created with the created notification(s) in the response body.
        400 Bad Request if the request is invalid.
        401 Unauthorized if the user is not authenticated.
        403 Forbidden if the actor_id does not match the authenticated user.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400

    recipient_ids = data.get("recipient_ids")
    notification_type = data.get("type")
    title = data.get("title")
    if (
        not isinstance(recipient_ids, list)
        or not recipient_ids
        or not all(isinstance(value, str) and value.strip() for value in recipient_ids)
        or not isinstance(notification_type, str)
        or not isinstance(title, str)
        or not title.strip()
    ):
        return jsonify({"error": "Invalid notification fields"}), 400
    if not _valid_link(data.get("link")):
        return jsonify({"error": "link must be a relative path"}), 400

    actor_id = data.get("actor_id")
    authenticated_user_id = _authenticated_user_id()
    if actor_id is not None and actor_id != authenticated_user_id:
        return jsonify({"error": "actor_id must match authenticated user"}), 403

    payload = data.get("payload")
    if payload is not None and not isinstance(payload, dict):
        return jsonify({"error": "payload must be an object"}), 400
    payload = dict(payload or {})
    if data.get("link") is not None:
        payload["link"] = data["link"]

    try:
        notifications = notification_service.create_notifications(
            recipient_ids,
            notification_type,
            title.strip(),
            data.get("body", ""),
            payload,
            actor_id or authenticated_user_id,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(notifications), 201


@app.get("/users/<user_id>/notifications")
def get_notifications(user_id):
    """
    Get notifications for a user.
    """
    error = _require_user(user_id)
    if error:
        return error
    unread_only = request.args.get("unread", "false").lower() == "true"
    try:
        page = max(request.args.get("page", 1, type=int), 1)
        per_page = min(max(request.args.get("per_page", 20, type=int), 1), 100)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid pagination"}), 400
    return jsonify(notification_service.get_user_notifications(
        user_id, unread_only, page, per_page
    ))


@app.get("/users/<user_id>/notifications/unread-count")
def get_unread_count(user_id):
    error = _require_user(user_id)
    if error:
        return error
    return jsonify({"unread_count": notification_service.get_unread_count(user_id)})


@app.post("/notifications/<notification_id>/read")
def mark_notification_read(notification_id):
    user_id = _authenticated_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    if not notification_service.mark_as_read(notification_id, user_id):
        return jsonify({"error": "Notification not found or already read"}), 404
    return jsonify({"success": True})


@app.post("/notifications/<notification_id>/unread")
def mark_notification_unread(notification_id):
    user_id = _authenticated_user_id()
    if user_id is None:
        return jsonify({"error": "Authenticated user required"}), 401
    if not notification_service.mark_as_unread(notification_id, user_id):
        return jsonify({"error": "Notification not found or already unread"}), 404
    return jsonify({"success": True})


@app.post("/users/<user_id>/notifications/read-all")
def mark_all_notifications_read(user_id):
    error = _require_user(user_id)
    if error:
        return error
    return jsonify({"marked": notification_service.mark_all_as_read(user_id)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)