"""Configurable Moodle semantics, isolated from the platform's academic domain."""
from html import unescape
import re
from hashlib import sha256

from .interfaces import LMSCatalogMapper, LMSImportError


DEFAULT_YEAR_LABELS = {label: year for year in range(1, 21)
                       for label in (f'Y{year}', f'Year {year}', f'Stage {year}', str(year))}


class MoodleCatalogMapper(LMSCatalogMapper):
    @staticmethod
    def fields():
        return [
            {'name': 'module_source', 'label': 'A platform module is', 'type': 'select', 'default': 'courses',
             'choices': {'courses': 'A Moodle course', 'activities': 'An activity inside a Moodle course'}},
            {'name': 'programme_source', 'label': 'A platform course/programme is defined by', 'type': 'select', 'default': 'category',
             'choices': {'category': 'Category at a chosen depth', 'course_field': 'Course field or custom field', 'moodle_course': 'The Moodle course itself (activity modules)'}},
            {'name': 'programme_category_depth', 'label': 'Programme category depth (1 = top level)', 'type': 'integer', 'default': 2, 'min': 1, 'max': 20},
            {'name': 'programme_field', 'label': 'Programme field/custom-field shortname', 'type': 'text', 'default': 'programme'},
            {'name': 'department_category_depth', 'label': 'Department category depth (0 = none)', 'type': 'integer', 'default': 1, 'min': 0, 'max': 20},
            {'name': 'year_source', 'label': 'Academic year is defined by', 'type': 'select', 'default': 'category_name',
             'choices': {'category_name': 'Recognized label in category ancestry', 'category_depth': 'Category at a chosen depth', 'course_field': 'Course field or custom field', 'activity_section': 'Activity section/topic name', 'none': 'No academic year available'}},
            {'name': 'year_category_depth', 'label': 'Year category depth (1 = top level)', 'type': 'integer', 'default': 3, 'min': 1, 'max': 20},
            {'name': 'year_field', 'label': 'Year field/custom-field shortname', 'type': 'text', 'default': 'year'},
            {'name': 'year_labels', 'label': 'Year labels → year numbers (JSON object)', 'type': 'json', 'default': DEFAULT_YEAR_LABELS},
            {'name': 'current_year_source', 'label': "Student's current year is defined by", 'type': 'select', 'default': 'enrolments',
             'choices': {'enrolments': 'Highest enrolled module year', 'profile_field': 'Moodle user profile field'}},
            {'name': 'current_year_field', 'label': 'Current year user-profile field shortname', 'type': 'text', 'default': 'current_year'},
            {'name': 'role_source', 'label': 'Student and lecturer roles are defined by', 'type': 'select', 'default': 'course_roles',
             'choices': {'enrolments': 'Treat enrolments as Student (legacy)', 'course_roles': 'Moodle course role shortnames'}},
            {'name': 'student_roles', 'label': 'Moodle Student role shortnames (comma separated)', 'type': 'list', 'default': ['student']},
            {'name': 'lecturer_roles', 'label': 'Moodle Lecturer role shortnames (comma separated)', 'type': 'list', 'default': ['editingteacher', 'teacher']},
        ]

    @classmethod
    def validate_options(cls, options):
        if options is None:
            options = {}
        if not isinstance(options, dict) or set(options) - {f['name'] for f in cls.fields()}:
            raise ValueError('Unknown Moodle mapping option.')
        result = {}
        for field in cls.fields():
            value = options.get(field['name'], field['default'])
            kind = field['type']
            if kind == 'select' and (not isinstance(value, str) or value not in field['choices']):
                raise ValueError('Choose a supported value for ' + field['label'] + '.')
            if kind == 'integer' and (type(value) is not int or not field['min'] <= value <= field['max']):
                raise ValueError('Invalid value for ' + field['label'] + '.')
            if kind == 'text' and (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,99}', value)):
                raise ValueError('Field shortnames must contain letters, numbers or underscores.')
            if kind == 'list':
                if not isinstance(value, list) or len(value) > 30 or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', v) for v in value):
                    raise ValueError('Enter valid role shortnames for ' + field['label'] + '.')
                value = sorted(set(value))
            if kind == 'json':
                if not isinstance(value, dict) or len(value) > 200 or any(not isinstance(k, str) or not 1 <= len(k) <= 100 or type(v) is not int or not 1 <= v <= 20 for k, v in value.items()):
                    raise ValueError('Year labels must map text labels to whole years from 1 to 20.')
            result[field['name']] = value
        normalized_labels = {}
        for label, year in result['year_labels'].items():
            normalized = cls.label(label)
            if not normalized:
                raise ValueError('Year labels must not be blank.')
            if normalized in normalized_labels and normalized_labels[normalized] != year:
                raise ValueError('Year labels must not assign conflicting years to the same label.')
            normalized_labels[normalized] = year
        if set(result['student_roles']) & set(result['lecturer_roles']):
            raise ValueError('Student and lecturer role shortnames must not overlap.')
        if result['year_source'] == 'activity_section' and result['module_source'] != 'activities':
            raise ValueError('Section/topic years require activity modules.')
        if result['programme_source'] == 'moodle_course' and result['module_source'] != 'activities':
            raise ValueError('Moodle courses can define programmes when modules are activities.')
        return result

    def __init__(self, options):
        self.options = self.validate_options(options)
        self.years = {self.label(k): v for k, v in self.options['year_labels'].items()}

    @staticmethod
    def label(value):
        return unescape(str(value)).strip().casefold()

    @staticmethod
    def field(course, shortname):
        if shortname in ('fullname', 'shortname', 'idnumber'):
            value = course.get(shortname)
        else:
            value = next((f.get('valueraw', f.get('value')) for f in course.get('customfields', []) if f.get('shortname') == shortname), None)
        if not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value).strip() or len(str(value)) > 1000:
            raise LMSImportError('A configured Moodle course field is missing or invalid; the import was not saved.')
        return unescape(str(value)).strip()

    def map_catalog(self, raw):
        options = self.options
        categories = {str(c['id']): c for c in raw['categories']}
        courses = {key: {'source_id': key, 'name': c['name'],
                         'parent_id': str(c['parent']) if c['parent'] else None, 'kind': 'category'}
                   for key, c in categories.items()}
        modules, module_courses = [], {}
        for source in raw['moodle_courses']:
            path, seen = [], set()
            current = str(source['categoryid'])
            while current in categories and current not in seen:
                seen.add(current)
                path.append(categories[current])
                current = str(categories[current]['parent'])
            if current != '0':
                raise LMSImportError('Moodle category ancestry is incomplete or cyclic; the import was not saved.')
            path.reverse()
            dept_depth = options['department_category_depth']
            if dept_depth and len(path) >= dept_depth:
                courses[str(path[dept_depth - 1]['id'])]['kind'] = 'department'
            source_id = str(source['id'])
            if options['programme_source'] == 'category':
                depth = options['programme_category_depth']
                # A single-level existing catalogue is a programme, not an invented department.
                if len(path) < depth and len(path) != 1:
                    raise LMSImportError('Configured programme category depth is missing from the Moodle hierarchy.')
                programme = str(path[min(depth, len(path)) - 1]['id']) if path else None
            elif options['programme_source'] == 'course_field':
                name = self.field(source, options['programme_field'])
                programme = 'programme:' + sha256(name.encode()).hexdigest()
                courses.setdefault(programme, {'source_id': programme, 'name': name, 'parent_id': None, 'kind': 'programme'})
            else:
                programme = 'moodle-course:' + source_id
            if programme is None:
                raise LMSImportError('No programme category is available for a Moodle course.')
            if options['year_source'] == 'course_field':
                year = self.years.get(self.label(self.field(source, options['year_field'])))
            elif options['year_source'] == 'category_depth':
                depth = options['year_category_depth']
                year = self.years.get(self.label(path[depth - 1]['name'])) if len(path) >= depth else None
            elif options['year_source'] == 'category_name':
                year = next((self.years[self.label(c['name'])] for c in reversed(path) if self.label(c['name']) in self.years), None)
            else:
                year = None
            if options['programme_source'] != 'moodle_course':
                courses[programme]['kind'] = 'programme'
            if options['module_source'] == 'courses':
                owner = programme if options['programme_source'] == 'course_field' else str(source['categoryid']) if str(source['categoryid']) in courses else programme
                modules.append({'source_id': source_id, 'name': source['fullname'], 'code': source['shortname'],
                                'course_id': owner, 'programme_id': programme, 'year': year})
                module_courses[source_id] = [source_id]
            else:
                owner = 'moodle-course:' + source_id
                courses[owner] = {'source_id': owner, 'name': source['fullname'], 'code': source['shortname'],
                                  'parent_id': programme if programme != owner else str(source['categoryid']) if str(source['categoryid']) in courses else None,
                                  'kind': 'programme' if owner == programme else 'course'}
                module_courses[source_id] = []
                for activity in raw['activities'].get(source_id, []):
                    activity_id = str(activity['id'])
                    modules.append({'source_id': activity_id, 'name': activity['name'], 'type': activity['modname'],
                                    'course_id': owner, 'programme_id': programme,
                                    'year': self.years.get(self.label(activity.get('section_name', ''))) if options['year_source'] == 'activity_section' else year})
                    module_courses[source_id].append(activity_id)
                    if len(modules) > 50000:
                        raise LMSImportError('Moodle module import exceeds the supported size limit.')
        enrolments = []
        for link in raw['enrolments']:
            for module_id in module_courses[link['course_source_id']]:
                enrolments.append({'user_source_id': link['user_source_id'], 'course_source_id': module_id,
                                   'target_type': 'module', 'roles': link['roles']})
                if len(enrolments) > 500000:
                    raise LMSImportError('Moodle enrolment import exceeds the supported size limit.')
        if options['role_source'] == 'course_roles':
            lecturers = {}
            for link in enrolments:
                if 'lecturer' in link['roles']:
                    lecturers.setdefault(link['course_source_id'], set()).add(link['user_source_id'])
            if any(len(people) > 1 for people in lecturers.values()):
                raise LMSImportError('Each module must have only one lecturer in Moodle; the import was not saved.')
        users = []
        for user in raw['users']:
            clean = {key: value for key, value in user.items() if key not in ('customfields', 'idnumber')}
            if options['current_year_source'] == 'profile_field':
                try:
                    label = self.field(user, options['current_year_field'])
                except LMSImportError:
                    label = None
                clean['current_year'] = self.years.get(self.label(label)) if label is not None else None
            users.append(clean)
        return {'users': users, 'courses': list(courses.values()), 'modules': modules,
                'enrolments': enrolments, 'enrolments_available': True, 'canonical': True}
