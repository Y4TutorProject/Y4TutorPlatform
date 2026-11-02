from copy import deepcopy
import ipaddress
import socket
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from lms_svc.lms.interfaces import LMSImportError
from lms_svc.lms.moodle import MoodleProvider
from lms_svc.lms.transport import PublicHTTPSConnection, PublicHTTPSOpener, resolve_public, validate_url
from lms_svc.lms.validation import validate_catalog


@pytest.mark.parametrize("url", ["https://example.edu/moodle", "https://another.edu:443", "https://[2606:4700:4700::1111]/moodle"])
def test_public_urls_do_not_need_host_approval(url):
    assert validate_url(url).startswith("https://")


@pytest.mark.parametrize("url", [
    "http://college.edu", "https://localhost", "https://127.0.0.1", "https://10.0.0.1",
    "https://169.254.169.254", "https://168.63.129.16", "https://100.100.100.200",
    "https://[::1]", "https://[fc00::1]", "https://[::ffff:127.0.0.1]", "https://[64:ff9b::a00:1]", "https://224.0.0.1",
    "https://college.local", "https://college.internal", "https://key@college.edu",
    "https://college.edu:8443", "https://college.edu?key=x", "https://college.edu#fragment",
    "https://college.edu\\@127.0.0.1", "https://college.edu\r\nInjected: value", "https://2130706433",
])
def test_private_and_ambiguous_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_url(url)


def dns_row(address):
    family = socket.AF_INET6 if ipaddress.ip_address(address).version == 6 else socket.AF_INET
    sockaddr = (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)
    return family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr


@pytest.mark.parametrize("addresses", [["10.0.0.2"], ["169.254.169.254"], ["1.1.1.1", "127.0.0.1"], ["2606:4700:4700::1111", "fd00::1"]])
def test_every_dns_answer_must_be_public(monkeypatch, addresses):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [dns_row(ip) for ip in addresses])
    with pytest.raises(LMSImportError, match="public internet"):
        resolve_public("college.edu", 443)


def test_pinned_numeric_connection_uses_original_hostname_for_tls(monkeypatch):
    calls = []
    def dns(*args, **kwargs):
        calls.append("dns")
        return [dns_row("1.1.1.1")]
    class Socket:
        def settimeout(self, timeout):
            assert timeout == 15
        def connect(self, address):
            assert address == ("1.1.1.1", 443)
            calls.append("connect")
        def close(self):
            pass
    class Context:
        def wrap_socket(self, sock, server_hostname):
            assert server_hostname == "college.edu"
            calls.append("tls")
            return sock
    connection = PublicHTTPSConnection("college.edu", timeout=15)
    assert connection._context.check_hostname
    connection._context = Context()
    monkeypatch.setattr(socket, "getaddrinfo", dns)
    monkeypatch.setattr(socket, "socket", lambda *args: Socket())
    connection.connect()
    assert calls == ["dns", "connect", "tls"]
    connection.close()


def test_later_dns_rebinding_is_blocked_before_opening_socket(monkeypatch):
    answers = iter([[dns_row("1.1.1.1")], [dns_row("127.0.0.1")]])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: next(answers))
    assert resolve_public("college.edu", 443)
    def forbid(*args):
        pytest.fail("No socket may be created for the rebound private address")
    monkeypatch.setattr(socket, "socket", forbid)
    with pytest.raises(LMSImportError):
        PublicHTTPSConnection("college.edu").connect()


def test_redirect_is_not_followed_and_connection_is_closed(monkeypatch):
    calls = []
    class Response:
        status = 302
        def close(self):
            calls.append("response closed")
    class Connection:
        def __init__(self, host, port, timeout):
            assert host == "college.edu" and port == 443
        def request(self, method, path, body, headers):
            calls.append("request")
        def getresponse(self):
            return Response()
        def close(self):
            calls.append("connection closed")
    monkeypatch.setattr("lms_svc.lms.transport.PublicHTTPSConnection", Connection)
    with pytest.raises(HTTPError):
        with PublicHTTPSOpener().open(Request("https://college.edu/webservice/rest/server.php", data=b"token"), timeout=15):
            pytest.fail("Redirect must not be returned as a successful response")
    assert calls == ["request", "response closed", "connection closed"]


def test_moodle_write_functions_and_reserved_parameters_are_blocked():
    provider = MoodleProvider("https://college.edu", "token")
    with pytest.raises(LMSImportError, match="not permitted"):
        provider._call("core_user_create_users")
    with pytest.raises(LMSImportError, match="cannot be overridden"):
        provider._call("core_user_get_users", wstoken="replacement")


@pytest.fixture
def catalog():
    return {"users": [{"source_id": "1", "email": "member@college.edu"}],
            "courses": [{"source_id": "2", "name": "Computing", "parent_id": None}],
            "modules": [{"source_id": "3", "name": "Databases", "course_id": "2"}]}


@pytest.mark.parametrize("kind,field,value", [
    ("users", "email", {"$ne": None}), ("users", "email", "invalid"),
    ("users", "username", ["unexpected"]), ("users", "suspended", "false"),
    ("users", "first_name", "x" * 201), ("users", "source_id", 1),
    ("modules", "course_id", "unknown"), ("modules", "name", {"$set": {}}),
    ("courses", "parent_id", "2"), ("courses", "parent_id", "missing"),
])
def test_record_fields_and_relationships_validated(catalog, kind, field, value):
    catalog[kind][0][field] = value
    with pytest.raises(LMSImportError):
        validate_catalog(catalog)


def test_unknown_fields_are_not_persisted_and_duplicates_rejected(catalog):
    catalog["users"][0].update(passhash="not-to-store", roles=["admin"], arbitrary={"nested": "payload"})
    result = validate_catalog(catalog)
    assert "passhash" not in result["users"][0] and "roles" not in result["users"][0]
    assert "arbitrary" not in result["users"][0]
    catalog["modules"].append(deepcopy(catalog["modules"][0]))
    with pytest.raises(LMSImportError):
        validate_catalog(catalog)
