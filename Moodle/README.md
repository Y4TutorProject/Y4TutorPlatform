# Local Moodle HTTPS

Start the stack from the repository root:

```sh
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml up -d --build
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml exec -T -w /var/www/html webserver composer install --no-dev --classmap-authoritative --no-interaction
```

Open https://moodle.tutor.localhost. Caddy redirects HTTP to HTTPS and
proxies requests to Moodle's Apache container. The hostname comes from
`MOODLE_DOCKER_WEB_HOST` in `.env`; it is also a Caddy alias on the external
`testcollege` network. Create that network with `docker network create testcollege`
if it does not exist.

Caddy uses its local certificate authority, persisted in the `caddy_data` volume.
Export its public root certificate:

```sh
`docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml cp caddy:/data/caddy/pki/authorities/local/root.crt Moodle/caddy/root.crt`
```

Import `caddy/root.crt` into your browser or operating system's trusted certificate
store to trust this local HTTPS endpoint. Other containers calling the endpoint
also need this root certificate in their trust store.

## Connect the tutor platform in development

Set `DEV_MODE=true` in the repository root `.env`. The server then permits private
addresses for the exact hostnames in `LMS_PRIVATE_HOSTS` (default:
`moodle.tutor.localhost`). HTTPS on port 443 and certificate verification remain
required. Loopback, link-local and metadata addresses remain blocked.
`DEV_MODE=false` (the default) ignores these exceptions and the development CA.
`LMS_ALLOWED_HOSTS`, when set, still restricts which hostnames can be used.

After exporting Caddy's root certificate as above, start the LMS containers with
the development networking and certificate mounts:

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build lms_svc lms_worker
```

Use `https://moodle.tutor.localhost` as the Moodle base URL in your account.
Recreate the LMS containers after changing `DEV_MODE`. Use the base Compose file
alone in deployment; the development override is only for the local Moodle stack.

The `moodle/` directory contains the Moodle application. Apache serves its `public/`
directory. Application settings belong in `moodle/config.php`, not
`moodle/public/config.php` (which is Moodle's configuration loader). The current
configuration reads database credentials and the hostname from the container
environment populated by `.env`, and sets:

```php
$CFG->wwwroot = 'https://' . getenv('MOODLE_DOCKER_WEB_HOST');
$CFG->sslproxy = true;
$CFG->routerconfigured = true;
```

Moodle's writable files persist in the `moodle_data` Docker volume at
`/var/www/moodledata`, outside the document root. Complete installation at
https://moodle.tutor.localhost/admin/index.php. Apache's direct HTTP port 8585
remains available for debugging.

Composer is included in the local webserver image. Run the Composer command again
after replacing or updating Moodle's source. Dependencies persist in `moodle/vendor`.
Apache's base image routes missing paths to `/r.php` using `FallbackResource`;
`routerconfigured` tells Moodle that this server configuration is enabled.

MariaDB uses the 11.4 series, with `MARIADB_AUTO_UPGRADE` enabled for existing data
directories. A database backup taken before the 10.11 upgrade is stored locally in
`backups/before-mariadb114.sql` and excluded from Git. PHP overrides are in
`php/moodle.ini`; rebuild the webserver image after changing them.

## Demo departments, courses, and students

`scripts/seed_demo.php` uses Moodle's APIs to create this hierarchy:

```text
Computing & Informatics                    Department category
  DevOps                                  Academic course category
    Y1                                    Year subcategory
      Linux Systems Administration        Moodle course (academic module)
      Scripting and Automation            Moodle course (academic module)
      ... seven further module courses
  Data Analytics
    Y1
      Programming for Data Analysis
      ... eight further module courses
```

The curriculum in `scripts/curriculum.json` supplies realistic names for five
departments, twenty academic courses per department, and nine modules per academic
course. Each academic course currently has one year (`Y1`): 100 academic course
categories, 100 year categories, and 900 separate Moodle module courses in total.
Modules have their own content areas and gradebooks; teaching activities are not
populated. Department core modules are reused across its academic courses, with
specialised module titles for DevOps and Data Analytics.

There are 100 synthetic students (`student001` through `student100`), twenty per
department. Each student belongs to one academic course and its `Y1`, and is
enrolled through cohort sync with the Student role in exactly its nine academic modules (900
enrolments total). With 100 students and 100 academic courses, this assigns one
student per academic course. `student001` takes DevOps, `student002` takes Data
Analytics, and so on in curriculum order; `student021` starts the next department.

There is one category-scoped cohort for each academic course and year in the
2026/27 academic session, for example `DevOps - Y1 - 2026/27`. The cohort lives in
the Y1 category context and is linked through Cohort sync to all nine module
courses. Add or remove registered students using the cohort's Assign members
screen; Moodle automatically updates those nine enrolments. The current demo
therefore has 100 cohorts, 100 cohort memberships, and 900 cohort sync methods.
Manual enrolments for the demo students are removed so they cannot bypass cohort
membership. The existing category hierarchy and student passwords are preserved.

```sh
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml cp Moodle/scripts/seed_demo.php webserver:/tmp/seed_demo.php
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml cp Moodle/scripts/curriculum.json webserver:/tmp/curriculum.json
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml cp Moodle/scripts/student_enrolments.php webserver:/tmp/student_enrolments.php
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml exec -T --user www-data webserver php /tmp/seed_demo.php
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml cp webserver:/var/www/moodledata/demo-students.csv Moodle/seed-output/students.csv
```

The CSV contains individual random passwords and must stay private; `seed-output/`
is excluded from Git. Accounts use reserved example email addresses and have
email delivery disabled. Existing admin accounts and unrelated courses are
preserved. The script recognises its own records by ID number, reuses existing
students without resetting their passwords, and updates their department names.
Rerunning does not create duplicate categories, module courses, or enrolments.
The original empty demo courses are migrated into the first academic module
of each programme; migration refuses to remove edited sections or activities.
The pre-migration database backup is `backups/before-academic-restructure.sql`.

Only newly created users are exported. If adding missing users while a credentials
file already exists, pass a new absolute output filename as the script argument.
When all students already exist, the existing credentials file is retained.

To repair enrolments without rebuilding the curriculum:

```sh
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml cp Moodle/scripts/student_enrolments.php webserver:/tmp/student_enrolments.php
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml cp Moodle/scripts/fix_student_enrolments.php webserver:/tmp/fix_student_enrolments.php
docker compose --env-file Moodle/.env -f Moodle/moodle-docker-compose.yml exec -T --user www-data webserver php /tmp/fix_student_enrolments.php
```

The enrolment sync creates/reuses the demo cohorts and module sync methods,
restores the seeded one-programme-per-student cohort membership, removes redundant
manual enrolments in seeded modules, and leaves unrelated courses and non-demo
users alone. It also runs at the end of the full seed. Rerunning the seed or repair
restores the demo assignment, so manage ongoing registrations through cohort
membership rather than rerunning the seed. Passwords are not changed.
Pre-conversion backup: `backups/before-cohort-sync.sql`.
