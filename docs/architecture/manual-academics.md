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

The college service owns `manual_courses`, `manual_modules`,
`manual_assignments`, and `manual_directory_users`. These collections are independent of versioned LMS imports.
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

Manual enrolment does not create user accounts. Direct assignment selects
registered, verified college accounts; CSV uploads can also queue assignments for
directory users who register later.

## CSV uploads

The administrator page provides downloadable **modules** and **users** templates.
Files use UTF-8 (an optional BOM is accepted), comma-separated values and a header
row. Limits are 1 MB of CSV content and 1,000 non-empty data rows. The upload route
accepts a multipart request up to 2 MB; other gateway request limits are unchanged.

1. Upload modules first: `course_code,course_name,module_code,module_name,year`.
   New courses are created automatically. Codes identify records within the
   college; a module code is scoped to its course and year. Repeating matching
   records reuses them. A conflicting name/code pair must be corrected.
2. Upload users: `email,first_name,last_name,username,course_code,year,module_code,role`.
   Names and username are optional directory metadata. College-domain emails are
   required when the college has a configured domain. Leave all assignment
   columns blank for a directory entry only. A course code and year assign a
   student to that course year. Adding a module code assigns that specific module
   as `student` or `tutor`. Repeat the user's email for additional assignments, with
   consistent profile fields. CSV uploads cannot grant administrator account roles.
3. Preview the file. Validation reports CSV line numbers and saves no records.
   Fix all errors, preview again, and choose **Import**. Apply revalidates the whole
   file against current records before writing. Invalid files save nothing.

Existing registered college users are linked immediately. Unregistered people are
stored as directory records with pending email-based assignments; they register
normally and verify their own college email. On their first dashboard visit, the
LMS service forwards the verified identity to the college service, which links
their pending assignments. Passwords, email verification and account-wide roles
are never set by CSV uploads. Directory data is shown separately from registered
accounts on the administration page.

`POST /college/{college_id}/academic/import/{modules|users}` accepts multipart
fields `file` and `dry_run` (`true` for preview, `false` for apply). It returns the
summary, up to 25 preview rows, and up to 100 line errors with the total error count.
Invalid rows return HTTP 422; malformed files return 400. Session, CSRF, college
role and owner checks match manual record management. Re-uploading the same file
is idempotent. Database writes are per record; after a service interruption,
preview and retry to finish any records that were not saved.

The internal manual academic endpoint also accepts a service-token protected
`POST` with `{user_id, email}` from the LMS service to resolve a verified user's
directory entry and enrolments. Browsers cannot call this internal endpoint.
