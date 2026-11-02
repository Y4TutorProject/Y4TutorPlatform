import http.cookiejar
import json
import os
import uuid
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from pymongo import MongoClient


base = "http://gateway"
browser = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(path, data=None, csrf=None):
    headers = {}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if csrf:
        headers["X-CSRFToken"] = csrf
    req = Request(base + path, data=None if data is None else json.dumps(data).encode(), headers=headers)
    try:
        response = browser.open(req, timeout=15)
    except HTTPError as error:
        response = error
    body = response.read()
    if "application/json" in response.headers.get("Content-Type", ""):
        body = json.loads(body)
    return response.status, body


def post(service, endpoint, data):
    status, token = request(f"/api/{service}/auth/csrf")
    assert status == 200, (status, token)
    return request(f"/api/{service}{endpoint}", data, token["csrf_token"])


name = "gateway_test_" + uuid.uuid4().hex[:12]
account = {"email": name + "@example.test", "password": uuid.uuid4().hex}
mongo = MongoClient(os.environ["MONGO_URI"])
collection = mongo[os.getenv("MONGO_DB_NAME", "users_db")][os.getenv("MONGO_COLLECTION_NAME", "users")]
try:
    for path in ["/", "/login", "/signup", "/account", "/health", "/users/static/auth.css", "/users/static/auth.js", "/registration/static/auth.css", "/registration/static/auth.js"]:
        status, _ = request(path)
        assert status == 200, (path, status)
    assert request("/does-not-exist")[0] == 404
    assert request("/api/users/users/me")[0] == 401
    assert request("/api/registration/auth/signup", account)[0] == 400
    status, result = post("registration", "/auth/signup", account)
    assert status == 201, (status, result)
    username = result["user"]["username"]
    assert username.startswith("user_")
    assert result["user"]["college_id"] is None
    assert request("/api/users/users/me")[0] == 401, "Signup must not log in"
    assert post("registration", "/auth/signup", account)[0] == 409
    assert post("users", "/auth/login", {"email": account["email"], "password": "incorrect"})[0] == 401
    status, result = post("users", "/auth/login", account)
    assert status == 200, (status, result)
    status, result = request("/api/users/users/me")
    assert status == 200 and result["user"]["username"] == username, (status, result)
    assert "passhash" not in result["user"]
    assert post("users", "/auth/logout", {})[0] == 200
    assert request("/api/users/users/me")[0] == 401
    print("PASS: gateway pages/assets, routing, CSRF protection, signup, duplicate signup, invalid login, login, account, logout")
finally:
    result = collection.delete_one({"email": account["email"]})
    print(f"Temporary smoke-test accounts removed: {result.deleted_count}")
    mongo.close()
