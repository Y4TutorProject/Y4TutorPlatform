# Dashboard

The dashboard serves as the frontend of the entire application (except login functionality). It connects to all the backend services, providing users with a unified interface to manage their academic/teaching/administrative activities depending on their role within the platform.

## Folder Structure

`app.py` - contains the main flask app, it builds the application configuration, templates and registeres the routes for the dashboard.
`users_client` - contains functionality for interacting with the user service, such as ensuring authentication and cookie forwarding between the dashboard and the user service.
`messaging_client` - contains functionality for interacting with the messaging service, such building requests to the service and forwarding cookies
`clean_text.py` - contains utility functions for cleaning and processing text data within the dashboard.

Templates - contains the HTML templates used by the dashboard for rendering the user interface.

## Templates

Files starting with `_` are partials that are included by other templates. They are not rendered on their own.

### Base layouts

- `dashboard_base.html` - signed-in layout. It extends the shared `base.html` and adds the navigation bar (Dashboard, Messages, My account, role switcher, Sign out) and the content area that child pages fill via `dashboard_content`.

### Pages

- `student_dashboard.html` - student home ("Find your tutor"): the module list, the tutor results area, and the "Apply to be a tutor" panel with module search.
- `tutor_dashboard.html` - tutor home: welcome message and the learning and teaching preference summaries.
- `admin_dashboard.html` - college admin home: academic management, CSV upload, LMS connection settings, imported LMS data and the pending tutor applications review list.
- `account.html` - account details (username, email) and links to set up or edit learning preferences, plus teaching preferences for tutors.
- `preferences.html` - one form for learning or teaching preference ratings (0-10 for each of the four styles). The `type` query value selects which kind it edits.
- `choose_username.html` - first-time username selection form.
- `messaging.html` - messaging page extending `dashboard_base.html`: chat list sidebar, conversation area, and message input. It opens a chat on load when `openChat` is set.
- `choose_role.html` - prompt shown when the user must pick a role from the navigation. No route renders it at the moment.
- `chatsPage.html` - earlier standalone messaging page that extends `base.html` and duplicates `messaging.html`. No route renders it at the moment.

### Partials

- `_preferences_summary.html` - read-only list of a user's learning or teaching scores with an edit link. Used by `tutor_dashboard.html`.
- `_academic_management.html` - admin forms to create courses and modules and assign users, with lists of existing courses, modules, assignments and the CSV directory.
- `_csv_upload.html` - admin CSV upload forms for modules and users, with a preview table.
- `_lms_settings.html` - admin form to save the college's LMS connection and run a sync.
- `_lms_imported_data.html` - admin table of the data imported from the LMS.

## Routes

Routes live in `routes/`, one Flask blueprint per concern. `routes/__init__.py` registers them all on the app. Every page route uses `@login_required` from `users_client.py`, which redirects signed-out visitors to `/login`.

- `auth.py` - onboarding step `/choose-username`.
- `account.py` - `/account` and `/preferences` (`?type=learning` or `?type=teaching`). Also holds `can_manage_college`, the check for admins who have a college.
- `dashboard.py` - `/dashboard` entry point. It sends users with no username to `/choose-username` and tutors without teaching preferences to `/preferences?type=teaching`, then renders the tutor, student or admin view by role, or redirects to `/account` if none apply. Also `/admin-dashboard` (college admins only) and a temporary `/check-user` debug route that returns the user's role fields.
- `student.py` - student view (loads the student's modules from the LMS service) and `/get_tutors`, which returns tutor profiles for a module.
- `tutor.py` - tutor view, plus `is_tutor` and `needs_teaching_preferences`. It defines no routes; `dashboard.py` and `account.py` call it.
- `admin.py` - college admin view. It defines no routes; `dashboard.py` calls it.
- `messaging.py` - `/messages` (chat list) and `/getmessages` (opens or creates a chat with another user).

All javascript are stored in [frontend_shared/static/js](https://github.com/Y4TutorProject/Y4TutorPlatform/tree/main/frontend_shared/static/js).
