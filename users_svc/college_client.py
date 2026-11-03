import json
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, build_opener


class CollegeServiceUnavailable(Exception):
    """Indicate that the college service could not validate a selection."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Prevent redirects away from the configured college API.

        Args:
            req (Request): Original request.
            fp (HTTPResponse): Redirect response.
            code (int): Redirect status.
            msg (str): Redirect message.
            headers (Message): Redirect response headers.
            newurl (str): Proposed redirect URL.

        Returns:
            None: Redirects are not followed.
        """
        return None


class CollegeClient:
    def __init__(self, base_url):
        """Configure the college API client.

        Args:
            base_url (str): Internal base URL of the college service.
        """
        self.base_url = base_url.rstrip("/")
        self.opener = build_opener(NoRedirect())

    def get_college(self, college_id):
        """Read a college from the service that owns college data.

        Args:
            college_id (str): Canonical UUID of the selected college.

        Returns:
            dict | None: Active college details, or None if unavailable for signup.

        Raises:
            CollegeServiceUnavailable: The API is unreachable or returns an
                unexpected response.
        """
        try:
            with self.opener.open(f"{self.base_url}/college/{college_id}", timeout=5) as response:
                data = json.load(response)
        except HTTPError as error:
            error.close()
            if error.code == 404:
                return None
            raise CollegeServiceUnavailable() from None
        except (URLError, OSError, ValueError):
            raise CollegeServiceUnavailable() from None
        if not isinstance(data, dict) or not isinstance(data.get("college"), dict):
            raise CollegeServiceUnavailable()
        college = data["college"]
        if college.get("id") != college_id or college.get("status") != "active":
            raise CollegeServiceUnavailable()
        return college
