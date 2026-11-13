import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote

import requests
from flask import abort, g, make_response, render_template, request, current_app, Blueprint

from messaging_client import forward_messaging_cookie, messaging_post
from users_client import login_required, open_upstream, upstream_request


bp = Blueprint("messaging", __name__)

def add_chat_usernames(chats):
    """Resolve participant names using the signed-in user's profile access."""
    if not isinstance(chats, list):
        abort(502, "Messaging service returned an invalid chat list")
    usernames = {}
    for chat in chats:
        if not isinstance(chat, dict) or not isinstance(chat.get("otherUserId"), str) or not chat["otherUserId"]:
            abort(502, "Messaging service returned an invalid chat")
        user_id = chat["otherUserId"]
        if user_id not in usernames:
            try:
                path = f"/users/{quote(user_id, safe='')}"
                with open_upstream(upstream_request("USERS_API_URL", path)) as response:
                    profile = json.load(response)
                user = profile.get("user") if isinstance(profile, dict) else None
                if (not isinstance(user, dict) or user.get("id") != user_id
                        or not isinstance(user.get("username"), str) or not user["username"].strip()):
                    raise ValueError("Invalid user profile")
                usernames[user_id] = user["username"]
            except HTTPError as error:
                error.close()
                current_app.logger.warning("Chat participant lookup failed with upstream HTTP status %s", error.code)
                if error.code != 404:
                    abort(502, "Could not load conversation usernames")
                usernames[user_id] = "Unavailable user"
            except (URLError, OSError, ValueError) as error:
                current_app.logger.warning("Chat participant lookup failed (%s)", type(error).__name__)
                abort(502, "Could not load conversation usernames")
        chat["displayName"] = usernames[user_id]
    return chats


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
    if not other.get('id') or not other.get('username'):
        abort(400, 'A tutor is required.')
    if other['id'] == current['id']:
        abort(400, 'You cannot message yourself.')
    request_body = {
        "user": {
            "id": current["id"],
            "username": current["username"],
            "status": "active",
        },
        "users": {other["id"]: other["username"]},
        "otherUserId": other["id"],
    }
    current_app.logger.warning("Creating chat with request body: %s", request_body) 
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
    chats = add_chat_usernames(chats_response.json().get("chats", []))
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
        chats=add_chat_usernames(data.json().get("chats", [])),
    )
    return forward_messaging_cookie(make_response(rendered), client)
