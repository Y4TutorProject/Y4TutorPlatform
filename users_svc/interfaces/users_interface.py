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
    @abstractmethod
    def log_in(self, email, password):
        pass

    @abstractmethod
    def change_status(self, user_uuid, new_status):
        pass
