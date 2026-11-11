<?php
// Department > academic course > Y1 categories > nine academic module courses.
define('CLI_SCRIPT', true);
// Hundreds of course contexts and deferred events are retained until commit.
ini_set('memory_limit', '1024M');
require('/var/www/html/config.php');
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->libdir . '/enrollib.php');
require_once($CFG->dirroot . '/user/lib.php');
require_once(__DIR__ . '/student_enrolments.php');
\core\session\manager::set_user(get_admin());
set_time_limit(0);
umask(0077);

$curriculum = json_decode(file_get_contents(__DIR__ . '/curriculum.json'), true, 512, JSON_THROW_ON_ERROR);
if (count($curriculum) !== 5) {
    throw new RuntimeException('Expected five departments.');
}
foreach ($curriculum as $department) {
    if (count($department['courses']) !== 20 || count($department['modules']) !== 9) {
        throw new RuntimeException('Each department needs twenty academic courses and nine module titles.');
    }
}
$output = $argv[1] ?? '/var/www/moodledata/demo-students.csv';
$newcredentials = [];

function demo_category(string $idnumber, string $name, int $parent): core_course_category {
    global $DB;
    $record = $DB->get_record('course_categories', ['idnumber' => $idnumber]);
    $data = (object)['name' => $name, 'parent' => $parent, 'idnumber' => $idnumber, 'visible' => 1];
    if (!$record) {
        return core_course_category::create($data);
    }
    $category = core_course_category::get($record->id);
    if ($category->name !== $name || (int)$category->parent !== $parent) {
        $category->update($data);
    }
    return $category;
}

// Refuse any collisions before changing the existing seed.
for ($index = 1; $index <= 100; $index++) {
    $username = sprintf('student%03d', $index);
    $user = $DB->get_record('user', ['username' => $username, 'mnethostid' => $CFG->mnet_localhost_id]);
    if ($user && ($user->idnumber !== 'tutor-demo-' . $username || $user->deleted)) {
        throw new RuntimeException('Unrelated or deleted account: ' . $username);
    }
    if (!$user && file_exists($output)) {
        throw new RuntimeException('Supply a new credentials output path when adding missing students.');
    }
}

$transaction = $DB->start_delegated_transaction();
foreach ($curriculum as $offset => $department) {
    $departmentnum = $offset + 1;
    $parent = demo_category(sprintf('tutor-demo-department-%02d', $departmentnum), $department['name'], 0);
    $students = [];
    for ($number = 1; $number <= 20; $number++) {
        $index = $offset * 20 + $number;
        $username = sprintf('student%03d', $index);
        $user = $DB->get_record('user', ['username' => $username, 'mnethostid' => $CFG->mnet_localhost_id]);
        if (!$user) {
            $password = 'Aa1!' . bin2hex(random_bytes(12));
            $userid = user_create_user((object)[
                'auth' => 'manual', 'confirmed' => 1, 'mnethostid' => $CFG->mnet_localhost_id,
                'username' => $username, 'password' => $password, 'idnumber' => 'tutor-demo-' . $username,
                'firstname' => 'Student', 'lastname' => sprintf('%03d', $index),
                'email' => $username . '@student.testcollege.ie', 'emailstop' => 1,
                'department' => $department['name'], 'institution' => 'Test College',
                'country' => 'IE', 'timezone' => 'Europe/Dublin',
            ]);
            $user = $DB->get_record('user', ['id' => $userid], '*', MUST_EXIST);
            $newcredentials[] = [$username, $password, $user->firstname, $user->lastname, $user->email, $department['name'], $department['courses'][$number - 1], 'Y1'];
        } elseif ($user->department !== $department['name']) {
            user_update_user((object)['id' => $user->id, 'department' => $department['name']], false);
        }
        $students[$number - 1] = $user;
    }

    foreach ($department['courses'] as $courseoffset => $academicname) {
        $base = sprintf('DEPT%02d-COURSE%02d', $departmentnum, $courseoffset + 1);
        $academic = demo_category('tutor-demo-academic-' . $base, $academicname, $parent->id);
        $year = demo_category('tutor-demo-year-' . $base . '-Y1', 'Y1', $academic->id);
        $titles = $department['overrides'][$academicname] ?? $department['modules'];
        if (count($titles) !== 9) {
            throw new RuntimeException('Expected nine module titles for ' . $academicname);
        }
        foreach ($titles as $moduleoffset => $title) {
            $shortname = $base . sprintf('-Y1-M%02d', $moduleoffset + 1);
            $idnumber = 'tutor-demo-module-' . $shortname;
            $course = $DB->get_record('course', ['idnumber' => $idnumber]);
            $legacy = false;
            if (!$course && $moduleoffset === 0) {
                $course = $DB->get_record('course', ['idnumber' => 'tutor-demo-' . $base]);
                $legacy = (bool)$course;
            }
            $collision = $DB->get_record('course', ['shortname' => $shortname]);
            if ($collision && (!$course || $collision->id !== $course->id)) {
                throw new RuntimeException('Unrelated course shortname: ' . $shortname);
            }
            if ($legacy) {
                // Only remove the old, empty generated section placeholders.
                if ($DB->record_exists('course_modules', ['course' => $course->id])) {
                    throw new RuntimeException('Legacy course contains activities; migration stopped to preserve them.');
                }
                $sections = $DB->get_records_select('course_sections', 'course = ? AND section > 0', [$course->id], 'section DESC');
                foreach ($sections as $section) {
                    if ($section->name !== sprintf('Module %02d', $section->section) || trim($section->summary) !== '') {
                        throw new RuntimeException('Legacy course contains edited sections; migration stopped to preserve them.');
                    }
                }
                foreach ($sections as $section) {
                    if (!course_delete_section($course, $section, false, false)) {
                        throw new RuntimeException('Could not remove an empty legacy section.');
                    }
                }
            }
            $data = (object)[
                'category' => $year->id, 'fullname' => $title, 'shortname' => $shortname,
                'idnumber' => $idnumber, 'format' => 'topics', 'visible' => 1,
                'summary' => $academicname . ' — Y1 academic module. Ready for learning activities and resources.',
                'summaryformat' => FORMAT_HTML,
            ];
            if ($course) {
                $data->id = $course->id;
                update_course($data);
                $course = get_course($course->id);
            } else {
                $data->numsections = 0;
                $data->startdate = strtotime('today');
                $data->enddate = 0;
                $data->newsitems = 0;
                $course = create_course($data);
            }
            // Enrolments are managed by programme/year cohorts after all modules exist.
        }
    }
    echo $department['name'] . ": 20 academic courses, 20 Y1 categories, 180 academic modules, 20 students\n";
}
// Cohort membership controls enrolment and repairs earlier manual enrolments.
demo_sync_student_enrolments();
if ($newcredentials) {
    $file = fopen($output, 'x');
    if (!$file) {
        throw new RuntimeException('Could not create credentials output.');
    }
    fputcsv($file, ['username', 'password', 'firstname', 'lastname', 'email', 'department', 'academic_course', 'year'], ',', '"', '');
    foreach ($newcredentials as $row) {
        fputcsv($file, $row, ',', '"', '');
    }
    fclose($file);
}
$transaction->allow_commit();
echo "Complete: 5 departments, 100 academic courses, 100 Y1 categories, 900 module courses, 100 students, 900 enrolments (9 per student).\n";
echo "Existing student passwords and credentials export preserved.\n";
