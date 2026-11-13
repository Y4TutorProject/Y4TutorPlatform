import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from dashboard_svc.app import create_app


@pytest.fixture
def frontend(monkeypatch):
    app = create_app({
        "TESTING": True,
        "USERS_API_URL": "http://users.test",
        "LMS_API_URL": "http://lms.test",
        "MATCHING_API_URL": "http://matching.test",
    })
    client = app.test_client()
    client.set_cookie("tutor_session", "signed-session")
    return app, client


def json_response(data):
    return BytesIO(json.dumps(data).encode())


def test_student_dashboard_renders_sidebar_and_tutor_area(frontend, monkeypatch):
    app, client = frontend

    def upstream(request, timeout):
        if request.full_url.endswith("/users/me"):
            return json_response({"user": {"email_verified": True, "roles": ["student"]}})
        return json_response({
            "student": {"username": "student"},
            "modules": [{"id": "module-1", "display_name": "Web & SQL"}],
        })

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    response = client.get("/dashboard")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-module="module-1"' in html
    assert "Web &amp; SQL" in html
    assert 'id="tutor-results"' in html
    assert "student_dashboard.css" in html
    assert '/dashboard/static/modules.js' in html
    assert html.index('/dashboard/static/auth.js') < html.index('/dashboard/static/modules.js')
    assert 'id="open-tutor-applications"' in html
    assert 'aria-controls="tutor-application-panel" aria-expanded="false" hidden' in html
    assert 'id="tutor-application-panel"' in html
    assert 'id="module-search-form"' in html
    assert 'id="programme-modules"' in html


@pytest.mark.parametrize('roles,status', [(['college_admin'], 200), (['student', 'college_admin'], 200), (['student'], 403)])
def test_manual_academic_controls_require_college_administrator(frontend, monkeypatch, roles, status):
    app, client = frontend
    monkeypatch.setattr(app.extensions['users_opener'], 'open', lambda *args, **kwargs:
        json_response({'user': {'id': 'admin', 'username': 'Admin', 'roles': roles,
                                'college_id': 'college-id', 'email_verified': True}}))
    response = client.get('/admin-dashboard')
    html = response.get_data(as_text=True)
    assert response.status_code == status
    assert ('id="academic-management"' in html) is (status == 200)
    assert ('id="lms-imported-data"' in html) is (status == 200)
    assert ('id="academic-csv-upload"' in html) is (status == 200)
    if status == 200:
        for marker in ('create-course-form', 'create-module-form', 'assign-academic-user-form'):
            assert f'id="{marker}"' in html
        assert 'data-college-id="college-id"' in html
        assert html.index('/dashboard/static/auth.js') < html.index('/dashboard/static/academic_admin.js')
        assert html.index('/dashboard/static/auth.js') < html.index('/dashboard/static/lms_catalog.js')
        assert html.index('/dashboard/static/auth.js') < html.index('/dashboard/static/csv_upload.js')


@pytest.mark.parametrize('kind', ['modules', 'users'])
def test_csv_templates_are_downloadable(frontend, kind):
    _, client = frontend
    response = client.get(f'/dashboard/static/templates/{kind}.csv')
    assert response.status_code == 200
    assert (b'course_code,course_name,module_code' if kind == 'modules' else b'email,first_name,last_name') in response.data


@pytest.mark.parametrize("tutor_ids", [[], ["tutor-1", "tutor-2"]])
def test_get_tutors_returns_profiles(frontend, monkeypatch, tutor_ids):
    app, client = frontend
    requested = []

    def upstream(request, timeout):
        requested.append(request.full_url)
        assert request.get_header("Cookie") == "tutor_session=signed-session"
        assert request.get_header("User-agent") == "test-browser"
        assert timeout == 5
        if request.full_url == "http://users.test/users/me":
            return json_response({"user": {"email_verified": True}})
        if request.full_url == "http://lms.test/students/me/modules/module-1/tutors":
            return json_response({"tutor_ids": tutor_ids})
        if request.full_url == "http://matching.test/get-recommendations":
            payload = json.loads(request.data.decode())
            return json_response([[tutor_id, 42] for tutor_id in payload["tutors"]])
        tutor_id = request.full_url.removeprefix("http://users.test/users/")
        assert tutor_id in tutor_ids
        return json_response({"user": {
            "id": tutor_id, "username": tutor_id, "teaching_preferences": {"visual": 5},
        }})

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    response = client.get("/get_tutors?module_id=module-1", headers={"User-Agent": "test-browser"})

    assert response.status_code == 200
    assert response.json == {"tutors": [
        {
            "id": tutor_id,
            "username": tutor_id,
            "teaching_preferences": {"visual": 5},
            "similarity": 42.0,
        }
        for tutor_id in tutor_ids
    ]}
    assert requested == [
        "http://users.test/users/me",
        "http://lms.test/students/me/modules/module-1/tutors",
        *[f"http://users.test/users/{tutor_id}" for tutor_id in tutor_ids],
        "http://matching.test/get-recommendations",
    ]


@pytest.mark.parametrize("payload", [{}, {"tutor_ids": "tutor-1"}, {"tutor_ids": [1]}])
def test_get_tutors_rejects_malformed_lms_response(frontend, monkeypatch, payload):
    app, client = frontend

    def upstream(request, timeout):
        if request.full_url.endswith("/users/me"):
            return json_response({"user": {"email_verified": True}})
        return json_response(payload)

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    assert client.get("/get_tutors?module_id=module-1").status_code == 502


@pytest.mark.parametrize("failure", [
    HTTPError("http://users.test", 404, "Not found", {}, None),
    URLError("unavailable"),
])
def test_get_tutors_reports_profile_lookup_failures(frontend, monkeypatch, failure):
    app, client = frontend

    def upstream(request, timeout):
        if request.full_url.endswith("/users/me"):
            return json_response({"user": {"email_verified": True}})
        if request.full_url.startswith("http://lms.test/"):
            return json_response({"tutor_ids": ["tutor-1"]})
        raise failure

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    assert client.get("/get_tutors?module_id=module-1").status_code == 502


def test_get_tutors_rejects_malformed_profile(frontend, monkeypatch):
    app, client = frontend

    def upstream(request, timeout):
        if request.full_url.endswith("/users/me"):
            return json_response({"user": {"email_verified": True}})
        if request.full_url.startswith("http://lms.test/"):
            return json_response({"tutor_ids": ["tutor-1"]})
        return json_response({"user": None})

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    assert client.get("/get_tutors?module_id=module-1").status_code == 502


def test_get_tutors_returns_502_when_matching_service_is_unavailable(frontend, monkeypatch, caplog):
    app, client = frontend

    def upstream(request, timeout):
        if request.full_url.endswith("/users/me"):
            return json_response({"user": {"id": "student-1", "email_verified": True}})
        if request.full_url.startswith("http://lms.test/"):
            return json_response({"tutor_ids": ["tutor-1"]})
        if request.full_url == "http://users.test/users/tutor-1":
            return json_response({"user": {"id": "tutor-1", "username": "Private Name"}})
        raise URLError("unavailable")

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    response = client.get("/get_tutors?module_id=module-1")

    assert response.status_code == 502
    assert "temporarily unavailable" in response.text
    assert "Tutor matching failed (URLError)" in caplog.text
    assert "Private Name" not in caplog.text


def test_get_tutors_rejects_profile_for_a_different_user(frontend, monkeypatch):
    app, client = frontend

    def upstream(request, timeout):
        if request.full_url.endswith("/users/me"):
            return json_response({"user": {"email_verified": True}})
        if request.full_url.startswith("http://lms.test/"):
            return json_response({"tutor_ids": ["tutor-1"]})
        return json_response({"user": {"id": "different-user"}})

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    assert client.get("/get_tutors?module_id=module-1").status_code == 502


def test_lecturer_review_screen_uses_current_user_endpoint(frontend, monkeypatch):
    app, client = frontend
    monkeypatch.setattr(app.extensions['users_opener'], 'open', lambda *args, **kwargs:
        json_response({'user': {'id': 'lecturer', 'roles': ['student'], 'college_id': 'college', 'email_verified': True}}))
    response = client.get('/tutor-applications')
    assert response.status_code == 200
    assert 'data-review-path="/lecturers/me/tutor-applications"' in response.text
    assert 'id="tutor-review-list"' in response.text


def test_lecturer_lands_on_teaching_dashboard_with_assigned_modules(frontend, monkeypatch):
    app, client = frontend
    modules = [{'id': 'teaching-1', 'name': 'Business & Finance', 'code': 'BUS1', 'year': 1}]
    def upstream(request, timeout):
        if request.full_url.endswith('/users/me'):
            return json_response({'user': {'email_verified': True, 'username': 'modulelecturer254', 'roles': ['student']}})
        return json_response({'student': {'username': 'modulelecturer254'}, 'modules': [], 'lecturer_modules': modules})
    monkeypatch.setattr(app.extensions['users_opener'], 'open', upstream)
    response = client.get('/dashboard')
    assert response.status_code == 200
    assert 'Your teaching modules' in response.text
    assert 'Business &amp; Finance' in response.text
    assert 'data-module-id="teaching-1"' in response.text
    assert 'id="tutor-review-list"' in response.text
    assert 'Find your tutor' not in response.text
    assert 'id="role-switcher"' not in response.text


def test_lecturer_dashboard_reads_authorized_teaching_modules(frontend, monkeypatch):
    app, client = frontend
    def upstream(request, timeout):
        if request.full_url.endswith('/users/me'):
            return json_response({'user': {'email_verified': True, 'roles': ['student']}})
        assert request.full_url == 'http://lms.test/lecturers/me/modules'
        return json_response({'modules': [{'id': 'm1', 'name': 'Networks', 'year': 2}]})
    monkeypatch.setattr(app.extensions['users_opener'], 'open', upstream)
    response = client.get('/lecturer-dashboard')
    assert response.status_code == 200
    assert 'Networks' in response.text


def test_tutor_results_exclude_the_signed_in_user(frontend, monkeypatch):
    app, client = frontend
    def upstream(request, timeout):
        if request.full_url.endswith('/users/me'):
            return json_response({'user': {'id': 'me', 'email_verified': True}})
        if request.full_url.startswith('http://lms.test/'):
            return json_response({'tutor_ids': ['me', 'another-tutor']})
        if request.full_url == 'http://matching.test/get-recommendations':
            return json_response([['another-tutor', 75]])
        assert request.full_url == 'http://users.test/users/another-tutor'
        return json_response({'user': {'id': 'another-tutor', 'username': 'Tutor'}})
    monkeypatch.setattr(app.extensions['users_opener'], 'open', upstream)
    response = client.get('/get_tutors?module_id=module-1')
    assert response.status_code == 200
    assert [u['id'] for u in response.json['tutors']] == ['another-tutor']


def test_message_tutor_rejects_self_chat_before_calling_messaging(frontend, monkeypatch):
    app, client = frontend
    monkeypatch.setattr(app.extensions['users_opener'], 'open', lambda *args, **kwargs:
        json_response({'user': {'id': 'me', 'username': 'Me', 'email_verified': True}}))
    def unexpected(*args, **kwargs):
        pytest.fail('A self-chat must never reach messaging.')
    monkeypatch.setattr('routes.messaging.messaging_post', unexpected)
    response = client.get('/getmessages?user_id=me&username=Me')
    assert response.status_code == 400
    assert 'You cannot message yourself.' in response.text


def test_message_tutor_opens_another_users_chat(frontend, monkeypatch):
    app, client = frontend
    monkeypatch.setattr(app.extensions['users_opener'], 'open', lambda *args, **kwargs:
        json_response({'user': {'id': 'me', 'username': 'Me', 'email_verified': True}}))
    calls=[]
    class Reply:
        ok=True
        def __init__(self, payload):
            self.payload=payload
        def json(self):
            return self.payload
    def messaging(client, path, payload):
        calls.append((path,payload))
        return Reply({'chatId':'chat-1'} if path=='/mychats/new' else {'chats':[]})
    monkeypatch.setattr('routes.messaging.messaging_post', messaging)
    response=client.get('/getmessages?user_id=another-tutor&username=Tutor')
    assert response.status_code==200
    assert 'data-open-chat-id="chat-1"' in response.text
    assert [path for path,_ in calls]==['/mychats/new','/mychats/me']
    assert calls[0][1]['otherUserId']=='another-tutor'


@pytest.mark.parametrize("path", ["/messages", "/getmessages?user_id=tutor-1&username=old-name"])
def test_conversations_show_current_usernames(frontend, monkeypatch, path):
    app, client = frontend
    requested = []

    def upstream(request, timeout):
        requested.append(request.full_url)
        assert request.get_header("Cookie") == "tutor_session=signed-session"
        if request.full_url.endswith("/users/me"):
            return json_response({"user": {
                "id": "me", "username": "Me", "email_verified": True,
            }})
        if request.full_url.endswith("/users/tutor-1"):
            return json_response({"user": {"id": "tutor-1", "username": "Tutor & friend"}})
        raise HTTPError(request.full_url, 404, "Not found", {}, None)

    class Reply:
        ok = True
        def __init__(self, payload):
            self.payload = payload
        def json(self):
            return self.payload

    def messaging(client, endpoint, payload):
        if endpoint == "/mychats/new":
            return Reply({"chatId": "chat-1"})
        return Reply({"chats": [
            {"chatId": "chat-1", "otherUserId": "tutor-1", "displayName": "tutor-1"},
            {"chatId": "chat-2", "otherUserId": "tutor-1", "displayName": "tutor-1"},
            {"chatId": "chat-3", "otherUserId": "missing", "displayName": "missing"},
        ]})

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    monkeypatch.setattr("routes.messaging.messaging_post", messaging)
    response = client.get(path)

    assert response.status_code == 200
    assert response.text.count('data-display-name="Tutor &amp; friend"') == 2
    assert 'data-display-name="Unavailable user"' in response.text
    assert 'data-display-name="tutor-1"' not in response.text
    assert requested.count("http://users.test/users/tutor-1") == 1
    assert requested.count("http://users.test/users/missing") == 1


def test_conversations_report_username_lookup_failure(frontend, monkeypatch):
    app, client = frontend

    def upstream(request, timeout):
        if request.full_url.endswith("/users/me"):
            return json_response({"user": {
                "id": "me", "username": "Me", "email_verified": True,
            }})
        raise URLError("unavailable")

    class Reply:
        ok = True
        def json(self):
            return {"chats": [{"chatId": "chat-1", "otherUserId": "tutor-1"}]}

    monkeypatch.setattr(app.extensions["users_opener"], "open", upstream)
    monkeypatch.setattr("routes.messaging.messaging_post", lambda *args: Reply())
    response = client.get("/messages")

    assert response.status_code == 502
    assert "Could not load conversation usernames" in response.text
