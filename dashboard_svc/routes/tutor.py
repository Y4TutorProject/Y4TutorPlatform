from flask import render_template


def render_tutor_dashboard(user, can_manage_college):
    return render_template(
        "tutor_dashboard.html",
        role="tutor",
        user=user,
        can_manage_college=can_manage_college,
        is_student=False,
    )


def is_tutor(user):
    """Return whether the users service lists the tutor role for this user."""
    return "tutor" in (user.get("roles") or [])


def needs_teaching_preferences(user):
    """Return whether an approved tutor still has to set their teaching preferences."""
    return user.get("teaching_preferences_completed") is not True and is_tutor(user)
