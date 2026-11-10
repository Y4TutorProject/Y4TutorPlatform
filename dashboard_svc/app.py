import os
from pathlib import Path

from flask import Flask, g
from jinja2 import ChoiceLoader, FileSystemLoader

from routes import register_routes
from users_client import create_opener


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
    app.config["DASHBOARD_SHARED_SECRET"] = os.getenv("DASHBOARD_SHARED_SECRET")
    if config:
        app.config.update(config)
    app.extensions["users_opener"] = create_opener()
    app.config["CURRENT_ROLE"] = None

    @app.context_processor
    def inject_user_roles():
        user = getattr(g, "user", None)
        userid = user.get("id") if user else None
        return {
            "user_roles": user.get("roles") if user else [],
            "current_role": user.get("active_role") if user else None,
            "userid": userid,
        }

    register_routes(app)

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    return app
