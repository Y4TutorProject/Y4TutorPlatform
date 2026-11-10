import uuid

import pytest

from users_svc.Objects.User import User
from test_lms_import import integration
from test_college_auth import services


@pytest.fixture
def setup_manual(integration, services):
    users_app, lms, dao, importer, payload, path, headers, _ = integration
    _, users, college, _, _, _, admin = services
    college_id = path.split('/')[2]
    users_app.extensions['users_dao'].collection.update_one({'id': admin['id']}, {'$set': {'college': college_id}})
    student = User('manual_student', 'unused', 'manual@college.test', college_id=college_id,
                   preferences_completed=True)
    tutor = User('manual_tutor', 'unused', 'tutor@college.test', college_id=college_id,
                 preferences_completed=True)
    for actor in (student, tutor):
        users_app.extensions['users_dao'].add_user(actor)
    base = f'/college/{college_id}/academic'

    def actor(user_id):
        with users.session_transaction() as session:
            session['_user_id'] = str(user_id)
        cookie = users.get_cookie('tutor_session').value
        college.set_cookie('tutor_session', cookie)
        lms.set_cookie('tutor_session', cookie)

    def post(kind, data):
        return college.post(base + '/' + kind, json=data, headers=headers)

    return {'users_app': users_app, 'users': users, 'college': college, 'lms': lms, 'id': college_id,
            'student': student, 'tutor': tutor, 'admin': admin, 'actor': actor, 'post': post,
            'base': base, 'headers': headers, 'dao': dao, 'integration': integration}


def create_catalog(s):
    course = s['post']('courses', {'name': 'Computing', 'code': 'COMP'}).json['course']
    modules = [s['post']('modules', {'course_id': course['id'], 'name': f'Year {year} module',
                                   'code': f'M{year}', 'year': year}).json['module'] for year in (1, 2)]
    return course, modules


def assign(s, user, target, kind='module', role='student', year=None):
    return s['post']('assignments', {'user_id': str(user.id), 'target_type': kind,
                                    'target_id': target['id'], 'role': role, 'year': year})


def test_create_and_assign_without_any_lms_connection(setup_manual):
    s = setup_manual
    course, modules = create_catalog(s)
    assert assign(s, s['student'], course, 'course', year=2).status_code == 201
    directory = s['users'].get(f"/college/{s['id']}/users")
    assert directory.status_code == 200
    assert 'passhash' not in str(directory.json)
    s['actor'](s['student'].id)
    response = s['lms'].get('/students/me')
    assert response.status_code == 200, response.json
    assert response.json['provider'] == 'manual'
    assert [m['id'] for m in response.json['modules']] == [modules[1]['id']]
    assert response.json['courses'][0]['id'] == course['id']
    eligible = s['lms'].get('/students/me/modules').json['modules']
    assert [m['id'] for m in eligible] == [modules[0]['id']]
    assert s['users'].get(f"/college/{s['id']}/users").status_code == 403


def test_course_year_changes_and_new_modules_are_reflected(setup_manual):
    s = setup_manual
    course, modules = create_catalog(s)
    assign(s, s['student'], course, 'course', year=2)
    extra = s['post']('modules', {'course_id': course['id'], 'name': 'New module', 'year': 2}).json['module']
    s['actor'](s['student'].id)
    assert {m['id'] for m in s['lms'].get('/students/me').json['modules']} == {modules[1]['id'], extra['id']}
    s['actor'](s['admin']['id'])
    assign(s, s['student'], course, 'course', year=1)
    assert len(s['college'].get(s['base'], headers=s['headers']).json['assignments']) == 1
    s['actor'](s['student'].id)
    assert [m['id'] for m in s['lms'].get('/students/me').json['modules']] == [modules[0]['id']]


def test_manual_tutor_assignment_and_removal_affect_lookup(setup_manual):
    s = setup_manual
    _, modules = create_catalog(s)
    assign(s, s['student'], modules[0])
    assigned = assign(s, s['tutor'], modules[0], role='tutor').json['assignment']
    s['actor'](s['student'].id)
    path = f"/students/me/modules/{modules[0]['id']}/tutors"
    assert s['lms'].get(path).json['tutor_ids'] == [str(s['tutor'].id)]
    s['actor'](s['admin']['id'])
    assert s['college'].delete(s['base'] + '/assignments/' + assigned['id'], headers=s['headers']).status_code == 200
    s['actor'](s['student'].id)
    assert s['lms'].get(path).json['tutor_ids'] == []


def test_manual_tutor_application_can_be_reviewed_without_lms(setup_manual):
    s = setup_manual
    course, modules = create_catalog(s)
    assign(s, s['student'], course, 'course', year=2)
    s['actor'](s['student'].id)
    response = s['lms'].post(f"/students/me/modules/{modules[0]['id']}/tutor-application",
                             json={'grade': 88}, headers=s['headers'])
    assert response.status_code == 200, response.json
    application = response.json['application']
    s['actor'](s['admin']['id'])
    response = s['lms'].post(f"/college/{s['id']}/tutor-applications/{application['id']}/review",
                             json={'decision': 'approved'}, headers=s['headers'])
    assert response.status_code == 200, response.json
    assert response.json['application']['status'] == 'approved'


@pytest.mark.parametrize('payload', [None, [], {'name': ''}, {'name': {'$ne': ''}}, {'name': 'a' * 201}])
def test_invalid_courses_are_rejected(setup_manual, payload):
    s = setup_manual
    assert s['post']('courses', payload).status_code == 400
    assert s['dao'].db.manual_courses.count_documents({}) == 0


def test_duplicates_invalid_year_and_foreign_relationships(setup_manual):
    s = setup_manual
    course, _ = create_catalog(s)
    assert s['post']('courses', {'name': 'Other', 'code': 'comp'}).status_code == 409
    for year in (0, 21, True, 1.5, '2'):
        assert s['post']('modules', {'name': 'Bad', 'course_id': course['id'], 'year': year}).status_code == 400
    assert s['post']('modules', {'name': 'Bad', 'course_id': str(uuid.uuid4()), 'year': 1}).status_code == 400
    foreign = User('foreign', 'unused', 'foreign@other.test', college_id=uuid.uuid4())
    s['users_app'].extensions['users_dao'].add_user(foreign)
    assert assign(s, foreign, course, 'course', year=1).status_code == 400
    assert assign(s, s['student'], course, 'course', role='tutor', year=1).status_code == 400


def test_manual_routes_enforce_session_csrf_and_ownership(setup_manual):
    s = setup_manual
    assert s['college'].post(s['base'] + '/courses', json={'name': 'Bad'}).status_code == 400
    assert s['college'].get(f"/college/{uuid.uuid4()}/academic", headers=s['headers']).status_code == 403
    s['actor'](s['student'].id)
    assert s['post']('courses', {'name': 'Bad'}).status_code == 403
    assert s['college'].get(s['base'], headers=s['headers']).status_code == 403
    s['college'].delete_cookie('tutor_session')
    assert s['college'].get(s['base'], headers=s['headers']).status_code == 401
    assert s['college'].get(f"/internal/college/{s['id']}/manual-academic").status_code == 401


def test_manual_records_survive_an_lms_import(setup_manual):
    s = setup_manual
    course, modules = create_catalog(s)
    assign(s, s['student'], course, 'course', year=2)
    _, _, _, importer, payload, path, _, _ = s['integration']
    before = s['college'].get(s['base'], headers=s['headers']).json
    importer.import_catalog(s['id'], payload)
    assert s['college'].get(s['base'], headers=s['headers']).json == before
    s['lms'].application.extensions['lms_sync'].connections.collection.insert_one({
        '_id': s['id'], 'provider': payload['provider'], 'base_url': payload['base_url']})
    s['actor'](s['student'].id)
    response = s['lms'].get('/students/me')
    assert response.status_code == 200, response.json
    assert [m['id'] for m in response.json['modules']] == [modules[1]['id']]


def test_manual_and_imported_enrolments_coexist_for_same_user(setup_manual):
    s = setup_manual
    course, modules = create_catalog(s)
    assign(s, s['student'], course, 'course', year=2)
    _, _, _, importer, payload, _, _, responses = s['integration']
    responses['core_user_get_users']['users'][0]['email'] = s['student'].email
    importer.import_catalog(s['id'], payload)
    s['lms'].application.extensions['lms_sync'].connections.collection.insert_one({
        '_id': s['id'], 'provider': payload['provider'], 'base_url': payload['base_url']})
    s['actor'](s['student'].id)
    response = s['lms'].get('/students/me')
    assert response.status_code == 200, response.json
    assert {m['name'] for m in response.json['modules']} == {'Databases', 'Year 2 module'}
    assert len(response.json['courses']) == 2


def test_inactive_and_foreign_users_are_not_assignable(setup_manual):
    s = setup_manual
    course, _ = create_catalog(s)
    s['users_app'].extensions['users_dao'].collection.update_one(
        {'id': str(s['student'].id)}, {'$set': {'status': 'suspended'}})
    directory = s['users'].get(f"/college/{s['id']}/users").json['users']
    assert str(s['student'].id) not in {u['id'] for u in directory}
    assert assign(s, s['student'], course, 'course', year=1).status_code == 400
    assert s['users'].get(f'/college/{uuid.uuid4()}/users').status_code == 403
