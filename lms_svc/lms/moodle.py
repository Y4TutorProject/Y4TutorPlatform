"""Moodle REST adapter. Credentials are sent in POST bodies and never stored."""
import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from .interfaces import LMSImportError, LMSProvider
from .transport import PublicHTTPSOpener


def records(value):
    if not isinstance(value, list) or len(value) > 50000 or any(not isinstance(record, dict) for record in value):
        raise LMSImportError("Moodle returned invalid records; the import was not saved.")
    return value


def source_id(record, key="id", allow_zero=False):
    value = record[key]
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise LMSImportError("Moodle returned an invalid identifier; the import was not saved.")
    return str(value)


def suspended(user):
    value = user.get("suspended", False)
    if type(value) not in (bool, int) or value not in (0, 1):
        raise LMSImportError("Moodle returned an invalid user status; the import was not saved.")
    return bool(value)


def parent_id(category):
    parent = source_id(category, "parent", allow_zero=True)
    return None if parent == "0" else parent


class MoodleProvider(LMSProvider):
    READ_FUNCTIONS = frozenset({"core_user_get_users", "core_course_get_courses",
                                "core_course_get_categories", "core_course_get_contents", "core_enrol_get_users_courses"})
    def __init__(self, base_url, api_key, mapping="academic", opener=None):
        self.endpoint = base_url + "/webservice/rest/server.php"
        self.api_key = api_key
        self.mapping = mapping
        self.opener = opener or PublicHTTPSOpener()

    def _call(self, function, **parameters):
        if function not in self.READ_FUNCTIONS:
            raise LMSImportError("This Moodle function is not permitted by the read-only integration.")
        if set(parameters) & {"wstoken", "wsfunction", "moodlewsrestformat"}:
            raise LMSImportError("Reserved Moodle request parameters cannot be overridden.")
        body = urlencode({"wstoken": self.api_key, "wsfunction": function,
                          "moodlewsrestformat": "json", **parameters}).encode()
        request = Request(self.endpoint, data=body, method="POST",
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise LMSImportError("Moodle response exceeds the import size limit.")
            data = json.loads(raw)
        except HTTPError as error:
            error.close()
            raise LMSImportError("Moodle rejected the request. Check the API key and service permissions.") from None
        except (URLError, OSError, ValueError, HTTPException):
            raise LMSImportError("Unable to read Moodle data. Check the URL and try again.") from None
        if isinstance(data, dict) and ("exception" in data or "errorcode" in data):
            raise LMSImportError("Moodle rejected the request. Check the API key and service permissions.")
        return data

    def fetch_catalog(self):
        try:
            result = self._call("core_user_get_users", **{
                "criteria[0][key]": "email", "criteria[0][value]": "%",
            })
            if result.get("warnings"):
                raise LMSImportError("Moodle returned warnings; the import was not saved. Check service permissions.")
            users = [{"source_id": source_id(u), "username": u.get("username", ""),
                      "email": u.get("email"), "first_name": u.get("firstname", ""),
                      "last_name": u.get("lastname", ""), "suspended": suspended(u)}
                     # Moodle's built-in guest is not a person and uses the
                     # placeholder address root@localhost.
                     for u in records(result["users"]) if u.get("username") != "guest"]
            moodle_courses = [c for c in records(self._call("core_course_get_courses")) if source_id(c) != "1"]
            if self.mapping == "academic":
                # Many colleges represent programmes with categories and subjects
                # with Moodle courses. Preserve hierarchy rather than flatten it.
                courses = [{"source_id": source_id(c), "name": c["name"],
                            "parent_id": parent_id(c)}
                           for c in records(self._call("core_course_get_categories"))]
                modules = [{"source_id": source_id(c), "name": c["fullname"],
                            "code": c["shortname"], "course_id": source_id(c, "categoryid")}
                           for c in moodle_courses]
            else:
                courses = [{"source_id": source_id(c), "name": c["fullname"], "code": c["shortname"]}
                           for c in moodle_courses]
                modules = []
                for course in courses:
                    sections = self._call("core_course_get_contents", courseid=course["source_id"], **{
                        "options[0][name]": "excludecontents", "options[0][value]": 1,
                    })
                    for section in records(sections):
                        modules.extend({"source_id": source_id(m), "name": m["name"],
                                        "course_id": course["source_id"], "type": m["modname"]}
                                       for m in records(section["modules"]))
            # This function returns active enrolments visible to the integration
            # user, with one lookup per person rather than per module.
            if len(users) > 5000:
                raise LMSImportError("Moodle enrolment import exceeds the supported user limit.")
            known_courses = {source_id(c) for c in moodle_courses}
            enrolments = []
            for user in users:
                if user["suspended"]:
                    continue
                enrolled = records(self._call("core_enrol_get_users_courses", userid=int(user["source_id"]), returnusercount=0))
                seen = set()
                for course in enrolled:
                    course_id = source_id(course)
                    if course_id == "1":
                        continue
                    if course_id not in known_courses or course_id in seen:
                        raise LMSImportError("Moodle returned invalid enrolment relationships; the import was not saved.")
                    seen.add(course_id)
                    enrolments.append({"user_source_id": user["source_id"], "course_source_id": course_id})
                    if len(enrolments) > 500000:
                        raise LMSImportError("Moodle enrolment import exceeds the size limit.")
            return {"users": users, "courses": courses, "modules": modules,
                    "enrolments": enrolments, "enrolments_available": True}
        except (KeyError, TypeError, AttributeError):
            raise LMSImportError("Moodle returned an unexpected data format; the import was not saved.") from None
