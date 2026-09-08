#!/usr/bin/env python3
"""Generate systemd units for the chosen location and user. Does not use sudo."""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from iauso.config import load_config

parser = argparse.ArgumentParser()
parser.add_argument("--project", required=True)
parser.add_argument("--user", required=True)
parser.add_argument("--out", required=True)
args = parser.parse_args()
project = Path(args.project).resolve()
if not re.fullmatch(r"/[a-zA-Z0-9_./-]+", str(project)) or not re.fullmatch(r"[a-z_][a-z0-9_-]*", args.user):
    raise SystemExit("Path or user not allowed in the units")
config = load_config(project / "config.json")
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True, mode=0o700)
(out / "iauso.service").write_text(f"""[Unit]
Description=iauso - Claude and Codex quota on the e-ink panel
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User={args.user}
SupplementaryGroups=gpio spi
WorkingDirectory={project}
ExecStart=/usr/bin/python3 -m iauso refresh --config {project}/config.json
Environment=PYTHONUNBUFFERED=1
Environment=GPIOZERO_PIN_FACTORY=lgpio
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
TimeoutStartSec=180
""", encoding="utf-8")
(out / "iauso.timer").write_text(f"""[Unit]
Description=Refresh the display quota periodically

[Timer]
OnBootSec=45s
OnUnitInactiveSec={config['poll_seconds']}s
AccuracySec=15s
Unit=iauso.service

[Install]
WantedBy=timers.target
""", encoding="utf-8")
print("Units generated.")
