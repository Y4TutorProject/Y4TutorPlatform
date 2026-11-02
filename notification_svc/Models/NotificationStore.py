from abc import ABC, abstractmethod
from typing import Optional


class NotificationStore(ABC):
    """Interface: the rest of the service depends on this, not on MongoDB."""

    @abstractmethod
    def create_many(
        self,
        recipient_ids: list[str],
        type: str,
        title: str,
        body: str = "",
        payload: Optional[dict] = None,
        actor_id: Optional[str] = None,
    ) -> list[dict]: ...

    @abstractmethod
    def get(self, notification_id: str) -> Optional[dict]: ...

    @abstractmethod
    def list_for_user(
        self,
        user_id: str,
        unread_only: bool = False,
        page: int = 1,
        per_page: int = 20,
    ) -> dict: ...

    @abstractmethod
    def unread_count(self, user_id: str) -> int: ...

    @abstractmethod
    def mark_read(self, notification_id: str, user_id: str) -> bool: ...

    @abstractmethod
    def mark_all_read(self, user_id: str) -> int: ...


