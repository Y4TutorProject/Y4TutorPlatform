# LMS adapters and academic mapping

Adapters convert LMS records into a common course, module and enrolment format. Tutoring rules use `programme_id` and numeric `year` fields supplied by the mapper.

## Contracts and dependency injection

| Interface | Responsibility |
| --- | --- |
| `LMSProvider` | Describe settings, validate options and fetch a catalogue |
| `LMSCatalogMapper` | Convert external records into platform records |
| `LMSHTTPTransport` | Check HTTPS, certificates, DNS and allowed addresses |
| `LMSImportStore` | Save catalogue references and enrolments |
| `AcademicCatalogClient` | Read and write academic records through the college API |
| `ConnectionStore` | Save encrypted credentials, settings and sync locks |
| `ModuleParticipationStore` | Save module memberships and tutor applications |
| `LMSAuthenticationClient` | Check users-service sessions and CSRF tokens |

`lms_svc.create_app()` accepts replacements for these dependencies. The default implementations use MongoDB and HTTP.

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

Source IDs are scoped to the college, provider and URL. The college service converts course and module relationships to stable UUIDs. `course_id` identifies the immediate parent; `programme_id` identifies the programme across year or semester categories.

Years are integers from 1 to 20, or null. Missing years grant no tutor eligibility. A user's `current_year` can override the highest enrolled year; an explicit null means unknown.

Enrolments can target courses or modules. Course enrolments expand to their modules. Imported roles are `student` and `lecturer`; tutor approval happens in the platform. Imported roles do not grant global administrator access.

## Moodle admin settings

Open **College system connection → Academic structure and role mapping**. `GET /api/lms/providers` supplies the form fields. Settings are checked on the server and saved as `provider_options` for manual and nightly syncs.

| Setting | Values |
| --- | --- |
| Platform module | Moodle course or activity |
| Platform course/programme | Category depth, course/custom field, or Moodle course for activity modules |
| Programme category depth | 1 for root, 2 for child, and so on |
| Programme field | Custom field shortname, `fullname`, `shortname` or `idnumber` |
| Department category depth | Optional; 0 disables it |
| Academic year source | Category label/depth, course field, activity section/topic, or unavailable |
| Year field | Course/custom field shortname |
| Year label map | Labels mapped to numbers, such as `{"Foundation":1,"Final":3}` |
| Student current year | Highest enrolled year or user profile field |
| Current year profile field | Profile field shortname |
| Module role source | Legacy enrolments or Moodle course role shortnames |
| Student roles | Default: `student` |
| Lecturer roles | Defaults: `editingteacher`, `teacher` |

Default category depths follow department → programme → year: programme depth 2 and department depth 1. Year labels include `Y1`, `Year 1`, `Stage 1` and numeric labels through 20. Admins can replace these mappings.

For courses with `degree` and `level` fields:

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

Course-role imports use `core_enrol_get_enrolled_users` with pagination and active-user filtering. Enable it for the integration user:

```sh
docker cp Moodle/scripts/enable_enrolment_service.php moodle-webserver-1:/tmp/enable_enrolment_service.php
docker exec -u www-data moodle-webserver-1 php /tmp/enable_enrolment_service.php --service=Tutor
```

When a Moodle course covers a whole programme, use activity modules, Moodle course programmes and section/topic year labels. Use a profile field for the student's current year if enrolment covers all years.

Saved connections without mapping options keep legacy role handling. Select **Moodle course role shortnames** to import lecturers. Missing fields, permissions or incomplete pages fail the import and keep the previous catalogue. Unmapped roles grant no membership.

## Adding another LMS

Implement `LMSProvider` in a Python package. Describe settings using `text`, `integer`, `select`, `list` or `json` fields, validate them in `validate_options()`, and implement `build(base_url, api_key, mapping, options, transport)` and `fetch_catalog()`.

Use the supplied HTTPS transport and return records in the common format. Register the class with a package entry point:

```toml
[project.entry-points."tutorplatform.lms_providers"]
canvas = "institution_canvas.adapter:CanvasProvider"
```

Installed adapters appear in the admin selector after a service restart. Duplicate IDs are rejected. Tests can pass `providers={"custom": CustomProvider}` directly to `create_app()`.

## Rollout and verification

Rebuild the services together, then run a sync to apply mapping changes:

```sh
docker compose up -d --build --no-deps college_svc lms_svc lms_worker dashboard_svc
```

Check programme IDs, years and roles in the new import. Existing IDs, approved tutor roles and older catalogue versions are kept. Mapping changes take effect after a successful import.
