"""Minimal REST client for the SolarWinds Observability SaaS API.

Configuration is read from environment variables:

- ``SWO_TOKEN`` (required): API Access token, sent as a Bearer token.
- ``SWO_REGION`` (optional): data center, default ``na-01``.
- ``SWO_BASE_URL`` (optional): full base URL, overrides ``SWO_REGION``.

The token is never printed or included in error messages.
"""

import os
import time
from urllib.parse import parse_qs, urlparse

import requests

DEFAULT_REGION = "na-01"
TOKEN_ENV = "SWO_TOKEN"
REGION_ENV = "SWO_REGION"
BASE_URL_ENV = "SWO_BASE_URL"

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5
DEFAULT_TIMEOUT = 30


class MissingTokenError(RuntimeError):
    """Raised when ``SWO_TOKEN`` is not set."""


class SwoApiError(RuntimeError):
    """Raised when the API returns an unsuccessful response."""

    def __init__(self, status_code, message):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code


def base_url_from_env(environ=None):
    """Return the API base URL from the environment."""
    environ = os.environ if environ is None else environ
    if environ.get(BASE_URL_ENV):
        return environ[BASE_URL_ENV].rstrip("/")
    region = environ.get(REGION_ENV) or DEFAULT_REGION
    return f"https://api.{region}.cloud.solarwinds.com/v1"


class SwoClient:
    """Authenticated session against the SWO REST API with retry and pagination."""

    def __init__(self, token=None, base_url=None, session=None, timeout=DEFAULT_TIMEOUT, sleep=time.sleep):
        token = token if token is not None else os.environ.get(TOKEN_ENV)
        if not token:
            raise MissingTokenError(f"Environment variable {TOKEN_ENV} is not set.")
        self.base_url = (base_url or base_url_from_env()).rstrip("/")
        self.timeout = timeout
        self._sleep = sleep
        self.session = session or requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        )

    def get(self, path, params=None):
        """GET ``path`` (relative to the base URL) and return the decoded JSON body."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException:
                if attempt == MAX_ATTEMPTS:
                    raise
                self._sleep(min(2 ** attempt, 30))
                continue
            if response.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                self._sleep(self._backoff_seconds(response, attempt))
                continue
            if not response.ok:
                raise SwoApiError(response.status_code, _error_text(response))
            return response.json()
        raise AssertionError("unreachable")  # pragma: no cover

    def paginate(self, path, items_key, params=None):
        """Yield every item from a paginated list endpoint.

        Follows ``pageInfo.nextPage`` (passed back as ``skipToken``) until the
        API returns an empty token.
        """
        query = dict(params or {})
        while True:
            body = self.get(path, params=query)
            yield from body.get(items_key, [])
            next_page = (body.get("pageInfo") or {}).get("nextPage")
            if not next_page:
                return
            # nextPage is a full path with its query string; only its skipToken is sent back.
            query["skipToken"] = parse_qs(urlparse(next_page).query)["skipToken"][0]

    @staticmethod
    def _backoff_seconds(response, attempt):
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            return int(retry_after)
        return min(2 ** attempt, 30)


def _error_text(response):
    try:
        body = response.json()
    except ValueError:
        return response.reason or "request failed"
    if isinstance(body, dict):
        return body.get("message") or body.get("error") or response.reason or "request failed"
    return response.reason or "request failed"
