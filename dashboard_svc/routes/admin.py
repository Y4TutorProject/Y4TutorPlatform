from flask import render_template


def render_admin_dashboard(user, can_manage_college):
    return render_template(
        "admin_dashboard.html",
        user=user,
        role="admin",
        can_manage_college=can_manage_college,
        is_student=False,
    )
