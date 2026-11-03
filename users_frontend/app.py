from pathlib import Path
import json
import os
from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from flask import Flask, abort, redirect, render_template, request
from jinja2 import ChoiceLoader, FileSystemLoader


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def create_app(config=None):
    shared = Path(__file__).resolve().parent.parent / "frontend_shared"
    app = Flask(__name__, static_folder=str(shared / "static"), static_url_path="/users/static")
    app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(shared / "templates")])
    # Use the same gateway hop as browser API calls to preserve Flask-Login's
    # session binding to the user agent and immediate peer address.
    app.config["USERS_API_URL"] = os.getenv("USERS_API_URL", "http://gateway/api/users")
    app.config["LMS_API_URL"] = os.getenv("LMS_API_URL", "http://gateway/api/lms")
    if config:
        app.config.update(config)
    app.extensions["users_opener"] = build_opener(NoRedirect())

    @app.get("/login")
    def login():
        return render_template("login.html")

    @app.get("/account")
    def account():
        session_cookie = request.cookies.get("tutor_session")
        if not session_cookie:
            return redirect("/login")
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
                return redirect("/login")
            abort(503)
        except (URLError, OSError, ValueError, AttributeError):
            abort(503)
        if not isinstance(user, dict) or user.get("email_verified") is not True:
            abort(503)
        can_manage_college = "college_admin" in (user.get("roles") or []) and bool(user.get("college_id"))
        is_student = "student" in (user.get("roles") or [])
        moodle = None
        moodle_error = None
        if is_student:
            upstream = Request(app.config["LMS_API_URL"].rstrip("/") + "/students/me", headers=dict(upstream.header_items()))
            try:
                with app.extensions["users_opener"].open(upstream, timeout=5) as response:
                    moodle = json.load(response)
            except HTTPError as error:
                error.close()
                if error.code == 401:
                    return redirect("/login")
                moodle_error = ("Your Moodle profile is not available yet. Ask your college administrator to check that your verified email matches Moodle and that the college has synchronized."
                                if error.code == 404 else "Moodle information is temporarily unavailable. Please try again later.")
            except (URLError, OSError, ValueError):
                moodle_error = "Moodle information is temporarily unavailable. Please try again later."
        return render_template("account.html", user=user, can_manage_college=can_manage_college,
                               is_student=is_student, moodle=moodle, moodle_error=moodle_error)

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    return app
