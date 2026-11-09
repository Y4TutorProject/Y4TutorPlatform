"""An academic programme (or category) owned by a college."""
import uuid


class Course:
    def __init__(self, course_id, college_id, name, source_id, parent_id=None, code=None, kind=None):
        self.course_id = uuid.UUID(str(course_id))
        self.college_id = uuid.UUID(str(college_id))
        self.name = name
        self.source_id = source_id
        self.parent_id = uuid.UUID(str(parent_id)) if parent_id else None
        self.code = code
        self.kind = kind

    def to_dict(self):
        """Return JSON-compatible course details and relationship IDs."""
        result = {"id": str(self.course_id), "college_id": str(self.college_id),
                  "name": self.name, "source_id": self.source_id,
                  "parent_id": str(self.parent_id) if self.parent_id else None}
        if self.code is not None:
            result["code"] = self.code
        if self.kind is not None:
            result['kind'] = self.kind
        return result
