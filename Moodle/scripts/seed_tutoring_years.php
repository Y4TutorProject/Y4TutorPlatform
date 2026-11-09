<?php
// Add isolated tutoring test accounts for Y1-Y4 in two existing programmes.
define('CLI_SCRIPT', true);
ini_set('memory_limit', '1024M');
require('/var/www/html/config.php');
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->libdir . '/enrollib.php');
\core\session\manager::set_user(get_admin());
set_time_limit(0);
umask(0077);

$output = $argv[1] ?? '/var/www/moodledata/tutoring-years.csv';
$curriculum = json_decode(file_get_contents(__DIR__ . '/curriculum.json'), true, 512, JSON_THROW_ON_ERROR);
$programmes = [['number' => 1, 'slug' => 'devops'], ['number' => 2, 'slug' => 'analytics']];
$credentials = [];
if (file_exists($output)) {
    $file = fopen($output, 'r');
    $header = fgetcsv($file, 0, ',', '"', '');
    if ($header !== ['username', 'password', 'email', 'programme', 'year']) {
        throw new RuntimeException('Unexpected credentials file format.');
    }
    while (($row = fgetcsv($file, 0, ',', '"', '')) !== false) {
        $credentials[$row[0]] = array_combine($header, $row);
    }
    fclose($file);
}
// Validate existing programmes and account ownership before creating anything.
foreach ($programmes as $programme) {
    $base = sprintf('DEPT01-COURSE%02d', $programme['number']);
    $DB->get_record('course_categories', ['idnumber' => 'tutor-demo-academic-' . $base], '*', MUST_EXIST);
    for ($year = 1; $year <= 4; $year++) {
        $username = 'tutor_test_' . $programme['slug'] . '_y' . $year;
        $user = $DB->get_record('user', ['username' => $username, 'mnethostid' => $CFG->mnet_localhost_id]);
        if ($user && ($user->deleted || $user->idnumber !== 'tutor-years-' . $username)) {
            throw new RuntimeException('Account name belongs to another user: ' . $username);
        }
        if ($user && !isset($credentials[$username])) {
            throw new RuntimeException('Existing test account credentials are missing; passwords will not be reset.');
        }
        $email = $username . '@student.testcollege.ie';
        $emailuser = $DB->get_record('user', ['email' => $email, 'deleted' => 0]);
        if ($emailuser && (!$user || $emailuser->id != $user->id)) {
            throw new RuntimeException('Test email belongs to another user: ' . $email);
        }
    }
}
$transaction = $DB->start_delegated_transaction();
$manual = enrol_get_plugin('manual');
$studentrole = $DB->get_record('role', ['shortname' => 'student'], '*', MUST_EXIST);
$rows = [];
foreach ($programmes as $programme) {
    $base = sprintf('DEPT01-COURSE%02d', $programme['number']);
    $academic = $DB->get_record('course_categories', ['idnumber' => 'tutor-demo-academic-' . $base], '*', MUST_EXIST);
    $name = $curriculum[0]['courses'][$programme['number'] - 1];
    $titles = $curriculum[0]['overrides'][$name] ?? $curriculum[0]['modules'];
    for ($yearnumber = 1; $yearnumber <= 4; $yearnumber++) {
        $yearidnumber = 'tutor-demo-year-' . $base . '-Y' . $yearnumber;
        $year = $DB->get_record('course_categories', ['idnumber' => $yearidnumber]);
        if (!$year) {
            $year = core_course_category::create((object)[
                'name' => 'Y' . $yearnumber, 'parent' => $academic->id,
                'idnumber' => $yearidnumber, 'visible' => 1,
            ]);
        } elseif ($year->parent != $academic->id || $year->name !== 'Y' . $yearnumber) {
            throw new RuntimeException('Unexpected existing year category; refusing to move it.');
        }
        $username = 'tutor_test_' . $programme['slug'] . '_y' . $yearnumber;
        $email = $username . '@student.testcollege.ie';
        $user = $DB->get_record('user', ['username' => $username, 'mnethostid' => $CFG->mnet_localhost_id]);
        if (!$user) {
            $password = $credentials[$username]['password'] ?? 'Aa1!' . bin2hex(random_bytes(12));
            $userid = \core\user::create_user((object)[
                'auth' => 'manual', 'confirmed' => 1, 'mnethostid' => $CFG->mnet_localhost_id,
                'username' => $username, 'password' => $password, 'idnumber' => 'tutor-years-' . $username,
                'firstname' => 'Test', 'lastname' => $name . ' Y' . $yearnumber,
                'email' => $email, 'emailstop' => 1, 'institution' => 'Test College',
                'department' => $curriculum[0]['name'], 'country' => 'IE', 'timezone' => 'Europe/Dublin',
            ]);
            $user = $DB->get_record('user', ['id' => $userid], '*', MUST_EXIST);
        } else {
            $password = $credentials[$username]['password'];
            if ($user->email !== $email) {
                throw new RuntimeException('Existing test account email has changed; refusing to overwrite it.');
            }
        }
        foreach ($titles as $offset => $title) {
            $shortname = $base . sprintf('-Y%d-M%02d', $yearnumber, $offset + 1);
            $idnumber = 'tutor-demo-module-' . $shortname;
            $course = $DB->get_record('course', ['idnumber' => $idnumber]);
            if (!$course) {
                if ($DB->record_exists('course', ['shortname' => $shortname])) {
                    throw new RuntimeException('Course shortname already in use: ' . $shortname);
                }
                $course = create_course((object)[
                    'category' => $year->id, 'fullname' => $title . ' (Y' . $yearnumber . ')',
                    'shortname' => $shortname, 'idnumber' => $idnumber, 'format' => 'topics',
                    'visible' => 1, 'numsections' => 0, 'newsitems' => 0,
                    'startdate' => strtotime('today'), 'enddate' => 0,
                    'summary' => 'Tutoring eligibility test module for ' . $name . ', Y' . $yearnumber,
                    'summaryformat' => FORMAT_HTML,
                ]);
            } elseif ($course->category != $year->id) {
                throw new RuntimeException('Existing module belongs to a different year: ' . $shortname);
            }
            $instance = $DB->get_record('enrol', ['courseid' => $course->id, 'enrol' => 'manual']);
            if (!$instance) {
                $instanceid = $manual->add_instance($course, ['status' => ENROL_INSTANCE_ENABLED]);
                $instance = $DB->get_record('enrol', ['id' => $instanceid], '*', MUST_EXIST);
            }
            $manual->enrol_user($instance, $user->id, $studentrole->id);
        }
        $rows[] = [$username, $password, $email, $name, 'Y' . $yearnumber];
        echo $username . ' -> ' . $name . ' Y' . $yearnumber . ': 9 Student module enrolments' . PHP_EOL;
    }
}
if (!file_exists($output)) {
    $file = fopen($output, 'x');
    if (!$file) {
        throw new RuntimeException('Cannot create private credentials file.');
    }
    fputcsv($file, ['username', 'password', 'email', 'programme', 'year'], ',', '"', '');
    foreach ($rows as $row) {
        fputcsv($file, $row, ',', '"', '');
    }
    fclose($file);
} elseif (count($credentials) !== count($rows)) {
    throw new RuntimeException('Existing credentials do not cover the complete test set.');
}
$transaction->allow_commit();
echo 'Ready: 8 students, 2 programmes, Y1-Y4, 72 module courses, 72 Student enrolments.' . PHP_EOL;
