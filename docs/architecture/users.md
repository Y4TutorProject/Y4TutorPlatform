# Users and registration

`registration_svc` handles signup and email verification. `users_svc` handles
login, logout and sessions. Both use the `users_db.users` MongoDB collection.

## Setup

Set these in `.env`, then run `docker compose up -d --build`:

- `SECRET_KEY`: at least 32 random characters.
- `SESSION_COOKIE_SECURE=false` for local HTTP; `true` with HTTPS.
- `PUBLIC_BASE_URL=http://localhost:8080` for verification links.

Generate a secret with:

```sh
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Open the app at http://localhost:8080 and Mailpit at http://localhost:8025.
Registration sends mail to `mailpit:1025` inside Compose.

## Signup

At `/signup`, choose student or college administrator:

- Students must select an active college and use its student email domain.
- Administrators create an account first, then register their college after
  verifying their email and signing in.

The API accepts `email`, `password`, `account_type` and an optional `username`.
`account_type` is `student` or `college_admin`; students also need `college_id`.
Passwords are 9–128 characters. Usernames are 3–30 letters, numbers or underscores
and are generated if omitted. Emails and usernames are trimmed and lowercased.
Client-supplied roles, status and verification flags are ignored.

New accounts cannot sign in until their email is verified. Verification links
expire after one hour and work once. Resends have a one-minute cooldown.
Existing accounts keep their previous access.

## API

Use the gateway prefixes below. Direct development ports are 5050 for
registration and 5051 for users.

Registration (`/api/registration`):

- `GET /auth/csrf`
- `POST /auth/signup`
- `POST /auth/verify-email` — body: `{ "token": "..." }`
- `POST /auth/resend-verification` — body: `{ "email": "..." }`

Users (`/api/users`):

- `GET /auth/csrf`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/verify` — session and CSRF check used by the college service.
- `GET /users/me`
- `POST /users/me/college` — links an administrator to their own college.

POSTs need `X-CSRFToken` from the receiving service and its session cookie.
Use the new token returned after login or logout. Registration and users have
separate session cookies. Passwords are stored as scrypt hashes.

Errors: 400 invalid input or CSRF, 401 invalid login/session, 403 denied access,
409 duplicate account or membership conflict, 503 service unavailable.

## Tests

```sh
python3.12 -m venv .venv-auth
.venv-auth/bin/python -m pip install -r users_svc/requirements-dev.txt
.venv-auth/bin/python -m pytest tests/test_auth.py tests/test_college_auth.py -q
```

Tests use mocked MongoDB and email delivery. The live Mailpit test is in
`tests/gateway_smoke.py`.

Public deployment still needs HTTPS, login/signup rate limits and a production
WSGI server for the APIs.
