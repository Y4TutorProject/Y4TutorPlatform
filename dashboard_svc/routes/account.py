from flask import Blueprint, abort, g, render_template, request

from users_client import login_required
from .tutor import is_tutor, needs_teaching_preferences

bp = Blueprint("account", __name__)

# Preference kind (the ?type= query value) -> the user field holding its scores.
PREFERENCE_FIELDS = {"learning": "preferences", "teaching": "teaching_preferences"}


def can_manage_college(user):
    return "college_admin" in (user.get("roles") or []) and bool(user.get("college_id"))


@bp.get("/account")
@login_required
def account():
    return render_template(
        "account.html",
        user=g.user,
        can_manage_college=can_manage_college(g.user),
        is_tutor=is_tutor(g.user),
    )


@bp.get("/preferences")
@login_required
def preferences():
    kind = request.args.get("type", "learning")
    field = PREFERENCE_FIELDS.get(kind)
    if field is None:
        abort(404)
    user = g.user
    # Learning preferences onboard new users; teaching preferences onboard newly approved tutors.
    onboarding = (user.get("preferences_completed") is False if kind == "learning"
                  else needs_teaching_preferences(user))
    return render_template(
        "preferences.html",
        user=user,
        kind=kind,
        scores=user.get(field) or {},
        onboarding=onboarding,
    )
