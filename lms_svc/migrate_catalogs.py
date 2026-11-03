"""Run once after deploying college academic storage; safe to rerun."""
from . import create_app


if __name__ == '__main__':
    app = create_app()
    count = app.extensions['lms_service'].store.migrate_legacy()
    print(f'Moved {count} academic catalogues to the college service.')
