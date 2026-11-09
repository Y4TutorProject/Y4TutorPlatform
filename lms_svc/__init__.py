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

import logging

def create_app(config=None, database=None, auth_client=None, college_client=None):
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
    importer = LMSImportService(MongoLMSImportStore(database, colleges), app.config["LMS_ALLOWED_HOSTS"].split(","),
                                private_hosts=app.config["LMS_PRIVATE_HOSTS"].split(",") if app.config["DEV_MODE"] else (),
                                ca_file=app.config["LMS_CA_FILE"] if app.config["DEV_MODE"] else None)
    sync = LMSSyncService(importer, MongoConnectionStore(database), app.config["LMS_ENCRYPTION_KEY"], colleges,
                          app.config["LMS_SYNC_TIMEZONE"], app.config["LMS_SYNC_HOUR"])
    app.extensions.update(lms_service=importer, lms_sync=sync, lms_database=database)

    @app.get("/students/me")
    def student_information():
        user = auth.authenticate(request.cookies.get("tutor_session"), request.headers.get("User-Agent", ""))
        if "student" not in user.get("roles", []):
            raise AuthenticationError("Student access required.", 403)
        college_id = user.get("college_id")
        college = colleges.get_college(college_id) if college_id else None
        if college is None:
            return jsonify(error="Your college is not available."), 404
        connection = sync.connections.get(college_id)
        catalog = importer.store.get(college_id, connection["provider"], connection["base_url"]) if connection else None
        if not catalog:
            return jsonify(error="Your college has not imported Moodle information yet."), 404
        # The verified account's college and email are the only lookup keys.
        # Never accept a requested email or return the college user directory.
        matches = [record for record in catalog["users"]
                   if record.get("email") and record["email"].strip().casefold() == user["email"].strip().casefold()]
        if len(matches) != 1 or matches[0].get("suspended"):
            return jsonify(error="No active Moodle profile matches your verified email address."), 404
        profile = {field: matches[0].get(field, "") for field in ("first_name", "last_name", "username", "email")}
        links = [entry for entry in catalog.get("enrolments", []) if entry["user_source_id"] == matches[0]["source_id"]]
        targets = {entry["target_id"] for entry in links}
        if catalog.get("mapping", "academic") == "academic":
            modules = [module for module in catalog["modules"] if module.get("id") in targets]
            course_ids = {module["course_id"] for module in modules}
        else:
            course_ids = targets
            modules = [module for module in catalog["modules"] if module["course_id"] in course_ids]
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
        # get tutors
        tutors = None
        if request.args.get("tutors", "true") != 'false' and catalog.get("enrolments_available", False):
            try:
                tutors = find_my_tutors(college_id, catalog, modules, USERS_API_URL=app.config["USERS_API_URL"])
            except CollegeServiceUnavailable:
                tutors = None
        # ------
        return jsonify(student=profile, college={"name": college["name"]},
                       imported_at=catalog["imported_at"], mapping=catalog.get("mapping", "academic"),
                       enrolments_available=catalog.get("enrolments_available", False),
                       courses=courses, modules=modules, tutors=tutors)


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



def find_my_tutors(college_id, catalog, modules, USERS_API_URL):
    LEVELS_UP = 10   # how far up the category tree counts as "my department"; 10 = the top-level category
    courses_by_id = {c["id"]: c for c in catalog["courses"] if "id" in c}
    # start at my modules' courses and climb up
    my_depts = set()
    for course_id in {m["course_id"] for m in modules}:
        for _ in range(LEVELS_UP):
            parent = courses_by_id.get(course_id, {}).get("parent_id")
            if parent not in courses_by_id:
                break
            course_id = parent
        my_depts.add(course_id)
    # 2. Everything underneath my department, at any depth (all years, all programmes)
    dept_ids = set(my_depts)
    changed = True
    while changed:
        changed = False
        for c in catalog["courses"]:
            if c.get("parent_id") in dept_ids and c.get("id") not in dept_ids:
                dept_ids.add(c["id"])
                changed = True

    enrolled = {}
    for e in catalog.get("enrolments", []):
        enrolled.setdefault(e["user_source_id"], set()).add(e["target_id"])
    module_course = {m["id"]: m["course_id"] for m in catalog["modules"]}
    by_email = {r["email"].strip().casefold(): r for r in catalog["users"]
                if r.get("email") and not r.get("suspended")}

    request_headers = {"X-Internal-Token": os.getenv("INTERNAL_API_TOKEN", "")}
    try:
        response = requests.get(f"{USERS_API_URL}/tutors", params={"college_id": college_id},
                                timeout=5, headers=request_headers)
    except requests.RequestException:
        return []
    if response.status_code != 200:
        return []
    tutors = response.json().get("tutors", [])

    result = []
    for t in tutors:
        profile = by_email.get((t.get("email") or "").strip().casefold())
        if not profile:
            continue
        theirs = enrolled.get(profile["source_id"], set())
        if {module_course.get(m) for m in theirs} & dept_ids:
            result.append({"id": t["id"], "username": t["username"],
                           "first_name": profile.get("first_name", ""),
                           "last_name": profile.get("last_name", "")})
    return result