from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import generate_csrf
from .Objects.Role import Role
import uuid


auth = Blueprint("auth", __name__)


def json_body():
    """Parse the request body as a JSON object.

    Returns:
        dict: Parsed JSON object from the request body.

    Raises:
        ValueError: The request body is not a JSON object.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("A JSON object is required.")
    return data


@auth.get("/auth/csrf")
def csrf_token():
    """Return a CSRF token tied to the current users session.

    Returns:
        Response: JSON response containing the session-bound CSRF token.
    """
    return jsonify(csrf_token=generate_csrf())


@auth.post("/auth/login")
def login():
    """Authenticate credentials, start a fresh session, and return user details and
    a CSRF token.

    Returns:
        Response | tuple[Response, int]: Public user details and a fresh CSRF
            token, or a JSON error response.
    """
    try:
        data = json_body()
    except ValueError as error:
        return jsonify(error=str(error)), 400
    try:
        user = current_app.extensions["users_service"].log_in(
            data.get("email"), data.get("password"),
        )
    except ValueError:
        user = None
    if user is None:
        return jsonify(error="Invalid email or password."), 401
    session.clear()
    login_user(user, remember=False)
    session.permanent = True
    return jsonify(user=user.to_public_dict(), csrf_token=generate_csrf())


@auth.post("/auth/logout")
@login_required
def logout():
    """End the authenticated session and return a CSRF token for the cleared
    session.

    Returns:
        Response: Logout confirmation and a CSRF token for the cleared session.
    """
    logout_user()
    session.clear()
    return jsonify(message="Logged out.", csrf_token=generate_csrf())


@auth.get("/users/me")
@login_required
def me():
    """Return public details for the authenticated user.

    Returns:
        Response: JSON response containing public details for the signed-in
            user.
    """
    return jsonify(user=current_user.to_public_dict())


@auth.post("/auth/verify")
@login_required
def verify():
    # CSRFProtect validates POSTs before this session check runs.
    """Confirm the authenticated session after CSRF validation for other services.

    Returns:
        Response: JSON response confirming the authenticated user after CSRF
            validation.
    """
    return jsonify(user=current_user.to_public_dict())


@auth.post("/users/me/college")
@login_required
def assign_college():
    """Complete onboarding by attaching a college owned by the signed-in admin.

    Returns:
        Response | tuple[Response, int]: Updated account or an ownership error.
    """
    if Role.COLLEGE_ADMIN not in current_user.roles:
        return jsonify(error="College administrator access required."), 403
    try:
        data = json_body()
        college_id = str(uuid.UUID(data.get("college_id")))
    except (ValueError, TypeError, AttributeError):
        return jsonify(error="A valid college ID is required."), 400
    college = current_app.extensions["college_client"].get_college(college_id)
    if college is None or college.get("admin_id") != str(current_user.id):
        return jsonify(error="This college does not belong to your account."), 403
    dao = current_app.extensions["users_dao"]
    if not dao.assign_college(str(current_user.id), college_id):
        return jsonify(error="Your account already belongs to another college."), 409
    return jsonify(user=dao.get_user(str(current_user.id)).to_public_dict())
