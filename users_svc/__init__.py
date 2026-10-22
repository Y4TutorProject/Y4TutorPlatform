import os
from datetime import timedelta

from flask import Flask, jsonify
from flask_login import LoginManager
from flask_wtf.csrf import CSRFError, CSRFProtect
from pymongo.errors import PyMongoError

from .users_dao.MongoUsersDAO import MongoUsersDAO
from .users_svc import UsersService


def create_app(config=None, dao=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY"),
        SESSION_COOKIE_NAME="tutor_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
        SESSION_REFRESH_EACH_REQUEST=False,
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
    app.extensions["users_service"] = UsersService(dao)

    CSRFProtect(app)
    login_manager = LoginManager()
    login_manager.session_protection = "strong"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        user = dao.get_user(user_id)
        return user if user and user.is_active else None

    @login_manager.unauthorized_handler
    def unauthorized():
        return jsonify(error="Authentication required."), 401

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return jsonify(error="Missing, invalid, or expired CSRF token."), 400

    @app.errorhandler(PyMongoError)
    def database_error(error):
        app.logger.error("User database operation failed (%s).", type(error).__name__)
        return jsonify(error="User service temporarily unavailable."), 503

    @app.after_request
    def security_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    from .auth import auth
    app.register_blueprint(auth)
    return app
