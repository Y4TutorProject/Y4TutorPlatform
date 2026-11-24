# Sessions Service

`sessions_svc` stores tutoring sessions and tells the reviews and payments
services when a session is booked, completed or cancelled. It is deliberately
minimal. Booking, scheduling and calendar features build on it under YGPT-34
and YGPT-33.

From Docker containers use `http://sessions_svc:5000`. From the host machine use
`http://localhost:5056`. Through the gateway the API is at `/api/sessions/`.

## Session record

| Field | Notes |
|---|---|
| `id` | UUID, created by the service |
| `tutorId`, `studentId` | Must be different users |
| `moduleId` | Module the session is for |
| `startTime`, `endTime` | Timestamps as strings |
| `status` | `booked`, `completed` or `cancelled` |
| `price` | Whole cents, for example `2500` is €25.00 |

A session starts as `booked` and can change once, to `completed` or
`cancelled`. Trying to change it again returns `409 Conflict`.

## API

Every endpoint except `/health` needs the dashboard signature, the same as the
messaging service: send `X-Dashboard-Signature`, the HMAC-SHA256 hex digest of
the raw request body using `DASHBOARD_SHARED_SECRET`. For `GET` requests the
body is empty.

| Method | Path | Result |
|---|---|---|
| `POST` | `/sessions` | `201` with the new session, or `400` if fields are missing or invalid |
| `GET` | `/sessions/<id>` | `200`, or `404` |
| `POST` | `/sessions/<id>/complete` | `200`, `404`, or `409` if not booked |
| `POST` | `/sessions/<id>/cancel` | `200`, `404`, or `409` if not booked |
| `GET` | `/health` | `200` |

## Events

After each change the service sends an event to the services that need it:

| Event | Sent to |
|---|---|
| `session.booked` | payments |
| `session.completed` | reviews and payments |
| `session.cancelled` | payments |

Each event is a `POST` to `<service URL>/events/sessions` with the body
`{"event": "...", "session": {...}}`. The `X-Sessions-Signature` header is the
HMAC-SHA256 hex digest of the body using `EVENTS_SHARED_SECRET`. Receiving
services must check this signature.

If a service URL is not set, the event is logged and skipped. If sending fails,
the error is logged and the session change still succeeds. Events are not
retried.

## Environment

MONGO_URI, MONGO_DB_NAME, MONGO_COLLECTION_NAME
Connection to `sessions_db`.

DASHBOARD_SHARED_SECRET
Shared with the dashboard to sign requests to this service.

EVENTS_SHARED_SECRET
Shared with the reviews and payments services to sign events. Generate it with:

```sh
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

REVIEWS_API_URL, PAYMENTS_API_URL
Base URLs of the reviews and payments services. Events for a service with no URL are skipped.
