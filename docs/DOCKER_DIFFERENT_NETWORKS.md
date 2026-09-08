# Docker and Raspberry Pi on different networks: step by step

This guide replaces the earlier same-LAN example. Configure the server first,
then the Raspberry Pi. The program already supports HTTPS and needs no changes
to the display driver.

We will use **Tailscale + Tailscale Serve**: both machines join the same private
network and the Raspberry Pi queries an HTTPS URL of the server. You do not need
to buy a domain or configure port forwarding on the routers. On networks with
heavily restricted outbound access you may need to allow Tailscale per its
documentation.

The API and the collector run in Docker. Tailscale is installed **on the server
system and on the Raspberry Pi**. No exit node is configured: the server's
queries to Claude and Codex use its normal Internet connection.

> **Using Cloudflare Tunnel instead?** If the server already runs `cloudflared`,
> you can skip Tailscale entirely: add a public hostname pointing to the API and
> the Raspberry Pi will reach it over plain HTTPS from anywhere. Keep
> `API_BIND_HOST` on an interface the tunnel connector can reach, and remember
> that if the tunnel has several connectors, all of them must be able to reach
> the target you configure (a host IP works for all of them; a Docker service
> name only works for a connector on that same Docker network).

## A. Configure the Docker server first

### A1. Check the system and Docker

Enter the server over your usual SSH connection or its console. Use a user with
`sudo`:

```bash
cat /etc/os-release
uname -m
sudo docker version
sudo docker compose version
```

This guide assumes **Ubuntu Server 22.04, 24.04 or 26.04, 64-bit**, x86-64 or
ARM64. If you already have Docker and Compose working, continue at A2. The
project commands also work on other Linux servers with standard Docker, but
their package installation may differ. Do not run the Ubuntu block on Amazon
Linux, Debian or Windows Server.

**Only for a fresh Ubuntu without Docker:** install from the official
repository:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl python3 unzip
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker compose version
```

Do not use this block to replace a Docker installation already serving other
projects. If there are conflicts with existing packages, review that host's
installation before changing it.

### A2. Copy and extract the project

If the server has git and access to the repository, the simplest option is
`cd ~ && git clone https://github.com/YOUR_USER/iauso.git` and skipping to the
command block below (omitting the `python3 -m zipfile` line).

Otherwise, download `iauso.zip`. Copy the file to the server's home folder using
your usual SSH connection, SFTP or WinSCP.

Example from Windows PowerShell, after replacing `SERVER_USER` and `SERVER_HOST`:

```powershell
scp "$HOME\Downloads\iauso.zip" SERVER_USER@SERVER_HOST:~/
```

If you use a `.pem` key, add `-i PATH_TO_YOUR_KEY.pem`. Keep the access method
your server already uses; the project does not require enabling SSH passwords.

On the server:

```bash
sudo apt-get update
sudo apt-get install -y python3 curl ca-certificates
cd ~
python3 -m zipfile -e iauso.zip "$HOME"
cd ~/iauso
```

If you are updating an existing installation, the ZIP keeps your sessions and
personal configuration because it does not include those files.

### A3. Prepare the API with local access

```bash
cd ~/iauso
sudo python3 scripts/init_server.py
nano .env
```

Leave these two lines:

```dotenv
API_BIND_HOST=127.0.0.1
API_PORT=8080
```

**Fix any `192.168...` left from the previous guide here.** The initializer
keeps an existing `.env`: running the script again does not change its IP
automatically.

Port 8080 will be reachable only on the server. Tailscale Serve will connect it
to the private HTTPS URL. If 8080 is already taken, choose another local port in
`.env` and use that same port in the `curl` and `tailscale serve` commands in A6.

The panel key is stored in `secrets/api-token`. Sessions and cache stay in
`server-data/`. The container folders use UID/GID 1000; this guide assumes
standard Docker, not rootless Docker.

### A4. Build the images and sign in

```bash
sudo docker compose config --quiet
sudo docker compose build collector api
sudo docker compose --profile auth build auth
```

Sign in to Codex with your ChatGPT account:

```bash
sudo docker compose --profile auth run --rm auth codex login --device-auth
```

Open the URL it shows on your computer or phone and enter the code. The device
method may require enabling it in your account security settings.

Sign in to Claude:

```bash
sudo docker compose --profile auth run --rm auth claude auth login
```

Choose your Claude subscription. If the browser gives you a code because it
cannot return to the container, paste it into the terminal when the tool asks.
Do not add `--console`: that mode is for API billing.

The temporary `auth` container is removed when the command finishes, but its
sessions stay on the server. The official CLIs may need more memory than the
monitor: Anthropic publishes a 4 GB requirement for Claude Code. They are not
installed on the Zero 2 W.

### A5. Start and check Docker

```bash
sudo docker compose up -d collector api refresher
sudo docker compose ps
sudo docker compose logs --tail=30 collector api
```

In the collector logs, look for the Claude and Codex statuses. `ok` means that
query returned quota. `needs_auth` or `expired` require reviewing that
provider's session.

Check the HTTP process answers:

```bash
curl --fail --show-error http://127.0.0.1:8080/healthz
```

Expected response:

```json
{"status":"up"}
```

This check only confirms the API answers. To verify the authenticated read
without printing the key:

```bash
sudo docker compose exec -T api python - <<'PY'
import json
import urllib.request
from iauso.api import read_api_token

request = urllib.request.Request(
    'http://127.0.0.1:8080/v1/usage',
    headers={'Authorization': 'Bearer ' + read_api_token('/run/secrets/api_token')},
)
with urllib.request.urlopen(request, timeout=10) as response:
    data = json.load(response)
for provider, item in data['providers'].items():
    print(provider + ': ' + item['status'])
PY
```

The port in this last block is the **container's internal** one, always 8080
even if you change the host port in `.env`.

### A6. Connect the server to Tailscale and enable private HTTPS

Create your account at [Tailscale](https://tailscale.com/) or use the one you
already have. Both machines must sign in with the **same user and on the same
Tailscale network**.

If the server does not have Tailscale:

```bash
curl -fsSL https://tailscale.com/install.sh -o /tmp/iauso-tailscale-install.sh
sudo sh /tmp/iauso-tailscale-install.sh
sudo systemctl enable --now tailscaled
sudo tailscale up
```

Open the URL shown and authorize the server in your account. If Tailscale was
already connected, keep its configuration and check directly:

```bash
tailscale status
tailscale ip -4
sudo tailscale serve status
```

Configure a private HTTPS port **8443** for this project:

```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8080
sudo tailscale serve status
```

If you already had a Serve service on 8443, choose another free Serve port. If
the CLI asks you to enable HTTPS, open the URL it indicates, enable it and repeat
the command. Tailscale's DNS name and a valid Tailscale-managed certificate are
used.

If configuration is missing, in the Tailscale console's **DNS** section enable
**MagicDNS** and **HTTPS Certificates**. The enabling screen explains that the
certificate name is published in the public certificate logs; access to the API
stays limited to your Tailscale network.

You will get an address like this one; **yours will be different**:

```text
https://my-server.my-net.ts.net:8443
```

Save it. The full API is that address followed by `/v1/usage`. The command must
report it is available inside your tailnet. We use `serve`, which grants access
inside that private network. Do not enable `funnel` for this project, because it
publishes the service on the Internet.

`--bg` keeps Serve active and restores the configuration on reboot. You do not
need to open 8080, 8443, 80 or 443 on the router or in the security group to
publish this API. Tailscale needs to be able to establish its own outbound
connection.

**The server is ready when:** Docker is up, the local authenticated query
answers, and Serve shows your private URL. Now move to the Raspberry Pi.

## B. Configure the Raspberry Pi Zero 2 W afterwards

### B1. Prepare Raspberry Pi OS and the display

If you do not have a system yet, flash Raspberry Pi OS Lite with Raspberry Pi
Imager. Configure Wi-Fi, user, password and SSH before flashing. Mount the HAT
with the Raspberry Pi powered off and unplugged; confirm **Waveshare 2.15inch
HAT+ (G), 296 × 160**, or set `"panel"` for another model — see
[PANELS.md](PANELS.md).

Connect over SSH from a computer on the Raspberry Pi's network, using its local
IP or the configured name. The `.local` domain only works on that local network;
it is not yet its remote address.

Put the project in the Raspberry Pi's home folder:
`cd ~ && git clone https://github.com/YOUR_USER/iauso.git` if it has git, or by
copying the same ZIP. Example from Windows on that network:

```powershell
scp "$HOME\Downloads\iauso.zip" PI_USER@raspberrypi.local:~/
```

On the Raspberry Pi:

```bash
sudo apt-get update
sudo apt-get install -y python3 curl ca-certificates
cd ~
python3 -m zipfile -e iauso.zip "$HOME"
cd ~/iauso
sudo systemctl stop iauso.timer 2>/dev/null || true
bash scripts/install_pi.sh
sudo reboot
```

The installer configures SPI and the GPIO permissions. It does not start
querying by itself. Use the same user for the whole display program and its
private files.

### B2. Connect the Raspberry Pi to the same Tailscale network

After the reboot, connect over SSH again. If Tailscale is not installed yet:

```bash
curl -fsSL https://tailscale.com/install.sh -o /tmp/iauso-tailscale-install.sh
sudo sh /tmp/iauso-tailscale-install.sh
sudo systemctl enable --now tailscaled
sudo tailscale up
```

Authorize the Raspberry Pi with the same user and on the same Tailscale network
as the server. If you already had Tailscale, keep the existing connection.

```bash
tailscale status
tailscale ip -4
```

Note the Raspberry Pi's Tailscale IP, for example `100.90.0.15`. That IP is used
to send it the key. Do not use its `192.168...` Wi-Fi address here.

Test the server URL obtained in A6 from the Raspberry Pi, replacing the full
example:

```bash
curl --fail --show-error https://my-server.my-net.ts.net:8443/healthz
```

You must get `{"status":"up"}`. Do not add `-k`: the certificate must validate
correctly. If your tailnet has custom access rules, they must let the Raspberry
Pi reach the server over TCP 8443.

### B3. Transfer the panel key

We will use Taildrop, included in Tailscale, to transfer only `api-token`. These
steps assume two personal machines enrolled with the same user; Taildrop is not
available for devices with server tags (`tag:`).

Before the first send, open **Settings → General** in the Tailscale console and
enable **Send Files**. It is an optional Tailscale feature that requires
enabling. If an organization manages it, ask the administrator to enable it.

In a terminal on the **server**, replace `100.90.0.15` with the Raspberry Pi's
Tailscale IP:

```bash
cd ~/iauso
sudo tailscale file cp secrets/api-token 100.90.0.15:
```

On the **Raspberry Pi**, receive the file and set its permissions:

```bash
umask 077
mkdir -p ~/.config/iauso
chmod 700 ~/.config/iauso
sudo tailscale file get --conflict=overwrite "$HOME/.config/iauso"
sudo chown "$(id -u):$(id -g)" "$HOME/.config/iauso/api-token"
chmod 600 ~/.config/iauso/api-token
```

The receiver collects Taildrop's pending files into that folder; send only this
key during the step. If it does not appear, check the transfer on the server and
run `file get` again. Do not copy `server-data/home/` or the provider sessions to
the Raspberry Pi.

### B4. Configure the HTTPS query

On the Raspberry Pi:

```bash
cd ~/iauso
cp config.json config.previous.json
cp config.api.example.json config.json
nano config.json
```

Replace the URL with the one obtained in A6:

```json
{
  "source": "api",
  "api_url": "https://my-server.my-net.ts.net:8443/v1/usage",
  "api_token_file": "~/.config/iauso/api-token",
  "api_allow_http": false,
  "timezone": "America/Santiago",
  "poll_seconds": 300,
  "stale_after_seconds": 900,
  "display": "epd",
  "panel": "2.15g"
}
```

To save in nano: `Ctrl+O`, `Enter`; to exit: `Ctrl+X`. If you were using an
inverted orientation, also keep `"rotation": 180`.

```bash
python3 -m iauso doctor --config config.json
```

It must report `API accesible` and each provider's status. An HTTP 401 from your
API points at the panel key; a valid JSON with `expired` or `needs_auth` points
at the provider session on the server.

### B5. Test the display and start updating

First physical test, with fictional data:

```bash
python3 -m iauso refresh --config config.json --demo
```

Wait at least three minutes from the refresh attempt. Then:

```bash
python3 -m iauso refresh --config config.json
sudo systemctl enable --now iauso.timer
systemctl list-timers iauso.timer
journalctl -u iauso.service -n 30 --no-pager
```

`deferred` means the display's minimum interval is being respected; the timer
will retry. The display service exits between updates, while Tailscale stays
connected. Docker keeps running on the server.

## C. Maintenance and troubleshooting

- **Tailscale cannot find the other machine:** check both appear in the same
  network of your account, are authorized and connected. Use `tailscale status`.
  You do not need to turn them into routers or configure an exit node.
- **HTTPS fails:** check the exact URL from `tailscale serve status`, its port
  and that HTTPS/MagicDNS are enabled. Check the time with `timedatectl status`
  and the access rules for TCP 8443. Do not disable certificate verification.
- **HTTP 503:** check `sudo docker compose logs --tail=50 collector api`; the
  collector may not have produced a valid reading yet.
- **Intermittent `SIN CONEXION`:** Raspberry Pi OS enables Wi-Fi power save by
  default and the radio may sleep between five-minute cycles. Check with
  `iw dev wlan0 get power_save`; to disable it permanently, create
  `/etc/NetworkManager/conf.d/99-wifi-powersave-off.conf` with `[connection]` /
  `wifi.powersave = 2` and restart NetworkManager.
- **Stale data:** the display keeps its last reading and its date. The server and
  Raspberry Pi cycles are independent; delivery can take close to ten minutes at
  the worst point of both cycles.
- **Recovering after an outage:** Docker uses `restart: unless-stopped`, Serve
  uses `--bg` and the Raspberry Pi has a systemd timer. With connectivity and
  valid sessions, they recover after a reboot.

To prevent a Tailscale expiry from disconnecting these two trusted devices, you
can open [Machines](https://console.tailscale.com/admin/machines), go into each
one's menu and choose **Disable key expiry**. They then stay authorized until you
revoke them; this does not renew the Claude or Codex sessions.

When a provider session expires, run only the corresponding command on the
server:

```bash
cd ~/iauso
sudo docker compose --profile auth run --rm auth codex login --device-auth
sudo docker compose --profile auth run --rm auth claude auth login
```

To rotate the panel key (not the Claude/Codex sessions) use
`sudo python3 scripts/init_server.py --rotate-token` on the server — see the full
detail in [DOCKER_API.md](DOCKER_API.md#6-check-and-maintain). Afterwards, repeat
B3 to take the new key to each Raspberry Pi.

The monitor does not renew tokens by itself and runs no prompts to keep a session
alive. It also does not measure every ChatGPT Pro feature globally: it shows the
Codex quota and the quota returned by Claude Code for your subscriptions.

## Validation scope

The API/Raspberry Pi codebase passes 30 tests and a run against real Gunicorn.
This update adds network and configuration instructions without changing the
query code or the driver. Command block syntax and the JSON configuration were
verified; Docker, Tailscale, real logins and the physical HAT were not run on
your machines.

## Official sources

- [Docker Engine for Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
- [Tailscale on Linux](https://tailscale.com/docs/install/linux).
- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).
- [Serve reference](https://tailscale.com/docs/reference/tailscale-cli/serve).
- [CLI / file transfer reference](https://tailscale.com/docs/reference/tailscale-cli).
- [Taildrop](https://tailscale.com/docs/features/taildrop).
- [Ports and connectivity](https://tailscale.com/docs/reference/faq/firewall-ports).
- [Device key expiry](https://tailscale.com/docs/features/access-control/key-expiry).
- [Codex authentication](https://learn.chatgpt.com/docs/auth).
- [Claude Code authentication](https://code.claude.com/docs/en/authentication).
