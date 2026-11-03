from urllib.parse import parse_qs, urlsplit

COLLEGE_ID = "4b26466a-a88e-4b45-aa10-cb2b5c744e21"


class MemoryMailer:
    def __init__(self):
        self.messages = []

    def send_verification(self, email, link):
        self.messages.append((email, link))


class ExampleColleges:
    def get_college(self, college_id):
        if college_id == COLLEGE_ID:
            return {"id": COLLEGE_ID, "name": "Example College", "domain": "example.com", "status": "active"}
        return None


def verify_latest(client, mailer):
    token = parse_qs(urlsplit(mailer.messages[-1][1]).fragment)["token"][0]
    csrf = client.get("/auth/csrf").json["csrf_token"]
    return client.post("/auth/verify-email", json={"token": token}, headers={"X-CSRFToken": csrf})
