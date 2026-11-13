import json
import math
from collections.abc import Mapping
from urllib.request import Request

from flask import current_app

from users_client import session_headers


def _finite_float(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Preference values must be numbers")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Preference values must be finite")
    return number


def _clean(prefs) -> dict[str, float]:
    if not isinstance(prefs, Mapping):
        raise ValueError("Preferences must be an object")
    return {str(k): _finite_float(v) for k, v in prefs.items()}


def build_payload(student_prefs, tutors: list[dict]) -> dict:
    """tutors: [{tutor_id: {pref: value}}, ...]"""
    student = _clean(student_prefs)

    tutor_items = []
    for t in tutors:
        tutor_id, prefs = next(iter(t.items()))
        if not tutor_id:
            raise ValueError("Tutor ID is missing")
        tutor_items.append((tutor_id, _clean(prefs)))

    feature_order = sorted(set(student).union(*(p for _, p in tutor_items)))

    def vec(prefs):
        return [prefs.get(k, 0.0) for k in feature_order]

    return {
        "student_vector": vec(student),
        "tutors": {tid: vec(p) for tid, p in tutor_items},
    }


def get_recommendations(payload: dict):
    req = Request(
        current_app.config["MATCHING_API_URL"].rstrip("/") + "/get-recommendations",
        data=json.dumps(payload, allow_nan=False).encode("utf-8"),
        headers={**session_headers(), "Content-Type": "application/json"},
        method="POST",
    )
    with current_app.extensions["users_opener"].open(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def get_similarity_scores(student_prefs, tutors: list[dict]) -> dict[str, float]:
    """Returns {tutor_id: similarity}."""
    results = get_recommendations(build_payload(student_prefs, tutors))
    return {tutor_id: similarity for tutor_id, similarity in results}