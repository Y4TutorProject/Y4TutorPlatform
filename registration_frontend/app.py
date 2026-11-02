from pathlib import Path

from flask import Flask, render_template
from jinja2 import ChoiceLoader, FileSystemLoader


def create_app():
    shared = Path(__file__).resolve().parent.parent / "frontend_shared"
    app = Flask(__name__, static_folder=str(shared / "static"), static_url_path="/registration/static")
    app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(shared / "templates")])

    @app.get("/signup")
    def signup():
        return render_template("signup.html")

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    return app
