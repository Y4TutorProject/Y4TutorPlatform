# College LMS integration

The LMS service imports provider-normalized college data and updates it every night.
Moodle is the bundled adapter; its academic and role mapping is configurable.
It has its own API (`lms_svc`), background worker (`lms_worker`) and MongoDB
database (`lms_db`) for connection credentials, imported profiles and enrolment
links. The college service owns academic `Course` and `Module` records in
`college_db`. An LMS failure leaves account sign-in available.

The college administration page (`/admin-dashboard`) includes an **Imported LMS
data** viewer for the latest successful import. Administrators can browse and
search courses/categories, modules, users, and enrolments with roles, with 25
records per page. The view shows import counts, source, and timestamp, and refreshes
after a successful manual sync. Its existing catalogue API requires the owning
college administrator's verified session and CSRF token. Imported user records do
not grant platform sign-in; users still register and verify their accounts.

## Setup

1. Enable Moodle web services and REST. Create a dedicated integration user and
   API token with permission to read:
   - `core_user_get_users`
   - `core_course_get_categories`
   - `core_course_get_courses`
   - `core_enrol_get_users_courses` (legacy active enrolments)
   - `core_enrol_get_enrolled_users` (when importing actual course roles)
   - `core_course_get_contents` (when mapping activities to modules)
2. Generate a separate random `COLLEGE_SYNC_TOKEN` and put it in `.env`. Compose
   shares it only with the college API, LMS API and LMS worker. This authenticates
   internal catalogue reads/writes; browser sessions cannot call those endpoints.
   Generate an encryption key and save it as `LMS_ENCRYPTION_KEY` in `.env`:

   ```sh
   python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
   ```

   Keep this key and back it up separately from the database. Losing it means
   administrators must enter their Moodle API keys again.
3. Start the services:

   ```sh
   docker compose up -d --build lms_db lms_svc lms_worker gateway dashboard_svc
   ```

4. Sign in as the college administrator. On the **Admin Dashboard**, select **Moodle**,
   enter its public HTTPS URL and API key, configure **Academic structure and role
   mapping**, and save the connection. Settings are supplied by the installed adapter.

Public HTTPS hosts need no manual approval. To restrict hosts, optionally set
`LMS_ALLOWED_HOSTS` to a comma-separated list. Internal-only Moodle sites are
blocked. Set `LMS_DB_PASSWORD` for the database credentials.

## Imported data

| Moodle | Platform |
| --- | --- |
| Users | College directory records |
| Categories | Degree programmes (`courses`) |
| Courses | Academic subjects (`modules`) |
| Active user course enrolments | Links from Moodle user IDs to college module IDs |

These are the compatibility defaults. Admins can choose category depths, custom
fields, activity modules and role shortnames; see [configurable mapping](lms-adapters.md). Only data visible to the Moodle token is imported.
Imported users must still register and verify their email to sign in. Passwords,
grades and files are not imported. Active enrolments use `core_enrol_get_users_courses` in legacy mode or
`core_enrol_get_enrolled_users` in role-aware mode; suspended users receive no links.
The token must be able to view the relevant users and courses. The API returns
only active enrolments visible to that token ([Moodle API documentation](https://phpdoc.moodledev.io/main/d6/d09/classcore__enrol__external.html)).
Imports are limited to 5,000 users and 500,000 enrolment links.

## Nightly updates

Saving an enabled connection queues an initial sync. After that, updates run at
**02:00 Europe/Dublin**, including daylight saving changes. Override this with
`LMS_SYNC_HOUR` and `LMS_SYNC_TIMEZONE`.

The worker checks for due jobs every 30 seconds and catches up after restarts.
Failed jobs retry after 15 minutes and keep the last successful data. A database
lock prevents overlapping syncs for the same connection.

Administrators can check sync status, select **Sync now**, or pause nightly updates.
API keys are saved encrypted; leaving the key blank keeps the existing credential.
Back up the `lms_db_data` volume as well as the encryption key.

## Security

- Only the owning college administrator can manage the connection, using a valid
  session and CSRF token.
- External requests require HTTPS on port 443. Private/internal addresses,
  metadata addresses and redirects are blocked. DNS is checked on every request,
  and the connection uses the checked IP to prevent DNS rebinding.
- Moodle calls use fixed read functions. POST keeps the API key out of URLs;
  GET alone would not prevent data being sent. Only the Moodle token and lookup
  parameters are sent, without platform user or course records.
- Incoming records are checked for valid types, lengths, IDs and relationships.
  Unknown fields are discarded. Responses and catalogs are limited to 8 MiB,
  with up to 50,000 records per collection. Invalid imports leave existing data intact.

Use a Moodle token restricted to the required read permissions. Treat imported
text as untrusted and escape it when displaying it. Large colleges may need a
paginated export adapter. Verify the connection against a real Moodle site before
deployment.

## Adding another system

Implement `LMSProvider.fetch_catalog()` and register the provider factory.
Each provider handles its own authentication and maps data into users, courses
and modules. Use the shared public HTTPS transport and validation.

`LMSImportStore` handles catalog storage; `ConnectionStore` handles saved settings
and sync locks. These interfaces keep provider code separate from scheduling and
storage. Blackboard and other connectors are not implemented yet.

## API and tests

Connection, sync and catalog endpoints are under
`/api/lms/college/{college_id}/lms`. See [the API specification](../api/openapi.yaml)
for request details.

```sh
.venv-auth/bin/python -m pytest tests/test_lms_security.py tests/test_lms_sync.py tests/test_lms_import.py -q
node --test tests/lms_ui.test.cjs
```

## Academic storage and migration

`college_svc/Objects/Course.py` and `Module.py` use UUID identities and `to_dict()`,
following the existing college domain object pattern. The academic interface,
service and Mongo DAO validate records and store them in `college_db.courses`,
`college_db.modules` and `college_db.academic_catalogs`. A module's `course_id`
references its owning Course; category hierarchy uses Course `parent_id`.
IDs stay stable across synchronizations and are scoped to college, provider and
source URL. Each immutable catalogue version retains consistent names and links.

`lms_db.lms_imports` contains profiles, a `catalog_ref` with the college catalogue,
course and module IDs, and enrolment links to those IDs. It does not duplicate
course/module records. The college service publishes a version after all records
are stored; the LMS service replaces its import only after college publication
succeeds. A failed import keeps the previous complete version readable. Unlinked
versions from interrupted imports can be retained safely; no automatic deletion
runs. The LMS service accesses college data through authenticated internal HTTP
endpoints, without direct college database credentials.

For an existing deployment, rebuild `college_svc`, `lms_svc`, `lms_worker` and
`dashboard_svc` with the shared service token, then run:

```sh
docker compose exec -T lms_svc python -m lms_svc.migrate_catalogs
```

Use the development Compose override as well when working with local Moodle.
The idempotent migration moves old courses/modules to college storage and replaces
them with references, preserving the last import time and profiles. Run **Sync
now** after granting the enrolment function to populate personal enrolments.
Legacy imports display a synchronization message until this completes.

For the local Moodle integration service, add the function without changing the
token or granting write functions:

```sh
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml cp Moodle/scripts/enable_enrolment_service.php webserver:/tmp/enable_enrolment_service.php
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml exec -T --user www-data webserver php /tmp/enable_enrolment_service.php --service=Tutor
```

## Student dashboard view

After sign-in, students see their own Moodle name, username, email, programme
hierarchy and enrolled modules on the student `/dashboard`. The read-only `GET /students/me`
LMS endpoint validates the users session and derives the college and verified
email from that account. It returns only the unique matching active Moodle
profile and modules linked to its Moodle source ID, plus the owning programmes
and their category ancestors. It ignores client-supplied email/college IDs.
Missing, suspended or ambiguous matches return no profile or academic records.
Other students' directory records, enrolments, unrelated modules and connection
credentials are never included. Empty enrolments show an explicit empty state;
missing imports and dependency outages show a message while leaving the platform
account usable.

## Module roles and tutor applications

The LMS database stores platform module roles in `module_memberships`, with a
unique `(college_id, user_id, module_id)` relationship and a `roles` array.
A verified student's first dashboard/profile or module-search request links their
platform account to their Moodle enrolments and records `student` on each enrolled
module. Subsequent reads and Moodle synchronizations refresh these memberships,
removing Student membership for withdrawn or suspended enrolments while preserving
independently approved Tutor membership. The Moodle source identity is retained
for synchronization; module roles do not change the account's global roles or
write back to Moodle.

`GET /api/lms/students/me/modules?q=...` searches module names and codes in eligible
previous years of the student's programme. Programme and year are explicit canonical module metadata supplied by the
configured provider mapper. Moodle's default layout remains department → programme
→ year; admins can configure other layouts or course fields.
Programme membership is derived from current enrolments, and results exclude
other programmes and colleges. No enrolments means no programme modules.

`POST /api/lms/students/me/modules/<module_id>/tutor-application` accepts
`{"grade": 85}` with a required numeric grade from 0 to 100 (decimals allowed). It requires the
current student's session and users-service CSRF token, checks programme access,
and creates one pending `tutor_applications` record per user/module. Applications
are permitted only for modules in earlier years of the same programme, including
previous-year modules that remain on their Moodle enrolment record. The highest enrolled year per
programme determines the current year. The mapper must supply a numeric academic year; unknown years do not
grant eligibility. Moodle year aliases and field sources are configurable. Year 1 students cannot apply. Search only returns eligible previous-year programme
modules, each with `can_apply_to_tutor` set to true. Ineligible modules are omitted
from both the API results and the dashboard list. Admin approval
rechecks current enrolments and eligibility before granting the Tutor role. Repeated
submissions return the same application; applying does not grant Tutor access.

The college administrator reviews pending applications on their dashboard:

- `GET /api/lms/college/<college_id>/tutor-applications` lists pending applications.
- `POST /api/lms/college/<college_id>/tutor-applications/<id>/review` accepts
  `{"decision": "approved"}` or `{"decision": "rejected"}`.

Both admin endpoints verify college ownership and require a session and CSRF
token. Approval records `tutor` on that module membership and retains an existing
`student` role. A repeated identical decision is safe; a conflicting decision is
rejected. Applications remain stored with the reviewer and review time.

See [LMS adapters and configurable mapping](lms-adapters.md) for provider
interfaces, installation, admin mapping options and role-aware Moodle import.
