import requests
from flask import Blueprint, abort, current_app, g, redirect, render_template

from users_client import authenticated_user, login_required

bp = Blueprint("auth", __name__)


@bp.get("/choose-username")
@login_required
def choose_username():
    user = g.user
    if user.get("username_completed") is not False:
        if user.get("preferences_completed") is False:
            return redirect("/preferences")
        if "college_admin" in (user.get("roles") or []) and not user.get("college_id"):
            return redirect("/register-college")
        return redirect("/dashboard")
    return render_template("choose_username.html", user=user)
