# Operational runbooks

Run these commands from the repository root with the `.env` used to start the local Compose stack.

## App cannot be reached

```sh
docker compose ps
curl --fail http://localhost:8080/health
docker compose logs --tail=100 gateway
```

For a 502 or 503, check the service handling the route:

```sh
docker compose logs --tail=100 dashboard_svc users_frontend registration_frontend users_svc college_svc lms_svc
```

Check missing environment values, database health and port conflicts. After fixing the cause, rebuild the affected service:

```sh
docker compose up -d --build --no-deps dashboard_svc
```

The gateway refreshes service addresses within about 10 seconds. Retry the affected page as well as `/health`.

## Login or verification fails

1. Check `users_svc`, `registration_svc` and `mailpit` logs.
2. For local HTTP, use `SESSION_COOKIE_SECURE=false` and `PUBLIC_BASE_URL=http://localhost:8080`.
3. Open the latest email at <http://localhost:8025>. Verification links work once and expire after one hour.
4. Keep the same browser, hostname and user agent during the session.
5. Complete verification, then retry sign-in.

## LMS sync fails

```sh
docker compose logs --tail=100 lms_svc lms_worker college_svc
```

Check the admin page's sync status. Check Moodle read permissions, URL, token, mapping fields and lecturer assignments. For local Moodle, check the network and certificate configuration.

`LMS_ENCRYPTION_KEY` must match the key used to save the credential. If it has been lost, enter the Moodle API key again in the admin form.

After fixing the cause, select **Sync now**. Check the import time, module list and student view. Failed imports keep the previous successful catalogue.

## Approved tutor cannot switch views

1. Confirm the account has tutor membership for at least one module in its college.
2. Check that `users_svc` and `lms_svc` have the same non-empty `COLLEGE_SYNC_TOKEN` and that `users_svc` can reach its `LMS_API_URL`.
3. Recreate the affected services after changing environment values.
4. Refresh an authenticated page or sign in again. The users service adds the account tutor role when the membership lookup succeeds.
5. Select **Switch to tutor role**, or **Tutor** on mobile. Complete teaching preference setup if prompted.

Failed membership lookups leave the student's access unchanged. The lookup retries
on later authenticated requests; existing tutor roles are retained.

## Chat does not connect

```sh
docker compose logs --tail=100 messaging_svc dashboard_svc gateway
```

Dashboard and messaging need the same `DASHBOARD_SHARED_SECRET`. Check that the browser receives the messaging session cookie. Inspect `/socket.io/` requests and chat response codes in browser network tools. Reverse proxies must forward WebSocket upgrade headers.

After the fix, sign in again and send a message between two test accounts. Check delivery and read state.

## Back up local data

Database files are bind-mounted under the five service directories. Saved LMS credentials also need the matching `LMS_ENCRYPTION_KEY`.

Stop the stack before copying database files. Choose an unused archive name:

```sh
docker compose stop
umask 077
tar -czf ../tutorplatform-backup.tar.gz .env users_svc/users_db_data college_svc/college_db_data lms_svc/lms_db_data messaging_svc/messaging_db_data sessions_svc/sessions_db_data
docker compose start
tar -tzf ../tutorplatform-backup.tar.gz
```

The archive contains credentials and user data. Store it outside the repository in an encrypted location with restricted access. Keep a recoverable copy of the encryption key separately.

## Restore and verify

Test restores in an isolated Docker environment using the matching code revision and MongoDB images. The Compose file uses fixed container names, so a different project name alone does not isolate another stack on the same daemon.

Keep containers stopped while restoring the five database directories and `.env`. Preserve a separate copy of the current data before replacing anything.

Start the stack and check database health, login, college ownership, academic records, LMS data and an existing chat. Record the backup date, revision and restore result.

## Documentation site fails

Run the documentation checks and inspect the failed Actions job. Fix or revert the documentation change through a PR, then merge to `main` to publish again.
