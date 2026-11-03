# College LMS integration

The LMS service imports college data from Moodle and updates it every night.
It has its own API (`lms_svc`), background worker (`lms_worker`) and MongoDB
database (`lms_db`). An LMS failure leaves the other platform services running.

## Setup

1. Enable Moodle web services and REST. Create a dedicated integration user and
   API token with permission to read:
   - `core_user_get_users`
   - `core_course_get_categories`
   - `core_course_get_courses`
2. Generate an encryption key and save it as `LMS_ENCRYPTION_KEY` in `.env`:

   ```sh
   python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
   ```

   Keep this key and back it up separately from the database. Losing it means
   administrators must enter their Moodle API keys again.
3. Start the services:

   ```sh
   docker compose up -d --build lms_db lms_svc lms_worker gateway users_frontend
   ```

4. Sign in as the college administrator. On **Your account**, select **Moodle**,
   enter its public HTTPS URL and API key, and save the connection. Moodle fields
   appear only when Moodle is selected.

Public HTTPS hosts need no manual approval. To restrict hosts, optionally set
`LMS_ALLOWED_HOSTS` to a comma-separated list. Internal-only Moodle sites are
blocked. Set `LMS_DB_PASSWORD` for the database credentials.

## Imported data

| Moodle | Platform |
| --- | --- |
| Users | College directory records |
| Categories | Degree programmes (`courses`) |
| Courses | Academic subjects (`modules`) |

This assumes Moodle categories represent programmes. Colleges using a different
structure need a custom mapping. Only data visible to the Moodle token is imported.
Imported users must still register and verify their email to sign in. Passwords,
grades, files and enrolments are not imported.

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
