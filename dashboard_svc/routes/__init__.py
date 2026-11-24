from . import account, auth, dashboard, messaging, pwa, sessions, student


def register_routes(app):
    """Register every dashboard blueprint on the app."""
    for module in (auth, account, dashboard, student, messaging, sessions, pwa):
        app.register_blueprint(module.bp)
