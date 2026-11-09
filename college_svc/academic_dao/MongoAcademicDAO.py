"""Versioned academic records; the manifest is published only after all writes."""
from ..interfaces.academic_interface import AcademicDAO
from ..Objects.Course import Course
from ..Objects.Module import Module


class MongoAcademicDAO(AcademicDAO):
    def __init__(self, database):
        self.courses = database['courses']
        self.modules = database['modules']
        self.catalogs = database['academic_catalogs']
        for collection in (self.courses, self.modules):
            collection.create_index([('college_id', 1), ('catalog_id', 1)])

    def save_catalog(self, college_id, catalog_id, courses, modules):
        for collection, records in ((self.courses, courses), (self.modules, modules)):
            for record in records:
                data = record.to_dict()
                data.update(catalog_id=catalog_id)
                collection.update_one({'_id': f'{catalog_id}:{data["id"]}'}, {'$setOnInsert': data}, upsert=True)
        # Old versions stay readable if LMS publication fails or overlaps a read.
        self.catalogs.update_one({'_id': catalog_id}, {'$setOnInsert': {
            'college_id': college_id, 'course_ids': [str(c.course_id) for c in courses],
            'module_ids': [str(m.module_id) for m in modules],
        }}, upsert=True)
        return self.get_catalog(college_id, catalog_id)

    def get_catalog(self, college_id, catalog_id):
        manifest = self.catalogs.find_one({'_id': catalog_id, 'college_id': college_id})
        if manifest is None:
            return None
        courses = {}
        for data in self.courses.find({'college_id': college_id, 'catalog_id': catalog_id}):
            course = Course(data['id'], college_id, data['name'], data['source_id'], data.get('parent_id'), data.get('code'), data.get('kind'))
            courses[data['id']] = course.to_dict()
        modules = {}
        for data in self.modules.find({'college_id': college_id, 'catalog_id': catalog_id}):
            module = Module(data['id'], college_id, data['course_id'], data['name'], data['source_id'], data.get('code'), data.get('type'), data.get('programme_id'), data.get('year'))
            modules[data['id']] = module.to_dict()
        return {'id': catalog_id, 'college_id': college_id,
                'courses': [courses[key] for key in manifest['course_ids']],
                'modules': [modules[key] for key in manifest['module_ids']]}
