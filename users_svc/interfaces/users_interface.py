from abc import ABC, abstractmethod


class UsersDAO(ABC):
    @abstractmethod
    def connect_to_database(self):
        """Check connectivity to the database.

        Returns:
            bool: True when the operation succeeds.
        """
        pass

    @abstractmethod
    def add_user(self, user):
        """Insert a new user into the data store.

        Args:
            user (User): User to store or serialize.

        Returns:
            bool: True when the operation succeeds.
        """
        pass

    @abstractmethod
    def update_user(self, user):
        """Update an existing user and report whether a record matched.

        Args:
            user (User): User to store or serialize.

        Returns:
            bool: True if a stored record matched the identifier; otherwise False.
        """
        pass

    @abstractmethod
    def get_user(self, user_id):
        """Return the user with the given ID, or None if no user matches.

        Args:
            user_id (str | uuid.UUID): User identifier to look up.

        Returns:
            User | None: Matching user, or None for an invalid or unknown
                identifier.
        """
        pass

    @abstractmethod
    def get_user_by_email(self, email):
        """Return the user with the given email, or None if no user matches.

        Args:
            email (str): Email address used to identify the account.

        Returns:
            User | None: Matching user, or None if the email is not registered.
        """
        pass

    @abstractmethod
    def setup_database(self):
        """Create the indexes required for unique user identities.

        Returns:
            bool: True after all required unique indexes are created.
        """
        pass


class UsersInterface(ABC):
    @abstractmethod
    def set_learning_preferences(self, user_uuid, preferences):
        """Save preference scores and return the updated user, or None if missing.

        Keys are LearningTeachingStyles members or lowercase names; scores are integers
        from 0 to 10 inclusive. Invalid preferences raise ValueError.
        """
        pass

    @abstractmethod
    def log_in(self, email, password):
        """Return an active user for valid credentials, or None when authentication
        fails.

        Args:
            email (str): Email address used to identify the account.
            password (str): Plaintext password to validate or hash.

        Returns:
            User | None: Active user for valid credentials, or None when
                authentication fails.
        """
        pass

    @abstractmethod
    def change_status(self, user_uuid, new_status):
        """Persist a new user status and return the user, or None if not found.

        Args:
            user_uuid (str | uuid.UUID): Identifier of the user to update.
            new_status (UserStatus | str): Status to assign to the user.

        Returns:
            User | None: Updated user, or None if the identifier does not match a
                user.
        """
        pass
