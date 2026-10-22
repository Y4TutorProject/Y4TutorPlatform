from abc import ABC, abstractmethod


class UsersDAO(ABC):
    @abstractmethod
    def connect_to_database(self):
        pass

    @abstractmethod
    def add_user(self, user):
        pass

    @abstractmethod
    def update_user(self, user):
        pass

    @abstractmethod
    def get_user(self, user_id):
        pass

    @abstractmethod
    def get_user_by_email(self, email):
        pass

    @abstractmethod
    def setup_database(self):
        pass


class UsersInterface(ABC):
    @staticmethod
    @abstractmethod
    def normalize_email(email):
        pass

    @abstractmethod
    def sign_up(self, username, password, email, college_id=None):
        pass

    @abstractmethod
    def log_in(self, email, password):
        pass

    @abstractmethod
    def change_status(self, user_uuid, new_status):
        pass

    @abstractmethod
    def hash_password(self, password):
        pass
