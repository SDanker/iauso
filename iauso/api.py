"""Read-only WSGI API and HTTP client for the Raspberry Pi.

The API only opens the public snapshot. It has no access to provider
credentials and never triggers upstream queries when serving a request.
"""

import hmac
import json
import os
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .providers import NoRedirects, UsageError, validate_snapshot
from .storage import MAX_JSON, read_json


def validate_api_url(url, allow_http=False):
    if not isinstance(url, str) or not url or any(c.isspace() for c in url):
        raise ValueError("api_url must be a URL without whitespace")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
        if (parsed.scheme not in (("https", "http") if allow_http else ("https",))
                or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path != "/v1/usage" or port == 0):
            raise ValueError()
    except ValueError:
        raise ValueError("Use https://server/v1/usage; HTTP requires api_allow_http=true") from None
    return url


def read_api_token(filename):
    try:
        with Path(filename).open("r", encoding="ascii") as handle:
            raw = handle.read(130)
        if len(raw) >= 130:
            raise ValueError()
        token = raw.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
            raise ValueError()
        return token
    except (OSError, ValueError, UnicodeError):
        raise ValueError("Missing a valid key in api_token_file (32 to 128 URL-safe characters)") from None


def fetch_snapshot(config):
    """GET a single destination, over TLS and without following redirects."""
    url = validate_api_url(config["api_url"], config["api_allow_http"])
    token = read_api_token(config["api_token_file"])
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json", "Cache-Control": "no-cache",
        "User-Agent": "iauso/1.2",
    })
    opener = urllib.request.build_opener(NoRedirects())
    try:
        with opener.open(request, timeout=config["http_timeout_seconds"]) as response:
            if response.status != 200:
                raise UsageError("offline", "Unexpected API response")
            raw = response.read(MAX_JSON + 1)
        if len(raw) > MAX_JSON:
            raise ValueError()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        if status in (401, 403):
            raise UsageError("offline", "API 401/403: check the panel key") from None
        raise UsageError("offline", "API unavailable; redirects are not followed") from None
    except (urllib.error.URLError, OSError, socket.timeout, ssl.SSLError):
        raise UsageError("offline", "Could not connect to the API") from None
    except (ValueError, UnicodeError):
        raise UsageError("offline", "The API did not return valid JSON") from None


class QuotaAPI:
    def __init__(self, snapshot_file, token_file, stale_after=900, clock=time.time):
        self.snapshot_file = snapshot_file
        self.token_file = token_file
        self.stale_after = stale_after
        self.clock = clock

    def __call__(self, environ, start_response):
        def reply(code, data, extra=()):
            body = json.dumps(data, allow_nan=False, separators=(",", ":")).encode()
            headers = [("Content-Type", "application/json; charset=utf-8"),
                       ("Content-Length", str(len(body))),
                       ("Cache-Control", "private, no-store, max-age=0"),
                       ("X-Content-Type-Options", "nosniff"),
                       # Safe with "*": it requires Bearer and uses no cookies/credentials.
                       ("Access-Control-Allow-Origin", "*")]
            start_response(code, headers + list(extra))
            return [body]

        method = environ.get("REQUEST_METHOD")
        if method == "OPTIONS":
            # CORS preflight; the real request still requires the Bearer token.
            start_response("204 No Content", [
                ("Content-Length", "0"), ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "GET, OPTIONS"),
                ("Access-Control-Allow-Headers", "Authorization"),
                ("Access-Control-Max-Age", "600"),
            ])
            return [b""]
        if method != "GET":
            return reply("405 Method Not Allowed", {"error": "method_not_allowed"}, (("Allow", "GET, OPTIONS"),))
        path = environ.get("PATH_INFO", "")
        if path == "/healthz":
            # Liveness only; 200 implies neither valid sessions nor fresh data.
            return reply("200 OK", {"status": "up"})
        try:
            expected = "Bearer " + read_api_token(self.token_file)
        except ValueError:
            return reply("503 Service Unavailable", {"error": "api_not_configured"})
        supplied = environ.get("HTTP_AUTHORIZATION", "")
        if not isinstance(supplied, str) or not supplied.isascii() or not hmac.compare_digest(supplied, expected):
            return reply("401 Unauthorized", {"error": "unauthorized"}, (("WWW-Authenticate", "Bearer"),))
        if path != "/v1/usage":
            return reply("404 Not Found", {"error": "not_found"})
        if environ.get("QUERY_STRING"):
            return reply("400 Bad Request", {"error": "query_not_supported"})
        try:
            # Staleness is recomputed even if the collector has stopped.
            data = validate_snapshot(read_json(self.snapshot_file), self.clock(), self.stale_after)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return reply("503 Service Unavailable", {"error": "snapshot_unavailable"})
        return reply("200 OK", data)


def create_app():
    stale_after = int(os.environ.get("APP_STALE_AFTER_SECONDS", "900"))
    if not 300 <= stale_after <= 86400:
        raise ValueError("APP_STALE_AFTER_SECONDS fuera de rango")
    token_file = os.environ.get("APP_API_TOKEN_FILE", "/run/secrets/api_token")
    read_api_token(token_file)  # Error de arranque sin clave; nunca un modo abierto.
    return QuotaAPI(os.environ.get("APP_SNAPSHOT_FILE", "/public/snapshot.json"),
                    token_file, stale_after)
