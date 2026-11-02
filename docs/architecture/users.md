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

The browser UI enters through Nginx at `http://localhost:8080`: `/login` and
`/account` are served by `users_frontend`, while `/signup` is served by
`registration_frontend`. Browser API calls use `/api/users/` and
`/api/registration/`; Nginx strips those prefixes before forwarding to the
corresponding API. See [frontend architecture](frontends.md).

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

Username is optional: when omitted, the registration service generates one.
The signup screen only asks for email, password, and password confirmation.
Signup has no account-type selector. New users start as active students; account
confirmation is TBD. Direct `account_type`, `roles`, and `status` fields from
clients are ignored.

The college combobox is disabled and marked **Not implemented yet** on the signup screen.
The college list will come from `college_db` once that service is set up; no
placeholder college records or memberships are stored during signup.

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
