from . import account, auth, dashboard, messaging, student


def register_routes(app):
    """Register every dashboard blueprint on the app."""
    for module in (auth, account, dashboard, student, messaging):
        app.register_blueprint(module.bp)
