"""Configuration defaults and validation for config.json."""

import os
from pathlib import Path
from zoneinfo import ZoneInfo

from .storage import read_json

DEFAULT = {
    "source": "local",
    "timezone": "America/Santiago",
    "language": "en",
    "display": "epd",
    "panel": "2.15g",
    "rotation": 0,
    "state_dir": "~/.local/state/iauso",
    "snapshot_file": "~/.local/state/iauso/inbox.json",
    "api_url": "",
    "api_token_file": "~/.config/iauso/api-token",
    "api_allow_http": False,
    "poll_seconds": 300,
    "min_refresh_seconds": 180,
    "stale_after_seconds": 900,
    "http_timeout_seconds": 15,
    "busy_timeout_seconds": 60,
    "claude": {"enabled": True, "credentials_file": "", "keychain_service": ""},
    "codex": {"enabled": True, "credentials_file": ""},
    "claude_windows": ["session", "weekly_all"],
    "codex_windows": ["primary", "secondary"],
    # Bar color thresholds, as percentage used. Below warn_percent the bar is
    # black; from warn_percent it uses the warning color and from crit_percent
    # the critical one. See docs/CONFIGURATION.md.
    "warn_percent": 70,
    "crit_percent": 90,
}


def load_config(filename=None):
    import copy
    config = copy.deepcopy(DEFAULT)
    if filename:
        data = read_json(filename)
        unknown = set(data) - set(DEFAULT)
        if unknown:
            raise ValueError("Unknown options in configuration: " + ", ".join(sorted(unknown)))
        for key, value in data.items():
            if key in ("claude", "codex"):
                if not isinstance(value, dict) or set(value) - set(config[key]):
                    raise ValueError("Invalid provider configuration")
                config[key].update(value)
            else:
                config[key] = value
    if config["source"] not in ("local", "file", "api"):
        raise ValueError("source must be local, file or api")
    if not isinstance(config["api_allow_http"], bool):
        raise ValueError("api_allow_http must be true or false")
    if config["source"] == "api":
        from .api import validate_api_url
        validate_api_url(config["api_url"], config["api_allow_http"])
    if config["display"] not in ("epd", "png") or config["rotation"] not in (0, 180):
        raise ValueError("display must be epd/png; rotation must be 0/180")
    from .panels import panel_info
    panel_info(config["panel"])
    from .i18n import strings
    strings(config["language"])
    ZoneInfo(config["timezone"])
    for key, low, high in (
        ("poll_seconds", 300, 86400), ("min_refresh_seconds", 180, 86400),
        ("stale_after_seconds", 300, 86400), ("http_timeout_seconds", 1, 30),
        ("busy_timeout_seconds", 20, 90),
    ):
        val = config[key]
        if isinstance(val, bool) or not isinstance(val, int) or not low <= val <= high:
            raise ValueError(f"{key} must be between {low} and {high} seconds")
    for key in ("warn_percent", "crit_percent"):
        val = config[key]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not 0 <= val <= 100:
            raise ValueError(f"{key} must be a percentage between 0 and 100")
    if config["warn_percent"] > config["crit_percent"]:
        raise ValueError("warn_percent cannot be greater than crit_percent")
    for key in ("state_dir", "snapshot_file", "api_token_file"):
        config[key] = str(Path(config[key]).expanduser().resolve())
    for provider in ("claude", "codex"):
        if not isinstance(config[provider]["enabled"], bool):
            raise ValueError("enabled must be true or false")
        path = config[provider]["credentials_file"]
        if not path:
            base = os.environ.get("CLAUDE_CONFIG_DIR" if provider == "claude" else "CODEX_HOME")
            base = Path(base).expanduser() if base else Path.home() / ("." + provider)
            path = base / (".credentials.json" if provider == "claude" else "auth.json")
        config[provider]["credentials_file"] = str(Path(path).expanduser().resolve())
        window_ids = config[provider + "_windows"]
        if not isinstance(window_ids, list) or len(window_ids) != 2 or not all(isinstance(x, str) for x in window_ids):
            raise ValueError("Each provider must select exactly two windows")
    return config
