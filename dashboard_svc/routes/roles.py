from flask import session


SWITCHABLE = ("tutor", "student")   #ordered by default priority

def switchable_roles(user):
    roles = user.get("roles") or []
    return [r for r in SWITCHABLE if r in roles]

def resolve_active_role(user):
    available_roles = switchable_roles(user)
    current_role = session.get("active_role")
    active_role = current_role if current_role in available_roles else (available_roles[0] if available_roles else None)
    if active_role:
        session["active_role"] = active_role
        return active_role
    session.pop("active_role", None)
    return None