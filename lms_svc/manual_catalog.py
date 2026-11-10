"""Combine independently managed manual enrolments with an imported catalogue."""
from copy import deepcopy

from .module_participation import enrolment_roles, tutor_modules


def merge_manual(catalog, manual, user):
    result = deepcopy(catalog) if catalog else {
        'provider': 'manual', 'imported_at': None, 'courses': [], 'modules': [],
        'users': [], 'enrolments': [], 'enrolments_available': True, 'mapping': 'academic',
    }
    result['courses'].extend(manual['courses'])
    result['modules'].extend(manual['modules'])
    matches = [profile for profile in result['users']
               if profile.get('email', '').strip().casefold() == user['email'].strip().casefold()]
    own_links = [a for a in manual['assignments'] if a.get('user_id') == user['id']]
    directory = next((p for p in manual.get('directory_users', []) if p['email'] == user['email'].strip().casefold()), None)
    source_id = matches[0]['source_id'] if len(matches) == 1 else 'manual:' + user['id']
    # An imported suspended/ambiguous profile must never be bypassed by manual data.
    if not matches and (own_links or directory):
        result['users'].append({**(directory or {}), 'source_id': source_id, 'email': user['email'],
                                'username': (directory or {}).get('username') or user['username'], 'suspended': False})
    manual_roles = {}
    for link in own_links:
        targets = [link['target_id']] if link['target_type'] == 'module' else [
            m['id'] for m in manual['modules'] if m['course_id'] == link['target_id'] and m['year'] == link['year']]
        for target in targets:
            result.setdefault('enrolments', []).append({
                'user_source_id': source_id, 'target_type': 'module', 'target_id': target, 'roles': [link['role']],
            })
            manual_roles.setdefault(target, set()).add(link['role'])
    result['_manual_roles'] = manual_roles
    return result


def manual_application_eligible(application, manual):
    user = {'id': application['user_id'], 'email': 'manual@local.invalid', 'username': ''}
    catalog = merge_manual(None, manual, user)
    roles = enrolment_roles(catalog, 'manual:' + user['id'])
    enrolled = [m for m in catalog['modules'] if 'student' in roles.get(m['id'], set())]
    return application['module_id'] in {m['id'] for m in tutor_modules(catalog, enrolled)}
