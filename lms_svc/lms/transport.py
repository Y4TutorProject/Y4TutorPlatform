"""Direct HTTPS to validated public IPs, with TLS verified against the hostname."""
import http.client
from contextlib import contextmanager
import ipaddress
import re
import socket
from urllib.error import HTTPError
from urllib.parse import urlsplit

from .interfaces import LMSImportError


def public_address(address):
    ip = ipaddress.ip_address(address)
    # Reject transition mechanisms and known platform metadata/virtual addresses.
    return (ip.is_global and not ip.is_multicast
            and address != "168.63.129.16"
            and not (isinstance(ip, ipaddress.IPv6Address)
                     and (ip.ipv4_mapped or ip.sixtofour or ip.teredo
                          or ip in ipaddress.ip_network("64:ff9b::/96")
                          or ip in ipaddress.ip_network("64:ff9b:1::/48"))))


def validate_url(url, allowed_hosts=(), private_hosts=()):
    if not isinstance(url, str) or not url or len(url) > 2048 or any(ord(c) <= 32 or ord(c) == 127 for c in url) or "\\" in url:
        raise ValueError("Enter a public HTTPS LMS base URL.")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != "https" or not host or parsed.port not in (None, 443)
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or parsed.path.startswith("//")):
            raise ValueError()
        host = host.encode("idna").decode("ascii").lower()
        if "%" in host:
            raise ValueError()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if ("." not in host or (host.endswith(".") or (host.endswith((".localhost", ".local", ".internal")) and host not in private_hosts))
                    or len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split("."))):
                raise ValueError()
        else:
            if not public_address(host):
                raise ValueError()
        if allowed_hosts and host not in allowed_hosts:
            raise ValueError()
    except (ValueError, UnicodeError):
        raise ValueError("Use a public HTTPS LMS URL on port 443 permitted by the endpoint policy.") from None
    netloc = f"[{host}]" if ":" in host else host
    return parsed._replace(netloc=netloc).geturl().rstrip("/")


def resolve_public(host, port, private_hosts=()):
    results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    def permitted(address):
        ip = ipaddress.ip_address(address)
        return public_address(address) or (host in private_hosts and ip.is_private
            and not (ip.is_loopback or ip.is_link_local or ip.is_unspecified
                     or ip.is_multicast or ip.is_reserved or getattr(ip, "ipv4_mapped", None)))
    if not results or any(not permitted(row[4][0]) for row in results):
        raise LMSImportError("LMS hostname must resolve only to public internet addresses.")
    return results


class PublicHTTPSConnection(http.client.HTTPSConnection):
    private_hosts = ()

    def connect(self):
        # Validate all answers, then use the numeric sockaddr directly: no second
        # DNS lookup between validation and connection. SNI/verification use host.
        addresses = resolve_public(self.host, self.port, self.private_hosts)
        for family, kind, protocol, _, address in addresses:
            sock = socket.socket(family, kind, protocol)
            try:
                sock.settimeout(self.timeout)
                sock.connect(address)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError:
                sock.close()
        raise OSError("Unable to connect to the public LMS endpoint.")


class PublicHTTPSOpener:
    def __init__(self, private_hosts=(), ca_file=None):
        self.private_hosts = frozenset(private_hosts)
        self.ca_file = ca_file

    @contextmanager
    def open(self, request, timeout):
        url = validate_url(request.full_url, private_hosts=self.private_hosts)
        parsed = urlsplit(url)
        connection = PublicHTTPSConnection(parsed.hostname, 443, timeout=timeout)
        connection.private_hosts = self.private_hosts
        if self.ca_file:
            connection._context.load_verify_locations(cafile=self.ca_file)
        try:
            connection.request(request.get_method(), parsed.path or "/", body=request.data, headers=dict(request.header_items()))
            response = connection.getresponse()
            if not 200 <= response.status < 300:
                response.close()
                raise HTTPError(url, response.status, "LMS request rejected", {}, None)
            try:
                yield response
            finally:
                response.close()
        finally:
            connection.close()
