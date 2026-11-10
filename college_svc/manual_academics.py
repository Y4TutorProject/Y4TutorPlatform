"""College-owned manual courses, modules and enrolments, independent of LMS sync."""
import hmac
import uuid

from flask import jsonify, request
from pymongo.errors import DuplicateKeyError

from .auth import AuthenticationError
from .Objects.Course import Course
from .Objects.Module import Module
from .Objects.CollegeStatus import CollegeStatus
from .implementations.academic_svc import text


def identifier(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('A valid record ID is required.') from None


def year(value):
    if type(value) is not int or not 1 <= value <= 20:
        raise ValueError('Year must be a whole number from 1 to 20.')
    return value


class ManualAcademics:
    def __init__(self, database):
        self.courses = database['manual_courses']
        self.modules = database['manual_modules']
        self.assignments = database['manual_assignments']
        self.courses.create_index([('college_id', 1), ('key', 1)], unique=True)
        self.modules.create_index([('college_id', 1), ('course_id', 1), ('year', 1), ('key', 1)], unique=True)

    @staticmethod
    def public(record):
        return {k: v for k, v in record.items() if k not in ('_id', 'key')}

    def catalog(self, college_id):
        return {name: [self.public(row) for row in collection.find({'college_id': college_id}).sort('name', 1)]
                for name, collection in [('courses', self.courses), ('modules', self.modules),
                                         ('assignments', self.assignments)]}

    def create_course(self, college_id, data):
        name = text(data.get('name'), 200).strip()
        code = text(data.get('code', ''), 80, required=False).strip()
        record_id = str(uuid.uuid4())
        record = Course(record_id, college_id, name, record_id, code=code, kind='programme').to_dict()
        self.courses.insert_one({**record, '_id': record_id, 'key': (code or name).casefold()})
        return record

    def create_module(self, college_id, data):
        course_id = identifier(data.get('course_id'))
        if not self.courses.find_one({'id': course_id, 'college_id': college_id}):
            raise ValueError('Choose a course from this college.')
        name = text(data.get('name'), 200).strip()
        code = text(data.get('code', ''), 80, required=False).strip()
        record_id = str(uuid.uuid4())
        record = Module(record_id, college_id, course_id, name, record_id, code=code,
                        programme_id=course_id, year=year(data.get('year'))).to_dict()
        self.modules.insert_one({**record, '_id': record_id, 'key': (code or name).casefold()})
        return record

    def assign(self, college_id, data, users):
        user_id = identifier(data.get('user_id'))
        kind, role = data.get('target_type'), data.get('role')
        if kind not in ('course', 'module') or role not in ('student', 'tutor') or (kind == 'course' and role != 'student'):
            raise ValueError('Assign students to courses or modules, and tutors to modules.')
        allowed_roles = {'student'} if role == 'student' else {'student', 'tutor'}
        if not any(u['id'] == user_id and allowed_roles.intersection(u.get('roles', [])) for u in users):
            raise ValueError('Choose an active student or tutor account from this college for this assignment.')
        target_id = identifier(data.get('target_id'))
        collection = self.courses if kind == 'course' else self.modules
        if not collection.find_one({'id': target_id, 'college_id': college_id}):
            raise ValueError('Choose a record from this college.')
        record_id = str(uuid.uuid5(uuid.UUID(college_id), f'{user_id}/{kind}/{target_id}/{role}'))
        record = {'id': record_id, 'college_id': college_id, 'user_id': user_id,
                  'target_type': kind, 'target_id': target_id, 'role': role,
                  'year': year(data.get('year')) if kind == 'course' else None}
        self.assignments.replace_one({'_id': record_id}, {**record, '_id': record_id}, upsert=True)
        return record


def register_manual_academics(app, database):
    store = ManualAcademics(database)
    app.extensions['manual_academics'] = store

    def authorize(college_id):
        user = app.extensions['users_auth'].verify(request.cookies.get('tutor_session'),
            request.headers.get('User-Agent', ''), request.headers.get('X-CSRFToken'))
        college_id = identifier(college_id)
        college = app.extensions['college_service'].get_college_by_id(college_id)
        if ('college_admin' not in user.get('roles', []) or not college or
                college.status != CollegeStatus.ACTIVE or str(college.admin_id) != user['id']):
            raise AuthenticationError('College administrator access required.', 403)
        return college_id

    @app.route('/college/<college_id>/academic', methods=['GET'])
    @app.route('/college/<college_id>/academic/<kind>', methods=['POST'])
    @app.route('/college/<college_id>/academic/assignments/<assignment_id>', methods=['DELETE'])
    def manage(college_id, kind=None, assignment_id=None):
        college_id = authorize(college_id)
        if request.method == 'GET':
            return jsonify(**store.catalog(college_id))
        if request.method == 'DELETE':
            result = store.assignments.delete_one({'id': identifier(assignment_id), 'college_id': college_id})
            return (jsonify(message='Assignment removed.'), 200) if result.deleted_count else (jsonify(error='Assignment not found.'), 404)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('A JSON object is required.')
        if kind == 'courses':
            return jsonify(course=store.create_course(college_id, data)), 201
        if kind == 'modules':
            return jsonify(module=store.create_module(college_id, data)), 201
        if kind == 'assignments':
            users = app.extensions['users_auth'].college_users(request.cookies.get('tutor_session'),
                request.headers.get('User-Agent', ''), college_id)
            return jsonify(assignment=store.assign(college_id, data, users)), 201
        return jsonify(error='Academic resource not found.'), 404

    @app.get('/internal/college/<college_id>/manual-academic')
    def internal(college_id):
        token = app.config['COLLEGE_SYNC_TOKEN']
        if not token or not hmac.compare_digest(token.encode(), request.headers.get('X-College-Sync-Token', '').encode()):
            return jsonify(error='Service authentication required.'), 401
        college_id = identifier(college_id)
        college = app.extensions['college_service'].get_college_by_id(college_id)
        if not college or college.status != CollegeStatus.ACTIVE:
            return jsonify(error='College not found.'), 404
        return jsonify(catalog={'college_id': college_id, **store.catalog(college_id)})

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(DuplicateKeyError)
    def duplicate(error):
        return jsonify(error='A record with that name or code already exists.'), 409

    @app.after_request
    def no_cache(response):
        response.headers['Cache-Control'] = 'no-store'
        return response
