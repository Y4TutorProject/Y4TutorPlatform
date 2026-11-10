from io import BytesIO
import uuid

import pytest

from college_svc.csv_import import MAX_BYTES, MAX_ROWS
from users_svc.Objects.User import User
from test_manual_academics import setup_manual, create_catalog
from test_lms_import import integration
from test_college_auth import services

MODULES = 'course_code,course_name,module_code,module_name,year\n'
USERS = 'email,first_name,last_name,username,course_code,year,module_code,role\n'


def upload(s, kind, content, apply=False, filename='data.csv', headers=None):
    return s['college'].post(s['base'] + '/import/' + kind, data={
        'file': (BytesIO(content.encode('utf-8') if isinstance(content, str) else content), filename),
        'dry_run': 'false' if apply else 'true',
    }, headers=s['headers'] if headers is None else headers)


def test_module_preview_apply_and_retry_are_idempotent(setup_manual):
    s = setup_manual
    content = '\ufeff' + MODULES + 'COMP,Computing,DB1,"Databases, SQL",1\nCOMP,Computing,WEB2,Web,2\n'
    preview = upload(s, 'modules', content)
    assert preview.status_code == 200, preview.json
    assert preview.json['summary']['courses_created'] == 1
    assert preview.json['summary']['modules_created'] == 2
    assert s['dao'].db.manual_courses.count_documents({}) == 0
    result = upload(s, 'modules', content, apply=True)
    assert result.json['applied'] is True
    records = s['college'].get(s['base'], headers=s['headers']).json
    assert len(records['courses']) == 1 and len(records['modules']) == 2
    assert any(m['name'] == 'Databases, SQL' for m in records['modules'])
    repeated = upload(s, 'modules', content, apply=True)
    assert repeated.json['summary']['modules_created'] == 0
    assert repeated.json['summary']['rows_already_present'] == 2
    assert s['college'].get(s['base'], headers=s['headers']).json == records


def test_invalid_row_prevents_all_writes_and_reports_line(setup_manual):
    s = setup_manual
    result = upload(s, 'modules', MODULES + 'COMP,Computing,DB1,Good,1\nCOMP,Computing,DB2,Bad,99\n', apply=True)
    assert result.status_code == 422
    assert result.json['errors'][0]['row'] == 3
    assert 'Year' in result.json['errors'][0]['message']
    assert result.json['applied'] is False
    assert s['dao'].db.manual_courses.count_documents({}) == 0
    assert s['dao'].db.manual_modules.count_documents({}) == 0


def test_conflicting_duplicate_codes_are_errors(setup_manual):
    s = setup_manual
    result = upload(s, 'modules', MODULES + 'COMP,Computing,DB1,Databases,1\nCOMP,Computing,DB1,Different,1\n')
    assert result.status_code == 422
    assert result.json['errors'][0]['row'] == 3
    create_catalog(s)
    assert upload(s, 'modules', MODULES + 'COMP,Wrong name,M3,New,3\n').status_code == 422


def test_users_directory_and_assignments_link_after_registration(setup_manual):
    s = setup_manual
    course, modules = create_catalog(s)
    content = USERS + 'later@college.test,Later,Student,later,COMP,2,,student\n'
    count = s['users_app'].extensions['users_dao'].collection.count_documents({})
    preview = upload(s, 'users', content)
    assert preview.json['summary']['awaiting_registration'] == 1
    assert s['dao'].db.manual_directory_users.count_documents({}) == 0
    assert upload(s, 'users', content, apply=True).json['applied'] is True
    assert s['users_app'].extensions['users_dao'].collection.count_documents({}) == count
    record = s['dao'].db.manual_assignments.find_one()
    assert record['user_id'] is None
    assert record['user_email'] == 'later@college.test'
    later = User('registered_later', 'unused', 'later@college.test', college_id=s['id'])
    s['users_app'].extensions['users_dao'].add_user(later)
    s['actor'](later.id)
    response = s['lms'].get('/students/me')
    assert response.status_code == 200, response.json
    assert response.json['student']['first_name'] == 'Later'
    assert [m['id'] for m in response.json['modules']] == [modules[1]['id']]
    assert s['dao'].db.manual_assignments.find_one()['user_id'] == str(later.id)
    assert s['dao'].db.manual_directory_users.find_one()['user_id'] == str(later.id)


def test_existing_users_link_immediately_and_multiple_assignments_are_supported(setup_manual):
    s = setup_manual
    _, modules = create_catalog(s)
    content = USERS + 'manual@college.test,A,Student,manual,COMP,2,,student\nmanual@college.test,A,Student,manual,COMP,1,M1,tutor\n'
    result = upload(s, 'users', content, apply=True)
    assert result.status_code == 200, result.json
    assert result.json['summary']['directory_users_created'] == 1
    assert result.json['summary']['assignments_created'] == 2
    assert result.json['summary']['awaiting_registration'] == 0
    assert {a['user_id'] for a in s['dao'].db.manual_assignments.find()} == {str(s['student'].id)}
    repeat = upload(s, 'users', content, apply=True)
    assert repeat.json['summary']['directory_users_created'] == 0
    assert repeat.json['summary']['assignments_created'] == 0
    assert repeat.json['summary']['assignments_updated'] == 0
    s['actor'](s['student'].id)
    assert s['lms'].get(f"/students/me/modules/{modules[0]['id']}/tutors").json['tutor_ids'] == [str(s['student'].id)]


def test_directory_only_rows_are_supported_without_courses(setup_manual):
    s = setup_manual
    response = upload(s, 'users', USERS + 'later@college.test,Later,Student,later,,,,\n', apply=True)
    assert response.status_code == 200, response.json
    assert s['dao'].db.manual_directory_users.count_documents({}) == 1
    assert s['dao'].db.manual_assignments.count_documents({}) == 0


@pytest.mark.parametrize('row', [
    'bad-email,A,B,a,,,,',
    'later@college.test,A,B,a,UNKNOWN,2,,student',
    'later@college.test,A,B,a,COMP,2,UNKNOWN,student',
    'later@college.test,A,B,a,COMP,1,,tutor',
    'later@college.test,A,B,a,COMP,1,M1,college_admin',
    'later@college.test,A,B,a,COMP,0,,student',
])
def test_invalid_user_rows_do_not_write(setup_manual, row):
    s = setup_manual
    create_catalog(s)
    response = upload(s, 'users', USERS + row + '\n', apply=True)
    assert response.status_code == 422, response.json
    assert s['dao'].db.manual_directory_users.count_documents({}) == 0
    assert s['dao'].db.manual_assignments.count_documents({}) == 0


def test_user_csv_domain_and_conflicting_rows_are_validated(setup_manual):
    s = setup_manual
    create_catalog(s)
    s['dao'].collection.update_one({'id': s['id']}, {'$set': {'domain': 'college.test'}})
    assert upload(s, 'users', USERS + 'other@foreign.test,A,B,a,,,,\n').status_code == 422
    content = USERS + 'later@college.test,A,B,a,COMP,1,,student\nlater@college.test,A,B,a,COMP,2,,student\n'
    assert upload(s, 'users', content, apply=True).status_code == 422
    assert s['dao'].db.manual_assignments.count_documents({}) == 0


@pytest.mark.parametrize('content,filename', [
    ('', 'data.csv'), ('name,year\nTest,1', 'data.csv'),
    (MODULES, 'data.csv'), (MODULES + 'COMP,Computing,DB1,Name,1,EXTRA\n', 'data.csv'),
    (b'\xff\xfe\x00', 'data.csv'), (MODULES + '"broken quote', 'data.csv'),
    (MODULES, 'data.txt'),
])
def test_bad_files_and_headers_are_rejected(setup_manual, content, filename):
    response = upload(setup_manual, 'modules', content, filename=filename)
    assert response.status_code in (400, 422)


def test_size_and_row_limits(setup_manual):
    s = setup_manual
    assert upload(s, 'modules', b'a' * (MAX_BYTES + 1)).status_code == 400
    content = MODULES + ('COMP,Computing,DB1,Databases,1\n' * (MAX_ROWS + 1))
    assert upload(s, 'modules', content).status_code == 400


def test_csv_upload_enforces_csrf_role_and_college_ownership(setup_manual):
    s = setup_manual
    content = MODULES + 'COMP,Computing,DB1,Databases,1\n'
    assert upload(s, 'modules', content, headers={}).status_code == 400
    foreign = {**s, 'base': f'/college/{uuid.uuid4()}/academic'}
    assert upload(foreign, 'modules', content).status_code == 403
    s['actor'](s['student'].id)
    assert upload(s, 'modules', content).status_code == 403
    s['college'].delete_cookie('tutor_session')
    assert upload(s, 'modules', content).status_code == 401
    assert s['college'].post(f"/internal/college/{s['id']}/manual-academic",
        json={'user_id': str(s['student'].id), 'email': s['student'].email}).status_code == 401


def test_csv_tutor_becomes_discoverable_after_registration(setup_manual):
    s = setup_manual
    _, modules = create_catalog(s)
    content = USERS + 'later_tutor@college.test,Later,Tutor,later_tutor,COMP,1,M1,tutor\nmanual@college.test,A,Student,manual,COMP,2,,student\n'
    assert upload(s, 'users', content, apply=True).status_code == 200
    path = f"/students/me/modules/{modules[0]['id']}/tutors"
    s['actor'](s['student'].id)
    assert s['lms'].get(path).json['tutor_ids'] == []
    tutor = User('later_tutor', 'unused', 'later_tutor@college.test', college_id=s['id'])
    s['users_app'].extensions['users_dao'].add_user(tutor)
    s['actor'](tutor.id)
    assert s['lms'].get('/students/me').status_code == 200
    s['actor'](s['student'].id)
    assert s['lms'].get(path).json['tutor_ids'] == [str(tutor.id)]
