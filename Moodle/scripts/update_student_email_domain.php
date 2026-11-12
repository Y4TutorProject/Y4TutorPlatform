<?php
// Update student-role accounts only; preview by default, --apply to save.
define('CLI_SCRIPT', true);
require('/var/www/html/config.php');
\core\session\manager::set_user(get_admin());
umask(0077);
$domain = 'student.testcollege.ie';
$users = $DB->get_records_sql(
    'SELECT DISTINCT u.id, u.email FROM {user} u
       JOIN {role_assignments} ra ON ra.userid = u.id
       JOIN {role} r ON r.id = ra.roleid
      WHERE r.shortname = :role AND u.deleted = 0 AND u.mnethostid = :host',
    ['role' => 'student', 'host' => $CFG->mnet_localhost_id]
);
$changes = [];
$targets = [];
foreach ($users as $user) {
    $prefix = strstr($user->email, '@', true);
    if (!$prefix) {
        throw new RuntimeException('Student has no valid email prefix: ' . $user->id);
    }
    $email = $prefix . '@' . $domain;
    if (isset($targets[strtolower($email)])) {
        throw new RuntimeException('Student email prefixes are not unique.');
    }
    $targets[strtolower($email)] = true;
    if ($DB->record_exists_sql('SELECT id FROM {user} WHERE LOWER(email) = :email AND id <> :id AND deleted = 0',
            ['email' => strtolower($email), 'id' => $user->id])) {
        throw new RuntimeException('Target email already belongs to another user: ' . $user->id);
    }
    if ($email !== $user->email) {
        $changes[] = ['id' => $user->id, 'old_email' => $user->email, 'email' => $email];
    }
}
echo count($users) . ' student accounts; ' . count($changes) . " email changes.\n";
if (!in_array('--apply', $argv, true) || !$changes) {
    exit(0);
}
$backup = $CFG->dataroot . '/student-email-backup-' . gmdate('Ymd-His') . '.json';
if (file_put_contents($backup, json_encode($changes, JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR)) === false) {
    throw new RuntimeException('Cannot save email backup.');
}
$transaction = $DB->start_delegated_transaction();
foreach ($changes as $change) {
    \core\user::update_user((object)['id' => $change['id'], 'email' => $change['email']], false);
}
$transaction->allow_commit();
echo 'Updated ' . count($changes) . " student emails. Previous emails backed up in Moodle data.\n";
