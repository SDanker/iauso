# Consultar las cuotas desde otro lado

La Raspberry con la pantalla e-ink no es la única forma de leer los datos.
Si ya tenés el servidor en modo `api` funcionando ([DOCKER_API.md](DOCKER_API.md)
o [SIN_DOCKER.md](SIN_DOCKER.md)), `GET /v1/usage` es un endpoint HTTP normal:
cualquier cosa que sepa hacer una petición HTTP con un header puede leerlo.
Esta pagina muestra dos ejemplos: una **página web** y un **bot de Telegram**.

Antes de seguir necesitás:

- La URL completa de tu API, por ejemplo `https://usage.tudominio.com/v1/usage`.
- La clave del panel (`secrets/api-token` en el servidor).

El formato de la respuesta esta documentado en
[DOCKER_API.md § Referencia de la API](DOCKER_API.md#7-referencia-de-la-api).

## Página web

Desde la version 1.2 la API responde con `Access-Control-Allow-Origin: *`
en `/v1/usage`, asi que un `fetch()` desde JavaScript en cualquier pagina
puede leerla directamente (antes solo funcionaba si la pagina se servia
desde el mismo origen que la API).

Guardá esto como `panel.html` y abrilo en cualquier navegador (no hace
falta servirlo desde ningún lado, funciona incluso abierto como archivo
local):

```html
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Cuotas IA</title>
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
<h1>Cuotas IA</h1>
<div id="app">Cargando...</div>
<script>
// Sustituí estos dos valores por los tuyos.
const API_URL = "https://usage.tudominio.com/v1/usage";
const API_TOKEN = "PEGA_AQUI_TU_TOKEN";

async function cargar() {
  const app = document.getElementById("app");
  try {
    const res = await fetch(API_URL, { headers: { Authorization: "Bearer " + API_TOKEN } });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    app.innerHTML = Object.entries(data.providers).map(([nombre, item]) => `
      <div class="card">
        <h2>${nombre.toUpperCase()}</h2>
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
cargar();
setInterval(cargar, 60000); // refresca cada minuto; la API cachea, no molesta a Claude/Codex
</script>
</body>
</html>
```

**Nota de seguridad:** este HTML lleva el token de la API escrito en
JavaScript, visible para quien abra el archivo o inspeccione la página. Es
la misma clave que usa la Raspberry — no es una API key de Claude/Codex ni
da acceso a tus sesiones, solo a leer estos porcentajes. Aun así:

- No la subas a una página pública ni a un repositorio.
- Si la vas a alojar en un sitio real (no solo abrir el archivo vos), que
  sea privado (con contraseña, o en tu red local) — esta página no agrega
  su propia autenticación.
- Si el token se filtra, rotalo (`scripts/init_server.py --rotate-token`
  o el equivalente manual en [SIN_DOCKER.md](SIN_DOCKER.md#rotar-la-clave-del-panel))
  y actualizá la página y tus Raspberries.

## Bot de Telegram

Un script chico que responde `/cuotas` con la misma información,
consultando tu API. Usa solo la librería estándar de Python (sin
dependencias nuevas), con *long polling* — no necesita un puerto abierto
ni webhook público, alcanza con que el servidor tenga salida a internet.

1. Hablá con [@BotFather](https://t.me/BotFather) en Telegram, `/newbot`,
   guardá el token que te da.
2. Escribile cualquier mensaje a tu bot nuevo y visitá
   `https://api.telegram.org/bot<TU_TOKEN>/getUpdates` en el navegador
   para encontrar tu `chat.id` — restringir el bot a ese chat evita que
   cualquiera que encuentre tu bot pueda leer tus cuotas.

Guardá esto como `scripts/telegram_bot.py`:

```python
"""Bot de Telegram minimo: /cuotas responde con el estado de la API.

Variables de entorno requeridas:
  TELEGRAM_BOT_TOKEN   token de @BotFather
  TELEGRAM_CHAT_ID     tu chat.id; el bot ignora mensajes de otros chats
  IAUSO_API_URL    https://tu-dominio/v1/usage
  IAUSO_API_TOKEN  la clave de secrets/api-token
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
    return "\n".join(lines) or "Sin datos todavia."


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
                continue  # Ignora a cualquiera que no seas vos.
            if text == "/cuotas":
                try:
                    send_message(chat_id, format_usage(fetch_usage()))
                except Exception as exc:  # noqa: BLE001 - reportar cualquier falla al chat
                    send_message(chat_id, "Error consultando la API: " + str(exc))


if __name__ == "__main__":
    main()
```

Corrélo como un servicio mas, con las mismas variables de entorno:

```ini
# /etc/systemd/system/iauso-telegram-bot.service
[Unit]
Description=Bot de Telegram para cuotas IA
After=network-online.target

[Service]
Type=simple
User=TU_USUARIO
Environment=TELEGRAM_BOT_TOKEN=xxxxxxxxx:yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy
Environment=TELEGRAM_CHAT_ID=123456789
Environment=IAUSO_API_URL=https://usage.tudominio.com/v1/usage
Environment=IAUSO_API_TOKEN=el-token-de-secrets-api-token
ExecStart=/usr/bin/python3 /home/TU_USUARIO/iauso/scripts/telegram_bot.py
Restart=on-failure
RestartSec=10
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
```

Poné el token del bot y la clave de la API directo en el archivo de la
unidad (o en un `EnvironmentFile=` aparte con permisos `600`) — no los
hardcodees en `telegram_bot.py` si pensás versionar ese archivo.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now iauso-telegram-bot.service
```

Escribile `/cuotas` a tu bot y deberías recibir el mismo detalle que
muestra la pantalla e-ink, en texto.

### Variantes

- **Avisar solo cuando hay problema:** en vez de responder a un comando,
  hacé que el script llame a `fetch_usage()` en un loop cada `poll_seconds`
  y solo llame a `send_message` cuando algún `status` sea distinto de
  `"ok"` — así el bot te escribe proactivamente si algo necesita atención
  (`needs_auth`, `expired`, etc.) en vez de esperar a que preguntes.
- **Un solo mensaje que se edita:** usá `editMessageText` de la API de
  Telegram con un `message_id` guardado, para tener un mensaje fijo que
  se actualiza en vez de mandar uno nuevo cada vez.
