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

MESSAGING_KEY
A base64-encoded 32-byte key used to encrypt message bodies stored in MongoDB.
Generate it with:

```sh
python3 -c 'import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())'
```

Keep this key secret and backed up securely. Previously stored messages cannot
be decrypted without the same key.

## Message encryption

Message bodies are encrypted with AES-256-GCM before being saved in the MongoDB
messages collection, using a fresh random nonce for each message. They are
decrypted when loaded by the messaging service. The `lastMessage` preview in
MongoDB chat documents is encrypted on writes and decrypted on reads as well.

Uploaded files are encrypted the same way before they are written to GridFS and
decrypted when downloaded. The stored blob is the nonce followed by the
ciphertext. A file that fails the authentication check is not returned.

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

The request body contains the current user and may include known participant
usernames:

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

`user.status` must be `active`. The optional `users` object maps participant
IDs to usernames. For conversation lists, the dashboard resolves each distinct
participant through the authenticated `GET /users/{id}` profile endpoint and
uses the returned username for the list and message pane. A participant whose
profile is no longer accessible is shown as "Unavailable user"; other lookup
failures prevent the page from loading.

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

## File uploads

Files are sent as a chat message through multipart form data. The sender is the
authenticated session user, so `senderId` and `timestamp` are not form fields.
The file is stored in MongoDB GridFS, and the message document keeps a reference
to it.

```http
POST /mychats/chat/{chatId}/files
Content-Type: multipart/form-data
```

Form fields:

* `file`: The file to upload. Required and must not be empty.
* `message`: Optional caption, at most 5,000 characters.

Allowed types are PDF (`application/pdf`), Word (`.docx`) and Excel (`.xlsx`).
Files are limited to 10 MB (`MAX_UPLOAD_BYTES`). Nginx allows 11 MB on this
route only, so changing the limit means updating `client_max_body_size` in
`nginx/default.conf` too.

Successful response (`201`):

```json
{
  "messageId": "1",
  "chatId": "chat-uuid",
  "senderId": "tutor-uuid",
  "senderUsername": "tutor456",
  "message": "Here is the worksheet",
  "timestamp": "2026-11-02T12:00:00Z",
  "messageType": "file",
  "fileName": "example.pdf",
  "mimeType": "application/pdf",
  "fileSize": 48213
}
```

Errors: `400` (no file, empty file, or caption too long), `404` (chat not found or
not a member), `413` (file too large), `415` (type not allowed).

## File downloads

Only members of the chat can download a file. The response is the file itself
with `Content-Disposition: attachment`. This header tells the browser to save the
response as a file rather than display it inline.

```http
GET /mychats/chat/{chatId}/files/{messageId}
```

Returns `404` if the chat is not found, the message is not a file message in
that chat, or the stored file is missing.

## Messaging endpoints

After `/mychats/me` establishes the messaging session, use:

```http
GET  /mychats/chat/{chatId}
POST /mychats/chat/{chatId}/read
```

Successful message response. Text messages have `messageType` set to `text`.
File messages have `messageType` set to `file` and also include `fileName`,
`mimeType` and `fileSize`:

```json
[
  {
    "messageId": "1",
    "chatId": "chat-uuid",
    "senderId": "tutor-uuid",
    "senderUsername": "tutor456",
    "message": "Hello",
    "timestamp": "2026-11-02T12:00:00Z",
    "messageType": "text"
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
