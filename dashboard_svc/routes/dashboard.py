from flask import Blueprint, abort, g, redirect

from users_client import login_required
from .account import can_manage_college
from .admin import render_admin_dashboard
from .student import render_student_dashboard
from .tutor import render_tutor_dashboard

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
    roles = user.get("roles") or []
    manages_college = can_manage_college(user)
    if "tutor" in roles:
        return render_tutor_dashboard(user, manages_college)
    if "student" in roles:
        return render_student_dashboard(user, manages_college)
    if manages_college:
        return render_admin_dashboard(user, manages_college)
    return redirect("/account")


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