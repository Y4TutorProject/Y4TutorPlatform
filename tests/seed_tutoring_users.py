"""Provision local Moodle year-test users through the platform signup APIs.

Passwords are read from a private CSV and never printed. Mail verification is
completed only against the explicitly supplied local Mailpit instance.
"""
import argparse
import csv
import http.cookiejar
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


def request(browser, url, data=None, csrf=None):
    headers = {'Content-Type': 'application/json'}
    if csrf:
        headers['X-CSRFToken'] = csrf
    req = Request(url, data=json.dumps(data).encode() if data is not None else None, headers=headers)
    try:
        response = browser.open(req, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def post(browser, base, service, path, data):
    status, token = request(browser, f'{base}/api/{service}/auth/csrf')
    if status != 200:
        raise RuntimeError('Cannot obtain local CSRF token.')
    return request(browser, f'{base}/api/{service}{path}', data, token['csrf_token'])


def verification_token(mailpit, email):
    for _ in range(20):
        with urlopen(mailpit + '/api/v1/messages?limit=100', timeout=10) as response:
            messages = json.load(response)['messages']
        for message in messages:
            if not any(recipient['Address'] == email for recipient in message['To']):
                continue
            with urlopen(mailpit + '/api/v1/message/' + message['ID'], timeout=10) as response:
                content = json.load(response)
            match = re.search(r'https?://\S+/verify-email#token=\S+', content['Text'])
            if match:
                return parse_qs(urlsplit(match.group(0)).fragment)['token'][0]
        time.sleep(0.2)
    raise RuntimeError('Local verification email did not arrive.')


def seed(args):
    base, mailpit = args.base.rstrip('/'), args.mailpit.rstrip('/')
    # This helper is intentionally limited to local test services.
    if urlsplit(base).hostname not in {'localhost', '127.0.0.1', 'gateway'} or urlsplit(mailpit).hostname not in {'localhost', '127.0.0.1', 'mailpit'}:
        raise RuntimeError('Use the local gateway and local Mailpit only.')
    with Path(args.credentials).open(newline='') as file:
        accounts = list(csv.DictReader(file))
    expected = {f'tutor_test_{programme}_y{year}' for programme in ('devops', 'analytics') for year in range(1, 5)}
    if {a['username'] for a in accounts} != expected or len(accounts) != 8:
        raise RuntimeError('Expected the eight isolated tutoring test accounts.')
    if any(a['email'] != a['username'] + '@student.testcollege.ie' or not a['password'] for a in accounts):
        raise RuntimeError('Invalid test account credentials.')
    browser = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    status, data = request(browser, base + '/api/colleges/college')
    if status != 200:
        raise RuntimeError('Cannot read local colleges.')
    colleges = [c for c in data['colleges'] if c.get('domain') == 'student.testcollege.ie' and (not args.college_id or c['id'] == args.college_id)]
    if len(colleges) != 1:
        raise RuntimeError('Select exactly one test college using --college-id.')
    college_id = colleges[0]['id']
    for account in accounts:
        browser = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        payload = {k: account[k] for k in ('username', 'email', 'password')}
        status, result = post(browser, base, 'users', '/auth/login', payload)
        if status == 401:
            status, result = post(browser, base, 'registration', '/auth/signup', {
                **payload, 'college_id': college_id, 'account_type': 'student',
            })
            if status == 409:
                # A previous interrupted run may have created an unverified user.
                status, _ = post(browser, base, 'registration', '/auth/resend-verification', {'email': account['email']})
                if status != 200:
                    raise RuntimeError('Could not resend local verification for ' + account['username'])
            elif status != 201:
                raise RuntimeError('Cannot register test account ' + account['username'] + ': ' + str(status))
            status, _ = post(browser, base, 'registration', '/auth/verify-email', {
                'token': verification_token(mailpit, account['email']),
            })
            if status != 200:
                raise RuntimeError('Cannot verify test account ' + account['username'])
            status, result = post(browser, base, 'users', '/auth/login', payload)
        if status != 200 or result['user']['college_id'] != college_id or result['user']['username'] != account['username']:
            raise RuntimeError('Test account login or ownership mismatch: ' + account['username'])
        if result['user'].get('username_completed') is False:
            status, _ = post(browser, base, 'users', '/users/me/username', {'username': account['username']})
            if status != 200:
                raise RuntimeError('Cannot complete username setup.')
        if result['user'].get('preferences_completed') is False:
            status, _ = post(browser, base, 'users', '/users/me/preferences', {'preferences': {
                'auditory': 5, 'visual': 7, 'reading_writing': 6, 'kinesthetic': 8,
            }})
            if status != 200:
                raise RuntimeError('Cannot complete preference setup.')
        status, result = request(browser, base + '/api/lms/students/me/modules')
        if status != 200:
            raise RuntimeError('Moodle import is unavailable for ' + account['username'] + ': ' + str(status))
        modules = result['modules']
        status, profile = request(browser, base + '/api/lms/students/me')
        if status != 200:
            raise RuntimeError('Student profile unavailable.')
        enrolled = [m for m in profile['modules'] if 'student' in m.get('roles', [])]
        eligible = [m for m in modules if m.get('can_apply_to_tutor')]
        year = int(account['year'][1:])
        if len(modules) != (year - 1) * 9 or len(enrolled) != 9 or len(eligible) != len(modules):
            raise RuntimeError('Unexpected programme/enrolment/year eligibility for ' + account['username'])
        print(f"{account['username']}: {account['programme']} {account['year']}, 9 Student memberships, {len(eligible)} eligible tutor modules")
    print('All eight platform accounts are verified and ready to use.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('credentials', help='Private tutoring-years.csv exported by Moodle seeder')
    parser.add_argument('--base', default='http://localhost:8080')
    parser.add_argument('--mailpit', default='http://localhost:8025')
    parser.add_argument('--college-id')
    seed(parser.parse_args())
