# Messaging Service

This service provides messaging features for a students and tutors. It uses Flask and Socket.IO for real time comminication between the client and server.

The key features include:

* Room based message broadcasting
* Instant message delivery
* File uploads

A user is directed here after a tutoring proposal has been accepted. Authentication is handled by the user service and passed through the dashboard to the messaging service.

The dashboard must sign the JSON request to `POST /mychats/me` with the shared
`DASHBOARD_SHARED_SECRET`. It sends `X-Dashboard-Signature`, which is the
HMAC-SHA256 hex digest of the raw request body. Messaging rejects missing or
invalid signatures and only accepts users with an `active` status.

## Environment

SECRET_KEY
A secret key is required to protect the integrity of data in transit.
GENERATE -> python3 -c 'import secrets; print(secrets.token_hex(32))'

SESSION_COOKIE_SECURE
Controls whether session cookies are sent only over HTTPS.
false = HTTP (development)
true  = HTTPS (production)

DASHBOARD_SHARED_SECRET
The secret shared only by the dashboard backend and messaging service. Never
expose this value to browser code.

## Dashboard integration

The dashboard authenticates the user with the user service, then sends the
authenticated user context to messaging. From Docker containers, use
`http://users_svc:5000` and `http://messaging_svc:5000`. From the host machine,
use `http://localhost:5051` and `http://localhost:5052`.

## Get the authenticated user

```http
GET /users/me
```

The user service returns:

```json
{
  "user": {
    "id": "student-uuid",
    "username": "student123",
    "email": "student@example.com",
    "college_id": null,
    "status": "active",
    "roles": ["student"]
  }
}
```

The dashboard must use the returned ID, username, status, and roles. The
browser must not be allowed to replace these values.

## Open messaging

The dashboard backend sends:

```http
POST /mychats/me
Content-Type: application/json
X-Dashboard-Signature: <signature>
```

The request body must contain the current user and usernames for all chat
participants:

```json
{
  "user": {
    "id": "student-uuid",
    "username": "student123",
    "status": "active",
    "roles": ["student"]
  },
  "users": {
    "student-uuid": "student123",
    "tutor-uuid": "tutor456"
  }
}
```

`user.status` must be `active`, and `user.roles` must be a non-empty array.
The `users` object maps participant IDs to usernames so messaging can display
names without calling the user service for every message.

## Request signature

Sign the exact raw request body with HMAC-SHA256:

```python
import hashlib
import hmac

signature = hmac.new(
    DASHBOARD_SHARED_SECRET.encode("utf-8"),
    raw_request_body,
    hashlib.sha256,
).hexdigest()
```

Send the resulting value as `X-Dashboard-Signature`. The signature must be
calculated from the exact bytes sent over HTTP

## Messaging endpoints

After `/mychats/me` establishes the messaging session, use:

```http
GET  /mychats/chat/{chatId}
POST /mychats/chat/{chatId}/read
```

Successful message response:

```json
[
  {
    "messageId": "1",
    "chatId": "chat-uuid",
    "senderId": "tutor-uuid",
    "senderUsername": "tutor456",
    "message": "Hello",
    "timestamp": "2026-11-02T12:00:00Z"
  }
]
```

Successful read response:

```json
{
  "success": true
}
```

These 2 endpoints verify that the current session user belongs to the requested
chat.

## Socket.IO

Connect using the messaging session cookie:

```javascript
const socket = io("http://localhost:5052", {
  auth: { userId: currentUser.id }
});
```

Send a message with:

```javascript
socket.emit("message", {
  chatId: "chat-uuid",
  senderId: currentUser.id,
  message: "Hello",
  timestamp: new Date().toISOString()
});
```

Messaging checks that the sender matches the session user and belongs to the
chat. Messages must be non-empty and no longer than 5,000 characters.

If the dashboard proxies `/mychats/me`, it must preserve the messaging session
cookie in the browser. A backend-to-backend request does not automatically
transfer that cookie to the browser. `SameSite=Lax` protects the cookie from
most cross-site requests; it does not replace the dashboard signature.
