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
and are saved in lowercase. The signup form offers an optional username; if omitted,
a temporary name is generated and the user chooses their username on first sign-in. Emails and usernames are trimmed and lowercased.
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
- `POST /users/me/preferences` — saves all four learning preference ratings.
- `POST /users/me/college` — links an administrator to their own college.

POSTs need `X-CSRFToken` from the receiving service and its session cookie.
Use the new token returned after login or logout. Registration and users have
separate session cookies. Passwords are stored as scrypt hashes.

Errors: 400 invalid input or CSRF, 401 invalid login/session, 403 denied access,
409 duplicate account or membership conflict, 503 service unavailable.

## Signed-in pages

The dashboard service owns `/dashboard`, `/admin-dashboard`, `/account`, and
`/preferences`, and `/choose-username`, including their templates and `/dashboard/static/` assets.
`/dashboard` selects the college admin, student, or tutor view using roles returned
by the users API. College admins see connection and synchronization settings;
students see their Moodle information and four learning preference scores.
`/admin-dashboard` requires the `college_admin` role and a registered college.
The users frontend serves `/login`; authentication and preference APIs remain in
the users service. Both frontends preserve the session cookie and browser user
agent when authenticating through the gateway.

## Username selection

Signup with a username sets `username_completed` to true. Signup without one
sets it to false, so login and dashboard visits lead to `/choose-username` before
preference or college setup. Existing generated `user_<20 hexadecimal digits>`
usernames also prompt when no completion flag is stored; existing chosen names
continue normally.

`POST /api/users/users/me/username` accepts `{"username": "chosen_name"}` and
requires the signed-in users session and its CSRF token. It normalizes the name,
uses the database's unique index to reject duplicates with HTTP 409, and atomically
marks username selection complete. It only changes the current user's initial
username; a repeated identical submission is safe.

## Learning preferences

New accounts complete preference onboarding at `/preferences` after email
verification and their first sign-in. Each of the four approaches has a rating
from 0 (no preference) to 10 (strong preference); equal ratings are allowed.
Saving all four ratings sets `preferences_completed` to true. Incomplete setup
is shown again on the next sign-in or dashboard visit. Existing accounts without
the completion field retain access without mandatory onboarding.

Users can edit their saved ratings through **Your account → Edit your learning
preferences**. `POST /api/users/users/me/preferences` accepts
`{"preferences": {"visual": 5, "auditory": 3, "reading_writing": 4, "kinesthetic": 8}}`.
It requires a signed-in session, a CSRF token, and all four scores, and updates
only the current account. College administrators continue to college registration
after preference setup if they have not yet registered their college.

The users service can save learning preference scores for an existing user:

```python
user = users_service.set_learning_preferences(user_id, {
    "visual": 5,
    "auditory": 3,
})
```

Supported keys are `visual`, `auditory`, `reading_writing`, and `kinesthetic`,
or their `LearningTeachingStyles` enum members. Scores must be integers from 0 to 10 inclusive.
Unspecified scores keep their current values and default to zero for new or
legacy accounts. Invalid input raises `ValueError`; an unknown user returns
`None`. Scores are saved to MongoDB and included in public user details.

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
