import os
from datetime import timedelta

from flask import Flask, jsonify
from flask_login import LoginManager
from flask_wtf.csrf import CSRFError, CSRFProtect
from pymongo.errors import PyMongoError

from .users_dao.MongoUsersDAO import MongoUsersDAO
from .users_svc import UsersService
from .college_client import CollegeClient, CollegeServiceUnavailable


def create_app(config=None, dao=None):
    """Create the users API with session authentication, CSRF protection, and its
    DAO.

    Args:
        config (dict | None): Flask configuration overrides. Defaults to None.
        dao (UsersDAO | None): Data access object. Defaults to MongoUsersDAO.

    Returns:
        Flask: Configured application with its routes, services, and error
            handlers.

    Raises:
        RuntimeError: SECRET_KEY is missing or shorter than 32 characters.
        PyMongoError: The configured database cannot be reached or initialized.
    """
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
        COLLEGE_API_URL=os.getenv("COLLEGE_API_URL", "http://college_svc:5000"),
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
    app.extensions["college_client"] = CollegeClient(app.config["COLLEGE_API_URL"])

    CSRFProtect(app)
    login_manager = LoginManager()
    login_manager.session_protection = "strong"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        """Load an active user for Flask-Login, or return None if missing or inactive.

        Args:
            user_id (str | uuid.UUID): User identifier to look up.

        Returns:
            User | None: Matching active user, or None if missing or inactive.
        """
        user = dao.get_user(user_id)
        return user if user and user.is_active else None

    @login_manager.unauthorized_handler
    def unauthorized():
        """Return a JSON 401 response when a route requires authentication.

        Returns:
            tuple[Response, int]: JSON error response with status 401.
        """
        return jsonify(error="Authentication required."), 401

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        """Return a generic JSON 400 response for a rejected CSRF token.

        Args:
            error (CSRFError): CSRF validation error handled by Flask.

        Returns:
            tuple[Response, int]: JSON error response with status 400.
        """
        return jsonify(error="Missing, invalid, or expired CSRF token."), 400

    @app.errorhandler(PyMongoError)
    def database_error(error):
        """Log the database error type and return a generic JSON 503 response.

        Args:
            error (PyMongoError): Database error handled by Flask.

        Returns:
            tuple[Response, int]: Generic JSON error response with status 503.
        """
        app.logger.error("User database operation failed (%s).", type(error).__name__)
        return jsonify(error="User service temporarily unavailable."), 503

    @app.errorhandler(CollegeServiceUnavailable)
    def college_unavailable(error):
        """Handle an unavailable college ownership lookup.

        Args:
            error (CollegeServiceUnavailable): College API lookup failure.

        Returns:
            tuple[Response, int]: Retryable error with status 503.
        """
        return jsonify(error="College service temporarily unavailable."), 503

    @app.after_request
    def security_headers(response):
        """Prevent response caching and MIME-type sniffing.

        Args:
            response (Response): Outgoing Flask response to update.

        Returns:
            Response: Response with caching and content-sniffing protections
                applied.
        """
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    from .auth import auth
    app.register_blueprint(auth)
    return app
