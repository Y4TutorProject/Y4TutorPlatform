"""Validated, retryable CSV uploads for college-owned academic records."""
import csv
import io
import re
import uuid

from flask import jsonify, request

from .Objects.Course import Course
from .Objects.Module import Module
from .implementations.academic_svc import text

MAX_BYTES = 1024 * 1024
MAX_ROWS = 1000
HEADERS = {
    'modules': ['course_code', 'course_name', 'module_code', 'module_name', 'year'],
    'users': ['email', 'first_name', 'last_name', 'username', 'course_code', 'year', 'module_code', 'role'],
}


def email_address(value):
    if not isinstance(value, str):
        raise ValueError('A valid email address is required.')
    value = value.strip().casefold()
    if len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value) or any(ord(c) < 32 for c in value):
        raise ValueError('A valid email address is required.')
    return value


def csv_year(value):
    if not re.fullmatch(r'[0-9]{1,2}', value) or not 1 <= int(value) <= 20:
        raise ValueError('Year must be a whole number from 1 to 20.')
    return int(value)


def read_csv(upload, kind):
    if upload is None or not (upload.filename or '').lower().endswith('.csv'):
        raise ValueError('Choose a CSV file.')
    content = upload.stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError('CSV files must be at most 1 MB.')
    try:
        reader = csv.reader(io.StringIO(content.decode('utf-8-sig'), newline=''), strict=True)
        headers = [h.strip().casefold() for h in next(reader)]
        if len(headers) != len(set(headers)) or set(headers) != set(HEADERS[kind]):
            raise ValueError('Use these column headers: ' + ', '.join(HEADERS[kind]) + '.')
        rows = []
        for values in reader:
            if not values or not any(v.strip() for v in values):
                continue
            if len(rows) >= MAX_ROWS:
                raise ValueError('Upload at most 1,000 data rows per file.')
            rows.append((reader.line_num, dict(zip(headers, [v.strip() for v in values]))
                         if len(values) == len(headers) else None))
        if not rows:
            raise ValueError('The CSV file has no data rows.')
        return rows
    except (UnicodeDecodeError, csv.Error):
        raise ValueError('Use a valid UTF-8 CSV file with comma-separated columns.') from None
    except StopIteration:
        raise ValueError('The CSV file is empty.') from None


def field(row, key, maximum, required=True):
    try:
        return text(row[key], maximum, required=required).strip()
    except ValueError:
        raise ValueError(f'{key} must be {"non-empty and " if required else ""}at most {maximum} characters, without control characters.') from None


class CSVImport:
    def __init__(self, store, college_id):
        self.store = store
        self.college_id = college_id
        self.writes = {'courses': {}, 'modules': {}, 'directory_users': {}, 'assignments': {}}
        self.errors = []
        self.preview = []
        self.summary = {}

    def record_id(self, value):
        return str(uuid.uuid5(uuid.UUID(self.college_id), value))

    def add_error(self, line, error):
        self.errors.append({'row': line, 'message': str(error)})

    def validate(self, kind, rows, users=None, domain=None):
        courses = {r['key']: r for r in self.store.courses.find({'college_id': self.college_id})}
        modules = {(r['course_id'], r['year'], r['key']): r for r in self.store.modules.find({'college_id': self.college_id})}
        if kind == 'modules':
            self.summary = {'courses_created': 0, 'modules_created': 0, 'rows_already_present': 0}
            for line, row in rows:
                try:
                    if row is None:
                        raise ValueError('The number of values does not match the column headers.')
                    course_code = field(row, 'course_code', 80)
                    course_name = field(row, 'course_name', 200)
                    module_code = field(row, 'module_code', 80)
                    module_name = field(row, 'module_name', 200)
                    year = csv_year(row['year'])
                    course_key = course_code.casefold()
                    course = courses.get(course_key)
                    if course and (course['name'].casefold() != course_name.casefold() or course.get('code', '').casefold() != course_key):
                        raise ValueError(f'Course code {course_code} is already used by a different course. Use its existing name and code.')
                    if course is None:
                        record_id = self.record_id('csv-course:' + course_key)
                        course = {**Course(record_id, self.college_id, course_name, record_id,
                                           code=course_code, kind='programme').to_dict(), 'key': course_key}
                    module_key = (course['id'], year, module_code.casefold())
                    existing = modules.get(module_key)
                    if existing and (existing['name'].casefold() != module_name.casefold() or existing.get('code', '').casefold() != module_code.casefold()):
                        raise ValueError(f'Module code {module_code} already has a different name in this course year.')
                    # Stage only after every field and relationship in this row is valid.
                    if course_key not in courses:
                        courses[course_key] = course
                        self.writes['courses'][course['id']] = course
                        self.summary['courses_created'] += 1
                    if existing:
                        self.summary['rows_already_present'] += 1
                    else:
                        record_id = self.record_id(f"csv-module:{course['id']}:{year}:{module_code.casefold()}")
                        module = {**Module(record_id, self.college_id, course['id'], module_name, record_id,
                                           code=module_code, programme_id=course['id'], year=year).to_dict(), 'key': module_code.casefold()}
                        modules[module_key] = module
                        self.writes['modules'][record_id] = module
                        self.summary['modules_created'] += 1
                    if len(self.preview) < 25:
                        self.preview.append({'row': line, **row})
                except ValueError as error:
                    self.add_error(line, error)
        else:
            self.validate_users(rows, courses, modules, users or [], domain)
        return self.result()

    def validate_users(self, rows, courses, modules, users, domain):
        registered = {u['email'].strip().casefold(): u for u in users if set(u.get('roles', [])) & {'student', 'tutor'}}
        emails_by_id = {u['id']: email for email, u in registered.items()}
        directory = {r['email']: r for r in self.store.directory.find({'college_id': self.college_id})}
        existing_assignments = {}
        for a in self.store.assignments.find({'college_id': self.college_id}):
            email = a.get('user_email') or emails_by_id.get(a.get('user_id'))
            if email:
                existing_assignments[(email, a['target_type'], a['target_id'], a['role'])] = a
        profiles, incoming_assignments = {}, {}
        self.summary = {'directory_users_created': 0, 'directory_users_updated': 0,
                        'assignments_created': 0, 'assignments_updated': 0, 'awaiting_registration': 0}
        for line, row in rows:
            try:
                if row is None:
                    raise ValueError('The number of values does not match the column headers.')
                email = email_address(row['email'])
                if domain and email.rsplit('@', 1)[1] != domain.casefold():
                    raise ValueError('Use an email address matching your college domain.')
                profile = {'email': email, **{k: field(row, k, 80 if k == 'username' else 200, required=False)
                                               for k in ('first_name', 'last_name', 'username')}}
                if email in profiles and profiles[email] != profile:
                    raise ValueError('Repeated email rows must use the same name and username.')
                role = row['role'].casefold() or 'student'
                if role not in ('student', 'tutor'):
                    raise ValueError('Role must be student or tutor; account administrator roles cannot be imported.')
                assignment = None
                key = None
                if row['course_code']:
                    course = courses.get(row['course_code'].casefold())
                    if not course or course.get('code', '').casefold() != row['course_code'].casefold():
                        raise ValueError('Course code not found. Upload the modules CSV first or create the course.')
                    year = csv_year(row['year'])
                    if row['module_code']:
                        module = modules.get((course['id'], year, row['module_code'].casefold()))
                        if not module or module.get('code', '').casefold() != row['module_code'].casefold():
                            raise ValueError('Module code not found in the specified course year.')
                        kind, target = 'module', module['id']
                    else:
                        if role != 'student':
                            raise ValueError('Tutor assignments require a module code.')
                        kind, target = 'course', course['id']
                    key = (email, kind, target, role)
                    existing = existing_assignments.get(key)
                    user_id = registered.get(email, {}).get('id') or directory.get(email, {}).get('user_id')
                    record_id = existing['id'] if existing else self.record_id(f'csv-assignment:{email}/{kind}/{target}/{role}')
                    assignment = {'id': record_id, 'college_id': self.college_id, 'user_email': email,
                                  'user_id': user_id, 'target_type': kind, 'target_id': target,
                                  'role': role, 'year': year if kind == 'course' else None}
                    if key in incoming_assignments and incoming_assignments[key] != assignment:
                        raise ValueError('Conflicting assignments for this user. Use one current year per course.')
                elif row['module_code'] or row['year'] or role == 'tutor':
                    raise ValueError('Provide a course code for a course or module assignment.')
                if email not in profiles:
                    record_id = self.record_id('csv-user:' + email)
                    record = {'id': record_id, 'college_id': self.college_id, **profile,
                              'user_id': registered.get(email, {}).get('id') or directory.get(email, {}).get('user_id')}
                    old = directory.get(email)
                    if old is None or any(old.get(k) != v for k, v in record.items()):
                        self.writes['directory_users'][record_id] = record
                        self.summary['directory_users_created' if old is None else 'directory_users_updated'] += 1
                    profiles[email] = profile
                    if email not in registered:
                        self.summary['awaiting_registration'] += 1
                if assignment and key not in incoming_assignments:
                    incoming_assignments[key] = assignment
                    old = existing_assignments.get(key)
                    if old is None or any(old.get(k) != v for k, v in assignment.items()):
                        self.writes['assignments'][assignment['id']] = assignment
                        self.summary['assignments_created' if old is None else 'assignments_updated'] += 1
                if len(self.preview) < 25:
                    self.preview.append({'row': line, **row})
            except ValueError as error:
                self.add_error(line, error)

    def result(self):
        return {'valid': not self.errors, 'summary': self.summary, 'preview': self.preview,
                'errors': self.errors[:100], 'error_count': len(self.errors)}

    def apply(self):
        if self.errors:
            raise ValueError('Fix the CSV errors before importing.')
        collections = {'courses': self.store.courses, 'modules': self.store.modules,
                       'directory_users': self.store.directory, 'assignments': self.store.assignments}
        for kind, records in self.writes.items():
            for record_id, record in records.items():
                if kind in ('courses', 'modules'):
                    collections[kind].update_one({'_id': record_id}, {'$setOnInsert': record}, upsert=True)
                else:
                    collections[kind].replace_one({'_id': record_id}, {**record, '_id': record_id}, upsert=True)


def register_csv_import(app, store, authorize):
    @app.before_request
    def csv_size_limit():
        if re.fullmatch(r'/college/[^/]+/academic/import/(modules|users)', request.path):
            request.max_content_length = 2 * MAX_BYTES

    @app.post('/college/<college_id>/academic/import/<kind>')
    def import_csv(college_id, kind):
        college_id = authorize(college_id)
        if kind not in HEADERS:
            return jsonify(error='Choose a modules or users CSV.'), 404
        rows = read_csv(request.files.get('file'), kind)
        dry_run = request.form.get('dry_run', 'true')
        if dry_run not in ('true', 'false'):
            raise ValueError('dry_run must be true or false.')
        users = app.extensions['users_auth'].college_users(request.cookies.get('tutor_session'),
            request.headers.get('User-Agent', ''), college_id) if kind == 'users' else []
        college = app.extensions['college_service'].get_college_by_id(college_id)
        plan = CSVImport(store, college_id)
        result = plan.validate(kind, rows, users, college.college_domain)
        result.update(rows=len(rows), applied=False)
        if dry_run == 'false' and result['valid']:
            plan.apply()
            result['applied'] = True
        return jsonify(**result), 200 if result['valid'] else 422
