"""Standalone LMS HTTP API. Other services never import this package."""
import os
import uuid

from flask import Flask, jsonify, request
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .auth import AuthenticationError, UsersAuthClient
from .college_client import CollegeClient, CollegeServiceUnavailable
from .connections import MongoConnectionStore, SyncBusy
from .lms.interfaces import LMSImportError
from .lms.service import LMSImportService
from .lms.store import MongoLMSImportStore
from .sync import LMSSyncService


def create_app(config=None, database=None, auth_client=None, college_client=None):
    app = Flask(__name__)
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=16 * 1024,
        MONGO_URI=os.getenv("MONGO_URI", "mongodb://lms_db:27017/"),
        MONGO_DB_NAME=os.getenv("MONGO_DB_NAME", "lms_db"),
        LMS_ENCRYPTION_KEY=os.getenv("LMS_ENCRYPTION_KEY"),
        LMS_ALLOWED_HOSTS=os.getenv("LMS_ALLOWED_HOSTS", ""),
        LMS_SYNC_TIMEZONE=os.getenv("LMS_SYNC_TIMEZONE", "Europe/Dublin"),
        LMS_SYNC_HOUR=os.getenv("LMS_SYNC_HOUR", "2"),
        USERS_API_URL=os.getenv("USERS_API_URL", "http://gateway/api/users"),
        COLLEGE_API_URL=os.getenv("COLLEGE_API_URL", "http://college_svc:5000"),
    )
    app.config.update(config or {})
    if not app.config["LMS_ENCRYPTION_KEY"]:
        raise RuntimeError("Set LMS_ENCRYPTION_KEY to a persistent Fernet key.")
    if database is None:
        client = MongoClient(app.config["MONGO_URI"], serverSelectionTimeoutMS=5000, tz_aware=True)
        database = client[app.config["MONGO_DB_NAME"]]
    auth = auth_client or UsersAuthClient(app.config["USERS_API_URL"])
    colleges = college_client or CollegeClient(app.config["COLLEGE_API_URL"])
    importer = LMSImportService(MongoLMSImportStore(database), app.config["LMS_ALLOWED_HOSTS"].split(","))
    sync = LMSSyncService(importer, MongoConnectionStore(database), app.config["LMS_ENCRYPTION_KEY"], colleges,
                          app.config["LMS_SYNC_TIMEZONE"], app.config["LMS_SYNC_HOUR"])
    app.extensions.update(lms_service=importer, lms_sync=sync, lms_database=database)

    def authorize(college_id):
        user = auth.verify(request.cookies.get("tutor_session"), request.headers.get("User-Agent", ""), request.headers.get("X-CSRFToken"))
        if "college_admin" not in user.get("roles", []):
            raise AuthenticationError("College administrator access required.", 403)
        try:
            college_id = str(uuid.UUID(college_id))
        except ValueError:
            raise AuthenticationError("College not found.", 403) from None
        college = colleges.get_college(college_id)
        if college is None or college.get("admin_id") != user["id"]:
            raise AuthenticationError("College not found or not owned by this administrator.", 403)
        return user

    @app.route("/college/<college_id>/lms/connection", methods=["GET", "PUT"])
    def connection(college_id):
        user = authorize(college_id)
        if request.method == "GET":
            return jsonify(connection=sync.public(sync.connections.get(college_id)))
        return jsonify(connection=sync.configure(college_id, user["id"], request.get_json(silent=True)))

    @app.post("/college/<college_id>/lms/sync")
    def synchronize(college_id):
        authorize(college_id)
        return jsonify(connection=sync.synchronize(college_id, force=True))

    @app.post("/college/<college_id>/lms/import")
    def import_once(college_id):
        authorize(college_id)
        catalog = importer.import_catalog(college_id, request.get_json(silent=True))
        return jsonify(provider=catalog["provider"], base_url=catalog["base_url"], mapping=catalog["mapping"],
                       imported_at=catalog["imported_at"], counts={k: len(catalog[k]) for k in ("users", "courses", "modules")})

    @app.get("/college/<college_id>/lms/catalog")
    def catalog(college_id):
        authorize(college_id)
        data = request.args.to_dict()
        if not data:
            data = sync.connections.get(college_id)
            if data is None:
                return jsonify(error="No saved connection."), 404
        provider, url = importer.validate_source(data)
        result = importer.store.get(college_id, provider, url)
        return (jsonify(catalog=result), 200) if result else (jsonify(error="No successful import found."), 404)

    @app.get("/health")
    def health():
        database.command("ping")
        return jsonify(status="ok")

    @app.errorhandler(AuthenticationError)
    def auth_error(error):
        return jsonify(error=str(error)), error.status

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(SyncBusy)
    def busy(error):
        return jsonify(error=str(error)), 409

    @app.errorhandler(LMSImportError)
    def upstream(error):
        return jsonify(error=str(error)), 502

    @app.errorhandler(CollegeServiceUnavailable)
    @app.errorhandler(PyMongoError)
    def unavailable(error):
        app.logger.warning("LMS dependency unavailable (%s).", type(error).__name__)
        return jsonify(error="LMS service temporarily unavailable."), 503

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    return app
