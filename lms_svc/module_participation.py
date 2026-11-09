"""Platform module memberships and college-reviewed tutor applications."""
from datetime import datetime, timezone
from html import unescape
import uuid
import re

from pymongo import ReturnDocument


class ModuleParticipation:
    def __init__(self, database):
        self.memberships = database['module_memberships']
        self.applications = database['tutor_applications']
        self.memberships.create_index([('college_id', 1), ('user_id', 1), ('module_id', 1)], unique=True)
        self.applications.create_index([('college_id', 1), ('user_id', 1), ('module_id', 1)], unique=True)

    @staticmethod
    def identity(college_id, user_id, module_id):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f'{college_id}/{user_id}/{module_id}'))

    def synchronize_student(self, user, module_ids, source_user_id, import_id):
        """Refresh the Student role from the current authenticated Moodle snapshot.

        Retain independently approved Tutor roles when enrolments change.
        """
        scope = {'college_id': user['college_id'], 'user_id': user['id']}
        self.memberships.update_many({**scope, 'module_id': {'$nin': list(module_ids)}},
                                     {'$pull': {'roles': 'student'}})
        for module_id in module_ids:
            self.memberships.update_one(
                {'_id': self.identity(user['college_id'], user['id'], module_id)},
                {'$set': {**scope, 'module_id': module_id, 'source_user_id': source_user_id,
                          'import_id': import_id}, '$addToSet': {'roles': 'student'}}, upsert=True)

    def refresh_import(self, document, academic):
        """Refresh linked accounts' Student memberships when Moodle synchronizes."""
        profiles = {u['source_id']: u for u in document['users']}
        accounts = {m['user_id']: m['source_user_id'] for m in self.memberships.find(
            {'college_id': document['college_id'], 'import_id': document['_id']})}
        for user_id, source_user_id in accounts.items():
            profile = profiles.get(source_user_id)
            targets = {link['target_id'] for link in document['enrolments']
                       if link['user_source_id'] == source_user_id}
            if document['mapping'] == 'academic':
                module_ids = targets
            else:
                module_ids = {m['id'] for m in academic['modules'] if m['course_id'] in targets}
            if not profile or profile.get('suspended'):
                module_ids = set()
            self.synchronize_student({'college_id': document['college_id'], 'id': user_id},
                                     module_ids, source_user_id, document['_id'])

    def module_details(self, user, modules, query=''):
        scope = {'college_id': user['college_id'], 'user_id': user['id']}
        memberships = {m['module_id']: m.get('roles', []) for m in self.memberships.find(scope)}
        applications = {a['module_id']: a['status'] for a in self.applications.find(scope)}
        query = unescape(query).casefold().strip()
        return [{**module, 'display_name': unescape(module['name']),
                 'display_code': unescape(module.get('code', '')), 'roles': memberships.get(module['id'], []),
                 'application_status': applications.get(module['id'])}
                for module in modules if query in unescape(f"{module['name']} {module.get('code', '')}").casefold()]

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
        targets = {e['target_id'] for e in catalog.get('enrolments', []) if e['user_source_id'] == source_id}
        enrolled = [m for m in catalog['modules'] if m['id'] in targets]
        return application['module_id'] in {m['id'] for m in tutor_modules(catalog, enrolled)}

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


def programme_modules(catalog, enrolled_modules):
    """Expand current enrolments to programmes and every year beneath them.

    Academic mapping uses department -> programme -> year categories. A flat
    catalogue treats its sole category level as the programme.
    """
    courses = {c['id']: c for c in catalog['courses']}
    programme_ids = set()
    for module in enrolled_modules:
        path, seen = [], set()
        current = module['course_id']
        while current in courses and current not in seen:
            seen.add(current)
            path.append(current)
            current = courses[current].get('parent_id')
        path.reverse()
        if path:
            programme_ids.add(path[1] if len(path) > 1 else path[0])
    allowed = set(programme_ids)
    while True:
        children = {c['id'] for c in catalog['courses'] if c.get('parent_id') in allowed}
        expanded = allowed | children
        if expanded == allowed:
            break
        allowed = expanded
    return [m for m in catalog['modules'] if m['course_id'] in allowed]


def academic_position(catalog, module, courses=None):
    """Resolve programme and year from department/programme/year categories."""
    if courses is None:
        courses = {c['id']: c for c in catalog['courses']}
    path, seen = [], set()
    current = module['course_id']
    while current in courses and current not in seen:
        seen.add(current)
        path.append(courses[current])
        current = courses[current].get('parent_id')
    path.reverse()
    if not path:
        return None, None
    programme_id = path[1]['id'] if len(path) > 1 else path[0]['id']
    for category in reversed(path):
        match = re.fullmatch(r'(?:y|year|stage)\s*[-_]?\s*([1-9][0-9]?)',
                             unescape(category['name']).strip(), re.IGNORECASE)
        if match:
            return programme_id, int(match.group(1))
    return programme_id, None


def tutor_modules(catalog, enrolled_modules):
    """Allow all earlier years within the same programme.

    The highest enrolled year in each programme is the student's current year.
    Unknown years never grant eligibility.
    """
    courses = {c['id']: c for c in catalog['courses']}
    positions = {}
    def position(module):
        if module['course_id'] not in positions:
            positions[module['course_id']] = academic_position(catalog, module, courses)
        return positions[module['course_id']]
    current_years = {}
    for module in enrolled_modules:
        programme_id, year = position(module)
        if year is not None:
            current_years[programme_id] = max(current_years.get(programme_id, 0), year)
    eligible = []
    for module in programme_modules(catalog, enrolled_modules):
        programme_id, year = position(module)
        if year is not None and year < current_years.get(programme_id, 0):
            eligible.append(module)
    return eligible
