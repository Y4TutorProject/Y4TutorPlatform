"""Public application assets shared by the platform frontends."""
from pathlib import Path

from flask import Blueprint, abort, current_app, send_from_directory

bp = Blueprint("pwa", __name__)
PUBLIC_ASSETS = {
    "offline.html", "pwa.js", "mobile.css", "icon-180.png",
    "icon-192.png", "icon-512.png",
}


def asset(filename, mimetype=None):
    return send_from_directory(
        Path(current_app.static_folder) / "pwa", filename, mimetype=mimetype,
    )


@bp.get("/manifest.webmanifest")
def manifest():
    return asset("manifest.webmanifest", "application/manifest+json")


@bp.get("/sw.js")
def service_worker():
    response = asset("sw.js", "application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@bp.get("/pwa/<path:filename>")
def public_asset(filename):
    if filename not in PUBLIC_ASSETS:
        abort(404)
    return asset(filename)
