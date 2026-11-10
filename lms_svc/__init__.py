"""Standalone LMS HTTP API. Other services never import this package."""
import os
import uuid

from flask import Flask, app, jsonify, request
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import requests

from .auth import AuthenticationError, UsersAuthClient
from .college_client import CollegeClient, CollegeServiceUnavailable
from .connections import MongoConnectionStore, SyncBusy
from .lms.interfaces import LMSImportError
from .lms.service import LMSImportService
from .lms.store import MongoLMSImportStore
from .sync import LMSSyncService
from .module_participation import ModuleParticipation, programme_modules, tutor_modules, enrolment_roles
from .manual_catalog import merge_manual, manual_application_eligible

import logging

def create_app(config=None, database=None, auth_client=None, college_client=None,
               providers=None, import_store=None, connection_store=None, participation_store=None):
    app = Flask(__name__)
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=16 * 1024,
        MONGO_URI=os.getenv("MONGO_URI", "mongodb://lms_db:27017/"),
        MONGO_DB_NAME=os.getenv("MONGO_DB_NAME", "lms_db"),
        LMS_ENCRYPTION_KEY=os.getenv("LMS_ENCRYPTION_KEY"),
        DEV_MODE=os.getenv("DEV_MODE", "false").lower() == "true",
        LMS_PRIVATE_HOSTS=os.getenv("LMS_PRIVATE_HOSTS", ""),
        LMS_CA_FILE=os.getenv("LMS_CA_FILE") or None,
        LMS_ALLOWED_HOSTS=os.getenv("LMS_ALLOWED_HOSTS", ""),
        LMS_SYNC_TIMEZONE=os.getenv("LMS_SYNC_TIMEZONE", "Europe/Dublin"),
        LMS_SYNC_HOUR=os.getenv("LMS_SYNC_HOUR", "2"),
        USERS_API_URL=os.getenv("USERS_API_URL", "http://gateway/api/users"),
        COLLEGE_API_URL=os.getenv("COLLEGE_API_URL", "http://college_svc:5000"),
        COLLEGE_SYNC_TOKEN=os.getenv("COLLEGE_SYNC_TOKEN", ""),
    )
    app.config.update(config or {})
    if not app.config["LMS_ENCRYPTION_KEY"]:
        raise RuntimeError("Set LMS_ENCRYPTION_KEY to a persistent Fernet key.")
    if database is None:
        client = MongoClient(app.config["MONGO_URI"], serverSelectionTimeoutMS=5000, tz_aware=True)
        database = client[app.config["MONGO_DB_NAME"]]
    auth = auth_client or UsersAuthClient(app.config["USERS_API_URL"])
    colleges = college_client or CollegeClient(app.config["COLLEGE_API_URL"], app.config["COLLEGE_SYNC_TOKEN"])
    participation = participation_store or ModuleParticipation(database)
    importer = LMSImportService(import_store or MongoLMSImportStore(database, colleges, participation), app.config["LMS_ALLOWED_HOSTS"].split(","),
                                providers=providers, private_hosts=app.config["LMS_PRIVATE_HOSTS"].split(",") if app.config["DEV_MODE"] else (),
                                ca_file=app.config["LMS_CA_FILE"] if app.config["DEV_MODE"] else None)
    sync = LMSSyncService(importer, connection_store or MongoConnectionStore(database), app.config["LMS_ENCRYPTION_KEY"], colleges,
                          app.config["LMS_SYNC_TIMEZONE"], app.config["LMS_SYNC_HOUR"])
    app.extensions.update(lms_service=importer, lms_sync=sync, lms_database=database)

    app.extensions["module_participation"] = participation

    def student_context(write=False):
        if write:
            user = auth.verify(request.cookies.get("tutor_session"), request.headers.get("User-Agent", ""), request.headers.get("X-CSRFToken"))
        else:
            user = auth.authenticate(request.cookies.get("tutor_session"), request.headers.get("User-Agent", ""))
        if "student" not in user.get("roles", []):
            raise AuthenticationError("Student access required.", 403)
        college_id = user.get("college_id")
        college = colleges.get_college(college_id) if college_id else None
        if college is None:
            raise AuthenticationError("Your college is not available.", 404)
        connection = sync.connections.get(college_id)
        catalog = importer.store.get(college_id, connection["provider"], connection["base_url"]) if connection else None
        manual = colleges.get_manual_academic(college_id, user)
        has_directory_profile = any(p['email'] == user['email'].strip().casefold() for p in manual.get('directory_users', []))
        if not catalog and not has_directory_profile and not any(a.get('user_id') == user['id'] for a in manual['assignments']):
            raise AuthenticationError("Your college has not imported LMS information yet.", 404)
        catalog = merge_manual(catalog, manual, user)
        # The verified account's college and email are the only lookup keys.
        # Never accept a requested email or return the college user directory.
        matches = [record for record in catalog["users"]
                   if record.get("email") and record["email"].strip().casefold() == user["email"].strip().casefold()]
        if len(matches) != 1 or matches[0].get("suspended"):
            raise AuthenticationError("No active LMS profile matches your verified email address.", 404)
        roles = enrolment_roles(catalog, matches[0]['source_id'])
        modules = [module for module in catalog['modules'] if 'student' in roles.get(module['id'], set())]
        participation.synchronize_user(
            user, {key: value - {'tutor'} for key, value in roles.items()}, matches[0]['source_id'],
            importer.store.source_identity(college_id, connection['provider'], connection['base_url'])
            if connection else 'manual:' + college_id)
        return user, college, catalog, matches[0], modules

    def module_details(user, catalog, modules, query=''):
        details = participation.module_details(user, modules, query)
        for module in details:
            module['roles'] = sorted(set(module['roles']) | catalog.get('_manual_roles', {}).get(module['id'], set()))
        return details

    @app.get('/providers')
    def providers():
        auth.authenticate(request.cookies.get('tutor_session'), request.headers.get('User-Agent', ''))
        return jsonify(providers=importer.provider_configurations())

    @app.get("/students/me")
    def student_information():
        user, college, catalog, match, modules = student_context()
        profile = {field: match.get(field, "") for field in ("first_name", "last_name", "username", "email")}
        course_ids = {module['course_id'] for module in modules}
        modules = module_details(user, catalog, modules)
        # Include the programme/category ancestors so "Y1" has its proper context.
        courses_by_id = {course["id"]: course for course in catalog["courses"] if "id" in course}
        pending = list(course_ids)
        while pending:
            course = courses_by_id.get(pending.pop())
            parent = course.get("parent_id") if course else None
            if parent and parent not in course_ids:
                course_ids.add(parent)
                pending.append(parent)
        children = {}
        for course in catalog["courses"]:
            if course.get("id") in course_ids:
                parent = course.get("parent_id")
                children.setdefault(parent if parent in course_ids else None, []).append(course)
        for siblings in children.values():
            siblings.sort(key=lambda course: course["name"].casefold())
        courses = []
        pending = list(reversed(children.get(None, [])))
        while pending:
            course = pending.pop()
            courses.append(course)
            pending.extend(reversed(children.get(course["id"], [])))
        return jsonify(student=profile, college={"name": college["name"]}, provider=catalog["provider"],
                       imported_at=catalog["imported_at"], mapping=catalog.get("mapping", "academic"),
                       enrolments_available=catalog.get("enrolments_available", False),
                       courses=courses, modules=modules)

    @app.get("/students/me/modules")
    def search_programme_modules():
        user, _, catalog, profile, modules = student_context()
        query = request.args.get("q", "")
        if len(query) > 200:
            raise ValueError("Search must be at most 200 characters.")
        available = tutor_modules(catalog, modules, profile)
        details = module_details(user, catalog, available, query)
        return jsonify(modules=[{**m, 'can_apply_to_tutor': True} for m in details])

    @app.get("/students/me/modules/<module_id>/tutors")
    def tutors_for_module(module_id):
        user, _, catalog, _, modules = student_context()
        available = programme_modules(catalog, modules)
        if module_id not in {module['id'] for module in available}:
            raise AuthenticationError("Module not found in your programme.", 404)
        manual = colleges.get_manual_academic(user['college_id'])
        manual_tutors = {a['user_id'] for a in manual['assignments']
                         if a.get('user_id') and a['target_type'] == 'module' and a['target_id'] == module_id and a['role'] == 'tutor'}
        return jsonify(tutor_ids=sorted(set(participation.tutors_for_module(user['college_id'], module_id)) | manual_tutors))

    @app.post("/students/me/modules/<module_id>/tutor-application")
    def apply_to_tutor(module_id):
        user, _, catalog, profile, modules = student_context(write=True)
        available = programme_modules(catalog, modules)
        module = next((m for m in available if m['id'] == module_id), None)
        if module is None:
            raise AuthenticationError("Module not found in your programme.", 404)
        if module_id not in {m['id'] for m in tutor_modules(catalog, modules, profile)}:
            raise AuthenticationError("You can only apply to tutor modules from previous years of your programme.", 403)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError("A JSON object is required.")
        grade = data.get("grade")
        if type(grade) not in (int, float) or not 0 <= grade <= 100:
            raise ValueError("Module grade must be a number from 0 to 100.")
        return jsonify(application=participation.apply(user, module, grade))

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

    @app.get("/college/<college_id>/tutor-applications")
    def tutor_applications(college_id):
        authorize(college_id)
        return jsonify(applications=participation.pending(str(uuid.UUID(college_id))))

    @app.post("/college/<college_id>/tutor-applications/<application_id>/review")
    def review_tutor_application(college_id, application_id):
        admin = authorize(college_id)
        data = request.get_json(silent=True)
        decision = data.get("decision") if isinstance(data, dict) else None
        if decision not in ("approved", "rejected"):
            raise ValueError("Decision must be approved or rejected.")
        if decision == 'approved':
            existing = participation.get_application(str(uuid.UUID(college_id)), application_id)
            manual = colleges.get_manual_academic(college_id)
            connection = sync.connections.get(college_id)
            catalog = importer.store.get(college_id, connection['provider'], connection['base_url']) if connection else None
            eligible = existing is not None and (
                manual_application_eligible(existing, manual) or
                (catalog is not None and participation.application_eligible(
                    existing, catalog, importer.store.source_identity(college_id, connection['provider'], connection['base_url']))))
            if not eligible:
                return jsonify(error="The student is no longer eligible to tutor this module in a previous year of their programme."), 409
        application = participation.review(str(uuid.UUID(college_id)), application_id, admin['id'], decision)
        if application is None:
            return jsonify(error="Application not found or already reviewed."), 409
        return jsonify(application=application)

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
