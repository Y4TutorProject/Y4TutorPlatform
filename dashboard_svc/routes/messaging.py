import requests
from flask import Blueprint, abort, g, make_response, render_template, request

from messaging_client import forward_messaging_cookie, messaging_post
from users_client import login_required

bp = Blueprint("messaging", __name__)


@bp.get("/getmessages")
@login_required
def open_chat():
    other = {"id": request.args.get("user_id"), "username": request.args.get("username")}
    return render_chat_with(g.user, other)


def render_chat_with(current, other):
    """Create (or reuse) a chat with another user and render the messaging page.

    The messaging service expects the current user, a map of the other
    participant's id to username, and the other user's id.
    """
    request_body = {
        "user": {
            "id": current["id"],
            "username": current["username"],
            "status": "active",
        },
        "users": {other["id"]: other["username"]},
        "otherUserId": other["id"],
    }
    client = requests.Session()
    response = messaging_post(client, "/mychats/new", request_body)
    if not response.ok:
        abort(502, "Messaging service could not create the chat")
    chat_id = response.json().get("chatId")
    if not chat_id:
        abort(500, "Failed to create or retrieve chat")

    chats_response = messaging_post(client, "/mychats/me", request_body)
    if not chats_response.ok:
        abort(502, "Messaging service could not load chats")
    chats = chats_response.json().get("chats", [])
    rendered = render_template(
        "messaging.html",
        user=current["id"],
        chats=chats,
        openChat=chat_id,
    )
    return forward_messaging_cookie(make_response(rendered), client)


@bp.get("/messages")
@login_required
def messages():
    client = requests.Session()
    data = messaging_post(client, "/mychats/me", {"user": g.user})
    if not data.ok:
        abort(502, "Messaging service could not load chats")
    rendered = render_template(
        "messaging.html",
        user=g.user["id"],
        chats=data.json().get("chats", []),
    )
    return forward_messaging_cookie(make_response(rendered), client)
