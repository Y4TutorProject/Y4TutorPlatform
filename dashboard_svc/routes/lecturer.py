"""Lecturer modules and tutor application review."""
import json
from urllib.error import HTTPError, URLError

from flask import abort, redirect, render_template

from clean_text import clean_deep
from users_client import open_upstream, upstream_request


def render_lecturer_dashboard(user, can_manage_college, modules=None):
    if modules is None:
        try:
            with open_upstream(upstream_request('LMS_API_URL', '/lecturers/me/modules')) as response:
                modules = json.load(response)['modules']
        except HTTPError as error:
            error.close()
            if error.code == 401:
                return redirect('/login')
            abort(error.code if error.code in (403, 404) else 503)
        except (URLError, OSError, ValueError, KeyError):
            abort(503)
    modules = sorted(clean_deep(modules), key=lambda m: (m.get('year') or 0, m['name'].casefold()))
    return render_template('lecturer_dashboard.html', user=user,
                           can_manage_college=can_manage_college, modules=modules, is_lecturer=True)
