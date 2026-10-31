from messages_dao.MongoMessagesDAO import MongoMessagesDAO


users = {}
dao = MongoMessagesDAO()
dao.connect_to_database()
dao.setup_database()


def get_last_read_message_id(user_id, chat_id):
    state = dao.get_chat_read_state(str(user_id), str(chat_id))
    return state["lastreadmessageId"] if state else None


def mark_chat_read(user_id, chat_id, message_id):
    existing_state = dao.get_chat_read_state(str(user_id), str(chat_id))
    state_id = existing_state["id"] if existing_state else None
    if state_id is None:
        state_id = dao.get_next_read_state_id()
    dao.add_or_update_chat_read_state(
        state_id,
        str(user_id),
        str(chat_id),
        str(message_id),
    )
