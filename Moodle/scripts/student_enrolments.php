<?php
// Shared by the seed and the enrolment repair CLI. Moodle must be bootstrapped.
function demo_sync_student_enrolments(): array {
    global $DB, $CFG;
    require_once($CFG->dirroot . '/cohort/lib.php');
    require_once($CFG->dirroot . '/enrol/cohort/locallib.php');
    $studentrole = $DB->get_record('role', ['shortname' => 'student'], '*', MUST_EXIST);
    $assignments = [];
    // Validate the complete target mapping before making any changes.
    for ($index = 1; $index <= 100; $index++) {
        $department = intdiv($index - 1, 20) + 1;
        $programme = ($index - 1) % 20 + 1;
        $base = sprintf('DEPT%02d-COURSE%02d', $department, $programme);
        $user = $DB->get_record('user', [
            'username' => sprintf('student%03d', $index),
            'idnumber' => sprintf('tutor-demo-student%03d', $index),
            'mnethostid' => $CFG->mnet_localhost_id,
            'deleted' => 0,
        ], '*', MUST_EXIST);
        $year = $DB->get_record('course_categories', ['idnumber' => 'tutor-demo-year-' . $base . '-Y1'], '*', MUST_EXIST);
        $courses = [];
        for ($module = 1; $module <= 9; $module++) {
            $course = $DB->get_record('course', [
                'idnumber' => 'tutor-demo-module-' . $base . sprintf('-Y1-M%02d', $module),
                'category' => $year->id,
            ], '*', MUST_EXIST);
            $courses[$course->id] = $course;
        }
        $academic = $DB->get_record('course_categories', ['id' => $year->parent], '*', MUST_EXIST);
        $assignments[] = ['user' => $user, 'courses' => $courses, 'year' => $year, 'academic' => $academic, 'base' => $base];
    }
    $counts = ['students' => 0, 'cohorts_created' => 0, 'cohort_members_added' => 0, 'cohort_sync_methods_created' => 0, 'removed_manual_enrolments' => 0];
    $transaction = $DB->start_delegated_transaction();
    if (!enrol_is_enabled('cohort')) {
        $enabled = array_filter(explode(',', $CFG->enrol_plugins_enabled));
        $enabled[] = 'cohort';
        $CFG->enrol_plugins_enabled = implode(',', array_unique($enabled));
        set_config('enrol_plugins_enabled', $CFG->enrol_plugins_enabled);
    }
    $cohortplugin = enrol_get_plugin('cohort');
    $trace = new null_progress_trace();
    foreach ($assignments as $assignment) {
        $user = $assignment['user'];
        $courses = $assignment['courses'];
        $cohortidnumber = 'tutor-demo-cohort-' . $assignment['base'] . '-Y1-2026';
        $cohort = $DB->get_record('cohort', ['idnumber' => $cohortidnumber]);
        $context = context_coursecat::instance($assignment['year']->id);
        $cohortdata = (object)[
            'contextid' => $context->id,
            'name' => $assignment['academic']->name . ' - Y1 - 2026/27',
            'idnumber' => $cohortidnumber,
            'description' => 'Registered students for this academic course, year, and academic session.',
            'descriptionformat' => FORMAT_HTML,
            'visible' => 1,
            'component' => '',
        ];
        if (!$cohort) {
            $cohortid = cohort_add_cohort($cohortdata);
            $cohort = $DB->get_record('cohort', ['id' => $cohortid], '*', MUST_EXIST);
            $counts['cohorts_created']++;
        } elseif ($cohort->contextid != $context->id || $cohort->name !== $cohortdata->name) {
            $cohortdata->id = $cohort->id;
            cohort_update_cohort($cohortdata);
        }
        // Membership in the cohort now controls the nine module enrolments.
        $othercohorts = $DB->get_records_sql(
            'SELECT c.* FROM {cohort} c JOIN {cohort_members} cm ON cm.cohortid = c.id
              WHERE cm.userid = :userid AND c.idnumber LIKE :prefix AND c.id <> :keep',
            ['userid' => $user->id, 'prefix' => 'tutor-demo-cohort-%-Y1-2026', 'keep' => $cohort->id]
        );
        foreach ($othercohorts as $othercohort) {
            cohort_remove_member($othercohort->id, $user->id);
        }
        if (!$DB->record_exists('cohort_members', ['cohortid' => $cohort->id, 'userid' => $user->id])) {
            cohort_add_member($cohort->id, $user->id);
            $counts['cohort_members_added']++;
        }
        // Create cohort enrolment before removing manual enrolment, retaining access.
        foreach ($courses as $course) {
            $instance = $DB->get_record('enrol', ['courseid' => $course->id, 'enrol' => 'cohort', 'customint1' => $cohort->id]);
            if (!$instance) {
                $cohortplugin->add_instance($course, [
                    'status' => ENROL_INSTANCE_ENABLED, 'roleid' => $studentrole->id,
                    'customint1' => $cohort->id, 'customint2' => 0,
                ]);
                $counts['cohort_sync_methods_created']++;
            } elseif ($instance->status != ENROL_INSTANCE_ENABLED || $instance->roleid != $studentrole->id) {
                $cohortplugin->update_instance($instance, (object)[
                    'status' => ENROL_INSTANCE_ENABLED, 'roleid' => $studentrole->id,
                    'customint1' => $cohort->id, 'customint2' => $instance->customint2,
                ]);
            } else {
                enrol_cohort_sync($trace, $course->id);
            }
        }
        $instances = $DB->get_records_sql(
            "SELECT e.* FROM {enrol} e
               JOIN {user_enrolments} ue ON ue.enrolid = e.id
               JOIN {course} c ON c.id = e.courseid
              WHERE ue.userid = :userid AND c.idnumber LIKE :prefix",
            ['userid' => $user->id, 'prefix' => 'tutor-demo-module-%']
        );
        foreach ($instances as $instance) {
            if ($instance->enrol === 'manual' || !isset($courses[$instance->courseid])) {
                $plugin = enrol_get_plugin($instance->enrol);
                if (!$plugin) {
                    throw new RuntimeException('Missing enrolment plugin: ' . $instance->enrol);
                }
                $plugin->unenrol_user($instance, $user->id);
                if ($instance->enrol === 'manual') {
                    $counts['removed_manual_enrolments']++;
                }
            }
        }
        $counts['students']++;
        if ($counts['students'] % 20 === 0) {
            echo 'Configured Y1 cohorts for ' . $counts['students'] . " students\n";
        }
    }
    $trace->finished();
    $transaction->allow_commit();
    return $counts;
}
