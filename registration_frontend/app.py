from pathlib import Path

from flask import Flask, render_template, request
from jinja2 import ChoiceLoader, FileSystemLoader


def create_app():
    """Create the registration frontend and onboarding pages.

    Returns:
        Flask: Configured frontend application.
    """
    shared = Path(__file__).resolve().parent.parent / "frontend_shared"
    app = Flask(__name__, static_folder=str(shared / "static"), static_url_path="/registration/static")
    app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(shared / "templates")])

    @app.get("/signup")
    def signup():
        """Show the student or college-administrator registration choice.

        Returns:
            str: Registration choice page HTML.
        """
        return render_template("signup_choice.html")

    @app.get("/signup/student")
    @app.get("/signup/college-admin")
    def signup_form():
        """Render the selected account signup form.

        Returns:
            str: Student or administrator account form HTML.
        """
        account_type = "college_admin" if request.path.endswith("college-admin") else "student"
        return render_template("signup.html", account_type=account_type)

    @app.get("/check-email")
    def check_email():
        """Render verification delivery and resend instructions.

        Returns:
            str: Email verification instructions HTML.
        """
        return render_template("check_email.html")

    @app.get("/verify-email")
    def verify_email():
        """Render the explicit email verification action.

        Returns:
            str: Verification confirmation page HTML.
        """
        return render_template("verify_email.html")

    @app.get("/register-college")
    def register_college():
        """Render the college administrator onboarding stage.

        Returns:
            str: College registration page HTML.
        """
        return render_template("register_college.html")

    @app.after_request
    def no_cache(response):
        """Disable caching for authentication pages.

        Args:
            response (Response): Outgoing frontend response.

        Returns:
            Response: Response with Cache-Control set to no-store.
        """
        response.headers["Cache-Control"] = "no-store"
        return response

    return app
