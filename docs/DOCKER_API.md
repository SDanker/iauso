# Docker server + API for the Raspberry Pi

**If the machines are on different networks, use
[DOCKER_DIFFERENT_NETWORKS.md](DOCKER_DIFFERENT_NETWORKS.md).** That guide
orders the install server-first, then the Raspberry Pi, using Tailscale and
private HTTPS. The LAN example in this document is for machines sharing a
network.

Version 1.2. The server queries Claude and Codex roughly every five minutes and
stores a JSON. The Raspberry Pi does `GET /v1/usage`, gets that JSON and updates
your Waveshare panel. You can connect several displays without increasing the
number of provider queries.

| Component | Role | Data it receives |
|---|---|---|
| `collector`, in Docker | Queries and stores the quota | Claude Code and Codex sessions, mounted read-only |
| `api`, in Docker | Serves the last reading over HTTP | Quota JSON and the panel key |
| `refresher`, in Docker | Renews the sessions before they expire, by running the official CLIs | The same sessions, mounted read-write |
| `auth`, temporary container | Starts or renews sessions using the official CLIs | Your logins, stored persistently on the server |
| Raspberry Pi | Queries the API and draws the display | Panel key and percentages/dates/statuses |

The project's API receives no prompts and runs no inference. The panel key is
generated locally and is not an OpenAI or Anthropic API key. The Codex
percentages are for Codex within your ChatGPT account, not for every ChatGPT Pro
feature.

## 1. Prepare the machines

The server needs 64-bit Linux, Docker Engine with Compose v2, Python 3 and
Internet access. The temporary authentication container supports x86-64 or
ARM64. The CLIs may need considerably more memory than the monitor; Claude Code
publishes a 4 GB RAM requirement. The Raspberry Pi will not run those tools.

These commands assume standard Docker with administrator privileges on a
personal server. The container directories use UID/GID 1000; rootless Docker or
a host with SELinux may require adapting permissions/mounts.

Put the project on both machines. It must end up as `~/iauso/`. With git:

```bash
cd ~ && git clone https://github.com/YOUR_USER/iauso.git
```

Or, if you received the ZIP, from the folder where you downloaded it:

```bash
python3 -m zipfile -e iauso.zip "$HOME"
```

If you already have the previous version, stop the timer on the Raspberry Pi
first:

```bash
sudo systemctl stop iauso.timer
```

Keep your `config.json` and private files when extracting the update. The ZIP
contains no credentials and no personal `config.json`.

On the server:

```bash
cd ~/iauso
sudo docker version
sudo docker compose version
```

If Docker or the Compose plugin are missing, follow the official installation
for [Ubuntu](https://docs.docker.com/engine/install/ubuntu/) or
[Debian](https://docs.docker.com/engine/install/debian/), depending on the
server. Do not run Ubuntu instructions on Amazon Linux or Windows Server. This
guide assumes a server with Docker working.

## 2. Choose the API address

**Full example for the same home network:** server `192.168.1.100`, port `8080`.
Replace that IP with the server's real address, with a DHCP reservation to keep
it stable.

```bash
cd ~/iauso
sudo python3 scripts/init_server.py --bind 192.168.1.100
```

The initializer creates private folders and a random key. It does not print the
key, does not delete sessions and does not replace existing files. On a second
run, change the IP by editing `.env`:

```bash
nano .env
```

Contents for this example:

```dotenv
API_BIND_HOST=192.168.1.100
API_PORT=8080
```

HTTP transmits the panel key and the quota unencrypted. Use this example only on
a trusted LAN or over an encrypted VPN. For a server on the Internet, publish
the API over HTTPS or a VPN; do not open the HTTP port directly on the router.

For an HTTPS proxy already running on the host, start with
`sudo python3 scripts/init_server.py` without `--bind`: the API stays on
`127.0.0.1:8080`. Configure your proxy to forward the domain and the
`Authorization` header to that address, without caching `/v1/usage`. If the
proxy is in another container, its `127.0.0.1` is a different one: connect both
to a Docker network and use `http://api:8080` inside that network. The package
does not install a domain, a certificate, or modify your existing proxy.

## 3. Build and sign in on the server

```bash
cd ~/iauso
sudo docker compose build collector api
sudo docker compose --profile auth build auth
sudo docker compose --profile auth run --rm auth codex login --device-auth
sudo docker compose --profile auth run --rm auth claude auth login
```

For Codex, open the URL shown on your computer or phone and complete the code
with your ChatGPT account. This method may require enabling device
authentication in your account security settings.

For Claude, open the URL shown and choose your Claude subscription. If the
automatic return to the container does not work, paste the code the browser
gives you into the terminal when the tool asks. Do not choose Console/API
billing nor add `--console` for this subscription monitor.

The `auth` container is removed when each command finishes, but the sessions
stay in `server-data/home/`. Its configuration forces Codex file storage. Do not
copy that folder to the Raspberry Pi and do not include it in a repository.

Check the collector can read the sessions:

```bash
sudo docker compose run --rm collector python -m iauso doctor --config /app/docker/config.collector.json
```

`sesion local legible` means the file is available; whether the provider accepts
it is checked in the next step.

Start the permanent services:

```bash
sudo docker compose up -d collector api refresher
sudo docker compose ps
sudo docker compose logs --tail=30 collector api
```

Look for `Claude=ok, Codex=ok` in the collector log. A different status may
appear if the account returns no quota or the session needs renewal. The
services restart with Docker after a server reboot; there is no need to keep a
terminal open.

The authentication image installs the official packages available at build time.
You can pin versions with `--build-arg CODEX_VERSION=... --build-arg
CLAUDE_VERSION=...`. The monitor image pins Gunicorn 26.2.0 and installs neither
Pillow, GPIO, nor the CLIs.

## 4. Deliver the panel key to the Raspberry Pi

On the server, create a temporary private copy readable by your SSH user:

```bash
cd ~/iauso
sudo install -o "$(id -un)" -g "$(id -gn)" -m 600 secrets/api-token "$HOME/iauso-api-token.txt"
```

On the Raspberry Pi, change `server_user` and the IP to your values:

```bash
umask 077
mkdir -p ~/.config/iauso
scp server_user@192.168.1.100:~/iauso-api-token.txt ~/.config/iauso/api-token
chmod 600 ~/.config/iauso/api-token
```

Verify the server's SSH identity when prompted. This step uses encrypted SSH and
neither prints the key nor puts it on the command line. On the Raspberry Pi, use
the same user that will install the display service.

When the copy finishes correctly, remove only the temporary copy on the server:

```bash
rm ~/iauso-api-token.txt
```

The original `secrets/api-token` must stay on the server. It is not a
ChatGPT/Claude password; it authorizes reading this panel.

## 5. Install and configure the Raspberry Pi

With Raspberry Pi OS Lite and the HAT already mounted, as your regular user:

```bash
cd ~/iauso
bash scripts/install_pi.sh
sudo reboot
```

If you already installed this version of the service, there is no need to repeat
the mounting or the physical test. After the reboot, connect over SSH again.
Save the previous configuration and create the API one:

```bash
cd ~/iauso
cp config.json config.previous.json
cp config.api.example.json config.json
nano config.json
```

For the example server on the LAN:

```json
{
  "source": "api",
  "api_url": "http://192.168.1.100:8080/v1/usage",
  "api_token_file": "~/.config/iauso/api-token",
  "api_allow_http": true,
  "timezone": "America/Santiago",
  "poll_seconds": 300,
  "stale_after_seconds": 900,
  "display": "epd",
  "panel": "2.15g"
}
```

With an HTTPS domain, use `"api_url": "https://your-domain/v1/usage"` and
`"api_allow_http": false`. The Raspberry Pi verifies the certificate. Redirects
are not followed: use the final URL directly. Keep your `rotation` if you had
flipped the panel.

Test the connection without refreshing the display:

```bash
python3 -m iauso doctor --config config.json
```

It must report `API accesible` and the status of both providers. This does make
an HTTP request to your server, but it does not cause an extra provider query.

For the first physical test:

```bash
python3 -m iauso refresh --config config.json --demo
```

Wait at least three minutes after the refresh attempt before testing with real
data:

```bash
python3 -m iauso refresh --config config.json
sudo systemctl enable --now iauso.timer
```

If `deferred` appears, the program is respecting the display interval. The next
automatic cycle will retry. The panel uses a full refresh and goes to sleep when
finished.

## 6. Check and maintain

On the Raspberry Pi:

```bash
systemctl list-timers iauso.timer
journalctl -u iauso.service -n 30 --no-pager
```

On the server:

```bash
cd ~/iauso
sudo docker compose ps
sudo docker compose logs --tail=50 collector api
```

Since version 1.2 the API also writes access logs, so you can confirm the
Raspberry Pi is actually reaching the server and with what result:

```bash
sudo docker compose logs api | grep v1/usage
```

The `User-Agent` identifies the caller (`iauso/1.2` for the display). The
default Gunicorn format does not include headers, so the panel key is never
logged.

Each machine has its own roughly five-minute cycle. A reading may take close to
two cycles to reach the panel. It is marked stale after 15 minutes without a
successful query. The JSON time is not replaced by the HTTP request time. If the
Internet is down, previous values are kept with their date and error status;
they are not replaced by 0 %.

### Keeping the sessions alive

**Sessions are not renewed just because Docker is running.** The collector only
reads them; renewing is the official CLIs' job, and on a dedicated server
nobody ever runs those CLIs. The Claude access token lasts about **8 hours**
(Codex's, about 10 days), so without help the panel gets stuck showing
`RENEW SESSION` a few hours after every login.

The **`refresher`** service closes that gap, and it is started with the rest of
the stack:

```bash
sudo docker compose up -d collector api refresher
```

It runs `scripts/refresh_loop.sh` inside the same image that holds the CLIs,
with the same credentials volume, so it needs no Docker socket and no scheduler
on the host — it works the same on Linux, macOS or Windows. Every 30 minutes it
reads the local expiry (free, no network) and only when a token is about to run
out does it run the official CLI once, which refreshes the token as a side
effect. Then it re-reads the file to confirm the refresh happened. Nothing else
is reimplemented: the credential files are still written only by their own CLI.

```bash
sudo docker compose logs refresher
```

```
2026-09-08T13:49:20Z claude: 7 h left, nothing to do
2026-09-08T13:49:20Z codex: 225 h left, nothing to do
```

To check it by hand without waiting for the next pass:

```bash
sudo docker compose run --rm -T refresher bash /app/scripts/refresh_loop.sh --once
```

The Claude refresh runs a one-word prompt, because that is the only call proven
to trigger the renewal (`claude auth status` reads the file without renewing).
It costs a negligible slice of quota a few times a day. The Codex refresh uses
`codex exec`, for the same reason: `codex login status` was also verified to
be read-only. Codex was not tested near expiry (its token lasts ~10 days), so
that part is by analogy - if it ever fails to renew, the log says so. Tune the pace with
`REFRESH_INTERVAL_SECONDS`, `CLAUDE_MARGIN_HOURS` and `CODEX_MARGIN_HOURS`.

When a refresh token itself expires, no automation can help: the log says
`sign in again` and you use the login commands below.

When `RENOVAR SESION` appears, repeat the corresponding provider
login on the server:

```bash
sudo docker compose --profile auth run --rm auth codex login --device-auth
sudo docker compose --profile auth run --rm auth claude auth login
```

Run only the command for the account that needs it. The official CLIs manage
those logins. The monitor implements no alternative OAuth flow, runs no prompts
to keep sessions alive and promises no indefinite renewal. The next cycle reads
the new credentials; if an HTTP 429 deadline exists, it is kept.

To update the CLIs in the temporary container:

```bash
sudo docker compose --profile auth build --pull --no-cache auth
```

To stop the server monitor while keeping sessions and cache:

```bash
sudo docker compose down
```

Do not delete `server-data/` to work around an HTTP 429: the provider backoff is
kept there too. To rotate the panel key (for example if you suspect it leaked):

```bash
cd ~/iauso
sudo python3 scripts/init_server.py --rotate-token
sudo docker compose up -d --force-recreate api
```

The previous key stops working as soon as `api` is recreated. Copy the new one
to each Raspberry Pi (replacing `~/.config/iauso/api-token`) before or right
after — in the meantime those Pis will receive HTTP 401.

## 7. API reference

| Route / response | Meaning |
|---|---|
| `GET /v1/usage`, `Authorization: Bearer …` | Returns JSON schema v1 with quota, statuses and dates |
| HTTP 200 | Valid JSON; check each provider's status to know whether the data is fresh |
| HTTP 401 | Panel key missing or wrong; independent of the Claude/Codex login |
| HTTP 503 | No valid snapshot yet, or the API key is not configured |
| HTTP 405 | Only GET is allowed |
| `OPTIONS /v1/usage` | CORS preflight; the real request still requires the Bearer token |
| `GET /healthz` | Checks the HTTP process answers; verifies neither quota nor sessions |

Responses carry `Access-Control-Allow-Origin: *`, so a web page can read the API
directly — see [INTEGRATIONS.md](INTEGRATIONS.md).

Illustrative partial example, **not a real reading**:

```json
{
  "schema_version": 1,
  "generated_at": 1788807600,
  "demo": false,
  "providers": {
    "claude": {
      "status": "ok",
      "updated_at": 1788807600,
      "windows": [
        {"id": "session", "label": "5 h", "used_percent": 74, "resets_at": 1788814800}
      ]
    },
    "codex": {"status": "no_data", "updated_at": null, "windows": []}
  }
}
```

No session tokens, account IDs or authentication files are sent. The Raspberry
Pi keeps its private cache and rejects malformed JSON, DEMO snapshots and
out-of-order dates. The API accepts no credentials in the URL and has no write
routes.

**Validation performed:** local HTTP tests of authentication, API, client, errors
and rendering with simulated data. See [VALIDATION.md](VALIDATION.md) for the
exact result.

Sources: [Codenotch](https://github.com/vinzdg/codenotch),
[Codex authentication](https://learn.chatgpt.com/docs/auth),
[Codex install](https://github.com/openai/codex),
[Claude CLI](https://code.claude.com/docs/en/cli-reference),
[Claude sessions](https://code.claude.com/docs/en/authentication),
[Claude install](https://code.claude.com/docs/en/setup),
[Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/) and
[Gunicorn](https://pypi.org/project/gunicorn/).
