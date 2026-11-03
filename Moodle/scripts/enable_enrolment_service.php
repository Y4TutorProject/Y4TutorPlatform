<?php
// Add the read-only enrolment lookup to an existing integration service.
define('CLI_SCRIPT', true);
require('/var/www/html/config.php');

$options = getopt('', ['service:']);
$shortname = $options['service'] ?? '';
if ($shortname === '') {
    fwrite(STDERR, "Usage: php enable_enrolment_service.php --service=SHORTNAME\n");
    exit(1);
}
$service = $DB->get_record('external_services', ['shortname' => $shortname], '*', MUST_EXIST);
$functions = $DB->get_fieldset_select('external_services_functions', 'functionname', 'externalserviceid = ?', [$service->id]);
foreach (['core_user_get_users', 'core_course_get_courses', 'core_course_get_categories'] as $required) {
    if (!in_array($required, $functions, true)) {
        throw new RuntimeException('The selected service is not the existing college import service.');
    }
}
$function = 'core_enrol_get_users_courses';
$DB->get_record('external_functions', ['name' => $function], 'id', MUST_EXIST);
if (!in_array($function, $functions, true)) {
    $DB->insert_record('external_services_functions', (object)[
        'externalserviceid' => $service->id,
        'functionname' => $function,
    ]);
}
echo "Read-only enrolment lookup enabled for the selected integration service.\n";
