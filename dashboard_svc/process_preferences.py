from flask import current_app
from urllib.request import Request
from users_client import session_headers
import json

def preference_to_vector(student_prefs: dict, tutors: list[dict]) -> dict:
    """
    converts student and tutor preferences into vector representations for matching system
    
    Args:
        student_prefs (dict): dictionary containing student's preferences - {"preference_name": value}
        tutors (list[dict]): list of tutors with their teaching preferences - [{"tutor_id": {"teaching_preferences": {...}}}]
    
    Returns:        
        dict: payload containing student vector and candidate vectors
    """
    tutor_items = [next(iter(t.items())) for t in tutors]
    try:
        feature_order = sorted(
            set(student_prefs).union(*(prefs for _, prefs in tutor_items))
        )

        def vec(prefs: dict) -> list[float]:
            """Convert a preference dictionary into a vector based on the feature order."""
            return [float(prefs.get(k, 0.0)) for k in feature_order]

        request_body = {
            "student_vector": vec(student_prefs),
            "tutors": {
                tutor_id: vec(prefs)
                for tutor_id, prefs in tutor_items
            },
        } 
        return get_recommendations(request_body)    
    except Exception as e:
        current_app.logger.error("Matcher -> %s: %s", getattr(e, "code", "N/A"), getattr(e, "read", lambda: b"")().decode("utf-8", errors="replace"))
        raise

def get_recommendations(request_body) -> dict:
    req = Request(
        current_app.config["MATCHING_API_URL"].rstrip("/") + "/get-recommendations",
        data=json.dumps(request_body).encode("utf-8"),
        headers={**session_headers(), "Content-Type": "application/json"},
        method="POST",
    )
    with current_app.extensions["users_opener"].open(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))