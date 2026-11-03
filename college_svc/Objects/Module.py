"""A subject or activity belonging to an academic course."""
import uuid


class Module:
    def __init__(self, module_id, college_id, course_id, name, source_id, code=None, module_type=None):
        self.module_id = uuid.UUID(str(module_id))
        self.college_id = uuid.UUID(str(college_id))
        self.course_id = uuid.UUID(str(course_id))
        self.name = name
        self.source_id = source_id
        self.code = code
        self.module_type = module_type

    def to_dict(self):
        """Return JSON-compatible module details and its owning course ID."""
        result = {"id": str(self.module_id), "college_id": str(self.college_id),
                  "course_id": str(self.course_id), "name": self.name, "source_id": self.source_id}
        if self.code is not None:
            result["code"] = self.code
        if self.module_type is not None:
            result["type"] = self.module_type
        return result
