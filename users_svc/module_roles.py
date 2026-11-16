"""Promote accounts using module memberships owned by the LMS service."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from .college_client import NoRedirect
from .Objects.Role import Role


class ModuleRolesClient:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.opener = build_opener(NoRedirect())

    def has_tutor_module(self, user):
        if not self.token or not user.college:
            return False
        request = Request(
            f'{self.base_url}/internal/college/{user.college}/users/{user.id}/module-roles',
            headers={'X-College-Sync-Token': self.token})
        try:
            with self.opener.open(request, timeout=5) as response:
                return json.load(response).get('tutor') is True
        except (HTTPError, URLError, OSError, ValueError, AttributeError):
            # A failed lookup must never grant a role or prevent student access.
            return False


def synchronize_tutor_role(app, user):
    if user and user.is_active and Role.TUTOR not in user.roles:
        if app.extensions['module_roles_client'].has_tutor_module(user):
            app.extensions['users_dao'].grant_tutor_role(user)
            user.roles.append(Role.TUTOR)
    return user
