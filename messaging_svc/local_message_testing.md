# Local Messaging Testing

This guide tests the messaging service without the dashboard. It uses the
existing JSON fixtures in `messaging_svc/tests/data/` and a browser console
script that acts as the dashboard's signed session request.

The JSON fixtures are test data and should be committed. MongoDB's runtime
files in `messaging_svc/messaging_db_data/` should not be committed.

## Requirements

- Docker Desktop
- The repository's `messaging_db` container
- Two separate browser windows, profiles, or an incognito window

The fixture users are:

| ID | Name | Fixture chats |
|---|---|---|
| `1` | Alice | `1`, `2`, `4`, `7`, `10` |
| `2` | Bob | `1`, `3`, `5` |
| `3` | Charlie | `2`, `3`, `6` |

## 1. Start MongoDB

From the repository root:

```powershell
docker compose up -d messaging_db
```

## 2. Load the JSON fixtures

The fixtures are not loaded automatically by the messaging service. Copy the
chat, message, and read-state JSON files into the MongoDB container:

```powershell
docker cp messaging_svc\tests\data\chats.json messaging_db:/tmp/chats.json
docker cp messaging_svc\tests\data\messages.json messaging_db:/tmp/messages.json
docker cp messaging_svc\tests\data\chat_read_state.json messaging_db:/tmp/chat_read_state.json
```

Replace the local messaging collections with the fixture data:

```powershell
docker exec messaging_db mongosh `
  -u admin -p password --authenticationDatabase admin `
  messaging_db --quiet --eval "db.chats.deleteMany({}); db.chats.insertMany(JSON.parse(fs.readFileSync('/tmp/chats.json')).chats); db.messages.deleteMany({}); db.messages.insertMany(JSON.parse(fs.readFileSync('/tmp/messages.json')).messages); db.chatReadStates.deleteMany({}); db.chatReadStates.insertMany(JSON.parse(fs.readFileSync('/tmp/chat_read_state.json')).chatReadStates); print('Messaging fixtures loaded')"
```

This gives you existing conversations such as:

- Chat `1`: Alice and Bob
- Chat `2`: Alice and Charlie
- Chat `3`: Bob and Charlie

The `users.json` file is useful as a name reference for local testing. User
accounts are owned by the user service and are not imported into the messaging
database.

## 3. Start the messaging service

From the repository root, in a separate PowerShell window:

```powershell
$env:SECRET_KEY = "local-secret-that-is-at-least-32-characters"
$env:DASHBOARD_SHARED_SECRET = "local-dashboard-secret"
$env:SESSION_COOKIE_SECURE = "false"
$env:MONGO_URI = "mongodb://localhost:27018"
python messaging_svc\app.py
```

Open:

```text
http://localhost:5052
```

## 4. Create a local messaging session

Open browser developer tools, select **Console**, and run this script. Change
only the `user` object when creating the second session.

```javascript
(async () => {
  const secret = "local-dashboard-secret";
  const body = JSON.stringify({
    user: {
      id: "1",
      username: "Alice",
      status: "active",
      roles: ["student"]
    },
    users: {
      "1": "Alice",
      "2": "Bob",
      "3": "Charlie"
    }
  });

  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signatureBytes = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(body)
  );
  const signature = [...new Uint8Array(signatureBytes)]
    .map(byte => byte.toString(16).padStart(2, "0"))
    .join("");

  const response = await fetch("/mychats/me", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Dashboard-Signature": signature
    },
    body
  });

  document.open();
  document.write(await response.text());
  document.close();
})();
```

For the second browser, use this user object:

```javascript
user: {
  id: "2",
  username: "Bob",
  status: "active",
  roles: ["tutor"]
}
```

Use separate browser sessions. Do not reuse the first tab or its cookies.
Hard-refresh both pages after creating the sessions.

## 5. Test normal messaging

1. Alice and Bob should both see Chat `1`.
2. Open Chat `1` in both browsers.
3. Send a message as Alice.
4. Confirm Bob receives it without refreshing.
5. Reply as Bob and confirm Alice receives it.
6. Refresh both pages and confirm the messages remain.

## 6. Test read and unread state

1. Leave Chat `1` closed in Bob's browser.
2. Send a message from Alice.
3. Confirm Chat `1` is marked unread for Bob.
4. Open Chat `1` as Bob.
5. Confirm the unread styling is removed.
6. Refresh and confirm the read state remains.

## 7. Test the typing indicator

1. Keep Chat `1` open in both browsers.
2. Start typing as Alice without sending.
3. Bob should see `Alice is typing...`.
4. Stop typing for approximately one second.
5. Confirm the indicator disappears.
6. Repeat in the opposite direction with Bob.
7. Also verify it disappears when the input is cleared, loses focus, the chat
   changes, or a message is sent.

## Troubleshooting

- **Blank chat list:** the session user is not a member of any loaded chat.
- **No messages:** the JSON fixtures were not loaded into `messaging_db`.
- **401 response:** the browser secret does not match
  `DASHBOARD_SHARED_SECRET`.
- **400 response:** the signed user payload is missing a required field or the
  user is not active.
- **MongoDB connection failure:** check that `messaging_db` is running and that
  `MONGO_URI` uses port `27018` from the host.
- **One-way typing only:** hard-refresh both pages and create each session in a
  separate browser profile so cookies and Socket.IO connections are separate.

All secrets and test values in this guide are for local development only.
