import html
import re

_UNICODE_ESC = re.compile(r"\\u([0-9a-fA-F]{4})")

def clean_text(s):
    s = _UNICODE_ESC.sub(lambda m: chr(int(m.group(1), 16)), s)  # \u0026 -> &
    return html.unescape(s)                                      # &amp;  -> &

def clean_deep(value):
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, list):
        return [clean_deep(v) for v in value]
    if isinstance(value, dict):
        return {k: clean_deep(v) for k, v in value.items()}
    return value