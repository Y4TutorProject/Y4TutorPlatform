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

    @app.get("/login")
    def login():
        user = authenticated_user()
        if user:
            if user.get("username_completed") is False:
                return redirect("/choose-username")
            if user.get("preferences_completed") is False:
                return redirect("/preferences")
            if "college_admin" in (user.get("roles") or []) and not user.get("college_id"):
                return redirect("/register-college")
            return redirect("/dashboard")
        return render_template("login.html")

    @app.get("/logout")
    def logout():
        response = redirect("/login")
        response.delete_cookie("tutor_session", path="/", secure=True, httponly=True, samesite="Lax")
        return response

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    return app
