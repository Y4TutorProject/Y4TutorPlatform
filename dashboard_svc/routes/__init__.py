from . import account, auth, dashboard, messaging, pwa, student


def register_routes(app):
    """Register every dashboard blueprint on the app."""
    for module in (auth, account, dashboard, student, messaging, pwa):
        app.register_blueprint(module.bp)
