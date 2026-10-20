from abc import ABC, abstractmethod

class RegistrationInterface(ABC):
    @abstractmethod
    def connect_to_database(self):
        pass

    @abstractmethod
    def add_to_database(self, data):
        pass

    @abstractmethod
    def validate_data(self, data):
        pass

    @abstractmethod
    def check_if_exists(self, data):
        pass