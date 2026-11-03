from flask import Flask, render_template, request, redirect
import os
import requests

def create_app():
    """Create the student dashboard application."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("DASHBOARD_SHARED_SECRET", "default_secret_key")
    USER_SERVICE_URL = os.environ.get("USERS_API_URL", "http://users_svc:5000")

    @app.get("/dashboard")
    def dashboard():
        user_response = requests.get(
            f"{USER_SERVICE_URL.rstrip('/')}/users/me",
            cookies={"tutor_session": request.cookies["tutor_session"]}
            if "tutor_session" in request.cookies
            else {},
            timeout=5,
        )
        user = user_response.json().get("user") if user_response.ok else None
        if not user:
            return redirect("/login")
        username, email, college_id, status, roles, email_verified = (
            user.get("username"),
            user.get("email"),
            user.get("college_id"),
            user.get("status"),
            user.get("roles"),
            user.get("email_verified"),
        )
        if not email_verified:
            return redirect("/verify-email")
        if roles is None or not isinstance(roles, list):
            roles = []
        # if the user is a studnt, redirect to the student dashboard
        if "student" in [role.lower() for role in roles]:
            return render_template(
                "student_dashboard.html",
                username=username
            )
        # if the user is a tutor, redirect to the tutor dashboard
        # if "tutor" in [role.lower() for role in roles]:
        #     return redirect("/tutor-dashboard")
        # # if the user is an admin, redirect to the admin dashboard
        # if "college-admin" in [role.lower() for role in roles]:
        #     return redirect("/admin-dashboard")
    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)