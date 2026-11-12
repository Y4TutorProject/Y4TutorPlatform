# Local development

The following is what is needed to start development on this application. A local running moodle site is not needed (but useful for testing the LML)

## Prerequisites

- Git
- Docker Engine
- Python 3.12 (for secret creation and testing)
- Node.js 18 (for testing frontend)
- Ports 8080, 8000, 8025 available. (databases uses multiple other ports to allow connection to MongoDB Compass - check the compose db section for these ports)

Clone the repo and enter it

```sh
git clone https://github.com/Y4TutorProject/Y4TutorPlatform.git
cd Y4TutorPlatform
```

## Configure the environment

Copy the example .env

```sh
cp .env.example .env
```

Generate a seperate value for each of the secret values `SECRET_KEY, DASHBOARD_SHARED_SECRET, COLLEGE_SYNC_TOKEN, INTERNAL_API_TOKEN`

```sh
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Add `INTERNAL_API_TOKEN` to `.env` if its not in the example. It is shared by internal users/LMS calls. Generate a LMS encryption key seperately:

```sh
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

Set that value as `LMS_ENCRYPTION_KEY`. Keep this stable if you wish to keep using the saved LMS credentials

For local HTTP, ensure theses settings are set

```sh
SESSION_COOKIE_SECURE=false
PUBLIC_BASE_URL=http://localhost:8080
GATEWAY_PORT=8080
DEV_MODE=false
```

**Note:** `.env` is ignored by Git

## Start the services

Validate the configuration before attempting to start:

```sh
docker compose config --quiet
```

If nothing returns then continue with the below commands

```sh
docker compose up -d --build
docker compose ps
```

The MongoDB services should become healthy. To test check the gateway:

```sh
curl --fail http://localhost:8080/health
```

A succesful response is `ok`. This only checks the gateway and does not check every backend is healthy.

| Address | Purpose |
| --- | --- |
| <http://localhost:8080> | Application |
| <http://localhost:8025> | Mailpit verification emails |
| <http://localhost:8000> | MkDocs live preview |

## Check the first user flow

1. Open `/signup` and create a college administrator account.
2. Open its verification email in Mailpit and follow the link.
3. Sign in, choose a username if prompted, and complete the preference form.
4. Register a college with a stduent email domain, such as `students.example.test`
5. In a seperate browser session, register a student with an address in that domain and verify it through Mailpit.
6. Sign in as the admin to add course, modules and enrolments through the forms or CSV templates. Sign in as the student to check their dashboard.

## Optional Moodle connection

For a real public HTTPS Moodle host, follow the LMS setup guide. Local Moodle testing also needs its own stack, network and trusted certificate. `docker-compose.dev.yml` expects an existing `testcollege` network and `Moodle/caddy/root.crt`; it it not part of the basic setup above. Keep `DEV_MODE=false` unless you are setting up that explicit local exception.

## Stop and restart

```sh
docker compose stop
docker compose start
```

MongoDB data is stored in the service data directories listed in Compose. Stopping containers keeps those files.

Do not delete those directories to fix a startup problem; use the recovery steps first.
