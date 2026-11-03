
try:
    from .Models.NotificationStore import NotificationStore
    from .Models.NotificationType import NotificationType
except ImportError:
    from Models.NotificationStore import NotificationStore
    from Models.NotificationType import NotificationType


class NotificationService:
    def __init__(self, notification_store: NotificationStore):
        self.store = notification_store

    def get_user_notifications(
        self,
        user_id,
        unread_only=False,
        page=1,
        per_page=20,
    ):
        return self.store.list_for_user(
            user_id,
            unread_only=unread_only,
            page=page,
            per_page=per_page,
        )

    def get_unread_count(self, user_id):
        return self.store.unread_count(user_id)

    def mark_as_read(self, notification_id, user_id):
        return self.store.mark_read(notification_id, user_id)

    def mark_as_unread(self, notification_id, user_id):
        return self.store.mark_unread(notification_id, user_id)

    def mark_all_as_read(self, user_id):
        return self.store.mark_all_read(user_id)

    def create_notifications(self, recipient_ids, notification_type, title, body="",
                             payload=None, actor_id=None):
        if notification_type not in {member.value for member in NotificationType}:
            raise ValueError("Invalid notification type")
        return self.store.create_many(
            recipient_ids,
            notification_type,
            title,
            body,
            payload,
            actor_id,
        )