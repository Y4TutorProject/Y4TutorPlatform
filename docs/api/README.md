# API specs

- [openapi.yaml](openapi.yaml): users, registration, colleges and gateway health.

OpenAPI 3.1 and can be imported into Swagger Editor or Postman.

For POSTs, fetch the receiving service's CSRF token first and keep its cookie.
College creation uses the users token and session. New accounts need email
verification; local verification messages appear at http://localhost:8025.

Matching currently takes a JSON body on a GET request. Some clients do not
support this; the spec documents the existing endpoint.
