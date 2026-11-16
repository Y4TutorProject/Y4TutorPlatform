import json
import uuid
from io import BytesIO
from urllib.error import URLError

import pytest

from test_auth import app, client, registration_app, registration_client, signup, login
from test_lms_import import integration
from test_college_auth import services


@pytest.mark.parametrize('module_role,expected', [('tutor', True), ('student', False), ('lecturer', False)])
def test_module_role_lookup_is_service_authenticated_and_college_scoped(integration, module_role, expected):
    _, client, *rest = integration
    app = client.application
    app.config['COLLEGE_SYNC_TOKEN'] = 'service-secret'
    college, user = str(uuid.uuid4()), str(uuid.uuid4())
    app.extensions['lms_database'].module_memberships.insert_one({
        'college_id': college, 'user_id': user, 'module_id': 'module', 'roles': [module_role]})
    path = f'/internal/college/{college}/users/{user}/module-roles'
    assert client.get(path).status_code == 401
    assert client.get(path, headers={'X-College-Sync-Token': 'wrong'}).status_code == 401
    headers = {'X-College-Sync-Token': 'service-secret'}
    assert client.get(path, headers=headers).json == {'tutor': expected}
    assert client.get(path.replace(college, str(uuid.uuid4())), headers=headers).json == {'tutor': False}
    app.config['COLLEGE_SYNC_TOKEN'] = ''
    assert client.get(path, headers=headers).status_code == 401


def test_existing_approval_promotes_signed_in_account_and_preserves_student(app, client, signup, monkeypatch):
    signup()
    assert login(client).status_code == 200
    roles = app.extensions['module_roles_client']
    roles.token = 'service-secret'
    calls = []

    def lookup(request, timeout):
        calls.append(request)
        return BytesIO(json.dumps({'tutor': True}).encode())

    monkeypatch.setattr(roles.opener, 'open', lookup)
    assert set(client.get('/users/me').json['user']['roles']) == {'student', 'tutor'}
    assert set(app.extensions['users_dao'].collection.find_one()['roles']) == {'student', 'tutor'}
    assert set(client.get('/users/me').json['user']['roles']) == {'student', 'tutor'}
    assert len(calls) == 1
    assert calls[0].get_header('X-college-sync-token') == 'service-secret'


@pytest.mark.parametrize('result', [False, 'unavailable'])
def test_no_membership_or_failed_lookup_does_not_promote(app, client, signup, monkeypatch, result):
    signup()
    roles = app.extensions['module_roles_client']
    roles.token = 'service-secret'

    def lookup(request, timeout):
        if result == 'unavailable':
            raise URLError('offline')
        return BytesIO(b'{"tutor": false}')

    monkeypatch.setattr(roles.opener, 'open', lookup)
    assert login(client).json['user']['roles'] == ['student']
    assert client.get('/users/me').json['user']['roles'] == ['student']


def test_approval_is_resolved_during_login(app, client, signup, monkeypatch):
    signup()
    monkeypatch.setattr(app.extensions['module_roles_client'], 'has_tutor_module', lambda user: True)
    assert set(login(client).json['user']['roles']) == {'student', 'tutor'}
