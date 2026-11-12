# API specs

[openapi.yaml](openapi.yaml) contains the OpenAPI 3.1 reference for registration, users, colleges, dashboard routes, messaging, LMS connections and gateway health. Open it in Swagger Editor or import it into Postman.

For POST requests, get a CSRF token from the receiving service and keep its session cookie. College and LMS requests use the users-service token and session. Local verification emails appear at <http://localhost:8025>.

## Reference coverage

| Area | Guide |
| --- | --- |
| Accounts, usernames and preferences | [Users and registration](../architecture/users.md) |
| Courses, modules, assignments and CSV imports | [Manual academic records](../architecture/manual-academics.md) |
| LMS connections, student modules and tutor applications | [LMS integration](../architecture/lms-integration.md) |
| Matching requests | [Matching system](../architecture/matching-system.md) |
| Chat sessions and Socket.IO | [Messaging](../architecture/messaging.md) |
| Notification records and API design | [Notifications](../architecture/notifications.md) |
