# Reading the quota from somewhere else

The Raspberry Pi with the e-ink display is not the only way to read the data. If
you already have the server running in `api` mode
([DOCKER_API.md](DOCKER_API.md) or [WITHOUT_DOCKER.md](WITHOUT_DOCKER.md)),
`GET /v1/usage` is an ordinary HTTP endpoint: anything that can make an HTTP
request with a header can read it. This page shows two examples: a **web page**
and a **Telegram bot**.

You will need:

- The full URL of your API, for example `https://usage.yourdomain.com/v1/usage`.
- The panel key (`secrets/api-token` on the server).

The response format is documented in
[DOCKER_API.md § API reference](DOCKER_API.md#7-api-reference).

## Web page

Since version 1.2 the API answers with `Access-Control-Allow-Origin: *` on
`/v1/usage`, so a `fetch()` from JavaScript on any page can read it directly
(previously it only worked if the page was served from the same origin as the
API).

Save this as `panel.html` and open it in any browser (it does not need to be
served from anywhere — it works even opened as a local file):

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AI quota</title>
<style>
  body { font-family: system-ui, sans-serif; background: #111; color: #eee; padding: 2rem; }
  .card { border: 1px solid #444; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; max-width: 320px; }
  .bar { background: #333; border-radius: 4px; height: 10px; overflow: hidden; margin: 4px 0; }
  .fill { background: #4caf50; height: 100%; }
  .fill.warn { background: #e0b400; }
  .fill.crit { background: #e04040; }
  .status { font-size: 0.85em; opacity: 0.8; }
</style>
</head>
<body>
<h1>AI quota</h1>
<div id="app">Loading...</div>
<script>
// Replace these two values with your own.
const API_URL = "https://usage.yourdomain.com/v1/usage";
const API_TOKEN = "PASTE_YOUR_TOKEN_HERE";

async function load() {
  const app = document.getElementById("app");
  try {
    const res = await fetch(API_URL, { headers: { Authorization: "Bearer " + API_TOKEN } });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    app.innerHTML = Object.entries(data.providers).map(([name, item]) => `
      <div class="card">
        <h2>${name.toUpperCase()}</h2>
        <div class="status">${item.status}</div>
        ${item.windows.map(w => `
          <div>${w.label}: <strong>${w.used_percent}%</strong></div>
          <div class="bar"><div class="fill ${w.used_percent >= 90 ? 'crit' : w.used_percent >= 70 ? 'warn' : ''}"
               style="width:${w.used_percent}%"></div></div>
        `).join("")}
      </div>
    `).join("");
  } catch (err) {
    app.textContent = "Error: " + err.message;
  }
}
load();
setInterval(load, 60000); // refresh every minute; the API caches, so providers are not hit
</script>
</body>
</html>
```

**Security note:** this HTML carries the API token written in JavaScript, visible
to anyone who opens the file or inspects the page. It is the same key the
Raspberry Pi uses — it is not a Claude/Codex API key and it does not grant
access to your sessions, only to reading these percentages. Even so:

- Do not upload it to a public page or a repository.
- If you host it somewhere real (not just opening the file yourself), keep it
  private (password-protected, or on your local network) — this page adds no
  authentication of its own.
- If the token leaks, rotate it (`scripts/init_server.py --rotate-token`, or the
  manual equivalent in
  [WITHOUT_DOCKER.md](WITHOUT_DOCKER.md#rotating-the-panel-key)) and update the
  page and your Raspberry Pis.

## Telegram bot

A small script that answers `/cuotas` with the same information, querying your
API. It uses only the Python standard library (no new dependencies), with long
polling — it needs no open port and no public webhook, just outbound Internet
access on the server.

1. Talk to [@BotFather](https://t.me/BotFather) on Telegram, `/newbot`, and save
   the token it gives you.
2. Send any message to your new bot and visit
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in the browser to find
   your `chat.id` — restricting the bot to that chat prevents anyone who finds
   your bot from reading your quota.

Save this as `scripts/telegram_bot.py`:

```python
"""Minimal Telegram bot: /cuotas replies with the API status.

Required environment variables:
  TELEGRAM_BOT_TOKEN   token from @BotFather
  TELEGRAM_CHAT_ID     your chat.id; the bot ignores messages from other chats
  IAUSO_API_URL        https://your-domain/v1/usage
  IAUSO_API_TOKEN      the key from secrets/api-token
"""
import json
import os
import time
import urllib.error
import urllib.request

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_URL = os.environ["IAUSO_API_URL"]
API_TOKEN = os.environ["IAUSO_API_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def fetch_usage():
    req = urllib.request.Request(API_URL, headers={"Authorization": "Bearer " + API_TOKEN})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def format_usage(data):
    lines = []
    for provider, item in data["providers"].items():
        lines.append(f"*{provider.upper()}*: {item['status']}")
        for w in item["windows"]:
            lines.append(f"  {w['label']}: {w['used_percent']}%")
    return "\n".join(lines) or "No data yet."


def send_message(chat_id, text):
    body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(f"{TELEGRAM_API}/sendMessage", data=body,
                                  headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=10).close()


def main():
    offset = 0
    while True:
        try:
            url = f"{TELEGRAM_API}/getUpdates?timeout=30&offset={offset}"
            with urllib.request.urlopen(url, timeout=35) as resp:
                updates = json.load(resp)["result"]
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = (message.get("text") or "").strip()
            if str(chat_id) != CHAT_ID:
                continue  # Ignore anyone who is not you.
            if text == "/cuotas":
                try:
                    send_message(chat_id, format_usage(fetch_usage()))
                except Exception as exc:  # noqa: BLE001 - report any failure to the chat
                    send_message(chat_id, "Error querying the API: " + str(exc))


if __name__ == "__main__":
    main()
```

Run it as one more service, with the same environment variables:

```ini
# /etc/systemd/system/iauso-telegram-bot.service
[Unit]
Description=Telegram bot for AI quota
After=network-online.target

[Service]
Type=simple
User=YOUR_USER
Environment=TELEGRAM_BOT_TOKEN=xxxxxxxxx:yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
Environment=TELEGRAM_CHAT_ID=123456789
Environment=IAUSO_API_URL=https://usage.yourdomain.com/v1/usage
Environment=IAUSO_API_TOKEN=the-key-from-secrets-api-token
ExecStart=/usr/bin/python3 /home/YOUR_USER/iauso/scripts/telegram_bot.py
Restart=on-failure
RestartSec=10
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
```

Put the bot token and the API key directly in the unit file (or in a separate
`EnvironmentFile=` with `600` permissions) — do not hardcode them in
`telegram_bot.py` if you plan to version that file.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now iauso-telegram-bot.service
```

Send `/cuotas` to your bot and you should get the same detail the e-ink display
shows, as text.

### Variations

- **Alert only when something is wrong:** instead of answering a command, have
  the script call `fetch_usage()` in a loop every `poll_seconds` and only call
  `send_message` when some `status` is different from `"ok"` — that way the bot
  writes to you proactively when something needs attention (`needs_auth`,
  `expired`, etc.) instead of waiting for you to ask.
- **A single message that gets edited:** use Telegram's `editMessageText` with a
  stored `message_id`, so you have one fixed message that updates instead of
  sending a new one every time.
