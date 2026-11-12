# Testing and quality

Python tests cover service logic using mocked MongoDB, HTTP responses and email delivery. JavaScript tests cover browser-side logic. Check the running Compose stack separately for complete user flows.

## Documentation checks

```sh
.venv-docs/bin/python scripts/check_docs.py
```

This runs formatting, Markdown, YAML, strict MkDocs and generated local-link checks.

## Python service tests

Set up a Python 3.12 environment:

```sh
python3.12 -m venv .venv-auth
.venv-auth/bin/python -m pip install -r users_svc/requirements-dev.txt -r dashboard_svc/requirements.txt
PYTHONPATH=dashboard_svc .venv-auth/bin/python -m pytest tests -q
```

`PYTHONPATH=dashboard_svc` allows the dashboard's local imports to resolve.

`tests/test_account_settings.py` imports the old `dashboard.app` path. To run the remaining tests while that collection error is being fixed:

```sh
PYTHONPATH=dashboard_svc .venv-auth/bin/python -m pytest tests --ignore=tests/test_account_settings.py -q
```

Record the excluded file with the result.

Matching uses its own environment:

```sh
python3.12 -m venv .venv-matching
.venv-matching/bin/python -m pip install -r matching_svc/requirements.txt
.venv-matching/bin/python -m pytest matching_svc/tests -q
```

| Area | Test files under `tests/` |
| --- | --- |
| Signup, sessions and colleges | `test_auth.py`, `test_college_auth.py` |
| LMS validation and imports | `test_lms_security.py`, `test_lms_import.py`, `test_lms_sync.py`, `test_lms_mapping.py` |
| Academic records and CSV | `test_academic_catalog.py`, `test_manual_academics.py`, `test_csv_import.py` |
| Student data and preferences | `test_student_moodle.py`, `test_account_page.py`, `test_learning_preferences.py` |
| Tutor lookup and PWA | `test_dashboard_tutors.py`, `test_pwa.py` |

## JavaScript checks

Use Node.js 18 or later:

```sh
node --test tests/*.test.cjs tests/test_dashboard_ui.js
```

These tests use DOM test doubles for forms, CSRF, admin screens, tutor applications, sign-out and PWA caching. Inspect failures against the intended UI before changing assertions.

`tests/pwa_browser.cjs` runs Playwright checks against the app in Chrome. Device installation and phone behaviour need testing on Android and iPhone.

## Measuring coverage

Install `pytest-cov` and run:

```sh
.venv-auth/bin/python -m pip install 'pytest-cov>=7,<8'
PYTHONPATH=dashboard_svc .venv-auth/bin/python -m pytest tests --ignore=tests/test_account_settings.py --cov=users_svc --cov=registration_svc --cov=college_svc --cov=lms_svc --cov=dashboard_svc --cov-report=term-missing --cov-report=html
```

Open `htmlcov/index.html`. Save the revision, command, result and exclusions with the report. This command measures the listed Python services.

## Manual and usability testing

Test registration, verification, academic setup, tutor lookup and messaging with test accounts. Include denied requests and accounts from different colleges.

Ask another person to follow the setup guide and complete tasks without explaining every click. Record the expected result, actual result, where they needed help and any follow-up changes.
