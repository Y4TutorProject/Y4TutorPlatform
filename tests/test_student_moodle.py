import pytest

from test_lms_import import integration
from test_college_auth import services


@pytest.fixture
def student(integration):
    users, client, _, importer, payload, path, headers, _ = integration
    college_id = path.split('/')[2]
    account = users.extensions['users_dao'].collection.find_one()
    users.extensions['users_dao'].collection.update_one({'id': account['id']}, {'$set': {
        'roles': ['student'], 'college': college_id,
    }})
    sync = client.application.extensions['lms_sync']
    sync.connections.collection.insert_one({'_id': college_id, 'provider': 'moodle', 'base_url': payload['base_url']})
    profile = {'source_id': '10', 'email': account['email'].upper(), 'first_name': 'Student',
               'last_name': 'Example', 'username': 'moodle-student', 'suspended': False}
    catalog = {'mapping': 'academic', 'enrolments_available': True,
               'enrolments': [{'user_source_id': '10', 'course_source_id': '20'}], 'users': [profile, {'source_id': '11', 'email': 'private@college.test'}],
               'courses': [{'source_id': '30', 'name': 'Computing'}],
               'modules': [{'source_id': '20', 'course_id': '30', 'name': 'Databases'}]}
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    return client, users, importer, college_id, payload, catalog, account


def test_student_gets_only_own_profile_and_college_catalogue(student):
    client, *_ = student
    response = client.get('/students/me?email=private@college.test&college_id=another')
    assert response.status_code == 200
    assert response.json['student']['username'] == 'moodle-student'
    assert response.json['modules'][0]['name'] == 'Databases'
    assert 'private@college.test' not in response.get_data(as_text=True)
    assert 'api_key' not in response.get_data(as_text=True)
    assert response.headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('case', ['missing', 'suspended', 'ambiguous', 'other_college'])
def test_no_profile_is_disclosed_for_invalid_match(student, case):
    client, users, importer, college_id, payload, catalog, account = student
    if case == 'missing':
        catalog['users'][0]['email'] = 'other@college.test'
    elif case == 'suspended':
        catalog['users'][0]['suspended'] = True
    elif case == 'ambiguous':
        catalog['users'].append(dict(catalog['users'][0], source_id='12'))
    else:
        users.extensions['users_dao'].collection.update_one({'id': account['id']}, {'$set': {'college': None}})
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    response = client.get('/students/me')
    assert response.status_code == 404
    assert 'student' not in response.json
    assert 'modules' not in response.json


def test_anonymous_and_non_student_cannot_read_student_information(student):
    client, users, *_, account = student
    users.extensions['users_dao'].collection.update_one({'id': account['id']}, {'$set': {'roles': ['college_admin']}})
    assert client.get('/students/me').status_code == 403
    client.delete_cookie('tutor_session')
    assert client.get('/students/me').status_code == 401


def test_student_never_receives_unenrolled_module_or_programme(student):
    client, _, importer, college_id, payload, catalog, _ = student
    catalog['courses'].append({'source_id': '31', 'name': 'Other programme'})
    catalog['modules'].append({'source_id': '21', 'course_id': '31', 'name': 'Private unrelated module'})
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    response = client.get('/students/me')
    assert response.status_code == 200
    assert response.json['enrolments_available'] is True
    assert len(response.json['modules']) == 1
    assert 'Private unrelated module' not in response.text
    assert 'Other programme' not in response.text
    catalog['enrolments'] = []
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    response = client.get('/students/me')
    assert response.json['modules'] == []
    assert response.json['courses'] == []


def test_enrolled_modules_include_programme_ancestors(student):
    client, _, importer, college_id, payload, catalog, _ = student
    catalog['courses'][0]['parent_id'] = '32'
    catalog['courses'].append({'source_id': '32', 'name': 'Department'})
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    response = client.get('/students/me')
    assert [c['name'] for c in response.json['courses']] == ['Department', 'Computing']
