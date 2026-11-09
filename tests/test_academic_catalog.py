from copy import deepcopy
import uuid

import pytest

from college_svc.Objects.Course import Course
from college_svc.Objects.Module import Module
from lms_svc.college_client import CollegeServiceUnavailable
from test_college_auth import services
from test_lms_import import integration


def test_course_and_module_objects_use_uuid_relationships():
    college_id, course_id, module_id = [uuid.uuid4() for _ in range(3)]
    course = Course(course_id, college_id, 'Computing', '30')
    module = Module(module_id, college_id, course_id, 'Databases', '20', 'DB4')
    assert isinstance(course.course_id, uuid.UUID)
    assert isinstance(module.module_id, uuid.UUID)
    assert module.to_dict()['course_id'] == course.to_dict()['id']
    assert module.to_dict()['college_id'] == course.to_dict()['college_id']
    with pytest.raises(ValueError):
        Module('invalid', college_id, course_id, 'Bad', '1')


def test_college_owns_records_and_lms_has_only_links(integration):
    _, client, dao, importer, payload, path, headers, _ = integration
    college_id = path.split('/')[2]
    catalog = importer.import_catalog(college_id, payload)
    stored = importer.store.collection.find_one()
    assert 'courses' not in stored and 'modules' not in stored
    assert stored['catalog_ref']['id'] == catalog['catalog_ref']['id']
    assert dao.db.courses.count_documents({'college_id': college_id}) == 1
    assert dao.db.modules.count_documents({'college_id': college_id}) == 1
    course = dao.db.courses.find_one()
    module = dao.db.modules.find_one()
    assert module['course_id'] == course['id']
    assert stored['enrolments'] == [{'user_source_id': '10', 'target_type': 'module', 'target_id': module['id'], 'roles': ['student']}]
    assert 'secret-test-token' not in str(list(dao.db.modules.find()))
    assert client.get(path + '/catalog', query_string={'base_url': payload['base_url']}, headers=headers).status_code == 200


def test_repeated_imports_reuse_ids_and_versions_preserve_old_reads(integration):
    _, _, dao, importer, payload, path, _, responses = integration
    college_id = path.split('/')[2]
    first = importer.import_catalog(college_id, payload)
    repeated = importer.import_catalog(college_id, payload)
    assert first['catalog_ref'] == repeated['catalog_ref']
    assert dao.db.modules.count_documents({}) == 1
    responses['core_course_get_courses'][1]['fullname'] = 'Advanced Databases'
    updated = importer.import_catalog(college_id, payload)
    assert updated['modules'][0]['id'] == first['modules'][0]['id']
    assert updated['catalog_ref']['id'] != first['catalog_ref']['id']
    old = importer.store.colleges.get_catalog(college_id, first['catalog_ref']['id'])
    assert old['modules'][0]['name'] == 'Databases'
    assert updated['modules'][0]['name'] == 'Advanced Databases'


def test_failed_college_write_preserves_lms_snapshot(integration, monkeypatch):
    _, _, _, importer, payload, path, _, _ = integration
    college_id = path.split('/')[2]
    importer.import_catalog(college_id, payload)
    before = importer.store.collection.find_one()
    def unavailable(*args):
        raise CollegeServiceUnavailable()
    monkeypatch.setattr(importer.store.colleges, 'save_catalog', unavailable)
    with pytest.raises(CollegeServiceUnavailable):
        importer.import_catalog(college_id, payload)
    assert importer.store.collection.find_one() == before


def test_legacy_migration_moves_records_without_changing_import_time(integration):
    _, _, dao, importer, payload, path, _, _ = integration
    college_id = path.split('/')[2]
    legacy = {'_id': importer.store._id(college_id, 'moodle', payload['base_url']),
              'college_id': college_id, 'provider': 'moodle', 'base_url': payload['base_url'],
              'imported_at': '2026-11-03T10:00:00+00:00', 'users': [], 'mapping': 'academic',
              'courses': [{'source_id': '30', 'name': 'Computing'}],
              'modules': [{'source_id': '20', 'course_id': '30', 'name': 'Databases'}]}
    importer.store.collection.insert_one(legacy)
    assert importer.store.migrate_legacy() == 1
    assert importer.store.migrate_legacy() == 0
    stored = importer.store.collection.find_one()
    assert stored['imported_at'] == legacy['imported_at']
    assert 'courses' not in stored and 'modules' not in stored
    assert stored['enrolments_available'] is False
    assert dao.db.modules.count_documents({}) == 1


def test_internal_academic_api_requires_service_token(services):
    _, _, client, _, *_ = services
    path = f'/internal/college/{uuid.uuid4()}/catalogs'
    for headers in ({}, {'X-College-Sync-Token': 'forged'}, {'X-College-Sync-Token': 'é'}):
        assert client.post(path, json={}, headers=headers).status_code == 401


def test_catalog_references_are_scoped_to_college(integration):
    _, _, _, importer, payload, path, _, _ = integration
    college_id = path.split('/')[2]
    catalog = importer.import_catalog(college_id, payload)
    academic = importer.store.colleges
    assert academic.get_college(college_id)
    # Exercise the DAO directly to test scoping even with a valid catalogue ID.
    _, _, dao, *_ = integration
    from college_svc.academic_dao.MongoAcademicDAO import MongoAcademicDAO
    assert MongoAcademicDAO(dao.db).get_catalog(str(uuid.uuid4()), catalog['catalog_ref']['id']) is None


@pytest.mark.parametrize('change', ['cycle', 'missing_parent', 'missing_course', 'duplicate'])
def test_invalid_academic_relationships_are_rejected_before_writes(integration, change):
    _, _, dao, _, _, path, _, _ = integration
    from college_svc.implementations.academic_svc import AcademicService
    from college_svc.academic_dao.MongoAcademicDAO import MongoAcademicDAO
    service = AcademicService(MongoAcademicDAO(dao.db))
    data = {'provider': 'moodle', 'base_url': 'https://college.test',
            'courses': [{'source_id': '30', 'name': 'Computing'}],
            'modules': [{'source_id': '20', 'course_id': '30', 'name': 'Databases'}]}
    if change in ('cycle', 'missing_parent'):
        data['courses'][0]['parent_id'] = '30' if change == 'cycle' else 'missing'
    elif change == 'missing_course':
        data['modules'][0]['course_id'] = 'missing'
    else:
        data['modules'].append(deepcopy(data['modules'][0]))
    with pytest.raises(ValueError):
        service.import_catalog(path.split('/')[2], data)
    assert dao.db.courses.count_documents({}) == 0
    assert dao.db.modules.count_documents({}) == 0
