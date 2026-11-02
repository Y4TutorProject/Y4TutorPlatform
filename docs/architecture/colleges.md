# Colleges

`college_svc` stores colleges in `college_db`. Registration reads colleges through
the service API, not directly from the database.

## API

Gateway prefix: `/api/colleges`. Direct development port: 5053.

- `GET /college` — active colleges, sorted by name. Public.
- `GET /college/<college_id>` — active college details, or 404. Public.
- `POST /college` — create a college. Requires a verified `college_admin`
  account and a users-session CSRF token.

Create request:

```json
{
  "name": "Example College",
  "domain": "students.college.ie"
}
```

`domain` is the part after `@` in student email addresses, without a URL.
Students must select a college and use an email matching this domain.

Each administrator can register one college. Creation records the owner and
links the college to their account. Repeating the same request retries unfinished
account linking without creating another college.

## Authentication

The service checks the session and CSRF token through the users API. It does not
trust identity headers or read the users database. These checks also apply to
direct requests on port 5053.

`USERS_API_URL` defaults to `http://gateway/api/users`. Sign in through the gateway
and keep the same cookie and user agent for college requests.

Responses: 201 created, 400 invalid input/CSRF, 401 invalid session, 403 wrong role,
404 college not found, 409 duplicate college, 503 service unavailable.

See [users and registration](users.md) for setup, email verification and test commands.
