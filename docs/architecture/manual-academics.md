# Manual courses, modules and enrolments

College administrators open **College administration** (`/admin-dashboard`) to create
courses and modules and assign existing active, verified users from their college.
Each module belongs to a course and academic year (1–20). Names are required; codes
are optional. Duplicate course codes/names and duplicate module codes/names within
the same course year return 409.

Assigning a student to a course year includes every module in that year, including
modules created later. Saving that course assignment again updates the student's
year. Students can also be assigned to individual modules. Tutor assignments apply
to individual modules and are module memberships; they do not change account-wide
roles. Assignments can be removed from the dashboard.

The college service owns `manual_courses`, `manual_modules`, and
`manual_assignments`. These collections are independent of versioned LMS imports.
The LMS service combines manual enrolments with imported enrolments when building
the student's dashboard, eligible tutor applications, and tutor lookup. A college
can use manual records without configuring an LMS. Existing imported suspended or
ambiguous profiles cannot be bypassed through manual enrolment.

## API

All administrator academic endpoints require the users session, a valid
`X-CSRFToken`, the `college_admin` role, and ownership of the active college.
Browser requests use the gateway prefix `/api/colleges`.

- `GET /college/{college_id}/academic`: manual courses, modules and assignments.
- `POST /college/{college_id}/academic/courses`: `{name, code?}`.
- `POST /college/{college_id}/academic/modules`: `{name, code?, course_id, year}`.
- `POST /college/{college_id}/academic/assignments`:
  `{user_id, target_type: "course"|"module", target_id, role: "student"|"tutor", year?}`.
  Course assignments require `role: "student"` and a year.
- `DELETE /college/{college_id}/academic/assignments/{assignment_id}`: remove an assignment.
- Users service `GET /college/{college_id}/users`: college-scoped administrator
  directory with IDs, usernames, emails and roles; no credentials.
- Internal `GET /internal/college/{college_id}/manual-academic`: service-token
  protected academic records used by the LMS service. This route is not exposed by
  the gateway.

Manual enrolment does not create user accounts. Users register and verify their
college account before an administrator assigns them.
