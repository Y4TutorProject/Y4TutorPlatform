# Colleges

`college_svc` stores college records in `college_db`. The registration service gets college details through its API.

## API

Through the gateway, college routes start with `/api/colleges`. For direct requests during development, the service runs on port 5053

- `GET /college` - active colleges, sorted by name. Public
- `GET /college/<college_id>` - active college details, or 404. Public
- `POST /college` - Create a college. Requires a verified `college_admin` account and a users-session CSRF token.

To create a college, send:

```json
{
  "name": "Example College",
  "domain": "students.college.ie"
}
```

`domain` is the part after the @ in a students email address. Enter the domain on its own without a url. Studnets registering with the college must use a matching email address.

Each administrator can register one college. Creating it records them as the owner and links it to their account. If that link fails to save, sending the same request again finishes the link without creating a second college.

## Authentication

The service asks the users API to check the session and CSRF token. It does not accept identity headers as proof of who the user is or read the users database itself. Direct requests on port 5053 go through the same checks.

`USERS_API_URL` defaults to `http://gateway/api/users`. Sign in through the gateway and keep the same cookie user agent for the college requests.

Response codes are 201 for creation, 400 for invalid input or CSRF, 401 for an invalid session, 403 for the wrong role, 404 for a missing college, 409 for a duplicate and 503 for when the service is unavailable
