# Server without Docker

This is an alternative to [DOCKER_API.md](DOCKER_API.md) for anyone who does not
want, or cannot use, Docker on the server. The `collector` and the `api` are
ordinary Python processes — here they run directly under `systemd` instead of in
containers.

**You lose the isolation Docker gives you** (namespaces, `read_only`,
`cap_drop`, per-service memory limits). This guide rebuilds the part that
matters most — that the process serving HTTP to the Internet cannot read your
Claude/Codex sessions — with two separate Linux users and file permissions, but
it is not equivalent to a container. If you can use Docker, use it.

## 1. Prepare the project

You need Linux with Python 3.11+ and `venv`. With the project already in
`~/iauso` (`git clone` or the extracted ZIP):

```bash
cd ~/iauso
python3 -m venv .venv
.venv/bin/pip install -r requirements-server.txt
mkdir -p server-state secrets
chmod 700 secrets
```

`requirements-server.txt` only brings Gunicorn — the project has no other
dependencies on the server.

## 2. Sign in to Claude and Codex

Install the official CLIs (`@anthropic-ai/claude-code`, `@openai/codex`) on the
server **with the same user that will run the `collector`** and sign in normally
(`claude auth login`, `codex login --device-auth`). Their memory requirements are
independent of the panel; check the server has enough RAM (Anthropic publishes
4 GB for Claude Code).

This is the same mechanism as the "local queries" section of the README — the
project only reads the files those CLIs already store
(`~/.claude/.credentials.json`, `~/.codex/auth.json`); it never asks them for an
API key.

## 3. Separate the user that serves HTTP

So the Internet-facing process has no way to read those credentials, give it its
own login-less user:

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin iauso-api
sudo groupadd iauso-panel
sudo usermod -aG iauso-panel "$(whoami)"
sudo usermod -aG iauso-panel iauso-api
```

The `iauso-panel` group is the only bridge between the two: the `collector`
(as your user) writes the public snapshot and the panel key there; the `api`
(as `iauso-api`) can only read them.

```bash
cd ~/iauso
chgrp iauso-panel server-state secrets
chmod 750 server-state secrets
python3 -c "import secrets,pathlib; p=pathlib.Path('secrets/api-token'); p.write_text(secrets.token_urlsafe(32)+chr(10))"
chmod 640 secrets/api-token
chgrp iauso-panel secrets/api-token
```

Log out and back in (or `newgrp iauso-panel`) so your user picks up the new
group before continuing.

## 4. Collector configuration

Copy your local config (the same idea as `docker/config.collector.json`, but
with `source: "local"` and your user's real paths):

```json
{
  "source": "local",
  "state_dir": "/home/YOUR_USER/iauso/server-state",
  "claude": {"enabled": true},
  "codex": {"enabled": true}
}
```

Save it as `server-config.json`. Test it before installing the service:

```bash
.venv/bin/python -m iauso doctor --config server-config.json
```

## 5. The two systemd units

Replace `YOUR_USER` and the path in both files.

`/etc/systemd/system/iauso-collector.service`:

```ini
[Unit]
Description=iauso collector
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/iauso
ExecStart=/home/YOUR_USER/iauso/.venv/bin/python -m iauso collect --config server-config.json --loop --output /home/YOUR_USER/iauso/server-state/snapshot.json
Restart=on-failure
RestartSec=15
NoNewPrivileges=yes
PrivateTmp=yes
UMask=0027

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/iauso-api.service`:

```ini
[Unit]
Description=iauso API
After=network-online.target iauso-collector.service

[Service]
Type=simple
User=iauso-api
Group=iauso-panel
WorkingDirectory=/home/YOUR_USER/iauso
Environment=APP_SNAPSHOT_FILE=/home/YOUR_USER/iauso/server-state/snapshot.json
Environment=APP_API_TOKEN_FILE=/home/YOUR_USER/iauso/secrets/api-token
Environment=APP_STALE_AFTER_SECONDS=900
ExecStart=/home/YOUR_USER/iauso/.venv/bin/gunicorn --bind 127.0.0.1:8080 --workers 2 --threads 2 --timeout 20 --access-logfile - iauso.api:create_app()
Restart=on-failure
RestartSec=15
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=read-only
ProtectSystem=strict

[Install]
WantedBy=multi-user.target
```

`ProtectHome=read-only` + `ProtectSystem=strict` on the API are the extra safety
net: even if someone managed to run code inside that process, the filesystem is
read-only except `/tmp` (`PrivateTmp`). The `collector` does not carry those
restrictions because it needs to write to `server-state/`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now iauso-collector.service
sudo systemctl enable --now iauso-api.service
```

**If `iauso-api` will not even start** (`status=203/EXEC` or similar in
`journalctl`), check that it can traverse your home folder: being a user
unrelated to yours, it needs traverse permission (not read) on
`/home/YOUR_USER`:

```bash
chmod o+x /home/YOUR_USER
```

That does not expose the contents of your home (`ls` still fails for other
users), it only allows traversing it to reach paths they already know. If you
prefer not to touch your home permissions, install the project in
`/opt/iauso` (owned `root:iauso-panel`, `750`) instead of `~/iauso` and adjust
the paths in this section.

## 6. Verify

```bash
curl http://127.0.0.1:8080/healthz
curl -H "Authorization: Bearer $(cat secrets/api-token)" http://127.0.0.1:8080/v1/usage
journalctl -u iauso-collector -n 30 --no-pager
journalctl -u iauso-api -n 30 --no-pager
```

You should see `{"status":"up"}` and, shortly after the `collector` makes its
first reading, a JSON with `Claude`/`Codex` set to `ok`.

From here on, everything [DOCKER_API.md](DOCKER_API.md) says about publishing the
API (HTTPS with Tailscale, a proxy, a Cloudflare Tunnel, etc.), taking the key to
the Raspberry Pi and configuring `config.json` there, is identical — the Pi
neither knows nor cares whether the server runs in Docker.

## Keeping the sessions alive

The collector only reads credentials; renewing them is the official CLIs' job.
The Claude access token lasts about **8 hours** (Codex's, about 10 days), so on
a server where nobody ever runs those CLIs the panel gets stuck on
`RENEW SESSION` a few hours after every login.

With Docker this is handled by the `refresher` service. Here, run the same loop
from a timer, as the user that owns the sessions:

```ini
# /etc/systemd/system/iauso-refresh.service
[Unit]
Description=Renew the iauso provider sessions
[Service]
Type=oneshot
User=YOUR_USER
Environment=CLAUDE_CONFIG_DIR=/home/YOUR_USER/.claude
Environment=CLAUDE_CREDENTIALS=/home/YOUR_USER/.claude/.credentials.json
Environment=CODEX_CREDENTIALS=/home/YOUR_USER/.codex/auth.json
ExecStart=/usr/bin/bash /home/YOUR_USER/iauso/scripts/refresh_loop.sh --once
```

```ini
# /etc/systemd/system/iauso-refresh.timer
[Unit]
Description=Renew the iauso provider sessions periodically
[Timer]
OnBootSec=10min
OnUnitActiveSec=30min
[Install]
WantedBy=timers.target
```

```bash
sudo systemctl enable --now iauso-refresh.timer
```

## Rotating the panel key

Without `scripts/init_server.py` (designed for Docker/UID 1000), rotate it by
hand:

```bash
python3 -c "import secrets,pathlib; p=pathlib.Path('secrets/api-token'); p.write_text(secrets.token_urlsafe(32)+chr(10))"
chmod 640 secrets/api-token
sudo systemctl restart iauso-api.service
```

Copy the new key to each Raspberry Pi before they start failing with HTTP 401.

## Updating

```bash
cd ~/iauso
git pull   # or extract the new ZIP, without touching server-state/ or secrets/
.venv/bin/pip install -r requirements-server.txt
sudo systemctl restart iauso-collector.service iauso-api.service
```
