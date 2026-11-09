from asyncio.log import logger
from pathlib import Path
import json
import os
from http.cookies import SimpleCookie
from urllib import response
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import hashlib
import hmac

from flask import Flask, abort, make_response, redirect, render_template, request, Response
from jinja2 import ChoiceLoader, FileSystemLoader
from clean_text import clean_deep
import requests



class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def create_app(config=None):
    shared =  Path(os.environ.get(
        "FRONTEND_SHARED_PATH",
        Path(__file__).resolve().parent.parent / "frontend_shared",
    ))
    app = Flask(__name__, static_folder=str(shared / "static"), static_url_path="/dashboard/static")
    app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(shared / "templates")])
    # Use the same gateway hop as browser API calls to preserve Flask-Login's
    # session binding to the user agent and immediate peer address.
    app.config["USERS_API_URL"] = os.getenv("USERS_API_URL", "http://gateway/api/users")
    app.config["LMS_API_URL"] = os.getenv("LMS_API_URL", "http://gateway/api/lms")
    app.config["MESSAGING_API_URL"] = os.getenv("MESSAGING_API_URL", "http://gateway/api/messaging")
    app.config["DASHBOARD_SHARED_SECRET"] = os.getenv("DASHBOARD_SHARED_SECRET")
    if config:
        app.config.update(config)
    app.extensions["users_opener"] = build_opener(NoRedirect())

    def messaging_post(client, path, payload):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            app.config["DASHBOARD_SHARED_SECRET"].encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return client.post(
            app.config["MESSAGING_API_URL"].rstrip("/") + path,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Dashboard-Signature": signature,
            },
            timeout=5,
        )

    def forward_messaging_cookie(response, client):
        cookie = client.cookies.get("messaging_session")
        if cookie:
            response.set_cookie(
                "messaging_session",
                cookie,
                httponly=True,
                secure=request.headers.get(
                    "X-Forwarded-Proto", request.scheme
                ).lower() == "https",
                samesite="Lax",
            )
        return response

    def authenticated_user():
        session_cookie = request.cookies.get("tutor_session")
        if not session_cookie:
            return None
        cookie = SimpleCookie()
        cookie["tutor_session"] = session_cookie
        upstream = Request(
            app.config["USERS_API_URL"].rstrip("/") + "/users/me",
            headers={"Cookie": cookie.output(header="").strip(),
                     "User-Agent": request.headers.get("User-Agent", "")},
        )
        try:
            with app.extensions["users_opener"].open(upstream, timeout=5) as response:
                user = json.load(response).get("user")
        except HTTPError as error:
            error.close()
            if error.code == 401:
                return None
            abort(503)
        except (URLError, OSError, ValueError, AttributeError):
            abort(503)
        return user if isinstance(user, dict) else None

    @app.get("/login")
    def login():
        if authenticated_user():
            return redirect("/dashboard")
        return render_template("login.html")

    @app.get("/dashboard")
    def dashboard():
        user = authenticated_user()
        if user is None:
            return redirect("/login")
        if not isinstance(user, dict) or user.get("email_verified") is not True:
            abort(503)
        session_cookie = request.cookies["tutor_session"]
        cookie = SimpleCookie()
        cookie["tutor_session"] = session_cookie
        upstream = Request(
            app.config["USERS_API_URL"].rstrip("/") + "/users/me",
            headers={"Cookie": cookie.output(header="").strip(),
                     "User-Agent": request.headers.get("User-Agent", "")},
        )
        can_manage_college = "college_admin" in (user.get("roles") or []) and bool(user.get("college_id"))
        is_student = "student" in (user.get("roles") or [])
        moodle = None
        moodle_error = None
        if is_student:
            upstream = Request(app.config["LMS_API_URL"].rstrip("/") + "/students/me", headers=dict(upstream.header_items()))
            try:
                with app.extensions["users_opener"].open(upstream, timeout=5) as response:
                    moodle = clean_deep(json.load(response))
            except HTTPError as error:
                error.close()
                if error.code == 401:
                    return redirect("/login")
                moodle_error = ("Your Moodle profile is not available yet. Ask your college administrator to check that your verified email matches Moodle and that the college has synchronized."
                                if error.code == 404 else "Moodle information is temporarily unavailable. Please try again later.")
            except (URLError, OSError, ValueError):
                moodle_error = "Moodle information is temporarily unavailable. Please try again later."
        if is_student:
            return render_template("student_dashboard.html", user=user, can_manage_college=can_manage_college,
                                is_student=is_student, moodle=moodle, moodle_error=moodle_error)
        if can_manage_college:
            return render_template("college_admin_dashboard.html", user=user, can_manage_college=can_manage_college,
                                is_student=is_student)
        else:
            return redirect("/account")

    @app.get("/getmessages")
    def messaging():
        user = authenticated_user()
        if user is None:
            return redirect("/login")
        if not isinstance(user, dict) or user.get("email_verified") is not True:
            abort(503)
        other_user_id, other_user_name = request.args.get("user_id"), request.args.get("username")
        if not other_user_id or not other_user_name:
            abort(400, "Missing user_id or username parameter")
        return trigger_messaging(user, {"id": other_user_id, "username": other_user_name})



    def trigger_messaging(current, other):
        """
        The dashboard must send a JSON object with this shape:
                {
        "user": {
            "id": "student-uuid",
            "username": "student123",
            "status": "active",
            "roles": ["student"]
        },
        "users": {
            "student-uuid": "student123",
            "tutor-uuid": "tutor456"
        }
        }
        """
        request_body = {
            "user": {
                "id": current["id"],
                "username": current["username"],
                "status": "active",
            },
            "users": {
                other["id"]: other["username"],
            },
            "otherUserId": other["id"]
        }
        client = requests.Session()
        response = messaging_post(client, "/mychats/new", request_body)
        if not response.ok:
            abort(502, "Messaging service could not create the chat")
        chat_id = response.json().get("chatId")
        if not chat_id:
            abort(500, "Failed to create or retrieve chat")

        chats_response = messaging_post(client, "/mychats/me", request_body)
        if not chats_response.ok:
            abort(502, "Messaging service could not load chats")
        chats = chats_response.json().get("chats", [])
        rendered = render_template(
            "messaging.html",
            user=current["id"],
            chats=chats,
            openChat=chat_id,
        )
        return forward_messaging_cookie(make_response(rendered), client)

    @app.get("/messages")
    def messages():
        user = authenticated_user()
        if user is None:
            return redirect("/login")
        if not isinstance(user, dict) or user.get("email_verified") is not True:
            abort(503)
        # get chat list for this user
        client = requests.Session()
        data = messaging_post(client, "/mychats/me", {"user": user})
        if not data.ok:
            abort(502, "Messaging service could not load chats")
        chatList = data.json().get("chats", [])
        rendered = render_template(
            "messaging.html",
            user=user["id"],
            chats=chatList,
        )
        return forward_messaging_cookie(make_response(rendered), client)
    
    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    return app
