import os
from pathlib import Path

from flask import Flask, g
from jinja2 import ChoiceLoader, FileSystemLoader

from routes import register_routes
from routes.roles import resolve_active_role, switchable_roles
from users_client import create_opener
import logging
from flask_wtf.csrf import CSRFProtect



def create_app(config=None):
    shared = Path(os.environ.get(
        "FRONTEND_SHARED_PATH",
        Path(__file__).resolve().parent.parent / "frontend_shared",
    ))
    app = Flask(__name__, static_folder=str(shared / "static"), static_url_path="/dashboard/static")
    app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(shared / "templates")])

    app.config["USERS_API_URL"] = os.getenv("USERS_API_URL", "http://gateway/api/users")
    app.config["LMS_API_URL"] = os.getenv("LMS_API_URL", "http://gateway/api/lms")
    app.config["MESSAGING_API_URL"] = os.getenv("MESSAGING_API_URL", "http://gateway/api/messaging")
    app.config["MATCHING_API_URL"] = os.getenv("MATCHING_API_URL", "http://gateway/api/matching")
    app.config["DASHBOARD_SHARED_SECRET"] = os.getenv("DASHBOARD_SHARED_SECRET")
    app.config["SECRET_KEY"] = os.getenv("SESSION_SECRET")
    if config:
        app.config.update(config)
    app.extensions["users_opener"] = create_opener()
    app.config["CURRENT_ROLE"] = None
    CSRFProtect(app)


    @app.context_processor
    def inject_roles():
        user = getattr(g, "user", None)
        if not user:
            return {"roles": [], "switchable_roles": [], "active_role": None, "can_switch": False}
        available = switchable_roles(user)

        return {
            "roles": user.get("roles") or [],
            "switchable_roles": available,
            "active_role": resolve_active_role(user),
            "can_switch": len(available) > 1,
        }

    register_routes(app)

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    return app
