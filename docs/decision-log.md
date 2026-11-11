# Decision log

Retrospective entries based on Nathan’s work. Rationale and alternatives are reconstructed for review.

## 001 — Require verified, college-aware registration

- **Date:** 2026-11-02
- **Status:** Implemented

**Decision:** Keep signup in the registration service and login/session management in the users service. Require email verification before sign-in; students select an active college and use its configured student email domain.

**Rationale:** Separate account creation from authentication and establish a verified college identity before granting access.

**Alternatives:**

- **Combined registration and authentication service:** fewer service boundaries, but couples signup changes to login and session handling.
- **College single sign-on:** delegates identity verification to the institution, but requires integration with each supported identity provider.

**Consequences:** Registration needs email delivery and a verification flow. College administrator onboarding includes registering and linking a college after verification.

## 002 — Import LMS data through a separate service and worker

- **Date:** 2026-11-02
- **Status:** Implemented

**Decision:** Use a dedicated LMS service, database and background worker for Moodle imports. Schedule synchronization, retain the last successful import after failure, and store connection credentials encrypted.

**Rationale:** Isolate LMS failures and avoid requiring live Moodle availability for every page request.

**Alternatives:**

- **Fetch Moodle data on each request:** fresher data, but page availability and response time depend on Moodle.
- **Run imports within the web service:** simpler deployment, but long-running imports share resources with user requests.

**Consequences:** Imported data can lag behind the source. Deployment must manage another service, worker, database and encryption key.

## 003 — Enforce privileged settings access on the server

- **Date:** 2026-11-03
- **Status:** Implemented

**Decision:** Verify the account session on the server and conditionally render college management settings using verified role and college information. Enforce authorization at the API boundary as well.

**Rationale:** Hiding a form in HTML or JavaScript does not prevent a visitor from inspecting it or calling its endpoints.

**Alternatives:**

- **API authorization with client-rendered settings:** protects operations, but sends the generic settings interface to the browser.
- **Centralize authorization in the gateway:** reduces repeated checks, but the gateway needs resource and college-ownership context.

**Consequences:** Unauthorized responses omit privileged settings. Authentication-service failures require an explicit failure response rather than trusting browser-supplied identity.

## 004 — Move authenticated account and dashboard pages into the dashboard service

- **Date:** 2026-11-09
- **Status:** Implemented

**Decision:** Move account, preferences and authenticated dashboard rendering out of the users frontend into the dashboard service. Keep the users frontend focused on sign-in.

**Rationale:** Group authenticated application pages in one frontend service instead of spreading account and dashboard rendering across separate services.

**Alternatives:**

- **Keep account pages in the users frontend:** avoids moving routes, but splits authenticated application pages between services.
- **Combine all frontend pages into one service:** simplifies routing and shared assets, but deploys sign-in and dashboard changes together.

**Consequences:** Gateway routes and authenticated service calls must support the dashboard service. Shared frontend assets need to remain consistent across services.

## 005 — Store editable learning and teaching preference scores

- **Date:** 2026-11-09
- **Status:** Implemented

**Decision:** Store numeric ratings from 0 to 10 for visual, auditory, reading/writing and kinesthetic preferences. Collect them during onboarding and allow later edits through the account flow.

**Rationale:** Represent preferences consistently as structured values that the application can display and use, while allowing users to revise their ratings.

**Alternatives:**

- **Free-text preferences:** more expressive, but harder to validate and compare consistently.
- **One preferred category per user:** simpler input, but cannot represent mixed preferences or their relative strength.

**Consequences:** The server validates the complete set of scores and tracks onboarding completion. These are self-reported preferences, not a measured assessment of ability.

## 006 — Require module-specific tutor eligibility and approval

- **Date:** 2026-11-09; updated 2026-11-10
- **Status:** Implemented

**Decision:** Allow eligible students to apply for earlier-year modules in their programme, with no eligibility granted when year information is unknown. Require approval before granting module tutor membership. The later lecturer change assigns imported-module reviews to the module’s lecturer; administrators retain review access for manually managed modules.

**Rationale:** Keep applications tied to academic progression and module-level review instead of granting tutor access simply because an application was submitted.

**Alternatives:**

- **Let students self-select tutor modules:** reduces review work, but removes academic progression and approval checks.
- **Have administrators review every application:** centralizes oversight, but increases their workload and removes module lecturers from the review process.

**Consequences:** Eligibility and reviewer permissions must be rechecked on the server. Missing or ambiguous academic and lecturer data can prevent an application or review until the source data is corrected.

## 007 — Isolate LMS-specific mappings behind provider interfaces

- **Date:** 2026-11-09
- **Status:** Implemented

**Decision:** Use provider, mapper, transport and storage interfaces around a canonical academic catalogue. Keep Moodle hierarchy and role mapping configurable rather than embedding Moodle category assumptions in tutoring policy.

**Rationale:** Allow institutions with different LMS layouts to supply the same academic concepts without rewriting the core tutoring rules.

**Alternatives:**

- **Hard-code one Moodle structure:** quicker for the initial institution, but requires code changes for different hierarchies.
- **Add provider-specific branches throughout the application:** supports more systems initially, but spreads integration logic across tutoring and dashboard code.

**Consequences:** Adapters must supply explicit programme relationships and academic years. Provider settings require validation, and each installed adapter needs mapping tests.

## 008 — Support manual academic records alongside LMS imports

- **Date:** 2026-11-10
- **Status:** Implemented

**Decision:** Allow college administrators to create courses and modules and manage enrolments through forms. Store manual records separately from imported snapshots and combine them when building student academic views and tutor lookup.

**Rationale:** Let a college manage academic data without an LMS connection and retain manually entered records across LMS synchronization.

**Alternatives:**

- **Require an LMS integration for every college:** gives one source of academic records, but blocks colleges without a supported LMS.
- **Edit imported snapshots directly:** uses fewer record types, but changes may be overwritten during synchronization.

**Consequences:** Both data sources need college-scoped permissions and consistent relationships. Manual enrolment selects existing registered users rather than creating credentials.

## 009 — Preview and validate CSV imports before applying them

- **Date:** 2026-11-10
- **Status:** Implemented

**Decision:** Provide module and user CSV templates, require preview before import in the UI, and revalidate files on apply. Treat unregistered people as directory records with pending assignments rather than creating login credentials.

**Rationale:** Support bulk onboarding while exposing row errors before users apply changes and keeping account verification separate from directory imports.

**Alternatives:**

- **Use forms for every record:** keeps validation local to individual edits, but makes bulk onboarding slow.
- **Import valid rows immediately and report failures afterwards:** allows partial progress, but makes the result harder to review and recover from.

**Consequences:** Imports need file/row limits, line-numbered errors and repeat-safe record matching. Pending assignments link after verified registration; interrupted per-record writes may require a preview and retry.

## 010 — Share the lilac visual theme across application pages

- **Date:** 2026-11-10
- **Status:** Implemented

**Decision:** Use shared navigation and stylesheet rules to carry the neutral/lilac design across dashboards, profiles and messaging, while retaining layouts suited to each page.

**Rationale:** Keep the application visually consistent as users move between account, academic and messaging tasks.

**Alternatives:**

- **Style each page independently:** allows local design freedom, but increases duplication and visual inconsistency.
- **Use Bootstrap defaults throughout:** reduces custom styling, but provides less control over the platform’s appearance.

**Consequences:** Changes to shared styles can affect several roles and pages, so visual checks should cover each major screen.
