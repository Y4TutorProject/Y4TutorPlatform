"""Publish LMS profiles and enrolment links after college academic data is saved."""
from datetime import datetime, timezone

from bson import BSON

from .interfaces import LMSImportError, LMSImportStore
from ..module_participation import ModuleParticipation


class MongoLMSImportStore(LMSImportStore):
    def __init__(self, database, colleges, participation=None):
        self.collection = database['lms_imports']
        self.colleges = colleges
        self.participation = participation or ModuleParticipation(database)

    @staticmethod
    def _id(college_id, provider, source_url):
        return LMSImportStore.source_identity(college_id, provider, source_url)

    def save(self, college_id, provider, source_url, catalog):
        # Check the complete incoming snapshot before any writes.
        if len(BSON.encode(catalog)) > 8 * 1024 * 1024:
            raise LMSImportError('Catalog exceeds the import size limit; the previous import is unchanged.')
        academic = self.colleges.save_catalog(college_id, provider, source_url, catalog['courses'], catalog['modules'])
        targets = {kind: {record['source_id']: record['id'] for record in academic[plural]}
                   for kind, plural in (('module', 'modules'), ('course', 'courses'))}
        links = []
        for entry in catalog.get('enrolments', []):
            kind = entry.get('target_type', 'module' if catalog.get('mapping', 'academic') == 'academic' else 'course')
            links.append({'user_source_id': entry['user_source_id'], 'target_type': kind,
                          'target_id': targets[kind][entry['course_source_id']], 'roles': entry.get('roles', ['student'])})
        document = {'_id': self._id(college_id, provider, source_url), 'college_id': str(college_id),
                    'provider': provider, 'base_url': source_url,
                    'imported_at': catalog.get('imported_at') or datetime.now(timezone.utc).isoformat(),
                    'mapping': catalog.get('mapping', 'academic'), 'canonical': catalog.get('canonical', False), 'users': catalog['users'],
                    'enrolments_available': catalog.get('enrolments_available', False), 'enrolments': links,
                    'catalog_ref': {'id': academic['id'], 'college_id': str(college_id),
                                    'course_ids': [c['id'] for c in academic['courses']],
                                    'module_ids': [m['id'] for m in academic['modules']]}}
        if len(BSON.encode(document)) > 8 * 1024 * 1024:
            raise LMSImportError('Catalog exceeds the import size limit; the previous import is unchanged.')
        self.collection.replace_one({'_id': document['_id']}, document, upsert=True)
        self.participation.refresh_import(document, academic)
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
