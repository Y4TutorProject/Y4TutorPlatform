import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote

from flask import Blueprint, abort, current_app, g, redirect, render_template, request

from clean_text import clean_deep
from users_client import login_required, open_upstream, upstream_request

bp = Blueprint("student", __name__)

MOODLE_UNAVAILABLE = "Moodle information is temporarily unavailable. Please try again later."
MOODLE_PROFILE_MISSING = (
    "Your Moodle profile is not available yet. Ask your college "
    "administrator to check that your verified email matches "
    "Moodle and that the college has synchronized."
)


def render_student_dashboard(user, can_manage_college):
    moodle = None
    moodle_error = None
    try:
        with open_upstream(upstream_request("LMS_API_URL", "/students/me")) as response:
            moodle = clean_deep(json.load(response))
    except HTTPError as error:
        error.close()
        if error.code == 401:
            return redirect("/login")
        moodle_error = MOODLE_PROFILE_MISSING if error.code == 404 else MOODLE_UNAVAILABLE
    except (URLError, OSError, ValueError):
        moodle_error = MOODLE_UNAVAILABLE

    if moodle and moodle.get('lecturer_modules'):
        from .lecturer import render_lecturer_dashboard
        return render_lecturer_dashboard(user, can_manage_college, moodle['lecturer_modules'])

    student = (moodle or {}).get("student") or {}
    modules = [
        {"module_id": module.get("id"), "module_name": module.get("display_name")}
        for module in (moodle.get("modules") if moodle else [])
    ]
    return render_template(
        "student_dashboard.html",
        username=student.get("username"),
        user=user,
        role="student",
        can_manage_college=can_manage_college,
        modules=modules,
        moodle_error=moodle_error,
    )


@bp.get("/get_tutors")
@login_required
def get_tutors():
    module_id = request.args.get("module_id")
    if not module_id:
        abort(400, "Missing module_id parameter")
    tutors_path = f"/students/me/modules/{quote(module_id, safe='')}/tutors"
    try:
        tutors = []
        with open_upstream(upstream_request("LMS_API_URL", tutors_path)) as response:
            result = json.load(response)
        if not isinstance(result, dict) or not isinstance(result.get("tutor_ids"), list):
            raise ValueError("Invalid LMS tutor list")
        for tutor_id in result["tutor_ids"]:
            if not isinstance(tutor_id, str) or not tutor_id:
                raise ValueError("Invalid LMS tutor ID")
            if tutor_id == g.user.get('id'):
                continue
            profile_path = f"/users/{quote(tutor_id, safe='')}"
            with open_upstream(upstream_request("USERS_API_URL", profile_path)) as response:
                profile = clean_deep(json.load(response))
            if not isinstance(profile, dict) or not isinstance(profile.get("user"), dict):
                raise ValueError("Invalid tutor profile")
            tutors.append(profile["user"])
    except HTTPError as error:
        error.close()
        current_app.logger.warning("Tutor lookup failed with upstream HTTP status %s", error.code)
        abort(502, "Failed to fetch tutors")
    except (URLError, OSError, ValueError) as error:
        current_app.logger.warning("Tutor lookup failed: %s", error)
        abort(502, "Failed to fetch tutors")
    return {"tutors": tutors}
