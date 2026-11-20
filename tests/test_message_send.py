def _socket(app, client, user_id):
    return app.extensions["socketio"].test_client(
        app, auth={"userId": user_id}, flask_test_client=client
    )


def _text_payload(sender_id="1", message="hi"):
    return {
        "chatId": "c1",
        "senderId": sender_id,
        "message": message,
        "timestamp": "2026-01-01T00:00:00+00:00",
    }


def test_socket_text_message_is_stored_and_emitted_as_text(app, client, login, chat, dao, emitted):
    login("1")
    socket = _socket(app, client, "1")

    socket.emit("message", _text_payload())

    (stored,) = dao.get_messages("c1")
    assert stored.messageType == "text"
    assert stored.message == "hi"
    payloads = [data for event, data, _ in emitted if event == "message"]
    assert payloads and all(p["messageType"] == "text" for p in payloads)
    assert all("fileName" not in p for p in payloads)


def test_socket_message_with_spoofed_sender_is_ignored(app, client, login, chat, dao, emitted):
    login("1")
    socket = _socket(app, client, "1")

    socket.emit("message", _text_payload(sender_id="2"))

    assert dao.get_messages("c1") == []
    assert emitted == []
