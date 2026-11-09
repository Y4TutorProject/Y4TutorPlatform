from flask import Blueprint, g, redirect

from users_client import login_required
from .account import can_manage_college
from .admin import render_admin_dashboard
from .student import render_student_dashboard
from .tutor import render_tutor_dashboard

bp = Blueprint("dashboard", __name__)


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
