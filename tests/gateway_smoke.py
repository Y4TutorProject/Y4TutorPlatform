"""Exercise signup, Mailpit verification, and college onboarding through Nginx."""
import http.cookiejar
import json
import os
import re
import time
import uuid
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from pymongo import MongoClient

base = "http://gateway"
mailpit = "http://mailpit:8025"
browser = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(path, data=None, csrf=None):
    headers = {}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if csrf:
        headers["X-CSRFToken"] = csrf
    req = Request(base + path, data=None if data is None else json.dumps(data).encode(), headers=headers)
    try:
        response = browser.open(req, timeout=20)
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


def verification_token(email):
    for attempt in range(10):
        with urlopen(mailpit + "/api/v1/messages?limit=100", timeout=10) as response:
            listing = json.load(response)
        for message in listing["messages"]:
            if any(recipient["Address"] == email for recipient in message["To"]):
                with urlopen(mailpit + "/api/v1/message/" + message["ID"], timeout=10) as response:
                    content = json.load(response)
                link = re.search(r"https?://\S+/verify-email#token=\S+", content["Text"])[0]
                return parse_qs(urlsplit(link).fragment)["token"][0]
        time.sleep(0.2)
    raise AssertionError("Verification email did not arrive in Mailpit")


name = "gateway_test_" + uuid.uuid4().hex[:12]
password = uuid.uuid4().hex
admin = {"email": name + "@example.test", "password": password, "account_type": "college_admin"}
student = {"email": "member_" + name + "@students.example.test", "password": password, "account_type": "student"}
mongo = MongoClient(os.environ["MONGO_URI"])
users = mongo["users_db"]["users"]
college_mongo = MongoClient(os.environ["COLLEGE_TEST_MONGO_URI"])
colleges = college_mongo["college_db"]["colleges"]
try:
    for path in ["/login", "/signup", "/signup/student", "/signup/college-admin", "/check-email", "/verify-email", "/register-college"]:
        assert request(path)[0] == 200, path
    assert post("registration", "/auth/signup", student)[0] == 400
    assert request("/api/colleges/college", {"name": name})[0] == 401
    status, result = post("registration", "/auth/signup", admin)
    assert status == 201, (status, result)
    assert result["user"]["roles"] == ["college_admin"] and not result["user"]["email_verified"]
    assert post("users", "/auth/login", admin)[0] == 401
    token = verification_token(admin["email"])
    assert post("registration", "/auth/verify-email", {"token": token})[0] == 200
    assert post("registration", "/auth/verify-email", {"token": token})[0] == 400
    assert post("users", "/auth/login", admin)[0] == 200
    assert request("/api/colleges/college", {"name": name})[0] == 400
    csrf = request("/api/users/auth/csrf")[1]["csrf_token"]
    payload = {"name": name, "domain": "students.example.test"}
    status, result = request("/api/colleges/college", payload, csrf)
    assert status == 201, (status, result)
    college_id = result["college"]["id"]
    assert request("/api/users/users/me")[1]["user"]["college_id"] == college_id
    assert request("/api/colleges/college", payload, csrf)[0] == 201
    assert post("users", "/auth/logout", {})[0] == 200
    listing = request("/api/colleges/college")[1]["colleges"]
    assert college_id in [college["id"] for college in listing]
    student["college_id"] = college_id
    assert post("registration", "/auth/signup", {**student, "email": "wrong@another.test"})[0] == 400
    status, result = post("registration", "/auth/signup", student)
    assert status == 201, (status, result)
    assert result["user"]["college_id"] == college_id
    assert post("users", "/auth/login", student)[0] == 401
    assert post("registration", "/auth/verify-email", {"token": verification_token(student["email"])})[0] == 200
    assert post("users", "/auth/login", student)[0] == 200
    assert request("/api/users/users/me")[1]["user"]["college_id"] == college_id
    csrf = request("/api/users/auth/csrf")[1]["csrf_token"]
    assert request("/api/colleges/college", {"name": "blocked", "domain": "blocked.test"}, csrf)[0] == 403
    assert post("users", "/auth/logout", {})[0] == 200
    print("PASS: administrator signup, Mailpit email verification, college registration and account linking")
    print("PASS: required student college, student email domain, Mailpit verification, login and permissions")
finally:
    result = users.delete_many({"email": {"$in": [admin["email"], student["email"]]}})
    print(f"Temporary test accounts removed: {result.deleted_count}")
    result = colleges.delete_one({"name": name})
    print(f"Temporary test colleges removed: {result.deleted_count}")
    mongo.close()
    college_mongo.close()
