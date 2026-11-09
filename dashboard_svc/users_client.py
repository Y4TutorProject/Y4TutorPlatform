import json
from functools import wraps
from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from flask import abort, current_app, g, redirect, request


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def create_opener():
    """Return a URL opener that surfaces upstream redirects instead of following them."""
    return build_opener(NoRedirect())


def session_headers():
    """Return headers that forward the browser's tutor_session cookie and user agent."""
    cookie = SimpleCookie()
    cookie["tutor_session"] = request.cookies["tutor_session"]
    return {
        "Cookie": cookie.output(header="").strip(),
        "User-Agent": request.headers.get("User-Agent", ""),
    }


def upstream_request(base_url_key, path):
    """Build an authenticated request to another service using the configured base URL."""
    return Request(
        current_app.config[base_url_key].rstrip("/") + path,
        headers=session_headers(),
    )


def open_upstream(upstream):
    """Open an upstream request with the app's non-redirecting opener."""
    return current_app.extensions["users_opener"].open(upstream, timeout=5)


def authenticated_user():
    """Return the signed-in user from the users service, or None when signed out."""
    if not request.cookies.get("tutor_session"):
        return None
    try:
        with open_upstream(upstream_request("USERS_API_URL", "/users/me")) as response:
            user = json.load(response).get("user")
    except HTTPError as error:
        error.close()
        if error.code == 401:
            return None
        abort(503)
    except (URLError, OSError, ValueError, AttributeError):
        abort(503)
    return user if isinstance(user, dict) else None


def login_required(view):
    """Redirect signed-out visitors to /login and expose the verified user as g.user."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = authenticated_user()
        if user is None:
            return redirect("/login")
        if user.get("email_verified") is not True:
            abort(503)
        g.user = user
        return view(*args, **kwargs)
    return wrapper
