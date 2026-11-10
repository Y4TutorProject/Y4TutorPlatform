"""Configurable provider semantics must not leak into tutoring policy."""
import pytest

from lms_svc.lms.interfaces import LMSImportError, LMSProvider
from lms_svc.lms.moodle_mapping import MoodleCatalogMapper
from lms_svc.module_participation import tutor_modules
from test_lms_import import integration
from test_college_auth import services


def test_programme_and_year_custom_fields_work_without_year_categories(integration):
    _, _, _, importer, payload, path, _, responses = integration
    responses['core_course_get_categories'] = [{'id': 30, 'name': 'Mixed modules', 'parent': 0}]
    responses['core_course_get_courses'] = [{'id': 1}] + [
        {'id': number, 'fullname': name, 'shortname': f'U{number}', 'categoryid': 30,
         'customfields': [{'shortname': 'degree', 'value': degree}, {'shortname': 'level', 'value': str(year)}]}
        for number, name, degree, year in [(20, 'Earlier unit', 'Degree A', 1), (21, 'Current unit', 'Degree A', 3), (22, 'Other degree', 'Degree B', 1)]
    ]
    responses['core_enrol_get_users_courses'] = [{'id': 21}]
    options = {'programme_source': 'course_field', 'programme_field': 'degree', 'year_source': 'course_field', 'year_field': 'level'}
    catalog = importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': options})
    current = next(m for m in catalog['modules'] if m['source_id'] == '21')
    assert current['year'] == 3
    assert {m['source_id'] for m in tutor_modules(catalog, [current])} == {'20'}
    assert current['programme_id'] == next(c['id'] for c in catalog['courses'] if c['name'] == 'Degree A')
    assert current['course_id'] == current['programme_id']


def test_category_depth_and_institution_specific_year_labels(integration):
    _, _, _, importer, payload, path, _, responses = integration
    responses['core_course_get_categories'] = [
        {'id': 10, 'name': 'Unusual programme name', 'parent': 0},
        {'id': 30, 'name': 'Foundation', 'parent': 10},
        {'id': 31, 'name': 'Final stage', 'parent': 10},
    ]
    responses['core_course_get_courses'] += [{'id': 21, 'fullname': 'Final unit', 'shortname': 'FINAL', 'categoryid': 31}]
    options = {'programme_category_depth': 1, 'department_category_depth': 0,
               'year_source': 'category_depth', 'year_category_depth': 2,
               'year_labels': {'Foundation': 1, 'Final stage': 4}}
    catalog = importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': options})
    assert {m['source_id']: m['year'] for m in catalog['modules']} == {'20': 1, '21': 4}
    assert len({m['programme_id'] for m in catalog['modules']}) == 1


def test_missing_year_metadata_does_not_grant_eligibility(integration):
    _, _, _, importer, payload, path, _, _ = integration
    catalog = importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': {'year_source': 'none'}})
    assert 'year' not in catalog['modules'][0]
    assert tutor_modules(catalog, catalog['modules']) == []


def test_role_shortnames_distinguish_students_from_lecturers(integration):
    _, _, _, importer, payload, path, _, responses = integration
    responses['core_user_get_users']['users'].append({'id': 11, 'email': 'lecturer@college.test'})
    responses['core_enrol_get_enrolled_users'] = [
        {'id': 10, 'roles': [{'id': 5, 'shortname': 'learner'}]},
        {'id': 11, 'roles': [{'id': 3, 'shortname': 'instructor'}]},
    ]
    catalog = importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': {
        'role_source': 'course_roles', 'student_roles': ['learner'], 'lecturer_roles': ['instructor'],
    }})
    assert {e['user_source_id']: e['roles'] for e in catalog['enrolments']} == {'10': ['student'], '11': ['lecturer']}


def test_activity_modules_share_explicit_programme_year_and_roles(integration):
    _, _, _, importer, payload, path, _, responses = integration
    responses['core_course_get_courses'][1]['customfields'] = [{'shortname': 'level', 'value': '2'}]
    responses['core_course_get_contents'] = [{'modules': [{'id': 40, 'name': 'Workshop', 'modname': 'assign'}]}]
    catalog = importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': {
        'module_source': 'activities', 'programme_category_depth': 1, 'year_source': 'course_field', 'year_field': 'level',
    }})
    module = catalog['modules'][0]
    assert module['source_id'] == '40' and module['year'] == 2
    assert catalog['enrolments'][0]['target_id'] == module['id']
    assert catalog['enrolments'][0]['roles'] == ['student']


@pytest.mark.parametrize('options', [
    {'programme_category_depth': True}, {'programme_category_depth': 0},
    {'year_labels': {'First': 0}}, {'year_labels': {'First': 1, 'FIRST': 2}},
    {'year_labels': []}, {'student_roles': ['instructor'], 'lecturer_roles': ['instructor']},
    {'module_source': 'unimplemented'}, {'programme_source': 'moodle_course'}, {'arbitrary_code': 'bad'},
])
def test_invalid_configuration_is_rejected(options):
    with pytest.raises(ValueError):
        MoodleCatalogMapper.validate_options(options)


def test_mapping_options_survive_save_restart_and_nightly_sync(integration):
    _, client, _, importer, payload, path, headers, responses = integration
    responses['core_course_get_courses'][1]['customfields'] = [{'shortname': 'stage', 'value': '4'}]
    options = {'programme_category_depth': 1, 'year_source': 'course_field', 'year_field': 'stage'}
    result = client.put(path + '/connection', json={**payload, 'provider_options': options}, headers=headers)
    assert result.status_code == 200
    assert result.json['connection']['provider_options']['year_field'] == 'stage'
    assert client.post(path + '/sync', headers=headers).status_code == 200
    stored = importer.store.get(path.split('/')[2], 'moodle', payload['base_url'])
    assert stored['modules'][0]['year'] == 4
    # A settings save which omits options preserves the institution's mapping.
    response = client.put(path + '/connection', json={**{k: v for k, v in payload.items() if k != 'provider_options'}, 'api_key': ''}, headers=headers)
    assert response.json['connection']['provider_options']['year_field'] == 'stage'


def test_failed_custom_field_import_preserves_previous_catalog(integration):
    _, _, _, importer, payload, path, _, _ = integration
    importer.import_catalog(path.split('/')[2], payload)
    previous = importer.store.collection.find_one()
    with pytest.raises(LMSImportError):
        importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': {'year_source': 'course_field', 'year_field': 'missing'}})
    assert importer.store.collection.find_one() == previous


def test_non_moodle_adapter_uses_configuration_storage_and_tutoring_policy(integration):
    _, client, _, importer, payload, path, headers, _ = integration
    class ExternalLMS(LMSProvider):
        label = 'Another LMS'
        @classmethod
        def configuration(cls):
            return {'label': cls.label, 'fields': [{'name': 'catalogue', 'type': 'text', 'label': 'Catalogue', 'default': 'main'}]}
        @classmethod
        def validate_options(cls, options):
            return {'catalogue': (options or {}).get('catalogue', 'main')}
        @classmethod
        def build(cls, base_url, api_key, mapping, options, transport):
            assert options == {'catalogue': 'custom'}
            assert hasattr(transport, 'open')
            return cls()
        def fetch_catalog(self):
            return {'canonical': True, 'users': [{'source_id': 'external-person', 'email': 'person@college.test'}],
                    'courses': [{'source_id': 'degree', 'name': 'Opaque programme'}],
                    'modules': [{'source_id': 'earlier', 'course_id': 'degree', 'programme_id': 'degree', 'year': 1, 'name': 'Alpha'},
                                {'source_id': 'current', 'course_id': 'degree', 'programme_id': 'degree', 'year': 4, 'name': 'Beta'}],
                    'enrolments_available': True,
                    'enrolments': [{'user_source_id': 'external-person', 'target_type': 'module', 'target_source_id': 'current', 'roles': ['student']}]}
    importer.providers['external'] = ExternalLMS
    result = client.get('/providers', headers=headers)
    assert any(p['id'] == 'external' and p['fields'][0]['name'] == 'catalogue' for p in result.json['providers'])
    catalog = importer.import_catalog(path.split('/')[2], {**payload, 'provider': 'external', 'provider_options': {'catalogue': 'custom'}})
    current = next(m for m in catalog['modules'] if m['source_id'] == 'current')
    assert [m['source_id'] for m in tutor_modules(catalog, [current])] == ['earlier']
    assert catalog['provider'] == 'external'


def test_role_aware_import_refuses_missing_roles_without_replacing_snapshot(integration):
    _, _, _, importer, payload, path, _, responses = integration
    importer.import_catalog(path.split('/')[2], payload)
    previous = importer.store.collection.find_one()
    responses['core_enrol_get_enrolled_users'] = [{'id': 10}]
    with pytest.raises(LMSImportError):
        importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': {'role_source': 'course_roles'}})
    assert importer.store.collection.find_one() == previous


def test_provider_discovery_requires_authentication(integration):
    _, client, *_ = integration
    client.delete_cookie('tutor_session')
    assert client.get('/providers').status_code == 401


def test_role_import_paginates_course_participants(integration, monkeypatch):
    from lms_svc.lms.moodle import MoodleProvider
    _, _, _, importer, payload, path, _, responses = integration
    people = [{'id': number, 'email': f'person{number}@college.test'} for number in range(10, 211)]
    responses['core_user_get_users']['users'] = people
    offsets = []
    def read(self, function, **parameters):
        if function == 'core_enrol_get_enrolled_users':
            offset = parameters['options[1][value]']
            offsets.append(offset)
            return [{'id': person['id'], 'roles': [{'shortname': 'student'}]} for person in people[offset:offset + 200]]
        return responses[function]
    monkeypatch.setattr(MoodleProvider, '_call', read)
    catalog = importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': {'role_source': 'course_roles'}})
    assert offsets == [0, 200]
    assert len(catalog['enrolments']) == 201


def test_profile_current_year_overrides_highest_enrolled_year(integration):
    _, _, _, importer, payload, path, _, responses = integration
    responses['core_course_get_courses'][1]['customfields'] = [{'shortname': 'level', 'value': '4'}]
    responses['core_user_get_users']['users'][0]['customfields'] = [{'shortname': 'academic_stage', 'value': '2'}]
    responses['core_course_get_courses'] += [
        {'id': 21, 'fullname': 'First year', 'shortname': 'FIRST', 'categoryid': 30, 'customfields': [{'shortname': 'level', 'value': '1'}]},
        {'id': 22, 'fullname': 'Third year', 'shortname': 'THIRD', 'categoryid': 30, 'customfields': [{'shortname': 'level', 'value': '3'}]},
    ]
    options = {'programme_category_depth': 1, 'year_source': 'course_field', 'year_field': 'level',
               'current_year_source': 'profile_field', 'current_year_field': 'academic_stage'}
    catalog = importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': options})
    assert catalog['users'][0]['current_year'] == 2
    enrolled = [m for m in catalog['modules'] if m['source_id'] == '20']
    assert {m['source_id'] for m in tutor_modules(catalog, enrolled, catalog['users'][0])} == {'21'}
    responses['core_user_get_users']['users'][0]['customfields'] = []
    unknown = importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': options})
    assert unknown['users'][0]['current_year'] is None
    assert tutor_modules(unknown, enrolled, unknown['users'][0]) == []


def test_programme_as_moodle_course_with_activity_section_years(integration):
    _, _, _, importer, payload, path, _, responses = integration
    responses['core_course_get_contents'] = [
        {'name': 'Foundation', 'modules': [{'id': 40, 'name': 'Intro unit', 'modname': 'assign'}]},
        {'name': 'Advanced', 'modules': [{'id': 41, 'name': 'Advanced unit', 'modname': 'assign'}]},
    ]
    responses['core_user_get_users']['users'][0]['customfields'] = [{'shortname': 'level', 'value': 'Final'}]
    options = {'module_source': 'activities', 'programme_source': 'moodle_course', 'year_source': 'activity_section',
               'year_labels': {'Foundation': 1, 'Advanced': 2, 'Final': 3},
               'current_year_source': 'profile_field', 'current_year_field': 'level'}
    catalog = importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': options})
    assert {m['source_id']: m['year'] for m in catalog['modules']} == {'40': 1, '41': 2}
    assert len({m['programme_id'] for m in catalog['modules']}) == 1
    assert len(tutor_modules(catalog, catalog['modules'], catalog['users'][0])) == 2


def test_multiple_lecturers_cannot_replace_previous_catalog(integration):
    _, _, _, importer, payload, path, _, responses = integration
    importer.import_catalog(path.split('/')[2], payload)
    previous = importer.store.collection.find_one()
    responses['core_user_get_users']['users'] += [
        {'id': 11, 'email': 'one@college.test'}, {'id': 12, 'email': 'two@college.test'}]
    responses['core_enrol_get_enrolled_users'] = [
        {'id': 11, 'roles': [{'shortname': 'editingteacher'}]},
        {'id': 12, 'roles': [{'shortname': 'teacher'}]}]
    with pytest.raises(LMSImportError, match='only one lecturer'):
        importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': {'role_source': 'course_roles'}})
    assert importer.store.collection.find_one() == previous


def test_one_lecturer_can_have_multiple_modules(integration):
    _, _, _, importer, payload, path, _, responses = integration
    responses['core_user_get_users']['users'].append({'id': 11, 'email': 'lecturer@college.test'})
    responses['core_course_get_courses'].append({'id': 21, 'fullname': 'Networks', 'shortname': 'NET', 'categoryid': 30})
    responses['core_enrol_get_enrolled_users'] = [{'id': 11, 'roles': [{'shortname': 'editingteacher'}]}]
    catalog = importer.import_catalog(path.split('/')[2], {**payload, 'provider_options': {'role_source': 'course_roles'}})
    from lms_svc.module_participation import module_lecturers
    assert set(module_lecturers(catalog)) == {m['id'] for m in catalog['modules']}
    assert set(module_lecturers(catalog).values()) == {'11'}
