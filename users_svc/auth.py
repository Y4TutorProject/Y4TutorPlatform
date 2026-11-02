from flask import Blueprint, current_app, jsonify, request, session
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import generate_csrf


auth = Blueprint("auth", __name__)


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("A JSON object is required.")
    return data


@auth.get("/auth/csrf")
def csrf_token():
    return jsonify(csrf_token=generate_csrf())


@auth.post("/auth/login")
def login():
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
    logout_user()
    session.clear()
    return jsonify(message="Logged out.", csrf_token=generate_csrf())


@auth.get("/users/me")
@login_required
def me():
    return jsonify(user=current_user.to_public_dict())
