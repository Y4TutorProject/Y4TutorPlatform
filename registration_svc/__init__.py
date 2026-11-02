import os

from flask import Flask, jsonify, request
from flask_wtf.csrf import CSRFError, CSRFProtect, generate_csrf
from pymongo.errors import DuplicateKeyError, PyMongoError

from users_svc.users_dao.MongoUsersDAO import MongoUsersDAO

from .implementations.registration_svc import RegistrationService


def create_app(config=None, dao=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY"),
        SESSION_COOKIE_NAME="registration_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true",
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Set SECRET_KEY to a random secret of at least 32 characters.")

    if dao is None:
        dao = MongoUsersDAO()
    dao.connect_to_database()
    dao.setup_database()
    app.extensions["users_dao"] = dao
    app.extensions["registration_service"] = RegistrationService(dao)
    CSRFProtect(app)

    @app.get("/auth/csrf")
    def csrf_token():
        return jsonify(csrf_token=generate_csrf())

    @app.post("/auth/signup")
    def signup():
        try:
            user = app.extensions["registration_service"].register_user(
                request.get_json(silent=True),
            )
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except DuplicateKeyError:
            return jsonify(error="Username or email is already registered."), 409
        return jsonify(user=user.to_public_dict()), 201

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return jsonify(error="Missing, invalid, or expired CSRF token."), 400

    @app.errorhandler(PyMongoError)
    def database_error(error):
        app.logger.error("Registration database operation failed (%s).", type(error).__name__)
        return jsonify(error="Registration service temporarily unavailable."), 503

    @app.after_request
    def security_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return app
