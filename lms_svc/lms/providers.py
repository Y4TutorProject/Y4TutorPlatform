"""Installed adapter discovery; orchestration never switches on provider names."""
from importlib.metadata import entry_points
import re

from .interfaces import LMSProvider
from .moodle import MoodleProvider


def installed_providers():
    providers = {'moodle': MoodleProvider}
    for entry in entry_points(group='tutorplatform.lms_providers'):
        adapter = entry.load()
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,49}', entry.name) or entry.name in providers or not isinstance(adapter, type) or not issubclass(adapter, LMSProvider):
            raise RuntimeError('Invalid or duplicate installed LMS adapter.')
        providers[entry.name] = adapter
    return providers
