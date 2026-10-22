from abc import ABC, abstractmethod

class RegistrationInterface(ABC):
    @abstractmethod
    def register_user(self, user_data):
        pass

    @abstractmethod
    def validate_user(self, user_data):
        pass