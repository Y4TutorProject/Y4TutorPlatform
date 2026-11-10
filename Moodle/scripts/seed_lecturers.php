<?php
/** Populate development Moodle with one lecturer per module (Moodle course).
 * Existing single lecturer assignments are retained. Conflicts abort before writes.
 * Usage: php /tmp/seed_lecturers.php --domain=student.testcollege.ie
 */
define('CLI_SCRIPT', true);
require('/var/www/html/config.php');
require_once($CFG->libdir . '/clilib.php');
require_once($CFG->dirroot . '/user/lib.php');
[$options, $unrecognized] = cli_get_params(['domain' => 'student.testcollege.ie'], []);
$domain = $options['domain'];
if ($unrecognized || !preg_match('/^[a-z0-9.-]+\.[a-z]{2,}$/i', $domain)) {
    cli_error('Provide a valid --domain for development lecturer accounts.');
}
$role = $DB->get_record('role', ['shortname' => 'editingteacher'], '*', MUST_EXIST);
$teacherroles = $DB->get_records_list('role', 'shortname', ['editingteacher', 'teacher']);
$courses = $DB->get_records_select('course', 'id <> ?', [SITEID], 'id');
$assignments = [];
foreach ($courses as $course) {
    $context = context_course::instance($course->id);
    $teachers = get_role_users(array_keys($teacherroles), $context, true, 'u.id, u.suspended, u.deleted', 'u.id');
    $active = array_filter($teachers, fn($u) => !$u->suspended && !$u->deleted);
    if (count($active) > 1) {
        cli_error("Course {$course->id} has multiple lecturers. Resolve this assignment before seeding.");
    }
    $assignments[$course->id] = $active;
}
$plugin = enrol_get_plugin('manual');
$transaction = $DB->start_delegated_transaction();
$created = 0;
foreach ($courses as $course) {
    if ($assignments[$course->id]) {
        continue;
    }
    // Share one synthetic lecturer across each Moodle category's modules.
    $username = 'modulelecturer' . $course->category;
    $user = $DB->get_record('user', ['username' => $username, 'mnethostid' => $CFG->mnet_localhost_id]);
    if (!$user) {
        $user = (object)[
            'username' => $username, 'auth' => 'manual', 'confirmed' => 1,
            'mnethostid' => $CFG->mnet_localhost_id, 'firstname' => 'Module',
            'lastname' => 'Lecturer ' . $course->category, 'email' => $username . '@' . $domain,
            'password' => generate_password(32), 'lang' => 'en',
        ];
        $user->id = \core\user::create_user($user);
        $created++;
    }
    if ($user->suspended || $user->deleted) {
        cli_error("Seed account {$username} is inactive. Resolve this before seeding.");
    }
    $instance = $DB->get_record('enrol', ['courseid' => $course->id, 'enrol' => 'manual']);
    if (!$instance) {
        $id = $plugin->add_instance($course, ['status' => ENROL_INSTANCE_ENABLED]);
        $instance = $DB->get_record('enrol', ['id' => $id], '*', MUST_EXIST);
    }
    if ($instance->status != ENROL_INSTANCE_ENABLED) {
        cli_error("Manual enrolment is disabled for course {$course->id}.");
    }
    $plugin->enrol_user($instance, $user->id, $role->id, 0, 0, ENROL_USER_ACTIVE);
}
$transaction->allow_commit();
cli_writeln("Created {$created} development lecturers; checked " . count($courses) . ' module courses.');
