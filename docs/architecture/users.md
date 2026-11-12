# Users and registration

`registration_svc` handles signup and email verification. `users_svc` handles login, logout and sessions. Both use `users_db.users`.

## Setup

Set these values in `.env`, then run `docker compose up -d --build`:

- `SECRET_KEY`: at least 32 random characters.
- `SESSION_COOKIE_SECURE=false` for local HTTP; `true` for HTTPS.
- `PUBLIC_BASE_URL=http://localhost:8080` for verification links.

Generate a secret with:

```sh
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Open the app at <http://localhost:8080> and verification emails at <http://localhost:8025>. Registration sends mail to `mailpit:1025` inside Compose.

## Signup

Students select an active college and use its student email domain. College admins create and verify their account before registering a college.

The signup API accepts `email`, `password`, `account_type` and an optional `username`. `account_type` is `student` or `college_admin`; students also need `college_id`.

Passwords must contain 9-128 characters. Usernames use 3-30 letters, numbers or underscores. Emails and usernames are trimmed and lowercased. Skipping the username creates a temporary name, which the user replaces on first sign-in.

New accounts need email verification before signing in. Links expire after one hour and work once. Resends have a one-minute cooldown. Client-supplied roles, status and verification flags are ignored.

## API

Registration uses `/api/registration` through the gateway, or port 5050 directly:

- `GET /auth/csrf`
- `POST /auth/signup`
- `POST /auth/verify-email` with `{"token": "..."}`
- `POST /auth/resend-verification` with `{"email": "..."}`

Users uses `/api/users` through the gateway, or port 5051 directly:

- `GET /auth/csrf`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/verify` for session and CSRF checks
- `GET /users/me`
- `POST /users/me/username`
- `POST /users/me/preferences`
- `POST /users/me/college`

POST requests need the receiving service's session cookie and `X-CSRFToken`. Login and logout return a new token. Registration and users have separate cookies. Passwords are stored as scrypt hashes.

Response codes are 400 for invalid input or CSRF, 401 for invalid login/session, 403 for denied access, 409 for duplicates or membership conflicts, and 503 for service failures.

## Signed-in pages

The dashboard serves `/dashboard`, `/admin-dashboard`, `/lecturer-dashboard`, `/account`, `/preferences` and `/choose-username`. It selects the view using account roles and module assignments. `/admin-dashboard` requires a college admin with a registered college.

The users frontend serves `/login`. Frontends forward the session cookie and browser user agent when checking authentication through the gateway.

## Username selection

Choosing a username sets `username_completed` to true. Users who skip it go to `/choose-username` before preference or college setup. Older generated `user_<20 hexadecimal digits>` names also prompt when there is no completion flag.

`POST /api/users/users/me/username` accepts `{"username": "chosen_name"}` with the users session and CSRF token. It sets the initial username and completion flag together. Duplicate names return 409. Repeating the same name is safe.

## Learning preferences

New accounts complete `/preferences` after verification and first sign-in. Users rate visual, auditory, reading/writing and kinesthetic preferences from 0 to 10. Equal ratings are allowed.

Saving all four sets `preferences_completed` to true. Incomplete setup appears on the next sign-in or dashboard visit. Older accounts without the flag retain access.

Users can change ratings under **Your account → Edit your learning preferences**. `POST /api/users/users/me/preferences` requires the session, CSRF token and all four scores:

```json
{
  "preferences": {
    "visual": 5,
    "auditory": 3,
    "reading_writing": 4,
    "kinesthetic": 8
  }
}
```

Admins continue to college registration if they have no college.

The internal service method accepts partial updates:

```python
user = users_service.set_learning_preferences(user_id, {
    "visual": 5,
    "auditory": 3,
})
```

Keys can be strings or `LearningTeachingStyles` members. Scores must be integers from 0 to 10. Omitted scores keep their values and default to zero on new records. Invalid input raises `ValueError`; an unknown user returns `None`.

## Tests

```sh
python3.12 -m venv .venv-auth
.venv-auth/bin/python -m pip install -r users_svc/requirements-dev.txt
.venv-auth/bin/python -m pytest tests/test_auth.py tests/test_college_auth.py -q
```

Tests mock MongoDB and email delivery. `tests/gateway_smoke.py` checks verification through the running gateway and Mailpit.
