# Manual courses, modules and enrolments

College admins can create courses and modules from the college administration dashboard and assign active verified users from their college.

Each module belongs to a course and an academic year from 1-20. Names are required but codes are optional. A duplicate course name or code returns 409. Module names and codes must be unique within the same course and year.

Assigning a student to a course year gives them all modules in that year, including any added later. Saving the course assignments updates their year. Students can also be assigned to individual modueles.

Tutor assignments apply to individual modules and leave the account's global roles unchanged. Admins can remove assignments from the dashboard.

The college service stores these records in `manual_courses, manual_modules, manual_assignments` and `manual_directory_users`, seperately from LMS imports. The LMS service uses both sources when building student dashboards, checking tutor eligibility and finding tutors.

A college can use manual records without connecting and LMS. Manual enrolment does not bypass restrictions on suspended or ambiguous imported profiles

## API

To use the admin endpoints, the caller must have a users session, a valid `X-CSRFToken`, the `college_admin` role and ownership of the active college. Browser requests go through `/api/colleges` on the gateway.

- `GET /college/{college_id}/academic` - manual courses, modules and assignments.
- `POST /college/{college_id}/academic/courses {name, code?}`
- `POST /college/{college_id}/academic/modules {name, code?, course_id, year}`
- `POST /college/{college_id}/academic/assignments {user_id, target_type: "course"|"module", target_id, role: "student"|"tutor", year?}`
- `DELETE /college/{college_id}/academic/assignments/{assignment_id}`

The forms assign users who already have registered, verified college accounts. CSV uploads can also save pending assignments for people who have not registered yet. Neither method created login credentials.

## CSV uploads

The administrator page provides downloadable moudles and users CSV templates. These files use UTF-8, comma seperated values and a header row. Limit is 1MB of CSV content and 1,000 non empty data rows.

1. Upload modules first, new courses are created automatically. Codes identify records within the college, a module code is scope to its course and year. Repeating matching records reuses them. A conflicting name/code pair must be corrected.
2. Then upload users. Name and usernames are optional directory metadata. College domain emails are required when the college has a configured domain. Leave all assignment columns blank for directory entry only, A course code and year assign a student to that course year. Adding a module code assigns that specific modul as `student` or `tutor`. Repeat the user's email for additional assignments, with consistent profile fields. CSV uploads cannot grant administrator account roles.
3. Preview the file. Validation reports CSV line numbers and saves no records. Fix all errors, preview again, and choose Import. Apply revalidates the whole file against current records before writing. Invalid files save nothing.

Users who already have college accounts are linked straight away. People who have not registered are saved as directory entries, with pending assignments matched by email. They still need to register and verify their own college email.

On their first dashboard visit, the LMS service sends their verified identity to the college service so it can link those assignments. CSV uploads cannot set passwords, verify emials or change account-wide roles. The admin page shows directory entries seperartely from registered accounts.

`POST /college/{college_id}/academic/import/{modules|users}` accepts multipart fields file and dry_run(true for preview false for apply). It returns a summary, up to 25 preview rows, and up to 100 line errors with the total error count. Invalid rows return HTTP 422, malformed files return 400. The same session, CSRF, role and ownership checks apply as for the forms. Uploading the same file again reuses matching records. Records are written individually, so if the service stops durng an import, preview and rety the file to finish it.

The internal manual academic endpoint also accepts a service-token protected `POST` with `{user_id, email}` from the LMS service to resolve a verified user's directory entry and enrolments. Browsers cannot call this endpoint.
