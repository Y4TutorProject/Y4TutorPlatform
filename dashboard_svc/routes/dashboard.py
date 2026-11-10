from flask import Blueprint, abort, g, redirect, render_template

from users_client import login_required
from .account import can_manage_college
from .admin import render_admin_dashboard
from .student import render_student_dashboard
from .tutor import needs_teaching_preferences, render_tutor_dashboard
from .lecturer import render_lecturer_dashboard

bp = Blueprint("dashboard", __name__)


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
    if user.get("username_completed") is False:
        return redirect("/choose-username")
    if needs_teaching_preferences(user):
        return redirect("/preferences?type=teaching")
    roles = user.get("roles") or []
    manages_college = can_manage_college(user)
    if "tutor" in roles:
        return render_tutor_dashboard(user, manages_college)
    if "student" in roles:
        return render_student_dashboard(user, manages_college)
    if manages_college:
        return render_admin_dashboard(user, manages_college)
    return redirect("/account")


@bp.get('/tutor-applications')
@login_required
def lecturer_applications():
    return render_template('lecturer_applications.html', user=g.user,
                           can_manage_college=can_manage_college(g.user))


@bp.get('/lecturer-dashboard')
@login_required
def lecturer_dashboard():
    return render_lecturer_dashboard(g.user, can_manage_college(g.user))


# temporary user data check
@bp.get("/check-user")
@login_required
def check_user():
    user = g.user
    return {
        "username_completed": user.get("username_completed"),
        "roles": user.get("roles"),
        "active_role": user.get("active_role"),
    }