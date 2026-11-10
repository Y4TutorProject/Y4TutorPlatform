<?php
/** Read-only verification of development lecturer assignments. */
define('CLI_SCRIPT', true);
require('/var/www/html/config.php');
$roles = $DB->get_records_list('role', 'shortname', ['editingteacher', 'teacher']);
$counts = ['modules' => 0, 'missing' => 0, 'multiple' => 0];
foreach ($DB->get_records_select('course', 'id <> ?', [SITEID]) as $course) {
    $people = [];
    foreach ($roles as $role) {
        foreach (get_enrolled_users(context_course::instance($course->id), '', 0, 'u.id, u.suspended', null, 0, 0, true) as $user) {
            if (!$user->suspended && user_has_role_assignment($user->id, $role->id, context_course::instance($course->id)->id)) {
                $people[$user->id] = true;
            }
        }
    }
    $counts['modules']++;
    $counts['missing'] += count($people) === 0 ? 1 : 0;
    $counts['multiple'] += count($people) > 1 ? 1 : 0;
}
echo json_encode($counts) . PHP_EOL;
foreach ($DB->get_records('external_services', null, 'id', 'id, name') as $service) {
    echo $service->name . ': course-role API ' . ($DB->record_exists('external_services_functions', [
        'externalserviceid' => $service->id, 'functionname' => 'core_enrol_get_enrolled_users']) ? 'enabled' : 'missing') . PHP_EOL;
}
