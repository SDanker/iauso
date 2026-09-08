import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .config import load_config
from .providers import (UsageError, collect, demo_snapshot, empty_provider,
                        load_credential, public_snapshot, validate_snapshot)
from .storage import exclusive_lock, read_json, write_json

LOG = logging.getLogger("iauso")


def read_state(path):
    if not path.exists():
        return {"schema_version": 1, "providers": {}}
    value = read_json(path)
    if value.get("schema_version") != 1 or not isinstance(value.get("providers"), dict):
        raise ValueError("Invalid local state; see the recovery guide")
    return value


def get_snapshot(config, state, now):
    if config["source"] == "local":
        return collect(config, state, now)
    identity = ("api:" + config["api_url"] if config["source"] == "api"
                else "file:" + config["snapshot_file"])
    tag = hashlib.sha256(identity.encode()).hexdigest()
    if state.get("remote_source_tag") != tag:
        state.pop("remote_snapshot", None)
        state["remote_source_tag"] = tag
    try:
        if config["source"] == "api":
            from .api import fetch_snapshot
            raw = fetch_snapshot(config)
        else:
            raw = read_json(config["snapshot_file"])
        snapshot = validate_snapshot(raw, now, config["stale_after_seconds"])
        # An older packet never replaces the latest reading received.
        if snapshot["generated_at"] < state.get("remote_snapshot", {}).get("generated_at", 0):
            raise ValueError("Out-of-order packet")
        state["remote_snapshot"] = snapshot
    except (OSError, ValueError, KeyError, TypeError, AttributeError, UsageError) as exc:
        LOG.warning("No valid snapshot; waiting for the collector")
        if isinstance(exc, UsageError):
            LOG.warning("%s", exc.message)
        raw = state.get("remote_snapshot")
        if raw:
            snapshot = validate_snapshot(raw, now, config["stale_after_seconds"])
            for item in snapshot["providers"].values():
                if item["status"] in ("ok", "stale"):
                    item["status"] = "offline"
        else:
            snapshot = public_snapshot({}, now, config["stale_after_seconds"])
            for item in snapshot["providers"].values():
                item["status"] = "offline"
    for provider in ("claude", "codex"):
        if not config[provider]["enabled"]:
            snapshot["providers"][provider] = empty_provider("disabled")
    return snapshot


def push_snapshot(target, snapshot):
    # The target is an SSH alias or user@host; options/commands are rejected.
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@-]*", target):
        raise ValueError("Invalid SSH target; use user@raspberrypi.local or an SSH alias")
    # Fixed command. JSON data over stdin, never interpolated into the shell.
    command = ('umask 077; mkdir -p "$HOME/.local/state/iauso" && '
               'tmp=$(mktemp "$HOME/.local/state/iauso/.inbox.XXXXXX") && '
               'cat > "$tmp" && mv "$tmp" "$HOME/.local/state/iauso/inbox.json"')
    subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", target, command],
                   input=json.dumps(snapshot, allow_nan=False).encode(), timeout=30, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="AI quota on Waveshare e-ink panels")
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("preview", "refresh", "collect", "doctor"):
        p = sub.add_parser(cmd)
        p.add_argument("--config", help="JSON file; defaults are used when omitted")
        if cmd in ("preview", "refresh"):
            p.add_argument("--demo", action="store_true", help="Fictional data; no sessions read and no Internet queries")
        if cmd == "preview":
            p.add_argument("--output", default="preview.png")
        if cmd == "collect":
            p.add_argument("--output", help="Export the snapshot without secrets")
            p.add_argument("--push", help="Push the snapshot over SSH to user@host")
            p.add_argument("--loop", action="store_true", help="Repeat every poll_seconds")
    worker = sub.add_parser("panel-worker", help=argparse.SUPPRESS)
    worker.add_argument("image")
    worker.add_argument("timeout", type=int)
    worker.add_argument("panel")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    os.umask(0o077)

    if args.command == "panel-worker":
        from PIL import Image
        from .display import send_to_panel
        send_to_panel(Image.open(args.image).convert("RGB"), args.timeout, args.panel)
        return 0
    config = load_config(args.config)
    if args.command == "doctor":
        from .panels import panel_info
        size = panel_info(config["panel"])["size"]
        print(f"Panel: {config['panel']} ({size[0]}x{size[1]}); source:", config["source"])
        if config["display"] == "epd":
            print("SPI0 CE0:", "available" if Path("/dev/spidev0.0").exists() else "not found (enable SPI and reboot)")
        if config["source"] == "local":
            for provider in ("claude", "codex"):
                if not config[provider]["enabled"]:
                    print(provider, "disabled")
                    continue
                try:
                    load_credential(provider, config[provider])
                    print(provider, "local session readable; provider query not tested yet")
                except UsageError as exc:
                    print(provider, exc.status, "-", exc.message)
        elif config["source"] == "api":
            from .api import fetch_snapshot
            try:
                snapshot = validate_snapshot(fetch_snapshot(config), time.time(), config["stale_after_seconds"])
                print("API reachable; Claude:", snapshot["providers"]["claude"]["status"],
                      "Codex:", snapshot["providers"]["codex"]["status"])
            except (UsageError, OSError, ValueError, KeyError, TypeError, AttributeError):
                print("API unavailable or without valid data; check URL, connectivity and panel key")
                return 1
        else:
            print("Snapshot:", "found" if Path(config["snapshot_file"]).exists() else "waiting for the collector")
        return 0

    # The collector runs without Pillow and never touches GPIO; handy elsewhere.
    if args.command == "collect" and config["source"] != "local":
        raise ValueError("The collector requires source=local")
    state_dir = Path(config["state_dir"])
    state_path = state_dir / "state.json"
    while True:
        with exclusive_lock(state_dir / "process.lock"):
            state = read_state(state_path)
            now = time.time()
            demo = getattr(args, "demo", False)
            snapshot = demo_snapshot(now) if demo else get_snapshot(config, state, now)
            # Save the backoff even if the driver or the SSH push fails later.
            write_json(state_path, state)
            if args.command == "collect":
                output = args.output or state_dir / "snapshot.json"
                write_json(output, snapshot)
                if args.push:
                    try:
                        push_snapshot(args.push, snapshot)
                    except (OSError, subprocess.SubprocessError):
                        if not args.loop:
                            raise
                        LOG.warning("SSH push failed; the collector will retry next cycle")
                LOG.info("Quota saved: Claude=%s, Codex=%s", snapshot["providers"]["claude"]["status"], snapshot["providers"]["codex"]["status"])
            else:
                from .render import render
                image = render(snapshot, config, now)
                if args.command == "preview":
                    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                    image.save(args.output)
                    LOG.info("Preview created: %s", args.output)
                else:
                    from .display import display_image
                    result = display_image(image, config, state, state_path, now)
                    LOG.info("Display: %s. Claude=%s, Codex=%s", result, snapshot["providers"]["claude"]["status"], snapshot["providers"]["codex"]["status"])
        if not getattr(args, "loop", False):
            break
        # The wait happens on the user machine, between collector cycles.
        time.sleep(config["poll_seconds"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        # No error ever prints HTTP bodies, environment variables or credentials.
        LOG.error("%s: %s", type(exc).__name__, str(exc))
        raise SystemExit(1)
