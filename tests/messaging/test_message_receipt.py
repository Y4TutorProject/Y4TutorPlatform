import io

from models.Message import Message


def test_history_returns_file_metadata_and_text_type(client, login, chat, dao):
    login("1")
    client.post(
        "/mychats/chat/c1/files",
        data={"file": (io.BytesIO(b"hello"), "notes.pdf", "application/pdf"), "message": "see attached"},
    )
    dao.add_message(Message({
        "id": dao.get_next_message_id(),
        "chatId": "c1",
        "senderId": "2",
        "message": "thanks",
        "timestamp": "2099-01-01T00:00:00+00:00",
    }))
    login("2")

    response = client.get("/mychats/chat/c1")

    assert response.status_code == 200
    file_item, text_item = response.get_json()
    assert file_item["messageType"] == "file"
    assert file_item["fileName"] == "notes.pdf"
    assert file_item["mimeType"] == "application/pdf"
    assert file_item["fileSize"] == 5
    assert file_item["message"] == "see attached"
    assert text_item["messageType"] == "text"
    assert "fileName" not in text_item


def test_history_rejects_non_member(client, login, chat):
    login("3")

    response = client.get("/mychats/chat/c1")

    assert response.status_code == 404
