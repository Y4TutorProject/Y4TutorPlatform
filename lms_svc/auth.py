import json

from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class AuthenticationError(Exception):
    def __init__(self, message, status):
        """Create an authentication failure with a public message and HTTP status.

        Args:
            message (str): Public error message.
            status (int): HTTP status associated with the authentication error.
        """
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject redirects so authentication cookies are never forwarded to another
        URL.

        Args:
            req (Request): Original HTTP request.
            fp (HTTPResponse): Response that requested a redirect.
            code (int): Redirect HTTP status code.
            msg (str): Redirect status message.
            headers (Message): Response headers supplied by urllib.
            newurl (str): Proposed redirect destination.

        Returns:
            None: Always None to prevent urllib from following the redirect.
        """
        return None


class UsersAuthClient:
    def __init__(self, base_url):
        """Configure the users API URL and an HTTP client that rejects redirects.

        Args:
            base_url (str): Base URL of the users API, including any gateway prefix.
        """
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(NoRedirect())

    def _request(self, method, path, headers, data=None):
        """Send an authentication request to the users API.

        Args:
            method (str): HTTP request method.
            path (str): API path relative to the configured base URL.
            headers (dict[str, str]): HTTP headers to forward to the users API.
            data (dict | None): Optional JSON request body.

        Returns:
            tuple[int, dict]: HTTP status and JSON response body.

        Raises:
            AuthenticationError: The users API cannot be reached; the error has HTTP
                status 503.
        """
        body = json.dumps(data).encode() if data is not None else None
        if body is not None:
            headers = {**headers, "Content-Type": "application/json"}
        request = Request(self.base_url + path, headers=headers, method=method, data=body)
        try:
            with self.opener.open(request, timeout=5) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            error.close()
            return error.code, {}
        except (URLError, OSError, ValueError):
            raise AuthenticationError("Authentication service temporarily unavailable.", 503) from None

    def authenticate(self, session_cookie, user_agent):
        """Authenticate a read-only request against the current users session."""
        if not session_cookie:
            raise AuthenticationError("Authentication required.", 401)
        cookie = SimpleCookie()
        cookie["tutor_session"] = session_cookie
        headers = {"Cookie": cookie.output(header="").strip(), "User-Agent": user_agent}
        status, data = self._request("GET", "/users/me", headers)
        if status == 401:
            raise AuthenticationError("Authentication required.", 401)
        if status != 200:
            raise AuthenticationError("Authentication service temporarily unavailable.", 503)
        user = data.get("user")
        if not isinstance(user, dict) or not user.get("email_verified"):
            raise AuthenticationError("Authentication required.", 401)
        return user

    def verify(self, session_cookie, user_agent, csrf_token):
        """Verify the users session and its CSRF token before a college write.

        Forward the session cookie and original user agent to preserve session
        binding.

        Args:
            session_cookie (str | None): Value of the tutor_session cookie.
            user_agent (str): Original client user agent used for session binding.
            csrf_token (str | None): CSRF token supplied in the X-CSRFToken header.

        Returns:
            dict: Verified user details.

        Raises:
            AuthenticationError: The session is invalid or inactive (401), CSRF
                validation fails (400), or the users service cannot verify the
                request (503).
        """
        if not session_cookie:
            raise AuthenticationError("Authentication required.", 401)
        cookie = SimpleCookie()
        cookie["tutor_session"] = session_cookie
        headers = {"Cookie": cookie.output(header="").strip(), "User-Agent": user_agent}
        # Check authentication first so an anonymous request returns 401 even
        # when it has no CSRF token. The users service checks active accounts.
        status, data = self._request("GET", "/users/me", headers)
        if status == 401:
            raise AuthenticationError("Authentication required.", 401)
        if status != 200:
            raise AuthenticationError("Authentication service temporarily unavailable.", 503)
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token
        status, data = self._request("POST", "/auth/verify", headers)
        if status == 401:
            raise AuthenticationError("Authentication required.", 401)
        if status == 400:
            raise AuthenticationError("Missing, invalid, or expired CSRF token.", 400)
        if status != 200:
            raise AuthenticationError("Authentication service temporarily unavailable.", 503)

        user = data.get("user")
        if not isinstance(user, dict) or not user.get("email_verified"):
            raise AuthenticationError("Authentication required.", 401)
        return user

