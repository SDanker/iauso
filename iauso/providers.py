"""Quota reading, based on the MIT adapters from vinzdg/codenotch.

Usage GET requests only. The official tools own their credentials and their
renewal. No conversations are ever generated and no API keys are used.
"""

import base64
import hashlib
import json
import math
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from .storage import MAX_JSON, read_json

ENDPOINTS = {
    "claude": "https://api.anthropic.com/api/oauth/usage",
    "codex": "https://chatgpt.com/backend-api/wham/usage",
}
STATUSES = {"ok", "needs_auth", "expired", "rate_limited", "offline", "error", "no_data", "disabled", "stale"}


class UsageError(Exception):
    def __init__(self, status, message, retry_after=0):
        super().__init__(message)
        self.status, self.message, self.retry_after = status, message, retry_after


@dataclass(repr=False)
class Credential:
    access_token: str = field(repr=False)
    account_id: str = field(default="", repr=False)

    @property
    def tag(self):
        # Account/token change: never attribute an earlier reading to it.
        return hashlib.sha256((self.account_id + "\0" + self.access_token).encode()).hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError("Invalid number")
    return value


def percent(value):
    val = number(value)
    if not 0 <= val <= 100:
        raise ValueError("Percentage out of range")
    return float(val)


def timestamp(value):
    if value is None:
        return None
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Date without timezone")
        value = parsed.timestamp()
    value = number(value)
    if not 0 <= value <= 32_503_680_000:
        raise ValueError("Date out of range")
    return float(value)


def _jwt_expiry(token):
    try:
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        return timestamp(claims.get("exp"))
    except (IndexError, ValueError, TypeError, AttributeError):
        return None  # Solo es una pista local; la validacion la hace el servidor.


def load_credential(provider, options, now=None):
    now = time.time() if now is None else now
    try:
        path = Path(options["credentials_file"])
        # Explicit keychain service for collector mode on Mac.
        if provider == "claude" and sys.platform == "darwin" and options.get("keychain_service"):
            proc = subprocess.run(
                ["/usr/bin/security", "find-generic-password", "-s", options["keychain_service"], "-w"],
                capture_output=True, timeout=20, check=True,
            )
            if len(proc.stdout) > MAX_JSON:
                raise ValueError()
            data = json.loads(proc.stdout)
        else:
            data = read_json(path)
        if provider == "claude":
            oauth = data["claudeAiOauth"]
            token = oauth["accessToken"]
            expiry = timestamp(number(oauth["expiresAt"]) / 1000) if oauth.get("expiresAt") is not None else None
            account = ""
        else:
            oauth = data["tokens"]
            token, account = oauth["access_token"], oauth["account_id"]
            if not isinstance(account, str) or not account.strip():
                raise ValueError()
            expiry = _jwt_expiry(token)
        if not isinstance(token, str) or not token.strip() or "\n" in token or "\r" in token:
            raise ValueError()
        if "\n" in account or "\r" in account:
            raise ValueError()
        if expiry is not None and expiry <= now:
            raise UsageError("expired", "Renew the session in the official tool")
        return Credential(token, account)
    except UsageError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        raise UsageError("needs_auth", "Sign in or check the credentials file") from None


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Tokens may only travel to their provider fixed HTTPS endpoint.
        return None


def retry_seconds(header, now):
    if not header:
        return 0
    try:
        value = float(header)
        return max(0, value) if math.isfinite(value) else 0
    except (ValueError, TypeError):
        try:
            return max(0, parsedate_to_datetime(header).timestamp() - now)
        except (ValueError, TypeError, OverflowError):
            return 0


def fetch_usage(provider, credential, timeout=15):
    headers = {
        "Authorization": "Bearer " + credential.access_token,
        "Accept": "application/json", "Cache-Control": "no-cache, no-store",
        "User-Agent": "iauso/1.0 (usage monitor)",
    }
    if provider == "claude":
        headers["anthropic-beta"] = "oauth-2025-04-20"
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["ChatGPT-Account-Id"] = credential.account_id
    request = urllib.request.Request(ENDPOINTS[provider], headers=headers, method="GET")
    opener = urllib.request.build_opener(NoRedirects())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_JSON + 1)
        if len(raw) > MAX_JSON:
            raise ValueError()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except urllib.error.HTTPError as exc:
        code = exc.code
        retry = retry_seconds(exc.headers.get("Retry-After"), time.time())
        exc.close()  # Nunca registrar el cuerpo de una respuesta autenticada.
        if code in (401, 403):
            raise UsageError("needs_auth", "Session rejected; open the official tool") from None
        if code == 429:
            raise UsageError("rate_limited", "Provider asked to wait", retry) from None
        raise UsageError("error", f"HTTP {code} response") from None
    except (urllib.error.URLError, socket.timeout, TimeoutError, ssl.SSLError, OSError):
        raise UsageError("offline", "Could not query the provider") from None
    except (ValueError, TypeError):
        raise UsageError("error", "Unrecognized usage response") from None


def duration_label(seconds, fallback):
    if seconds is None:
        return fallback
    seconds = number(seconds)
    if seconds <= 0:
        return fallback
    if seconds < 3600:
        return f"{seconds / 60:g} min"
    if seconds < 86400:
        return f"{seconds / 3600:g} h"
    return f"{seconds / 86400:g} d"


def parse_codex(data, now):
    # Excludes code_review_rate_limit and additional_rate_limits, as Codenotch does.
    rate = data.get("rate_limit")
    if rate is None:
        return []
    if not isinstance(rate, dict):
        raise ValueError("invalid rate_limit")
    result = []
    for key in ("primary", "secondary"):
        window = rate.get(key + "_window")
        if window is None:
            continue
        reset = timestamp(window.get("reset_at"))
        if reset is None and window.get("reset_after_seconds") is not None:
            reset = timestamp(now + number(window["reset_after_seconds"]))
        result.append({"id": key,
                       "label": duration_label(window.get("limit_window_seconds"), "Primary" if key == "primary" else "Other quota"),
                       "used_percent": percent(window["used_percent"]), "resets_at": reset})
    return result


def parse_claude(data, now):
    labels = {"session": "5 h", "weekly_all": "7 d", "weekly_opus": "Opus 7 d", "weekly_sonnet": "Sonnet 7 d"}
    result = {}
    limits = data.get("limits")
    if limits is not None:
        if not isinstance(limits, list):
            raise ValueError("invalid limits")
        for item in limits:
            key = item["kind"]
            if not isinstance(key, str):
                raise ValueError("invalid kind")
            result[key] = {"id": key, "label": labels.get(key, key),
                           "used_percent": percent(item["percent"]), "resets_at": timestamp(item.get("resets_at"))}
    # Merges both formats; the list may omit a window that just reset.
    for field_name, key in (("five_hour", "session"), ("seven_day", "weekly_all"),
                            ("seven_day_opus", "weekly_opus"), ("seven_day_sonnet", "weekly_sonnet")):
        window = data.get(field_name)
        if window is not None and key not in result:
            result[key] = {"id": key, "label": labels[key], "used_percent": percent(window["utilization"]),
                           "resets_at": timestamp(window.get("resets_at"))}
    # null/missing never becomes 0%; billing extras are not quota.
    return sorted(result.values(), key=lambda w: (0 if w["id"] == "session" else 1 if w["id"] == "weekly_all" else 2, w["id"]))


def empty_provider(status="no_data"):
    return {"status": status, "windows": [], "updated_at": None, "message": ""}


def collect(config, state, now=None, fetcher=fetch_usage, credential_loader=load_credential):
    now = time.time() if now is None else now
    providers = state.setdefault("providers", {})
    for provider in ("claude", "codex"):
        options = config[provider]
        if not options["enabled"]:
            providers[provider] = empty_provider("disabled")
            continue
        previous = providers.setdefault(provider, empty_provider())
        # The normal interval is persisted too, so restarts do not trigger queries.
        if previous.get("retry_at", 0) > now:
            continue
        try:
            credential = credential_loader(provider, options, now)
            if previous.get("credential_tag") != credential.tag:
                previous = providers[provider] = {**empty_provider(), "credential_tag": credential.tag}
            data = fetcher(provider, credential, config["http_timeout_seconds"])
            windows = (parse_claude if provider == "claude" else parse_codex)(data, now)
            providers[provider] = {
                "status": "ok" if windows else "no_data", "windows": windows, "updated_at": now,
                "message": "" if windows else "The provider reports no quota",
                "credential_tag": credential.tag, "failures": 0, "retry_at": now + config["poll_seconds"],
            }
        except (ValueError, KeyError, TypeError, AttributeError, UsageError) as exc:
            error = exc if isinstance(exc, UsageError) else UsageError("error", "Unrecognized quota format")
            failures = min(20, previous.get("failures", 0) + 1)
            delay = max(config["poll_seconds"], min(900, 60 * 2 ** (failures - 1)), error.retry_after)
            previous.update(status=error.status, message=error.message, failures=failures, retry_at=now + delay)
    return public_snapshot(state, now, config["stale_after_seconds"])


def public_snapshot(state, now, stale_after):
    result = {"schema_version": 1, "generated_at": now, "demo": False, "providers": {}}
    for provider in ("claude", "codex"):
        data = state.get("providers", {}).get(provider, empty_provider())
        updated = data.get("updated_at")
        status = data["status"]
        if status == "ok" and (updated is None or now - updated > stale_after):
            status = "stale"
        # Allowlist: never export credentials, account identifiers or HTTP bodies.
        result["providers"][provider] = {"status": status, "updated_at": updated, "windows": data.get("windows", [])}
    return result


def validate_snapshot(raw, now, stale_after):
    if raw.get("schema_version") != 1 or raw.get("demo") is not False:
        raise ValueError("A real version 1 snapshot is required")
    generated = timestamp(raw.get("generated_at"))
    if generated is None or generated > now + 120:
        raise ValueError("Invalid snapshot time; check NTP")
    result = {"schema_version": 1, "generated_at": generated, "demo": False, "providers": {}}
    for provider in ("claude", "codex"):
        item = raw["providers"][provider]
        status = item["status"]
        if status not in STATUSES:
            raise ValueError("Unknown status")
        updated = timestamp(item.get("updated_at"))
        if updated is not None and updated > generated + 120:
            raise ValueError("Data from the future")
        windows = []
        for window in item["windows"]:
            if len(windows) >= 20:
                raise ValueError("Too many windows")
            if not all(isinstance(window[k], str) and 0 < len(window[k]) <= 64 for k in ("id", "label")):
                raise ValueError("Invalid quota label")
            windows.append({"id": window["id"], "label": window["label"],
                            "used_percent": percent(window["used_percent"]), "resets_at": timestamp(window.get("resets_at"))})
        if status == "ok" and (updated is None or now - updated > stale_after or now - generated > stale_after):
            status = "stale"
        if status == "ok" and not windows:
            status = "no_data"
        result["providers"][provider] = {"status": status, "updated_at": updated, "windows": windows}
    return result


def demo_snapshot(now=None):
    now = time.time() if now is None else now
    state = {"providers": {}}
    for provider, ids, values in (("claude", ("session", "weekly_all"), (74, 92)),
                                  ("codex", ("primary", "secondary"), (42, 18))):
        state["providers"][provider] = {"status": "ok", "updated_at": now, "windows": [
            {"id": ids[0], "label": "5 h", "used_percent": values[0], "resets_at": now + 7200},
            {"id": ids[1], "label": "7 d", "used_percent": values[1], "resets_at": now + 3 * 86400},
        ]}
    result = public_snapshot(state, now, 900)
    result["demo"] = True
    return result
