"""Academic domain validation and deterministic identities for imported records."""
import hashlib
import json
import uuid

from ..Objects.Course import Course
from ..Objects.Module import Module
from ..interfaces.academic_interface import AcademicInterface


def text(value, maximum=200, required=True):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()) or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid academic record field.')
    return value


class AcademicService(AcademicInterface):
    def __init__(self, dao):
        self.dao = dao

    def import_catalog(self, college_id, data):
        college_id = str(uuid.UUID(college_id))
        if not isinstance(data, dict):
            raise ValueError('A JSON object is required.')
        provider = text(data.get('provider'))
        source_url = text(data.get('base_url'), 2048)
        courses, modules = data.get('courses'), data.get('modules')
        if any(not isinstance(records, list) or len(records) > 50000 for records in (courses, modules)):
            raise ValueError('Invalid academic records.')
        def identity(kind, source_id):
            return str(uuid.uuid5(uuid.UUID(college_id), json.dumps([provider, source_url, kind, source_id])))
        normalized = {'courses': [], 'modules': []}
        try:
            seen = set()
            for record in courses:
                source_id = text(record['source_id'])
                if source_id in seen:
                    raise ValueError('Duplicate course.')
                seen.add(source_id)
                clean = {'source_id': source_id, 'name': text(record['name'], 1000),
                         'parent_id': text(record['parent_id']) if record.get('parent_id') is not None else None}
                if 'code' in record:
                    clean['code'] = text(record['code'], required=False)
                if 'kind' in record:
                    clean['kind'] = text(record['kind'])
                normalized['courses'].append(clean)
            parents = {c['source_id']: c['parent_id'] for c in normalized['courses']}
            done = set()
            for source_id in parents:
                current, chain = source_id, set()
                while current is not None and current not in done:
                    if current not in parents or current in chain:
                        raise ValueError('Invalid course hierarchy.')
                    chain.add(current)
                    current = parents[current]
                done.update(chain)
            seen = set()
            for record in modules:
                source_id = text(record['source_id'])
                course_id = text(record['course_id'])
                if source_id in seen or course_id not in parents:
                    raise ValueError('Invalid module relationship.')
                seen.add(source_id)
                clean = {'source_id': source_id, 'course_id': course_id, 'name': text(record['name'], 1000)}
                if 'programme_id' in record:
                    clean['programme_id'] = text(record['programme_id'])
                    if clean['programme_id'] not in parents:
                        raise ValueError('Invalid programme relationship.')
                if 'year' in record and record['year'] is not None:
                    if type(record['year']) is not int or not 1 <= record['year'] <= 20:
                        raise ValueError('Invalid academic year.')
                    clean['year'] = record['year']
                for field in ('code', 'type'):
                    if field in record:
                        clean[field] = text(record[field], required=False)
                normalized['modules'].append(clean)
        except (KeyError, TypeError, AttributeError):
            raise ValueError('Invalid academic record.') from None
        normalized['courses'].sort(key=lambda r: r['source_id'])
        normalized['modules'].sort(key=lambda r: r['source_id'])
        catalog_id = hashlib.sha256(json.dumps([college_id, provider, source_url, normalized], sort_keys=True).encode()).hexdigest()
        course_objects = [Course(identity('course', c['source_id']), college_id, c['name'], c['source_id'],
                                 identity('course', c['parent_id']) if c['parent_id'] else None, c.get('code'), c.get('kind'))
                          for c in normalized['courses']]
        module_objects = [Module(identity('module', m['source_id']), college_id, identity('course', m['course_id']),
                                 m['name'], m['source_id'], m.get('code'), m.get('type'),
                                 identity('course', m['programme_id']) if m.get('programme_id') else None, m.get('year'))
                          for m in normalized['modules']]
        return self.dao.save_catalog(college_id, catalog_id, course_objects, module_objects)

    def get_catalog(self, college_id, catalog_id):
        return self.dao.get_catalog(str(uuid.UUID(college_id)), catalog_id)
