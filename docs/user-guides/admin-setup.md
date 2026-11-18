# College administrator setup

Use this guide to register a college, add its courses and modules, and connect its student records. Complete it before students and lecturers sign up.

## 1. Create an administrator account

1. Open the sign-up page and select **Register as an administrator**.
2. Enter your name, username, email address and password.
3. Open the verification email and select **Verify email**. Links work once and expire after one hour.
4. Sign in with your new account.

## 2. Register the college

1. Open the college registration page at `/register-college`.
2. Enter the college name and its **student domain**, such as `students.college.ie`.
3. Select **Register college**.

Enter the domain on its own, without `@` or a web address. Students must sign up with an email address that uses this domain.

## 3. Set up courses and modules

Choose one of the two methods below. You can use both.

### Connect Moodle

1. Open **College system connection** and select **Moodle**.
2. Enter the Moodle public HTTPS address and API key.
3. Configure **Academic structure and role mapping** so the courses, modules, years and lecturer roles match how your Moodle is organised.
4. Save the connection and run a sync. The platform refreshes the connection every night.

If a sync fails, the previous courses and modules stay in place. Check the runbook for [LMS sync problems](../operations/runbooks.md).

### Add courses and modules manually

1. Open **Create course** and enter the course details.
2. Open **Create module** and add the modules for that course.
3. Assign users who already have verified college accounts.

To add people who haven't registered yet, upload a CSV file. Each row adds a directory entry and an optional assignment. Use the college email domain for every row. Students who register and verify their email are linked to their assignments automatically. CSV uploads can't set passwords, verify emails or grant administrator access.

## 4. Check the imports

In the **Imported LMS data** section of the administrator dashboard, confirm that:

- every course and module appears,
- students are linked to the correct course year, and
- each module has one assigned lecturer.

Modules with no active lecturer have no reviewer for tutor applications. Moodle imports with more than one lecturer on a module fail until the extra lecturer is removed in Moodle.

## Tutor applications for manual modules

Manually created modules are reviewed by the college administrator, not by a lecturer. Open the **Manual module tutor applications** list on the administrator dashboard to approve or reject them.
