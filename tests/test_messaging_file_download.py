import io

from messaging_svc.models.Message import Message


def _seed_file_message(dao, chat_id="c1", sender_id="1", data=b"hello"):
    file_id = dao.save_file(
        io.BytesIO(data), "notes.pdf", "application/pdf", len(data), chat_id, sender_id
    )
    message = Message({
        "id": dao.get_next_message_id(),
        "chatId": chat_id,
        "senderId": sender_id,
        "message": "",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "messageType": "file",
        "file_id": file_id,
        "file_name": "notes.pdf",
        "mime_type": "application/pdf",
        "file_size": len(data),
    })
    dao.add_message(message)
    return message


def test_download_returns_file_as_attachment(client, login, chat, dao):
    login("2")
    message = _seed_file_message(dao)

    response = client.get(f"/mychats/chat/c1/files/{message.id}")

    assert response.status_code == 200
    assert response.data == b"hello"
    assert response.mimetype == "application/pdf"
    disposition = response.headers["Content-Disposition"]
    assert disposition.startswith("attachment")
    assert "notes.pdf" in disposition


def test_download_rejects_non_member(client, login, chat, dao):
    login("3")
    message = _seed_file_message(dao)

    response = client.get(f"/mychats/chat/c1/files/{message.id}")

    assert response.status_code == 404


def test_download_rejects_text_message(client, login, chat, dao):
    login("1")
    text_message = Message({
        "id": "5",
        "chatId": "c1",
        "senderId": "1",
        "message": "hi",
        "timestamp": "2026-01-01T00:00:00+00:00",
    })
    dao.add_message(text_message)

    response = client.get("/mychats/chat/c1/files/5")

    assert response.status_code == 404


def test_download_rejects_message_from_another_chat(client, login, chat, dao):
    login("1")
    message = _seed_file_message(dao, chat_id="c2")

    response = client.get(f"/mychats/chat/c1/files/{message.id}")

    assert response.status_code == 404


def test_download_returns_404_when_stored_file_is_missing(client, login, chat, dao):
    login("1")
    message = _seed_file_message(dao)
    dao.files.pop(message.file_id)

    response = client.get(f"/mychats/chat/c1/files/{message.id}")

    assert response.status_code == 404
