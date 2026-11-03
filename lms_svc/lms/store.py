"""Publish LMS profiles and enrolment links after college academic data is saved."""
from datetime import datetime, timezone
from hashlib import sha256

from bson import BSON

from .interfaces import LMSImportError, LMSImportStore


class MongoLMSImportStore(LMSImportStore):
    def __init__(self, database, colleges):
        self.collection = database['lms_imports']
        self.colleges = colleges

    @staticmethod
    def _id(college_id, provider, source_url):
        return sha256(f'{college_id}\n{provider}\n{source_url}'.encode()).hexdigest()

    def save(self, college_id, provider, source_url, catalog):
        # Check the complete incoming snapshot before any writes.
        if len(BSON.encode(catalog)) > 8 * 1024 * 1024:
            raise LMSImportError('Catalog exceeds the import size limit; the previous import is unchanged.')
        academic = self.colleges.save_catalog(college_id, provider, source_url, catalog['courses'], catalog['modules'])
        kind = 'module' if catalog.get('mapping', 'academic') == 'academic' else 'course'
        records = academic['modules'] if kind == 'module' else academic['courses']
        targets = {record['source_id']: record['id'] for record in records}
        links = [{'user_source_id': e['user_source_id'], 'target_type': kind, 'target_id': targets[e['course_source_id']]}
                 for e in catalog.get('enrolments', [])]
        document = {'_id': self._id(college_id, provider, source_url), 'college_id': str(college_id),
                    'provider': provider, 'base_url': source_url,
                    'imported_at': catalog.get('imported_at') or datetime.now(timezone.utc).isoformat(),
                    'mapping': catalog.get('mapping', 'academic'), 'users': catalog['users'],
                    'enrolments_available': catalog.get('enrolments_available', False), 'enrolments': links,
                    'catalog_ref': {'id': academic['id'], 'college_id': str(college_id),
                                    'course_ids': [c['id'] for c in academic['courses']],
                                    'module_ids': [m['id'] for m in academic['modules']]}}
        if len(BSON.encode(document)) > 8 * 1024 * 1024:
            raise LMSImportError('Catalog exceeds the import size limit; the previous import is unchanged.')
        self.collection.replace_one({'_id': document['_id']}, document, upsert=True)
        return self._public(document, academic)

    @staticmethod
    def _public(document, academic=None):
        result = {key: value for key, value in document.items() if key != '_id'}
        if academic is not None:
            result.update(courses=academic['courses'], modules=academic['modules'])
        return result

    def get(self, college_id, provider, source_url):
        document = self.collection.find_one({'_id': self._id(college_id, provider, source_url)})
        if not document:
            return None
        reference = document.get('catalog_ref')
        if reference:
            academic = self.colleges.get_catalog(str(college_id), reference['id'])
            return self._public(document, academic)
        # Legacy snapshots remain readable until the migration or next full sync.
        return self._public(document)

    def migrate_legacy(self):
        """Move existing academic records without fetching Moodle or changing dates."""
        count = 0
        for document in self.collection.find({'catalog_ref': {'$exists': False}}):
            self.save(document['college_id'], document['provider'], document['base_url'], document)
            count += 1
        return count
