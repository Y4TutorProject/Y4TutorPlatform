<?php
define('CLI_SCRIPT', true);
ini_set('memory_limit', '1024M');
require('/var/www/html/config.php');
require_once($CFG->libdir . '/enrollib.php');
require_once(__DIR__ . '/student_enrolments.php');
\core\session\manager::set_user(get_admin());
set_time_limit(0);
echo json_encode(demo_sync_student_enrolments(), JSON_PRETTY_PRINT) . "\n";
