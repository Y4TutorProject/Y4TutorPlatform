from abc import ABC, abstractmethod

class RegistrationInterface(ABC):
    @abstractmethod
    def register_user(self, user_data):
        """Validate and persist signup data, returning the created user.

        Args:
            user_data (dict): Signup fields containing email, password, and an
                an account_type and optional username. Students require college_id.

        Returns:
            User: Persisted account awaiting email verification.
        """
        pass

    @abstractmethod
    def validate_user(self, user_data):
        """Validate and normalize signup fields.

        Args:
            user_data (dict): Signup fields containing email, password, and an
                an account_type and optional username. Students require college_id.

        Returns:
            dict: Validated credentials with normalized email and username.
        """
        pass