ARG MOODLE_DOCKER_PHP_VERSION=8.3
FROM moodlehq/moodle-php-apache:${MOODLE_DOCKER_PHP_VERSION}

COPY --from=composer/composer:2-bin /composer /usr/local/bin/composer
COPY php/moodle.ini /usr/local/etc/php/conf.d/zz-moodle.ini
