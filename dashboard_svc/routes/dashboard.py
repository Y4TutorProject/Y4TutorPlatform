from flask import Blueprint, abort, g, redirect, render_template, session

from users_client import login_required
from .roles import switchable_roles, resolve_active_role
from .account import can_manage_college
from .admin import render_admin_dashboard
from .student import render_student_dashboard
from .tutor import needs_teaching_preferences, render_tutor_dashboard
from .lecturer import render_lecturer_dashboard

bp = Blueprint("dashboard", __name__)

SWITCHABLE = ("tutor", "student")


@bp.get('/admin-dashboard')
@login_required
def admin_dashboard():
    if not can_manage_college(g.user):
        abort(403)
    return render_admin_dashboard(g.user, True)



@bp.get("/dashboard")
@login_required
def dashboard():
    user = g.user
    active_role = resolve_active_role(user)
    if user.get("username_completed") is False:
        return redirect("/choose-username")

    manages_college = can_manage_college(user)

    if active_role == "tutor":
        if needs_teaching_preferences(user):
            return redirect("/preferences?type=teaching")
        return render_tutor_dashboard(user, manages_college)
    if active_role == "student":
        return render_student_dashboard(user, manages_college)
    if manages_college:
        return render_admin_dashboard(user, manages_college)
    return redirect("/account")

# role switching e.g. letting a user switch between tutor and student dashboards if they have both roles
@bp.post("/dashboard/switch/<role>")
@login_required
def switch_dashboard(role):
    if role not in switchable_roles(g.user):
        abort(403)
    session["active_role"] = role
    return redirect("/dashboard")


@bp.get('/tutor-applications')
@login_required
def lecturer_applications():
    return render_template('lecturer_applications.html', user=g.user,
                           can_manage_college=can_manage_college(g.user))


@bp.get('/lecturer-dashboard')
@login_required
def lecturer_dashboard():
    return render_lecturer_dashboard(g.user, can_manage_college(g.user))


