"""Platform module memberships and college-reviewed tutor applications."""
from datetime import datetime, timezone
from html import unescape
import uuid
from abc import ABC, abstractmethod

from pymongo import ReturnDocument


class ModuleParticipationStore(ABC):
    @abstractmethod
    def synchronize_user(self, user, roles, source_user_id, import_id):
        """Mirror imported module roles without changing approved Tutor roles."""

    @abstractmethod
    def module_details(self, user, modules, query=''):
        """Read role and application state for the current user."""

    @abstractmethod
    def tutors_for_module(self, college_id, module_id):
        """List platform user IDs with an approved tutor role for a module."""

    @abstractmethod
    def apply(self, user, module, grade):
        """Submit a module-specific tutor application."""

    @abstractmethod
    def get_application(self, college_id, application_id):
        """Read one college-scoped application for eligibility checks."""

    @abstractmethod
    def pending(self, college_id):
        """List the owning college's pending applications."""

    @abstractmethod
    def review(self, college_id, application_id, admin_id, decision):
        """Review an application and persist approved module membership."""

    @abstractmethod
    def refresh_import(self, document, academic):
        """Reconcile known user memberships after a new import."""

    @abstractmethod
    def application_eligible(self, application, catalog, import_id):
        """Recheck an applicant against the current canonical import."""


class ModuleParticipation(ModuleParticipationStore):
    def __init__(self, database):
        self.memberships = database['module_memberships']
        self.applications = database['tutor_applications']
        self.memberships.create_index([('college_id', 1), ('user_id', 1), ('module_id', 1)], unique=True)
        self.applications.create_index([('college_id', 1), ('user_id', 1), ('module_id', 1)], unique=True)

    @staticmethod
    def identity(college_id, user_id, module_id):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f'{college_id}/{user_id}/{module_id}'))

    def synchronize_user(self, user, module_roles, source_user_id, import_id):
        """Refresh LMS Student/Lecturer roles, retaining independently approved Tutor."""
        scope = {'college_id': user['college_id'], 'user_id': user['id']}
        self.memberships.update_many(scope, {'$pull': {'roles': {'$in': ['student', 'lecturer']}}})
        for module_id, roles in module_roles.items():
            if not roles:
                continue
            self.memberships.update_one(
                {'_id': self.identity(user['college_id'], user['id'], module_id)},
                {'$set': {**scope, 'module_id': module_id, 'source_user_id': source_user_id,
                          'import_id': import_id}, '$addToSet': {'roles': {'$each': sorted(roles)}}}, upsert=True)

    def refresh_import(self, document, academic):
        """Refresh linked accounts' canonical roles when any provider synchronizes."""
        profiles = {u['source_id']: u for u in document['users']}
        accounts = {m['user_id']: m['source_user_id'] for m in self.memberships.find(
            {'college_id': document['college_id'], 'import_id': document['_id']})}
        for user_id, source_user_id in accounts.items():
            profile = profiles.get(source_user_id)
            roles = enrolment_roles({**document, **academic}, source_user_id) if profile and not profile.get('suspended') else {}
            self.synchronize_user({'college_id': document['college_id'], 'id': user_id},
                                  roles, source_user_id, document['_id'])

    def module_details(self, user, modules, query=''):
        scope = {'college_id': user['college_id'], 'user_id': user['id']}
        memberships = {m['module_id']: m.get('roles', []) for m in self.memberships.find(scope)}
        applications = {a['module_id']: a['status'] for a in self.applications.find(scope)}
        query = unescape(query).casefold().strip()
        return [{**module, 'display_name': unescape(module['name']),
                 'display_code': unescape(module.get('code', '')), 'roles': memberships.get(module['id'], []),
                 'application_status': applications.get(module['id'])}
                for module in modules if query in unescape(f"{module['name']} {module.get('code', '')}").casefold()]

    def tutors_for_module(self, college_id, module_id):
        """List platform user IDs with an approved tutor role for a module."""
        memberships = self.memberships.find(
            {'college_id': college_id, 'module_id': module_id, 'roles': 'tutor'},
            {'_id': 0, 'user_id': 1})
        return sorted(membership['user_id'] for membership in memberships)

    def apply(self, user, module, grade):
        now = datetime.now(timezone.utc).isoformat()
        application_id = self.identity(user['college_id'], user['id'], module['id'])
        # An application is idempotent and never grants a role by itself.
        data = {'college_id': user['college_id'], 'user_id': user['id'],
                'username': user['username'], 'module_id': module['id'],
                'module_name': module['name'], 'status': 'pending', 'grade': grade,
                'submitted_at': now}
        self.applications.update_one({'_id': application_id}, {'$setOnInsert': data}, upsert=True)
        return self.public(self.applications.find_one({'_id': application_id}))

    @staticmethod
    def public(application):
        return {**{k: v for k, v in application.items() if k != '_id'},
                'module_name': unescape(application['module_name']), 'id': application['_id']}

    def get_application(self, college_id, application_id):
        return self.applications.find_one({'_id': application_id, 'college_id': college_id})

    def pending(self, college_id):
        return [self.public(a) for a in self.applications.find({'college_id': college_id, 'status': 'pending'})]

    def application_eligible(self, application, catalog, import_id):
        sources = {m['source_user_id'] for m in self.memberships.find({
            'college_id': application['college_id'], 'user_id': application['user_id'],
            'import_id': import_id})}
        if len(sources) != 1:
            return False
        source_id = sources.pop()
        profile = next((u for u in catalog['users'] if u['source_id'] == source_id), None)
        if profile is None or profile.get('suspended'):
            return False
        roles = enrolment_roles(catalog, source_id)
        enrolled = [m for m in catalog['modules'] if 'student' in roles.get(m['id'], set())]
        return application['module_id'] in {m['id'] for m in tutor_modules(catalog, enrolled, profile)}

    def review(self, college_id, application_id, admin_id, decision):
        application = self.applications.find_one_and_update(
            {'_id': application_id, 'college_id': college_id, 'status': {'$in': ['pending', decision]}},
            {'$set': {'status': decision, 'reviewed_by': admin_id,
                      'reviewed_at': datetime.now(timezone.utc).isoformat()}},
            return_document=ReturnDocument.AFTER)
        if application is None:
            return None
        if decision == 'approved':
            self.memberships.update_one(
                {'_id': self.identity(college_id, application['user_id'], application['module_id'])},
                {'$set': {'college_id': college_id, 'user_id': application['user_id'],
                          'module_id': application['module_id']}, '$addToSet': {'roles': 'tutor'}}, upsert=True)
        return self.public(application)


def enrolment_roles(catalog, source_user_id):
    """Expand canonical course/module enrolments without provider-specific rules."""
    result = {}
    modules_by_course = {}
    for module in catalog['modules']:
        modules_by_course.setdefault(module['course_id'], []).append(module['id'])
    for link in catalog.get('enrolments', []):
        if link['user_source_id'] != source_user_id:
            continue
        targets = [link['target_id']] if link['target_type'] == 'module' else modules_by_course.get(link['target_id'], [])
        for target in targets:
            result.setdefault(target, set()).update(link.get('roles', ['student']))
    return result


def academic_position(catalog, module, courses=None):
    """Read canonical programme/year metadata; never infer provider hierarchy."""
    return module.get('programme_id', module['course_id']), module.get('year')


def programme_modules(catalog, enrolled_modules):
    programmes = {academic_position(catalog, m)[0] for m in enrolled_modules}
    return [m for m in catalog['modules'] if academic_position(catalog, m)[0] in programmes]


def tutor_modules(catalog, enrolled_modules, student_profile=None):
    """Allow all earlier years within the same programme.

    Providers can supply an explicit profile current_year; otherwise the highest
    enrolled year per programme is used. Unknown years never grant eligibility.
    """
    positions = {}
    def position(module):
        if module['id'] not in positions:
            positions[module['id']] = academic_position(catalog, module)
        return positions[module['id']]
    current_years = {}
    for module in enrolled_modules:
        programme_id, year = position(module)
        if year is not None:
            current_years[programme_id] = max(current_years.get(programme_id, 0), year)
    if student_profile is not None and 'current_year' in student_profile:
        if student_profile['current_year'] is None:
            return []
        programmes = {position(m)[0] for m in enrolled_modules}
        current_years = {programme: student_profile['current_year'] for programme in programmes}
    eligible = []
    for module in programme_modules(catalog, enrolled_modules):
        programme_id, year = position(module)
        if year is not None and year < current_years.get(programme_id, 0):
            eligible.append(module)
    return eligible


def module_lecturers(catalog):
    """Return only modules with one uniquely identified, active lecturer."""
    candidates = {}
    for profile in catalog['users']:
        if profile.get('suspended'):
            continue
        for module_id, roles in enrolment_roles(catalog, profile['source_id']).items():
            if 'lecturer' in roles:
                candidates.setdefault(module_id, set()).add(profile['source_id'])
    return {module_id: next(iter(people)) for module_id, people in candidates.items() if len(people) == 1}
