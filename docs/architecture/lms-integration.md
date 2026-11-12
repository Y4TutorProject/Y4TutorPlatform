# College LMS integration

The LMS service imports college data from Moodle and updates it every night. It runs as an API (`lms_svc`), worker (`lms_worker`) and MongoDB database (`lms_db`). The college service stores courses and modules in `college_db`.

Admins can browse the latest import under **Imported LMS data** on `/admin-dashboard`. The viewer shows courses, modules, users and enrolments, with search and 25 records per page. A successful sync refreshes the counts and import time.

## Setup

Enable Moodle web services and REST, then create an integration user and token with these read functions:

- `core_user_get_users`
- `core_course_get_categories`
- `core_course_get_courses`
- `core_enrol_get_users_courses` for legacy enrolments
- `core_enrol_get_enrolled_users` for course roles
- `core_course_get_contents` when using activities as modules

Generate a separate `COLLEGE_SYNC_TOKEN` in `.env`. The college API, LMS API and worker use it for internal catalogue requests. Generate `LMS_ENCRYPTION_KEY` with:

```sh
python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

Keep the encryption key when backing up the database. Saved Moodle credentials depend on it.

Start the services:

```sh
docker compose up -d --build lms_db lms_svc lms_worker gateway dashboard_svc
```

Sign in as the college admin, open **College system connection**, select Moodle and enter its public HTTPS URL and API key. Configure **Academic structure and role mapping**, then save.

Set `LMS_DB_PASSWORD` for the database. `LMS_ALLOWED_HOSTS` can restrict connections to a comma-separated list of hosts.

## Imported data

| Moodle | Platform default |
| --- | --- |
| Users | College directory records |
| Categories | Courses and programmes |
| Courses | Modules |
| Active enrolments | Links between imported users and modules |

Mapping settings control category depths, custom fields, activities and role names. The import includes records visible to the Moodle token, with limits of 5,000 users and 500,000 enrolment links. Passwords, grades and files are excluded. Imported users register and verify their platform accounts separately.

## Nightly updates

Saving an enabled connection queues the first sync. Updates then run at **02:00 Europe/Dublin**. Change the schedule with `LMS_SYNC_HOUR` and `LMS_SYNC_TIMEZONE`.

The worker checks for jobs every 30 seconds and catches up after a restart. Failed jobs retry after 15 minutes, keeping the last successful import. A database lock prevents two syncs for the same connection running together.

Admins can select **Sync now** or pause nightly updates. Leaving the API key blank when saving keeps the existing encrypted key.

## Security

Connection changes require the owning admin's session and CSRF token. External requests use HTTPS on port 443. Private addresses, metadata addresses and redirects are blocked. Each request checks DNS and connects to the checked IP.

Moodle requests use fixed read functions and send the token in a POST body. Imported records are checked for valid fields, IDs and relationships. Responses and catalogues are limited to 8 MiB and 50,000 records per collection. An invalid import leaves the previous data in place.

## Adding another system

Implement `LMSProvider.fetch_catalog()` and register the provider. The adapter handles authentication and maps records into users, courses, modules and enrolments using the shared HTTPS transport.

`LMSImportStore` saves imports. `ConnectionStore` saves settings, credentials and sync locks.

## API and tests

Connection, sync and catalogue routes use `/api/lms/college/{college_id}/lms` through the gateway.

```sh
.venv-auth/bin/python -m pytest tests/test_lms_security.py tests/test_lms_sync.py tests/test_lms_import.py -q
node --test tests/lms_ui.test.cjs
```

## Academic storage and migration

The college service stores courses, modules and catalogue versions in `college_db.courses`, `college_db.modules` and `college_db.academic_catalogs`. Modules reference their course through `course_id`; courses use `parent_id` for the category hierarchy.

IDs remain stable across syncs and are scoped to the college, provider and source URL. The LMS database stores profiles, enrolments and a `catalog_ref` pointing to the college records.

The college service publishes a catalogue after saving all its records. The LMS service then replaces its current import. A failure keeps the previous complete version available. The services exchange records through authenticated internal HTTP requests.

To migrate older imports, rebuild the college service, LMS API, worker and dashboard with the shared token, then run:

```sh
docker compose exec -T lms_svc python -m lms_svc.migrate_catalogs
```

The migration moves courses and modules to college storage and keeps profiles and import times. It can be run again safely. Select **Sync now** after enabling the enrolment function.

For local Moodle, enable the read function with:

```sh
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml cp Moodle/scripts/enable_enrolment_service.php webserver:/tmp/enable_enrolment_service.php
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml exec -T --user www-data webserver php /tmp/enable_enrolment_service.php --service=Tutor
```

## Student dashboard view

`GET /api/lms/students/me` uses the signed-in account's college and verified email to find its active Moodle profile. It returns that profile's enrolled modules and programme hierarchy. Client-supplied email addresses and college IDs are ignored.

A missing, suspended or ambiguous profile returns no academic records. Empty enrolments and service failures show a message on the dashboard.

## Module roles and tutor applications

Module roles are stored in `module_memberships`, with one record per `(college_id, user_id, module_id)` and a `roles` array. Dashboard visits, module searches and syncs refresh student memberships from enrolments. Withdrawn or suspended enrolments lose student membership; approved tutor membership is kept. These roles leave global account roles and Moodle records unchanged.

`GET /api/lms/students/me/modules?q=...` searches eligible earlier-year modules in the student's programme. The highest enrolled year determines their current year unless the mapper supplies it explicitly. Unknown years grant no eligibility. Year 1 students cannot apply.

Submit an application with:

```http
POST /api/lms/students/me/modules/<module_id>/tutor-application
Content-Type: application/json
X-CSRFToken: <users-service token>
```

```json
{"grade": 85}
```

Grades must be numeric from 0 to 100. The request requires the student's session and creates one pending application per user and module. Repeated submissions return the same application.

Lecturers review applications at `/tutor-applications`:

- `GET /api/lms/lecturers/me/tutor-applications` lists their pending applications.
- `POST /api/lms/lecturers/me/tutor-applications/<id>/review` accepts `{"decision": "approved"}` or `{"decision": "rejected"}`, with a session and CSRF token.

The lecturer's verified email must match one active imported profile, and they must be the module's assigned lecturer. Self-review is blocked. College admins review manually managed modules through `/college/<college_id>/tutor-applications`.

Approval checks eligibility again, adds the module's tutor role and records the reviewer and time. Repeating the same decision is safe; conflicting decisions are rejected.

Moodle course-role mapping uses `editingteacher` and `teacher` for lecturers by default. Existing legacy connections need `course_roles` selected and a new sync. Multiple lecturers on one module cause the import to fail; a module without an active lecturer has no assigned reviewer.

For local testing, seed lecturers with:

```sh
docker cp Moodle/scripts/seed_lecturers.php moodle-webserver-1:/tmp/seed_lecturers.php
docker exec --user www-data moodle-webserver-1 php /tmp/seed_lecturers.php --domain=student.testcollege.ie
```

Use the development college's email domain. The script keeps existing single-lecturer assignments and creates one test lecturer per Moodle category. Platform accounts need a matching verified email and their own password.

Lecturers see their teaching modules and pending applications at `/dashboard` or `/lecturer-dashboard`. `GET /api/lms/lecturers/me/modules` returns their assigned modules. Teaching a module does not grant student tutoring eligibility.
