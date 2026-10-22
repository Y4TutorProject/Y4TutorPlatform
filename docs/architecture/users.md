# Users
The user service manages the sign up and login. It uses MongoDB, Werkzeug scrypt for hashing and Flask-Login cookie sessions.

## ENV Settings
The users service needs
SECRET_KEY
GENERATE -> python3 -c 'import secrets; print(secrets.token_hex(32))'
SESSION_COOKIE_SECURE
Use false for HTTP or True with HTTPS

## API
Api is available at http://localhost:5051

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

Passwords must be 9-128 characters, usernames are 3-30 letters.
usernames and emails are trimmed and lowered

New users have to be confirmed unless they are created using a connection (TBD)

College membership is not covered in this service

## Errors
400 for invalid input
401 for invalid credentials or missing auth
409 for duplicate username/email
503 for a database failure

# Tests
```sh
python3 -m venv .venv-auth
.venv-auth/bin/python -m pip install -r users_svc/requirements-dev.txt
.venv-auth/bin/python -m pytest -q
```

These tests use Flask API and mock mongoDB using mongomock with CSRF enabled.
They do not use the running database.

# Production Preperation
Before exposing the service the login/signup rate will need limits and use HTTPS using WSGI instead of flask dev server.