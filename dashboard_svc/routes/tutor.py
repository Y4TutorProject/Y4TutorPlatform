from flask import render_template


def render_tutor_dashboard(user, can_manage_college):
    return render_template(
        "tutor_dashboard.html",
        role="tutor",
        user=user,
        can_manage_college=can_manage_college,
        is_student=False,
    )
