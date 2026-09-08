# Servidor sin Docker

Esta es una alternativa a [DOCKER_API.md](DOCKER_API.md) para quien no quiere
o no puede usar Docker en el servidor. El `collector` y la `api` son
procesos Python normales — acá se corren directo con `systemd`, en vez de
en contenedores.

**Perdés el aislamiento que da Docker** (namespaces, `read_only`,
`cap_drop`, límites de memoria por servicio). Esta guía reconstruye la
parte que más importa — que el proceso que atiende HTTP en internet no
pueda leer tus sesiones de Claude/Codex — con dos usuarios Linux
separados y permisos de archivo, pero no es equivalente a un contenedor.
Si podés usar Docker, usalo.

## 1. Preparar el proyecto

Necesitás Linux con Python 3.11+ y `venv`. Con el proyecto ya en
`~/iauso` (`git clone` o el ZIP extraído):

```bash
cd ~/iauso
python3 -m venv .venv
.venv/bin/pip install -r requirements-server.txt
mkdir -p server-state secrets
chmod 700 secrets
```

`requirements-server.txt` solo trae Gunicorn — el proyecto no tiene más
dependencias en el servidor.

## 2. Iniciar sesión en Claude y Codex

Instalá las CLI oficiales (`@anthropic-ai/claude-code`, `@openai/codex`)
en el servidor **con el mismo usuario que va a correr el `collector`** e
iniciá sesión normalmente (`claude auth login`, `codex login
--device-auth`). Sus requisitos de memoria son independientes del panel;
revisá que el servidor tenga RAM suficiente (Anthropic publica 4 GB para
Claude Code).

Este es el mismo mecanismo que la sección "B. Consulta local" del
[README](../../README.es.md#b-consulta-local-en-la-raspberry) — el proyecto solo
lee los archivos que esas CLI ya guardan (`~/.claude/.credentials.json`,
`~/.codex/auth.json`), nunca les pide una API key.

## 3. Separar el usuario que sirve HTTP

Para que el proceso expuesto a internet (la API) no tenga forma de leer
esas credenciales, creale su propio usuario sin sesión:

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin iauso-api
sudo groupadd iauso-panel
sudo usermod -aG iauso-panel "$(whoami)"
sudo usermod -aG iauso-panel iauso-api
```

El grupo `iauso-panel` es el único puente entre ambos: el `collector`
(con tu usuario) escribe ahí el snapshot público y la clave del panel; la
`api` (como `iauso-api`) solo puede leerlos.

```bash
cd ~/iauso
chgrp iauso-panel server-state secrets
chmod 750 server-state secrets
python3 -c "import secrets,pathlib; p=pathlib.Path('secrets/api-token'); p.write_text(secrets.token_urlsafe(32)+chr(10))"
chmod 640 secrets/api-token
chgrp iauso-panel secrets/api-token
```

Cerrá sesión y volvé a entrar (o `newgrp iauso-panel`) para que tu
usuario tome el grupo nuevo antes de seguir.

## 4. Config del `collector`

Copiá tu config local (la misma idea que `docker/config.collector.json`,
pero con `source: "local"` y las rutas reales de tu usuario):

```json
{
  "source": "local",
  "state_dir": "/home/TU_USUARIO/iauso/server-state",
  "claude": {"enabled": true},
  "codex": {"enabled": true}
}
```

Guardalo como `server-config.json`. Probalo antes de instalar el servicio:

```bash
.venv/bin/python -m iauso doctor --config server-config.json
```

## 5. Las dos unidades systemd

Sustituí `TU_USUARIO` y la ruta en ambos archivos.

`/etc/systemd/system/iauso-collector.service`:

```ini
[Unit]
Description=iauso collector
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=TU_USUARIO
WorkingDirectory=/home/TU_USUARIO/iauso
ExecStart=/home/TU_USUARIO/iauso/.venv/bin/python -m iauso collect --config server-config.json --loop --output /home/TU_USUARIO/iauso/server-state/snapshot.json
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
WorkingDirectory=/home/TU_USUARIO/iauso
Environment=APP_SNAPSHOT_FILE=/home/TU_USUARIO/iauso/server-state/snapshot.json
Environment=APP_API_TOKEN_FILE=/home/TU_USUARIO/iauso/secrets/api-token
Environment=APP_STALE_AFTER_SECONDS=900
ExecStart=/home/TU_USUARIO/iauso/.venv/bin/gunicorn --bind 127.0.0.1:8080 --workers 2 --threads 2 --timeout 20 iauso.api:create_app()
Restart=on-failure
RestartSec=15
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=read-only
ProtectSystem=strict

[Install]
WantedBy=multi-user.target
```

`ProtectHome=read-only` + `ProtectSystem=strict` en la API son la red de
seguridad adicional: aunque alguien lograra ejecutar codigo dentro de ese
proceso, el sistema de archivos queda de solo lectura salvo `/tmp`
(`PrivateTmp`). El `collector` no lleva esas restricciones porque
necesita escribir en `server-state/`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now iauso-collector.service
sudo systemctl enable --now iauso-api.service
```

**Si `iauso-api` no puede ni arrancar** (`status=203/EXEC` o similar en
`journalctl`), revisá que pueda atravesar tu carpeta personal: al ser un
usuario sin relación con la tuya, necesita permiso de tránsito (no de
lectura) sobre `/home/TU_USUARIO`:

```bash
chmod o+x /home/TU_USUARIO
```

Eso no expone el contenido de tu home (`ls` sigue fallando para otros
usuarios), solo permite atravesarlo para llegar a rutas que ya conocés. Si
preferís no tocar los permisos de tu home, instalá el proyecto en
`/opt/iauso` (dueño `root:iauso-panel`, `750`) en vez de
`~/iauso` y ajustá las rutas de esta sección.

## 6. Verificar

```bash
curl http://127.0.0.1:8080/healthz
curl -H "Authorization: Bearer $(cat secrets/api-token)" http://127.0.0.1:8080/v1/usage
journalctl -u iauso-collector -n 30 --no-pager
journalctl -u iauso-api -n 30 --no-pager
```

Deberías ver `{"status":"up"}` y, poco después de que el `collector` haga
su primera lectura, un JSON con `Claude`/`Codex` en `ok`.

De acá en adelante, todo lo que dice [DOCKER_API.md](DOCKER_API.md) sobre
publicar la API (HTTPS con Tailscale, un proxy, Cloudflare Tunnel, etc.),
llevarle la clave a la Raspberry y configurar `config.json` ahí, es
idéntico — la Raspberry no sabe ni le importa si el servidor corre en
Docker o no.

## Rotar la clave del panel

Sin `scripts/init_server.py` (pensado para Docker/UID 1000), rotala a mano:

```bash
python3 -c "import secrets,pathlib; p=pathlib.Path('secrets/api-token'); p.write_text(secrets.token_urlsafe(32)+chr(10))"
chmod 640 secrets/api-token
sudo systemctl restart iauso-api.service
```

Copiá la clave nueva a cada Raspberry antes de que se acostumbren a fallar
con HTTP 401.

## Actualizar

```bash
cd ~/iauso
git pull   # o extraer el ZIP nuevo, sin tocar server-state/ ni secrets/
.venv/bin/pip install -r requirements-server.txt
sudo systemctl restart iauso-collector.service iauso-api.service
```
