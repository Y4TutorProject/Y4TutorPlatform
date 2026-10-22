from college_svc.Objects import CollegeStatus

class College:
    def __init__(self, college_id, college_name):
        self.college_id = college_id
        self.college_name = college_name
        self.college_domain = None
        self.status = CollegeStatus