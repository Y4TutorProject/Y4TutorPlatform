import json
from pathlib import Path

from dashboard_svc.app import create_app


def test_pwa_resources_are_public_and_have_correct_scope():
    client = create_app({'TESTING': True}).test_client()
    response = client.get('/manifest.webmanifest')
    manifest = json.loads(response.data)
    assert response.mimetype == 'application/manifest+json'
    assert manifest['start_url'] == '/dashboard'
    assert manifest['scope'] == '/'
    assert manifest['display'] == 'standalone'
    worker = client.get('/sw.js')
    assert worker.status_code == 200
    assert worker.headers['Service-Worker-Allowed'] == '/'
    assert worker.headers['Cache-Control'] == 'no-store'
    for path in ['/pwa/offline.html', '/pwa/pwa.js', '/pwa/mobile.css',
                 '/pwa/icon-180.png', *[icon['src'] for icon in manifest['icons']]]:
        assert client.get(path).status_code == 200
    for path in ['/pwa/manifest.webmanifest', '/pwa/sw.js', '/pwa/unknown', '/pwa/../app.py']:
        assert client.get(path).status_code == 404


def test_login_includes_shared_pwa_controls():
    from users_frontend.app import create_app as users_app
    response = users_app({'TESTING': True}).test_client().get('/login')
    html = response.get_data(as_text=True)
    assert 'href="/manifest.webmanifest"' in html
    assert 'href="/pwa/icon-180.png"' in html
    assert 'id="pwa-install"' in html
    assert 'id="pwa-update"' in html
    assert response.headers['Cache-Control'] == 'no-store'


def test_gateway_exposes_root_pwa_resources():
    config = (Path(__file__).parents[1] / 'nginx/default.conf').read_text()
    for path in ['/sw.js', '/manifest.webmanifest']:
        assert f'location = {path} {{ proxy_pass $dashboard; }}' in config
    assert 'location /pwa/ { proxy_pass $dashboard; }' in config


def test_all_role_templates_include_mobile_navigation():
    from flask import render_template
    app = create_app({'TESTING': True})
    for role, template in [('student', 'student_dashboard.html'), ('tutor', 'tutor_dashboard.html'),
                           ('lecturer', 'lecturer_dashboard.html'), ('college_admin', 'admin_dashboard.html')]:
        with app.test_request_context('/dashboard'):
            html = render_template(template, user={'id': 'test', 'username': 'Test user',
                                   'college_id': 'college', 'preferences': {}, 'roles': [role]},
                                   modules=[], is_lecturer=role == 'lecturer', can_manage_college=role == 'college_admin')
        assert 'href="/pwa/mobile.css"' in html
        assert 'aria-controls="platform-nav-actions"' in html
        assert 'aria-expanded="false"' in html
        assert 'href="/manifest.webmanifest"' in html
