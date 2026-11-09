from flask import Blueprint, g, render_template

from users_client import login_required

bp = Blueprint("account", __name__)


def can_manage_college(user):
    return "college_admin" in (user.get("roles") or []) and bool(user.get("college_id"))


@bp.get("/account")
@login_required
def account():
    return render_template(
        "account.html",
        user=g.user,
        can_manage_college=can_manage_college(g.user),
    )


@bp.get("/preferences")
@login_required
def preferences():
    return render_template("preferences.html", user=g.user)
