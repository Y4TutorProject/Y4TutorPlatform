class User:

    def __init__(self, userData:dict):
        self.id = userData['id']
        self.name = userData['name']
        self.password = userData['password']

    def get_name_by_id(self, id):
        if id == self.id:
            return self.name

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "password": self.password
        }