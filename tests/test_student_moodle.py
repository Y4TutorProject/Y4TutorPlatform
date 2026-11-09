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
               'modules': [{'source_id': '20', 'course_id': '30', 'name': 'Databases', 'programme_id': '30', 'year': 1}]}
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


def student_post(client, path, data):
    return client.post(path, json=data, headers=client.application.extensions['student_test_headers'])


@pytest.fixture
def programme(student, integration):
    client, users, importer, college_id, payload, catalog, account = student
    client.application.extensions['student_test_headers'] = integration[6]
    catalog['courses'] = [
        {'source_id': '1', 'name': 'Department'},
        {'source_id': '2', 'name': 'Computing &amp; Informatics', 'parent_id': '1'},
        {'source_id': '30', 'name': 'Year 3', 'parent_id': '2'},
        {'source_id': '31', 'name': 'Year 2', 'parent_id': '2'},
        {'source_id': '3', 'name': 'Other programme', 'parent_id': '1'},
    ]
    catalog['modules'] += [
        {'source_id': '21', 'course_id': '31', 'name': 'Networks &amp; Security', 'code': 'NET2'},
        {'source_id': '22', 'course_id': '3', 'name': 'Private other module'},
    ]
    catalog['modules'][0].update(programme_id='2', year=3)
    catalog['modules'][1].update(programme_id='2', year=2)
    catalog['modules'][2].update(programme_id='3', year=1)
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    return student


def test_programme_search_includes_other_years_but_excludes_other_programmes(programme):
    client, users, importer, college_id, payload, catalog, account = programme
    response = client.get('/students/me/modules')
    assert response.status_code == 200
    assert {m['source_id'] for m in response.json['modules']} == {'21'}
    enrolled = client.get('/students/me').json['modules'][0]
    assert enrolled['roles'] == ['student']
    membership = client.application.extensions['lms_database'].module_memberships.find_one()
    assert membership['user_id'] == account['id']
    assert membership['module_id'] == enrolled['id']
    assert membership['roles'] == ['student']
    searched = client.get('/students/me/modules?q=net2').json['modules']
    assert len(searched) == 1
    assert searched[0]['display_name'] == 'Networks & Security'
    assert searched[0]['roles'] == []
    assert client.get('/students/me/modules?q=private').json['modules'] == []


def test_removing_enrolment_removes_student_membership(programme):
    client, _, importer, college_id, payload, catalog, _ = programme
    assert client.get('/students/me/modules').status_code == 200
    catalog['enrolments'] = []
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    assert client.application.extensions['lms_database'].module_memberships.find_one()['roles'] == []
    assert client.get('/students/me/modules').json['modules'] == []


def test_tutor_application_requires_programme_membership_and_csrf(programme):
    client, users, importer, college_id, payload, catalog, account = programme
    modules = client.get('/students/me/modules').json['modules']
    module = next(m for m in modules if m['source_id'] == '21')
    path = f"/students/me/modules/{module['id']}/tutor-application"
    assert client.post(path, json={}).status_code == 400
    response = student_post(client, path, {'grade': 85, 'user_id': 'forged'})
    assert response.status_code == 200
    assert response.json['application']['status'] == 'pending'
    assert response.json['application']['grade'] == 85
    assert response.json['application']['user_id'] == account['id']
    assert student_post(client, path, {'grade': 85}).json['application']['id'] == response.json['application']['id']
    assert client.application.extensions['lms_database'].tutor_applications.count_documents({}) == 1
    assert client.application.extensions['lms_database'].module_memberships.count_documents({'roles': 'tutor'}) == 0
    full = importer.store.get(college_id, 'moodle', payload['base_url'])
    outside = next(m for m in full['modules'] if m['source_id'] == '22')
    assert student_post(client, f"/students/me/modules/{outside['id']}/tutor-application", {}).status_code == 404
    assert client.get('/students/me/modules?q=net2').json['modules'][0]['application_status'] == 'pending'


@pytest.mark.parametrize('decision', ['approved', 'rejected'])
def test_only_owning_admin_can_review_and_approval_grants_module_role(programme, decision):
    client, users, _, college_id, _, _, account = programme
    module = next(m for m in client.get('/students/me/modules').json['modules'] if m['source_id'] == '21')
    application = student_post(client, f"/students/me/modules/{module['id']}/tutor-application", {'grade': 85}).json['application']
    base = f"/college/{college_id}/tutor-applications"
    path = f"{base}/{application['id']}/review"
    assert student_post(client, path, {'decision': decision}).status_code == 403
    users.extensions['users_dao'].collection.update_one({'id': account['id']}, {'$set': {'roles': ['college_admin']}})
    headers = client.application.extensions['student_test_headers']
    assert len(client.get(base, headers=headers).json['applications']) == 1
    assert client.post(path, json={'decision': decision}).status_code == 400
    assert student_post(client, path, {'decision': decision}).status_code == 200
    assert student_post(client, path, {'decision': decision}).status_code == 200
    opposite = 'rejected' if decision == 'approved' else 'approved'
    assert student_post(client, path, {'decision': opposite}).status_code == 409
    membership = client.application.extensions['lms_database'].module_memberships.find_one({'module_id': module['id']})
    assert bool(membership and 'tutor' in membership['roles']) is (decision == 'approved')
    assert users.extensions['users_dao'].get_user(account['id']).roles[0].value == 'college_admin'
    assert client.get(base, headers=headers).json['applications'] == []


def test_other_college_admin_cannot_review_application(programme):
    import uuid
    client, users, importer, college_id, _, _, account = programme
    module = next(m for m in client.get('/students/me/modules').json['modules'] if m['source_id'] == '21')
    application = student_post(client, f"/students/me/modules/{module['id']}/tutor-application", {'grade': 85}).json['application']
    users.extensions['users_dao'].collection.update_one({'id': account['id']}, {'$set': {'roles': ['college_admin']}})
    # A different college is never allowed to address this application's ID.
    other = str(uuid.uuid4())
    assert student_post(client, f"/college/{other}/tutor-applications/{application['id']}/review", {'decision': 'approved'}).status_code == 403
    assert client.application.extensions['lms_database'].tutor_applications.find_one()['status'] == 'pending'


@pytest.mark.parametrize('grade', [None, -1, 101, True, False, '85', [], {}, float('nan'), float('inf')])
def test_tutor_application_rejects_invalid_grades(programme, grade):
    client, *_ = programme
    module = next(m for m in client.get('/students/me/modules').json['modules'] if m['source_id'] == '21')
    response = student_post(client, f"/students/me/modules/{module['id']}/tutor-application", {'grade': grade})
    assert response.status_code == 400
    assert client.application.extensions['lms_database'].tutor_applications.count_documents({}) == 0


@pytest.mark.parametrize('grade', [0, 100, 85.5])
def test_tutor_application_persists_valid_grades(programme, grade):
    client, *_ = programme
    module = next(m for m in client.get('/students/me/modules').json['modules'] if m['source_id'] == '21')
    response = student_post(client, f"/students/me/modules/{module['id']}/tutor-application", {'grade': grade})
    assert response.status_code == 200
    assert response.json['application']['grade'] == grade
    assert client.application.extensions['lms_database'].tutor_applications.find_one()['grade'] == grade


@pytest.fixture
def year_restricted(programme):
    client, _, importer, college_id, payload, catalog, _ = programme
    catalog['courses'][2]['name'] = 'Y4'
    catalog['courses'] += [
        {'source_id': '32', 'name': 'Year 1', 'parent_id': '2'},
        {'source_id': '33', 'name': 'Stage 3', 'parent_id': '2'},
        {'source_id': '34', 'name': 'Year 5', 'parent_id': '2'},
        {'source_id': '35', 'name': 'Unclassified modules', 'parent_id': '2'},
    ]
    catalog['modules'] += [
        {'source_id': '23', 'course_id': '32', 'name': 'First year module'},
        {'source_id': '24', 'course_id': '33', 'name': 'Third year module'},
        {'source_id': '25', 'course_id': '30', 'name': 'Same year module'},
        {'source_id': '26', 'course_id': '34', 'name': 'Future year module'},
        {'source_id': '27', 'course_id': '35', 'name': 'Unknown year module'},
    ]
    catalog['modules'][0]['year'] = 4
    for module, year in zip(catalog['modules'][-5:], [1, 3, 4, 5, None]):
        module.update(programme_id='2', year=year)
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    return programme


def test_all_previous_years_are_eligible_but_same_future_and_unknown_are_not(year_restricted):
    client, *_ = year_restricted
    modules = client.get('/students/me/modules').json['modules']
    assert {m['source_id'] for m in modules if m['can_apply_to_tutor']} == {'21', '23', '24'}
    assert {m['source_id'] for m in modules} == {'21', '23', '24'}
    _, _, importer, college_id, payload, _, _ = year_restricted
    full = importer.store.get(college_id, 'moodle', payload['base_url'])
    for module in full['modules']:
        if module['source_id'] == '22':
            continue
        response = student_post(client, f"/students/me/modules/{module['id']}/tutor-application", {'grade': 80})
        assert response.status_code == (200 if module['source_id'] in {'21', '23', '24'} else 403)


def test_first_year_student_has_no_eligible_modules(year_restricted):
    client, _, importer, college_id, payload, catalog, _ = year_restricted
    catalog['enrolments'] = [{'user_source_id': '10', 'course_source_id': '23'}]
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    modules = client.get('/students/me/modules').json['modules']
    assert modules == []
    full = importer.store.get(college_id, 'moodle', payload['base_url'])
    for module in full['modules']:
        if module['source_id'] == '22':
            continue
        assert student_post(client, f"/students/me/modules/{module['id']}/tutor-application", {'grade': 90}).status_code == 403


def test_previous_year_enrolment_does_not_block_tutoring(year_restricted):
    client, _, importer, college_id, payload, catalog, _ = year_restricted
    catalog['enrolments'].append({'user_source_id': '10', 'course_source_id': '23'})
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    modules = client.get('/students/me/modules').json['modules']
    assert {m['source_id'] for m in modules if m['can_apply_to_tutor']} == {'21', '23', '24'}


def test_admin_cannot_approve_an_application_that_is_no_longer_eligible(year_restricted):
    client, users, importer, college_id, payload, catalog, account = year_restricted
    module = next(m for m in client.get('/students/me/modules').json['modules'] if m['source_id'] == '21')
    application = student_post(client, f"/students/me/modules/{module['id']}/tutor-application", {'grade': 85}).json['application']
    catalog['enrolments'] = [{'user_source_id': '10', 'course_source_id': '23'}]
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    users.extensions['users_dao'].collection.update_one({'id': account['id']}, {'$set': {'roles': ['college_admin']}})
    response = student_post(client, f"/college/{college_id}/tutor-applications/{application['id']}/review", {'decision': 'approved'})
    assert response.status_code == 409
    assert client.application.extensions['lms_database'].module_memberships.count_documents({'roles': 'tutor'}) == 0


def test_lecturer_enrolment_is_not_automatically_student_membership(student):
    client, _, importer, college_id, payload, catalog, _ = student
    assert client.get('/students/me').json['modules']
    catalog['enrolments'][0]['roles'] = ['lecturer']
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    membership = client.application.extensions['lms_database'].module_memberships.find_one()
    assert membership['roles'] == ['lecturer']
    assert client.get('/students/me').json['modules'] == []
    assert client.get('/students/me/modules').json['modules'] == []


def test_explicit_profile_year_limits_search_and_direct_applications(year_restricted):
    client, _, importer, college_id, payload, catalog, _ = year_restricted
    catalog['users'][0]['current_year'] = 2
    importer.store.save(college_id, 'moodle', payload['base_url'], catalog)
    modules = client.get('/students/me/modules').json['modules']
    assert {m['source_id'] for m in modules} == {'23'}
    full = importer.store.get(college_id, 'moodle', payload['base_url'])
    same_year = next(m for m in full['modules'] if m['source_id'] == '21')
    assert student_post(client, f"/students/me/modules/{same_year['id']}/tutor-application", {'grade': 90}).status_code == 403
