# Docker y Raspberry en redes distintas: guía paso a paso

Esta guía reemplaza el ejemplo anterior de una misma LAN. Primero configura el servidor; después, la Raspberry. El programa sigue siendo la versión 1.1: ya admite HTTPS y no requiere cambios en el controlador de pantalla.

Usaremos **Tailscale + Tailscale Serve**: ambos equipos se unen a tu misma red privada y la Raspberry consulta una URL HTTPS del servidor. No necesitas comprar un dominio ni configurar redirecciones de puertos en los routers. En redes con salida a Internet muy restringida puede ser necesario permitir Tailscale según su documentación.

La API y el recolector se ejecutan en Docker. Tailscale se instala **en el sistema del servidor y en la Raspberry**. No se configura un exit node: las consultas del servidor a Claude y Codex usan su conexión normal a Internet.

## A. Configurar primero el servidor Docker

### A1. Revisar el sistema y Docker

Entra al servidor por tu conexión SSH habitual o su consola. Usa un usuario con `sudo`:

```bash
cat /etc/os-release
uname -m
sudo docker version
sudo docker compose version
```

Esta guía supone **Ubuntu Server 22.04, 24.04 o 26.04 de 64 bits**, x86-64 o ARM64. Si ya tienes Docker y Compose funcionando, continúa en A2. Los comandos del proyecto también sirven en otros servidores Linux con Docker estándar, pero su instalación de paquetes puede ser distinta. No ejecutes el bloque de Ubuntu en Amazon Linux, Debian o Windows Server.

**Solo para un Ubuntu nuevo sin Docker:** instala desde el repositorio oficial:

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

No utilices este bloque para sustituir una instalación Docker que ya sirve otros proyectos. Si hay conflictos con paquetes existentes, revisa la instalación de ese host antes de cambiarla.

### A2. Copiar y extraer el proyecto

Si el servidor tiene git y acceso al repositorio, lo más simple es `cd ~ && git clone https://github.com/TU_USUARIO/iauso.git` y saltar al bloque de comandos de abajo (omitiendo la línea `python3 -m zipfile`).

Si no, descarga `iauso.zip`. Copia el archivo a la carpeta personal del servidor usando tu conexión SSH habitual, SFTP o WinSCP.

Ejemplo desde PowerShell de Windows, después de sustituir `USUARIO_SERVIDOR` y `HOST_SERVIDOR`:

```powershell
scp "$HOME\Downloads\iauso.zip" USUARIO_SERVIDOR@HOST_SERVIDOR:~/
```

Si usas una clave `.pem`, agrega `-i RUTA_A_TU_CLAVE.pem`. Conserva la forma de acceso que ya utiliza tu servidor; el proyecto no requiere habilitar contraseñas SSH.

En el servidor:

```bash
sudo apt-get update
sudo apt-get install -y python3 curl ca-certificates
cd ~
python3 -m zipfile -e iauso.zip "$HOME"
cd ~/iauso
```

Si actualizas una instalación existente, el ZIP conserva las sesiones y configuraciones personales porque no incluye esos archivos.

### A3. Preparar la API con acceso local

```bash
cd ~/iauso
sudo python3 scripts/init_server.py
nano .env
```

Deja estas dos líneas:

```dotenv
API_BIND_HOST=127.0.0.1
API_PORT=8080
```

**Corrige aquí cualquier `192.168...` de la guía anterior.** El inicializador conserva un `.env` existente: ejecutar de nuevo el script no cambia su IP automáticamente.

El puerto 8080 quedará accesible solo en el servidor. Tailscale Serve lo conectará a la URL privada HTTPS. Si el 8080 ya está ocupado, elige otro puerto local en `.env` y utiliza ese mismo puerto en los comandos `curl` y `tailscale serve` de A6.

La clave propia del panel se guarda en `secrets/api-token`. Las sesiones y la caché quedan en `server-data/`. Las carpetas de los contenedores utilizan UID/GID 1000; esta guía supone Docker estándar, no Docker rootless.

### A4. Construir las imágenes e iniciar sesión

```bash
sudo docker compose config --quiet
sudo docker compose build collector api
sudo docker compose --profile auth build auth
```

Inicia sesión en Codex con tu cuenta ChatGPT:

```bash
sudo docker compose --profile auth run --rm auth codex login --device-auth
```

Abre la URL que muestre en tu computador o teléfono e introduce el código. El método por dispositivo puede requerir habilitación en la seguridad de tu cuenta.

Inicia sesión en Claude:

```bash
sudo docker compose --profile auth run --rm auth claude auth login
```

Elige tu suscripción Claude. Si el navegador entrega un código porque no puede regresar al contenedor, pégalo en la terminal cuando la herramienta lo pida. No agregues `--console`: ese modo es para facturación API.

El contenedor temporal `auth` se elimina al terminar el comando, pero sus sesiones quedan en el servidor. Las CLI oficiales pueden necesitar más memoria que el monitor: Anthropic publica un requisito de 4 GB para Claude Code. No se instalan en la Zero 2 W.

### A5. Arrancar y comprobar Docker

```bash
sudo docker compose up -d collector api refresher
sudo docker compose ps
sudo docker compose logs --tail=30 collector api
```

En los registros del recolector busca los estados de Claude y Codex. `ok` significa que la consulta correspondiente devolvió cuotas. `needs_auth` o `expired` requieren revisar la sesión de ese proveedor.

Comprueba que el proceso HTTP responde:

```bash
curl --fail --show-error http://127.0.0.1:8080/healthz
```

Respuesta esperada:

```json
{"status":"up"}
```

Esta comprobación solo confirma que la API responde. Para verificar la lectura autenticada sin imprimir la clave:

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

El puerto de este último bloque es el **interno del contenedor**, siempre 8080 aunque cambies el puerto del host en `.env`.

### A6. Conectar el servidor a Tailscale y habilitar HTTPS privado

Crea tu cuenta en [Tailscale](https://tailscale.com/) o utiliza la que ya tengas. Los dos equipos deben entrar con el **mismo usuario y en la misma red Tailscale**.

Si el servidor no tiene Tailscale:

```bash
curl -fsSL https://tailscale.com/install.sh -o /tmp/iauso-tailscale-install.sh
sudo sh /tmp/iauso-tailscale-install.sh
sudo systemctl enable --now tailscaled
sudo tailscale up
```

Abre la URL mostrada y autoriza el servidor en tu cuenta. Si Tailscale ya estaba conectado, conserva su configuración y comprueba directamente:

```bash
tailscale status
tailscale ip -4
sudo tailscale serve status
```

Configura un puerto HTTPS privado **8443** para este proyecto:

```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8080
sudo tailscale serve status
```

Si ya tenías un servicio Serve en 8443, elige otro puerto libre de Serve. Si la CLI solicita habilitar HTTPS, abre la URL indicada, habilítalo y repite el comando. Se utiliza el nombre DNS de Tailscale y un certificado válido administrado por Tailscale.

Si falta configuración, en la sección **DNS** de la consola Tailscale activa **MagicDNS** y **HTTPS Certificates**. La pantalla de habilitación informa de la publicación del nombre del certificado en los registros públicos de certificados; el acceso a la API sigue limitado a tu red Tailscale.

Obtendrás una dirección parecida a esta; **la tuya será distinta**:

```text
https://mi-servidor.mi-red.ts.net:8443
```

Guárdala. La API completa será esa dirección seguida de `/v1/usage`. El comando debe indicar que está disponible dentro de tu tailnet. Utilizamos `serve`, que da acceso dentro de esa red privada. No habilites `funnel` para este proyecto, porque publica el servicio en Internet.

`--bg` mantiene Serve activo y recupera la configuración al reiniciar. No hace falta abrir 8080, 8443, 80 o 443 en el router o en el Security Group para publicar esta API. Tailscale necesita poder establecer su propia conexión saliente.

**El servidor queda listo cuando:** Docker está levantado, la consulta local autenticada responde y Serve muestra tu URL privada. Ahora pasa a la Raspberry.

## B. Configurar después la Raspberry Pi Zero 2 W

### B1. Preparar Raspberry Pi OS y la pantalla

Si todavía no tienes sistema, graba Raspberry Pi OS Lite con Raspberry Pi Imager. Configura Wi-Fi, usuario, contraseña y SSH antes de grabar. Monta el HAT con la Raspberry apagada y desconectada; confirma **Waveshare 2.15inch HAT+ (G), 296 × 160**, no otra variante.

Conéctate por SSH desde un computador en la red de la Raspberry, usando su IP local o el nombre configurado. El dominio `.local` solo sirve en esa red local; todavía no es su dirección remota.

Pon el proyecto en la carpeta personal de la Raspberry: `cd ~ && git clone https://github.com/TU_USUARIO/iauso.git` si tiene git, o copiando el mismo ZIP. Ejemplo desde Windows en esa red:

```powershell
scp "$HOME\Downloads\iauso.zip" USUARIO_PI@raspberrypi.local:~/
```

En la Raspberry:

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

El instalador configura SPI y los permisos de GPIO. No inicia las consultas por sí mismo. Usa el mismo usuario para todo el programa de pantalla y sus archivos privados.

### B2. Conectar la Raspberry a la misma red Tailscale

Después del reinicio, vuelve a entrar por SSH. Si Tailscale aún no está instalado:

```bash
curl -fsSL https://tailscale.com/install.sh -o /tmp/iauso-tailscale-install.sh
sudo sh /tmp/iauso-tailscale-install.sh
sudo systemctl enable --now tailscaled
sudo tailscale up
```

Autoriza la Raspberry con el mismo usuario y en la misma red Tailscale que el servidor. Si ya tenías Tailscale, conserva la conexión existente.

```bash
tailscale status
tailscale ip -4
```

Anota la IP Tailscale de la Raspberry, por ejemplo `100.90.0.15`. Esta IP servirá para enviarle la clave. No uses aquí su dirección Wi-Fi `192.168...`.

Prueba desde la Raspberry la URL del servidor obtenida en A6, sustituyendo el ejemplo completo:

```bash
curl --fail --show-error https://mi-servidor.mi-red.ts.net:8443/healthz
```

Debes recibir `{"status":"up"}`. No añadas `-k`: el certificado debe validarse correctamente. Si tu tailnet tiene reglas de acceso personalizadas, deben permitir a la Raspberry llegar al servidor por TCP 8443.

### B3. Transferir la clave propia del panel

Utilizaremos Taildrop, incluido en Tailscale, para transferir únicamente `api-token`. Estos pasos suponen dos equipos personales inscritos con el mismo usuario; Taildrop no está disponible para dispositivos con etiquetas de servidor (`tag:`).

Antes del primer envío, abre **Settings → General** en la consola de Tailscale y activa **Send Files**. Es una función opcional de Tailscale que requiere habilitación. Si la administra una organización, solicita su habilitación al administrador.

En una terminal del **servidor**, sustituye `100.90.0.15` por la IP Tailscale de la Raspberry:

```bash
cd ~/iauso
sudo tailscale file cp secrets/api-token 100.90.0.15:
```

En la **Raspberry**, recibe el archivo y fija sus permisos:

```bash
umask 077
mkdir -p ~/.config/iauso
chmod 700 ~/.config/iauso
sudo tailscale file get --conflict=overwrite "$HOME/.config/iauso"
sudo chown "$(id -u):$(id -g)" "$HOME/.config/iauso/api-token"
chmod 600 ~/.config/iauso/api-token
```

El receptor recoge los archivos pendientes de Taildrop en esa carpeta; envía solo esta clave durante el paso. Si no aparece, comprueba la transferencia del servidor y vuelve a ejecutar `file get`. No copies `server-data/home/` ni las sesiones de proveedores a la Raspberry.

### B4. Configurar la consulta HTTPS

En la Raspberry:

```bash
cd ~/iauso
cp config.json config.previous.json
cp config.api.example.json config.json
nano config.json
```

Sustituye la URL por la obtenida en A6:

```json
{
  "source": "api",
  "api_url": "https://mi-servidor.mi-red.ts.net:8443/v1/usage",
  "api_token_file": "~/.config/iauso/api-token",
  "api_allow_http": false,
  "timezone": "America/Santiago",
  "poll_seconds": 300,
  "stale_after_seconds": 900,
  "display": "epd"
}
```

Para guardar en nano: `Ctrl+O`, `Enter`; para salir: `Ctrl+X`. Si usabas orientación invertida, conserva también `"rotation": 180`.

```bash
python3 -m iauso doctor --config config.json
```

Debe indicar `API accesible` y el estado de cada proveedor. HTTP 401 de tu API apunta a la clave del panel; un JSON válido con `expired` o `needs_auth` apunta a la sesión del proveedor en el servidor.

### B5. Probar la pantalla e iniciar las actualizaciones

Primera prueba física, con datos ficticios:

```bash
python3 -m iauso refresh --config config.json --demo
```

Espera al menos tres minutos desde el intento de refresco. Después:

```bash
python3 -m iauso refresh --config config.json
sudo systemctl enable --now iauso.timer
systemctl list-timers iauso.timer
journalctl -u iauso.service -n 30 --no-pager
```

`deferred` significa que se respeta el intervalo mínimo de la pantalla; el temporizador reintentará. El servicio de pantalla termina entre actualizaciones, mientras que Tailscale permanece conectado. Docker sigue ejecutándose en el servidor.

## C. Mantenimiento y solución de problemas

- **Tailscale no encuentra al otro equipo:** comprueba que ambos aparecen en la misma red de tu cuenta, están autorizados y conectados. Usa `tailscale status`. No es necesario convertirlos en routers ni configurar un exit node.
- **Falla HTTPS:** comprueba la URL exacta de `tailscale serve status`, su puerto y que HTTPS/MagicDNS estén habilitados. Revisa la hora con `timedatectl status` y las reglas de acceso a TCP 8443. No desactives la comprobación de certificados.
- **HTTP 503:** revisa `sudo docker compose logs --tail=50 collector api`; puede que el recolector todavía no haya creado una lectura válida.
- **Datos antiguos:** la pantalla mantiene su última lectura y su fecha. Los ciclos del servidor y de la Raspberry son independientes; la entrega puede tardar cerca de diez minutos en el peor punto de ambos ciclos.
- **Restablecer después de una caída:** Docker usa `restart: unless-stopped`, Serve utiliza `--bg` y la Raspberry tiene un temporizador systemd. Con conexión y sesiones válidas, se recuperan tras el reinicio.

Para evitar que una caducidad de Tailscale desconecte estos dos dispositivos de confianza, puedes abrir [Machines](https://console.tailscale.com/admin/machines), entrar al menú de cada uno y elegir **Disable key expiry**. Así permanecen autorizados hasta que los revoques; esto no renueva las sesiones de Claude ni Codex.

Cuando caduque una sesión del proveedor, ejecuta en el servidor solo el comando correspondiente:

```bash
cd ~/iauso
sudo docker compose --profile auth run --rm auth codex login --device-auth
sudo docker compose --profile auth run --rm auth claude auth login
```

El monitor no renueva tokens por sí mismo ni hace prompts para mantener una sesión. Tampoco mide globalmente todas las funciones de ChatGPT Pro: muestra las cuotas de Codex y las cuotas devueltas por Claude Code para tus suscripciones.

Para rotar la clave propia del panel (no las sesiones de Claude/Codex) usa `sudo python3 scripts/init_server.py --rotate-token` en el servidor — ver el detalle completo en [DOCKER_API.md](DOCKER_API.md#6-comprobar-y-mantener). Después hay que repetir B3 para llevarle la clave nueva a cada Raspberry.

## Alcance de la validación

El código base de API/Raspberry pasó 29 pruebas y una prueba con Gunicorn real. Esta actualización añade instrucciones de red y configuración, sin cambiar el código de consulta ni el controlador. Se verificó la sintaxis de los bloques de comandos y la configuración JSON; no se ejecutaron Docker, Tailscale, logins reales ni el HAT físico en los equipos del usuario.

## Fuentes oficiales

- [Docker Engine para Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
- [Tailscale en Linux](https://tailscale.com/docs/install/linux).
- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve).
- [Referencia de Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).
- [Referencia CLI / transferencia de archivos](https://tailscale.com/docs/reference/tailscale-cli).
- [Taildrop](https://tailscale.com/docs/features/taildrop).
- [Puertos y conectividad](https://tailscale.com/docs/reference/faq/firewall-ports).
- [Caducidad de dispositivos](https://tailscale.com/docs/features/access-control/key-expiry).
- [Autenticación de Codex](https://learn.chatgpt.com/docs/auth).
- [Autenticación de Claude Code](https://code.claude.com/docs/en/authentication).
