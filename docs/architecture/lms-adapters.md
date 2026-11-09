# LMS adapters and configurable academic mapping

The LMS core consumes canonical academic data. Provider-specific naming, REST
functions, category layouts and role names live in adapters and their mappers.
Tutoring policy reads a module's explicit `programme_id` and numeric `year`; it
never parses a Moodle category name or assumes a fixed hierarchy.

## Contracts and dependency injection

- `LMSProvider` describes its admin settings, validates options/mapping modes,
  builds an adapter using the supplied transport, and returns a complete catalogue.
- `LMSCatalogMapper` converts external records into canonical academic records.
- `LMSHTTPTransport` supplies validated HTTPS with hostname/TLS verification and
  protection against private/metadata IPs and DNS rebinding. The local development
  exception remains an explicit allowlist plus a trusted certificate.
- `LMSImportStore` publishes immutable catalogue references and enrolment links.
- `AcademicCatalogClient` is the college service boundary; academic objects and
  their metadata are owned by the college service, not duplicated in LMS storage.
- `ConnectionStore` owns encrypted credentials, settings and synchronization leases.
- `ModuleParticipationStore` owns module memberships and tutor applications.
- `LMSAuthenticationClient` verifies users sessions and CSRF tokens.

`lms_svc.create_app()` accepts replacements for providers, authentication, college
client, import store, connection store and participation store. Concrete MongoDB
and HTTP implementations are selected in that composition root. Controllers do
not reach through these interfaces into Mongo collections.

## Canonical catalogue

```json
{
  "users": [{"source_id": "person-1", "email": "student@college.example"}],
  "courses": [{"source_id": "degree-1", "name": "Computing", "kind": "programme"}],
  "modules": [{
    "source_id": "unit-1", "course_id": "degree-1",
    "programme_id": "degree-1", "year": 2, "name": "Databases"
  }],
  "enrolments_available": true,
  "enrolments": [{
    "user_source_id": "person-1", "target_type": "module",
    "target_source_id": "unit-1", "roles": ["student"]
  }]
}
```

Source IDs are scoped to college, provider and source URL. The college service
converts course/module relationships to stable UUIDs. `course_id` identifies a
module's immediate owner; `programme_id` explicitly identifies its programme even
when intermediate year/semester categories exist. Year is a nullable integer
from 1 to 20. Missing year metadata never grants tutor eligibility. A canonical
user may supply `current_year` to override the highest-enrolled-year default; an
explicit null means the year is unknown and grants no eligibility.

Enrolment targets can be modules or courses. Course-level enrolments expand to
that course's modules without knowing which LMS produced them. Imported module
roles are `student` and `lecturer`; independent `tutor` approval is a platform
workflow. A lecturer is not automatically marked as a student, and an imported
role never grants platform administrator rights or a global account role.
Legacy `course_source_id` enrolment input and old activity snapshots remain
readable. New adapters should use explicit target types and source IDs.

## Moodle admin settings

Open **Admin Dashboard → College system connection → Academic structure and role
mapping**. The form is built from `GET /api/lms/providers`, which describes only
installed adapters and their supported fields. The same settings are validated
server-side, saved as `provider_options`, restored on reload and used by both
manual and nightly syncs. Blank API keys retain the existing encrypted credential.

| Setting | Choices and meaning |
| --- | --- |
| Platform module | A Moodle course, or an activity inside a Moodle course |
| Platform course/programme | A category at a selected depth, a course/custom field, or the Moodle course itself when modules are activities |
| Programme category depth | 1 means the root category; 2 means its child; institutions choose their own layout |
| Programme field | A custom field shortname, or `fullname`, `shortname`, or `idnumber` |
| Department category depth | Optional classification; 0 disables it |
| Academic year source | Recognized category label, category at a selected depth, course/custom field, activity section/topic name, or unavailable |
| Year field | A course/custom field shortname when using fields |
| Year label map | Institution-specific labels mapped to numeric years; for example `{"Foundation":1,"Intermediate":2,"Final":3}` |
| Student current year | Highest enrolled module year, or a Moodle user profile field |
| Current year profile field | Profile field shortname; missing/unrecognized values fail closed |
| Module role source | Legacy enrolments-as-Student, or actual Moodle course role shortnames |
| Student roles | Institution-specific shortnames, default `student` |
| Lecturer roles | Institution-specific shortnames, defaults `editingteacher` and `teacher` |

Default category settings preserve the existing department → programme → year
Moodle seed (programme depth 2, department depth 1). A one-level legacy catalogue
is treated as a programme. Institutions with other layouts can change the depth
or use custom fields. Defaults recognize `Y1`, `Year 1`, `Stage 1`, and numeric
labels through year 20. These aliases are entirely configurable.

For example, an institution whose Moodle courses have `degree` and `level` fields
can configure:

```json
{
  "programme_source": "course_field",
  "programme_field": "degree",
  "year_source": "course_field",
  "year_field": "level",
  "role_source": "course_roles",
  "student_roles": ["learner"],
  "lecturer_roles": ["instructor"]
}
```

Actual Moodle role import uses the read-only `core_enrol_get_enrolled_users`
function with active-user filtering and pagination. Enable it in the integration's
web-service function list and give the integration user permission to read course
participants/roles. The local helper enables this read-only function without
changing tokens or granting write functions:

```sh
docker cp Moodle/scripts/enable_enrolment_service.php moodle-webserver-1:/tmp/enable_enrolment_service.php
docker exec -u www-data moodle-webserver-1 php /tmp/enable_enrolment_service.php --service=Tutor
```

For a Moodle course representing a whole programme, choose activity modules,
Moodle course programmes, section/topic year labels and a user-profile current
year if enrolment covers all years at once.

Existing saved connections without options retain the legacy role mode. Choose
**Moodle course role shortnames** to distinguish lecturers. Missing permissions,
missing configured fields, invalid relationships or incomplete pages fail the
import and retain the last successful catalogue. Unknown/unmapped Moodle roles
are not granted Student or Lecturer membership.

## Adding another LMS

Implement `LMSProvider` in an installed Python package. Supply configuration
fields with types `text`, `integer`, `select`, `list`, or `json`, validate them in
`validate_options()`, and implement `build(base_url, api_key, mapping, options,
transport)` plus `fetch_catalog()`. Use the supplied HTTPS transport for external
requests and return canonical records rather than exposing vendor names to policy.
The credential field can hold the adapter's API key or access token.

Register the class using a package entry point:

```toml
[project.entry-points."tutorplatform.lms_providers"]
canvas = "institution_canvas.adapter:CanvasProvider"
```

Installed adapters are discovered when the service starts and appear in the admin
selector automatically. Duplicate adapter IDs are rejected. Tests and embedded
setups can instead pass `providers={"custom": CustomProvider}` to `create_app()`.
Moodle is the bundled production adapter; other vendors need their own adapter
implementation and real-service verification. A non-Moodle adapter integration
test exercises settings, canonical storage and tutoring eligibility without
Moodle records or changes to the import/storage/policy code.

## Rollout and verification

Rebuild the college service, LMS API, LMS worker and dashboard together. Run one
successful sync to populate the new explicit academic metadata. Existing IDs,
accounts, approved Tutor roles and old immutable catalogue versions are retained.
Mapping edits apply only after a successful import; they are never applied to an
older snapshot using a different set of rules.

```sh
docker compose up -d --build --no-deps college_svc lms_svc lms_worker dashboard_svc
```
