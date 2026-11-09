from pathlib import Path
import json
import os
from http.cookies import SimpleCookie
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from flask import Flask, abort, redirect, render_template, request
from jinja2 import ChoiceLoader, FileSystemLoader


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def create_app(config=None):
    shared = Path(__file__).resolve().parent.parent / "frontend_shared"
    app = Flask(__name__, static_folder=str(shared / "static"), static_url_path="/dashboard/static")
    app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(shared / "templates")])
    # LMS names may contain encoded entities. Return plain text so Jinja
    # still escapes any HTML after decoding it.
    app.jinja_env.filters["lms_text"] = lambda value: unescape(str(value)) if value is not None else ""
    # Use the same gateway hop as browser API calls to preserve Flask-Login's
    # session binding to the user agent and immediate peer address.
    app.config["USERS_API_URL"] = os.getenv("USERS_API_URL", "http://gateway/api/users")
    app.config["LMS_API_URL"] = os.getenv("LMS_API_URL", "http://gateway/api/lms")
    if config:
        app.config.update(config)
    app.extensions["users_opener"] = build_opener(NoRedirect())

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

    def student_lms():
        cookie = SimpleCookie()
        cookie["tutor_session"] = request.cookies["tutor_session"]
        upstream = Request(
            app.config["LMS_API_URL"].rstrip("/") + "/students/me",
            headers={"Cookie": cookie.output(header="").strip(),
                     "User-Agent": request.headers.get("User-Agent", "")},
        )
        try:
            with app.extensions["users_opener"].open(upstream, timeout=5) as response:
                return json.load(response), None
        except HTTPError as error:
            error.close()
            if error.code == 401:
                return None, "session_expired"
            message = (
                "Your LMS profile is not available yet. Ask your college administrator to check "
                "that your verified email matches LMS and that the college has synchronized."
                if error.code == 404 else
                "LMS information is temporarily unavailable. Please try again later."
            )
        except (URLError, OSError, ValueError):
            message = "LMS information is temporarily unavailable. Please try again later."
        return None, message

    @app.get("/dashboard")
    @app.get("/admin-dashboard")
    def dashboard():
        user = authenticated_user()
        if user is None:
            return redirect("/login")
        roles = user.get("roles")
        if not isinstance(roles, list):
            roles = []
        is_admin = "college_admin" in roles
        if request.path == "/admin-dashboard" and not is_admin:
            abort(403)
        if user.get("email_verified") is not True:
            return redirect("/verify-email")
        if user.get("username_completed") is False:
            return redirect("/choose-username")
        if user.get("preferences_completed") is False:
            return redirect("/preferences")
        if is_admin:
            if not user.get("college_id"):
                return redirect("/register-college")
            return render_template("admin_dashboard.html", user=user)
        if "student" in roles:
            lms, lms_error = student_lms()
            if lms_error == "session_expired":
                return redirect("/login")
            return render_template("student_dashboard.html", user=user,
                                   lms=lms, lms_error=lms_error)
        if "tutor" in roles:
            return render_template("tutor_dashboard.html", user=user)
        abort(403)

    @app.get("/choose-username")
    def choose_username():
        user = authenticated_user()
        if user is None:
            return redirect("/login")
        if user.get("username_completed") is not False:
            return redirect("/dashboard")
        return render_template("choose_username.html", user=user)

    @app.get("/preferences")
    def preferences():
        user = authenticated_user()
        if user is None:
            return redirect("/login")
        if user.get("username_completed") is False:
            return redirect("/choose-username")
        return render_template("preferences.html", user=user,
                               onboarding=user.get("preferences_completed") is False)

    @app.get("/account")
    def account():
        user = authenticated_user()
        if user is None:
            return redirect("/login")
        if not isinstance(user, dict) or user.get("email_verified") is not True:
            abort(503)
        if user.get("username_completed") is False:
            return redirect("/choose-username")
        return render_template("account.html", user=user)

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


app = create_app()
