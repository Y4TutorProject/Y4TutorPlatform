# Users
The registration service owns signup and account validation. The user service owns login, logout, sessions, and user status. Both use the same MongoDB users collection and share the user model, DAO, and credential helpers from `users_svc`. Passwords use Werkzeug scrypt; login uses Flask-Login cookie sessions.

## ENV Settings
Both services need
SECRET_KEY
GENERATE -> python3 -c 'import secrets; print(secrets.token_hex(32))'
SESSION_COOKIE_SECURE
Use false for HTTP or True with HTTPS

## API
Registration API is available at http://localhost:5050:

- `GET /auth/csrf` returns a registration CSRF token.
- `POST /auth/signup` creates an account and does not log it in.

Users API is available at http://localhost:5051:

- `GET /auth/csrf` returns a users CSRF token.
- `POST /auth/login` logs in an existing account.
- `POST /auth/logout` ends the session.
- `GET /users/me` returns the authenticated user.

Fetch the CSRF token from the service receiving the POST. The services use separate session cookies (`registration_session` and `tutor_session`).

X-CSRFToken will need to be sent on every POST request. After login or logout use the new token thats returned.

Browsers should use same-origin requests with credentials

## JSON Structure
```json
{
  "username": "student_one",
  "email": "student@example.com",
  "password": "a long unique password"
}
```

Passwords must be 9-128 characters, usernames are 3-30 letters, numbers, or underscores.
usernames and emails are trimmed and lowered

New users currently start as active students; account confirmation is TBD.

College membership is not covered in this service

## Errors
400 for invalid input
401 for invalid credentials or missing auth
409 for duplicate username/email
503 for a database failure

# Tests
```sh
python3.12 -m venv .venv-auth
.venv-auth/bin/python -m pip install -r users_svc/requirements-dev.txt
.venv-auth/bin/python -m pytest -q tests/test_auth.py
```

These tests exercise signup through registration and login through users with a shared test database. They use Flask API and mock mongoDB using mongomock with CSRF enabled.
They do not use the running database.

# Production Preperation
Before exposing the service the login/signup rate will need limits and use HTTPS using WSGI instead of flask dev server.