"""Moodle REST adapter. Credentials are sent in POST bodies and never stored."""
import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request

from .interfaces import LMSImportError, LMSProvider
from .transport import PublicHTTPSOpener
from .moodle_mapping import MoodleCatalogMapper


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
    label = "Moodle"
    mapping_modes = ("academic", "activities")

    @classmethod
    def configuration(cls):
        return {"label": cls.label, "fields": MoodleCatalogMapper.fields()}

    @classmethod
    def validate_options(cls, options):
        return MoodleCatalogMapper.validate_options(options)

    @classmethod
    def options_for_mapping(cls, mapping, options):
        if options is None and mapping == 'activities':
            options = {'module_source': 'activities', 'programme_source': 'moodle_course'}
        return cls.validate_options(options)

    @classmethod
    def build(cls, base_url, api_key, mapping, options, transport):
        return cls(base_url, api_key, mapping=mapping, options=options, opener=transport)

    READ_FUNCTIONS = frozenset({"core_user_get_users", "core_course_get_courses",
                                "core_course_get_categories", "core_course_get_contents", "core_enrol_get_users_courses", "core_enrol_get_enrolled_users"})
    def __init__(self, base_url, api_key, mapping="academic", opener=None, options=None):
        self.endpoint = base_url + "/webservice/rest/server.php"
        self.api_key = api_key
        if options is None and mapping == 'activities':
            options = {'module_source': 'activities', 'programme_source': 'moodle_course'}
        self.options = self.validate_options(options)
        self.mapper = MoodleCatalogMapper(self.options)
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
                      "last_name": u.get("lastname", ""), "suspended": suspended(u),
                      "customfields": u.get("customfields", []), "idnumber": u.get("idnumber")}
                     # Moodle's built-in guest is not a person and uses the
                     # placeholder address root@localhost.
                     for u in records(result["users"]) if u.get("username") != "guest"]
            moodle_courses = [c for c in records(self._call("core_course_get_courses")) if source_id(c) != "1"]
            categories = records(self._call("core_course_get_categories"))
            for category in categories:
                source_id(category)
                parent_id(category)
            activities = {}
            if self.options['module_source'] == 'activities':
                for course in moodle_courses:
                    sections = self._call("core_course_get_contents", courseid=source_id(course), **{
                        "options[0][name]": "excludecontents", "options[0][value]": 1,
                    })
                    activities[source_id(course)] = []
                    for section in records(sections):
                        for activity in records(section['modules']):
                            source_id(activity)
                            activities[source_id(course)].append({**activity, 'section_name': section.get('name', '')})
            known_users = {u['source_id']: u for u in users}
            known_courses = {source_id(c) for c in moodle_courses}
            enrolments = []
            if self.options['role_source'] == 'course_roles':
                if len(moodle_courses) > 5000:
                    raise LMSImportError("Moodle role import exceeds the supported course limit.")
                for course in moodle_courses:
                    seen, offset = set(), 0
                    while True:
                        participants = records(self._call('core_enrol_get_enrolled_users', courseid=course['id'], **{
                            'options[0][name]': 'onlyactive', 'options[0][value]': 1,
                            'options[1][name]': 'limitfrom', 'options[1][value]': offset,
                            'options[2][name]': 'limitnumber', 'options[2][value]': 200,
                        }))
                        for participant in participants:
                            user_id = source_id(participant)
                            if user_id in seen or user_id not in known_users:
                                raise LMSImportError("Moodle returned incomplete or duplicate course participants.")
                            seen.add(user_id)
                            if known_users[user_id]['suspended']:
                                continue
                            role_names = {role['shortname'] for role in records(participant['roles'])}
                            roles = [role for role, configured in (
                                ('student', self.options['student_roles']), ('lecturer', self.options['lecturer_roles']))
                                if role_names.intersection(configured)]
                            if roles:
                                enrolments.append({'user_source_id': user_id, 'course_source_id': source_id(course), 'roles': roles})
                                if len(enrolments) > 500000:
                                    raise LMSImportError('Moodle enrolment import exceeds the size limit.')
                        if len(participants) < 200:
                            break
                        offset += 200
                        if offset >= 50000:
                            raise LMSImportError("Moodle course participant import exceeds the supported limit.")
            else:
                if len(users) > 5000:
                    raise LMSImportError("Moodle enrolment import exceeds the supported user limit.")
                for user in users:
                    if user['suspended']:
                        continue
                    enrolled = records(self._call("core_enrol_get_users_courses", userid=int(user['source_id']), returnusercount=0))
                    seen = set()
                    for course in enrolled:
                        course_id = source_id(course)
                        if course_id == '1':
                            continue
                        if course_id not in known_courses or course_id in seen:
                            raise LMSImportError("Moodle returned invalid enrolment relationships; the import was not saved.")
                        seen.add(course_id)
                        enrolments.append({'user_source_id': user['source_id'], 'course_source_id': course_id, 'roles': ['student']})
                        if len(enrolments) > 500000:
                            raise LMSImportError('Moodle enrolment import exceeds the size limit.')
            if len(enrolments) > 500000:
                raise LMSImportError("Moodle enrolment import exceeds the size limit.")
            return self.mapper.map_catalog({'users': users, 'moodle_courses': moodle_courses,
                                            'categories': categories, 'activities': activities, 'enrolments': enrolments})
        except (KeyError, TypeError, AttributeError):
            raise LMSImportError("Moodle returned an unexpected data format; the import was not saved.") from None
