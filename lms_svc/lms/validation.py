"""Strict normalized catalog schemas; unknown attributes are discarded."""
import re

from .interfaces import LMSImportError


def text(value, maximum, required=False):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()) or any(ord(c) < 32 for c in value):
        raise ValueError()
    return value


def identifier(value):
    return text(value, 200, required=True)


def validate_catalog(catalog):
    try:
        if not isinstance(catalog, dict):
            raise ValueError()
        normalized = {}
        for kind in ("users", "courses", "modules"):
            records = catalog[kind]
            if not isinstance(records, list) or len(records) > 50000:
                raise ValueError()
            normalized[kind] = []
            seen = set()
            for record in records:
                source_id = identifier(record["source_id"])
                if source_id in seen:
                    raise ValueError()
                seen.add(source_id)
                clean = {"source_id": source_id}
                if kind == "users":
                    for field in ("username", "first_name", "last_name"):
                        clean[field] = text(record.get(field, ""), 200)
                    email = record.get("email")
                    if email is not None and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", text(email, 254, required=True)):
                        raise ValueError()
                    clean["email"] = email
                    suspended = record.get("suspended", False)
                    if not isinstance(suspended, bool):
                        raise ValueError()
                    clean["suspended"] = suspended
                else:
                    clean["name"] = text(record["name"], 1000, required=True)
                    for field in ("code", "type"):
                        if field in record:
                            clean[field] = text(record[field], 200)
                    if kind == "courses" and "parent_id" in record:
                        clean["parent_id"] = identifier(record["parent_id"]) if record["parent_id"] is not None else None
                    if kind == "modules":
                        clean["course_id"] = identifier(record["course_id"])
                normalized[kind].append(clean)
        courses = {c["source_id"]: c for c in normalized["courses"]}
        if any(m["course_id"] not in courses for m in normalized["modules"]):
            raise ValueError()
        # Reject missing parents and cycles before publishing programme hierarchy.
        done = set()
        for source_id in courses:
            current, chain = source_id, set()
            while current is not None and current not in done:
                if current not in courses or current in chain:
                    raise ValueError()
                chain.add(current)
                current = courses[current].get("parent_id")
            done.update(chain)
        return normalized
    except (ValueError, KeyError, TypeError):
        raise LMSImportError("LMS returned invalid records or relationships; the previous catalog is unchanged.") from None
