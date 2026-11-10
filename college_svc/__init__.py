import os
import hmac

from flask import Flask, jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

from .college_dao.MongoCollegeDAO import MongoCollegeDAO
from .implementations.college_svc import CollegeService
from .auth import AuthenticationError, UsersAuthClient
from .Objects.CollegeStatus import CollegeStatus
from .academic_dao.MongoAcademicDAO import MongoAcademicDAO
from .implementations.academic_svc import AcademicService
from .manual_academics import register_manual_academics

def create_app(config=None, dao=None, auth_client=None):
    """Create the college API with a DAO and users-session verification client.

    Args:
        config (dict | None): Flask configuration overrides. Defaults to None.
        dao (CollegeDAO | None): Data access object. Defaults to
            MongoCollegeDAO.
        auth_client (UsersAuthClient | None): Session verifier. Defaults to a
            UsersAuthClient using USERS_API_URL.

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
        SESSION_COOKIE_NAME="college_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true",
        MAX_CONTENT_LENGTH=16 * 1024,
        COLLEGE_SYNC_TOKEN=os.getenv("COLLEGE_SYNC_TOKEN", ""),
        # Verify through the gateway to retain Flask-Login's strong session
        # binding: users_svc sees the same proxy address as it did at login.
        USERS_API_URL=os.getenv("USERS_API_URL", "http://gateway/api/users"),
    )
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Set SECRET_KEY to a random secret of at least 32 characters.")

    if dao is None:
        dao = MongoCollegeDAO()
    dao.connect_to_database()
    dao.setup_database()
    app.extensions["college_dao"] = dao
    app.extensions["college_service"] = CollegeService(dao)
    app.extensions["users_auth"] = auth_client or UsersAuthClient(app.config["USERS_API_URL"])
    academic = AcademicService(MongoAcademicDAO(dao.db))
    app.extensions["academic_service"] = academic
    register_manual_academics(app, dao.db)

    @app.before_request
    def academic_request_limit():
        if request.path.startswith("/internal/college/"):
            request.max_content_length = 8 * 1024 * 1024

    @app.route("/internal/college/<college_id>/catalogs", methods=["POST"])
    @app.route("/internal/college/<college_id>/catalogs/<catalog_id>", methods=["GET"])
    def academic_catalog(college_id, catalog_id=None):
        token = app.config["COLLEGE_SYNC_TOKEN"]
        supplied = request.headers.get("X-College-Sync-Token", "")
        if not token or not hmac.compare_digest(token.encode(), supplied.encode()):
            return jsonify(error="Service authentication required."), 401
        college = app.extensions["college_service"].get_college_by_id(college_id)
        if college is None or college.status != CollegeStatus.ACTIVE:
            return jsonify(error="College not found."), 404
        try:
            if request.method == "POST":
                return jsonify(catalog=academic.import_catalog(college_id, request.get_json(silent=True)))
            catalog = academic.get_catalog(college_id, catalog_id)
            return (jsonify(catalog=catalog), 200) if catalog else (jsonify(error="Catalogue not found."), 404)
        except ValueError:
            return jsonify(error="Invalid academic catalogue."), 400

    @app.get("/college")
    def list_colleges():
        """Return active colleges without requiring a signed-in session.

        Returns:
            Response: JSON list of colleges available during signup.
        """
        colleges = app.extensions["college_service"].list_active_colleges()
        return jsonify(colleges=[college.to_dict() for college in colleges])

    @app.get("/college/<college_id>")
    def get_college(college_id):
        """Return an active college for registration validation.

        Args:
            college_id (str): UUID of the requested college.

        Returns:
            Response | tuple[Response, int]: College details, or status 404 for
                an invalid, missing, or inactive college.
        """
        college = app.extensions["college_service"].get_college_by_id(college_id)
        if college is None or college.status != CollegeStatus.ACTIVE:
            return jsonify(error="College not found."), 404
        return jsonify(college=college.to_dict())

    @app.post("/college")
    def create_college():
        """Verify authentication and CSRF, then create a college from request JSON.

        Returns:
            tuple[Response, int]: Created record with status 201, or a validation or
                duplicate-record error.

        Raises:
            AuthenticationError: Session or CSRF verification fails, or the users
                service is unavailable.
        """
        user = app.extensions["users_auth"].verify(
            request.cookies.get("tutor_session"),
            request.headers.get("User-Agent", ""),
            request.headers.get("X-CSRFToken"),
        )
        if "college_admin" not in user.get("roles", []):
            return jsonify(error="College administrator access required."), 403
        try:
            college = app.extensions["college_service"].create_college(
                request.get_json(silent=True), admin_id=user["id"],
            )
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except DuplicateKeyError:
            return jsonify(error="College ID or name is already registered."), 409
        app.extensions["users_auth"].assign_college(
            request.cookies.get("tutor_session"), request.headers.get("User-Agent", ""),
            request.headers.get("X-CSRFToken"), str(college.college_id),
        )
        return jsonify(college=college.to_dict()), 201

    @app.errorhandler(AuthenticationError)
    def authentication_error(error):
        """Return the public authentication error message and its HTTP status.

        Args:
            error (AuthenticationError): Authentication failure and its public HTTP
                status.

        Returns:
            tuple[Response, int]: JSON error response and the authentication failure
                status.
        """
        return jsonify(error=str(error)), error.status

    @app.errorhandler(PyMongoError)
    def database_error(error):
        """Log the database error type and return a generic JSON 503 response.

        Args:
            error (PyMongoError): Database error handled by Flask.

        Returns:
            tuple[Response, int]: Generic JSON error response with status 503.
        """
        app.logger.error("College database operation failed (%s).", type(error).__name__)
        return jsonify(error="College service temporarily unavailable."), 503

    return app
