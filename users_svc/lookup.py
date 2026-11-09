import logging
import os

from flask import Blueprint, current_app, jsonify, request

lookup = Blueprint("lookup", __name__)

def _internal_request_is_trusted():
    """Check if the request is from an internal service with a valid token."""
    token = os.getenv("INTERNAL_API_TOKEN", "")
    sent = request.headers.get("X-Internal-Token", "")
    return bool(token) and bool(sent) and token == sent

@lookup.get("/tutors")
def list_tutors():
    """List active, verified tutors in the signed-in user's college."""
    if not _internal_request_is_trusted():
        return jsonify(error="Unauthorized."), 401
    service = current_app.extensions["users_service"]
    college_id = request.args.get("college_id")
    if not college_id:
        return jsonify(error="Missing college ID."), 400
    found = service.list_tutors(college_id=college_id)
    return jsonify(tutors=[
        {"id": str(t.id), "username": t.username, "college_id": str(t.college), "email": t.email}
        for t in found
    ])