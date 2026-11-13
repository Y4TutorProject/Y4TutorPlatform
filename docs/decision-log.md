# Decision log

These entries record implemented decisions. Reasons and alternatives were written up afterwards.

## 001 - Registration and email verification

**Date:** 2026-11-02

**Decision:** Keep signup in the registration service and login in the users service. Students select a college and verify an email matching its student domain.

**Why:** This checks access to the college email address before allowing sign-in.

**Other options:** Combine signup and login in one service, or use college single sign-on.

**Trade-off:** Registration depends on email delivery. College single sign-on would require a connection to each institution.

## 002 - Run Moodle imports in the background

**Date:** 2026-11-02

**Decision:** Use a separate LMS service, worker and database. Import on a schedule, encrypt saved API keys and keep the last successful import after a failure.

**Why:** Dashboard requests can use saved data when Moodle is slow or unavailable.

**Other options:** Fetch Moodle data on each page request, or run imports inside the web service.

**Trade-off:** Data can be out of date between syncs. The worker, database and encryption key need maintaining.

## 003 - Check permissions before rendering settings

**Date:** 2026-11-03

**Decision:** Check the session, role and college on the server before rendering college settings. Check permissions again at the API.

**Why:** Hiding a form with CSS or JavaScript leaves its contents in the page source.

**Other options:** Render all settings and rely on API checks, or put permission checks in the gateway.

**Trade-off:** Rendering depends on a successful session check. Gateway checks would also need college ownership information.

## 004 - Move account pages into the dashboard service

**Date:** 2026-11-09

**Decision:** Move account and preference pages to the dashboard service. Keep sign-in in the users frontend.

**Why:** Account pages share navigation and user flows with the dashboard.

**Other options:** Keep account pages in the users frontend, or combine all frontend pages in one service.

**Trade-off:** Gateway routes need updating, and the frontends need shared styles and scripts.

## 005 - Use scores for learning and teaching preferences

**Date:** 2026-11-09

**Decision:** Store visual, auditory, reading/writing and kinesthetic ratings from 0 to 10. Collect them during setup and allow edits from the account page.

**Why:** Scores give users a consistent way to express a mixture of preferences.

**Other options:** Use free text, or ask users to choose one category.

**Trade-off:** The server must validate every score. These ratings describe self-reported preferences.

## 006 - Check tutor eligibility for each module

**Date:** 2026-11-09; updated 2026-11-10

**Decision:** Let students apply for earlier-year modules in their programme. Lecturers review imported modules; college admins review manually managed modules. Approval grants module tutor membership.

**Why:** Tutor access needs a module-specific eligibility check and review.

**Other options:** Allow self-selection, or send all applications to college admins.

**Trade-off:** Missing year or lecturer information can block applications. Eligibility and reviewer permissions need checking again on approval.

## 007 - Keep Moodle mapping separate from tutoring rules

**Date:** 2026-11-09

**Decision:** Use provider and mapper interfaces to produce common academic records. Make Moodle hierarchy and role settings configurable.

**Why:** Colleges organise Moodle differently. Tutoring rules can use programme and year fields supplied by the mapper.

**Other options:** Assume one Moodle layout, or add LMS-specific checks throughout the application.

**Trade-off:** Each adapter needs mapping tests and must supply the fields used by eligibility checks.

## 008 - Allow colleges to enter academic records manually

**Date:** 2026-11-10

**Decision:** Add admin forms for courses, modules and enrolments. Store manual records separately from imports and use both sources for dashboards and tutor lookup.

**Why:** Colleges can manage records without an LMS connection, and manual entries survive later syncs.

**Other options:** Require an LMS connection, or allow direct edits to imported snapshots.

**Trade-off:** Both sources need college ownership checks and consistent relationships. Manual enrolment uses registered accounts.

## 009 - Preview CSV files before importing

**Date:** 2026-11-10

**Decision:** Provide module and user templates, preview files before import and validate again on apply. Save unregistered people as directory entries with pending assignments.

**Why:** Admins can check bulk records before saving them. Users still register and verify their own accounts.

**Other options:** Use forms for every record, or import valid rows immediately and report errors afterwards.

**Trade-off:** The importer needs file limits, line errors and duplicate handling. Interrupted writes may require a preview and retry.

## 010 - Use the same theme across pages

**Date:** 2026-11-10

**Decision:** Use shared navigation and neutral/lilac styles across dashboards, profiles and messaging.

**Why:** Shared styles keep navigation and controls consistent between pages.

**Other options:** Style each page separately, or keep the default Bootstrap appearance.

**Trade-off:** Shared CSS changes need checking across roles and screens.

## 011 - Integrate tutor matching through the dashboard

**Date:** 2026-11-13

**Decision:** Build vectors in the dashboard using sorted preference keys, defaulting missing values to 0. Send them to the matching system using a POST request, then look up scores by tutor ID and sort tutors by similarity.

**Why:** The matching service stays independent. Sorted keys align vector dimensions, and an ID lookup avoids a nested search.

**Other options:** Send preference dictionaries to the matcher, or merge scores using a nested loop.

**Trade-off:** New keys can shift vector positions, so vectors must be rebuilt together for each request. Tutors without a score need explicit handling.

## 012 - Use sliders for preference scores

**Date:** 2026-11-13

**Decision:** Use sliders instead of numeric input boxes to collect learning and teaching preference scores from 0 to 10.

**Why:** Sliders make the available score range visible while users adjust their preferences.

**Other options:** Keep numeric input boxes.

**Trade-off:** Sliders still need a visible value and server-side validation of submitted scores.

