import io

PDF = "application/pdf"


def _upload(client, data=b"hello", filename="notes.pdf", mimetype=PDF, caption=None):
    form = {"file": (io.BytesIO(data), filename, mimetype)}
    if caption is not None:
        form["message"] = caption
    return client.post("/mychats/chat/c1/files", data=form)


def test_upload_stores_file_and_message(client, login, chat, dao, emitted):
    login("1")

    response = _upload(client, caption="see attached")

    assert response.status_code == 201
    body = response.get_json()
    assert body["messageType"] == "file"
    assert body["fileName"] == "notes.pdf"
    assert body["mimeType"] == PDF
    assert body["fileSize"] == 5

    message = dao.get_message(body["messageId"])
    assert message.file_id in dao.files
    assert dao.files[message.file_id]["data"] == b"hello"
    assert dao.get_chat("c1").lastMessage == "see attached"


def test_upload_emits_to_every_chat_member(client, login, chat, emitted):
    login("1")

    _upload(client)

    assert {room for _, _, room in emitted} == {"user:1", "user:2"}


def test_upload_without_caption_uses_file_name_as_last_message(client, login, chat, dao):
    login("1")

    _upload(client)

    assert dao.get_chat("c1").lastMessage == "File: notes.pdf"


def test_upload_rejects_non_member(client, login, chat, dao):
    login("3")

    response = _upload(client)

    assert response.status_code == 404
    assert dao.messages == {}
    assert dao.files == {}


def test_upload_rejects_disallowed_mime_type(client, login, chat, dao):
    login("1")

    response = _upload(client, mimetype="application/x-msdownload")

    assert response.status_code == 415
    assert dao.files == {}


def test_upload_rejects_empty_file(client, login, chat, dao):
    login("1")

    response = _upload(client, data=b"")

    assert response.status_code == 400
    assert dao.files == {}


def test_upload_rejects_file_over_size_limit(client, login, chat, dao, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "MAX_UPLOAD_BYTES", 4)
    login("1")

    response = _upload(client, data=b"12345")

    assert response.status_code == 413
    assert dao.files == {}


def test_upload_requires_file_field(client, login, chat):
    login("1")

    response = client.post("/mychats/chat/c1/files", data={})

    assert response.status_code == 400
