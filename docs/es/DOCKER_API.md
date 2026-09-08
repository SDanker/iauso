# Servidor Docker + Raspberry por API

**Si los equipos están en redes distintas, utiliza [DOCKER_REDES_DISTINTAS.md](DOCKER_REDES_DISTINTAS.md).** Esa guía ordena la instalación del servidor y después la Raspberry, usando Tailscale y HTTPS privado. El ejemplo LAN de este documento es para equipos que comparten red.

Versión 1.1. El servidor consulta Claude y Codex aproximadamente cada cinco minutos y guarda un JSON. La Raspberry hace `GET /v1/usage`, obtiene ese JSON y actualiza tu Waveshare 2.15inch HAT+ (G). Puedes conectar varias pantallas sin aumentar las consultas a los proveedores.

| Componente | Función | Datos que recibe |
|---|---|---|
| `collector`, en Docker | Consulta y guarda las cuotas | Sesiones de Claude Code y Codex, montadas solo para lectura |
| `api`, en Docker | Sirve la última lectura mediante HTTP | JSON de cuotas y una clave propia del panel |
| `refresher`, en Docker | Renueva las sesiones antes de que expiren, ejecutando las CLI oficiales | Las mismas sesiones, montadas con escritura |
| `auth`, contenedor temporal | Inicia o renueva sesiones usando las CLI oficiales | Tus inicios de sesión, con almacenamiento persistente en el servidor |
| Raspberry | Consulta la API y dibuja la pantalla | Clave propia del panel y porcentajes/fechas/estados |

La API del proyecto no recibe prompts ni hace inferencias. La clave propia del panel se genera localmente y no es una API key de OpenAI o Anthropic. Los porcentajes de Codex corresponden a Codex dentro de tu cuenta ChatGPT, no a todas las funciones de ChatGPT Pro.

## 1. Preparar los equipos

En el servidor necesitas Linux de 64 bits, Docker Engine con Compose v2, Python 3 y acceso a Internet. El contenedor temporal de autenticación admite x86-64 o ARM64. Las CLI pueden requerir bastante más memoria que el monitor; Claude Code publica un requisito de 4 GB de RAM. La Raspberry no ejecutará esas herramientas.

Estos comandos asumen Docker estándar con privilegios de administrador en un servidor personal. Los directorios de los contenedores utilizan UID/GID 1000; Docker rootless o un host con SELinux puede requerir adaptar los permisos/montajes.

Pon el proyecto en ambos equipos. Debe quedar la carpeta `~/iauso/`. Con git:

```bash
cd ~ && git clone https://github.com/TU_USUARIO/iauso.git
```

O, si recibiste el ZIP, desde la carpeta donde lo descargaste:

```bash
python3 -m zipfile -e iauso.zip "$HOME"
```

Si ya tienes la versión anterior, detén primero el temporizador en la Raspberry:

```bash
sudo systemctl stop iauso.timer
```

Conserva tu `config.json` y tus archivos privados al extraer la actualización. El ZIP no contiene credenciales ni un `config.json` personal.

En el servidor:

```bash
cd ~/iauso
sudo docker version
sudo docker compose version
```

Si Docker o el complemento Compose no están instalados, sigue la instalación oficial para [Ubuntu](https://docs.docker.com/engine/install/ubuntu/) o [Debian](https://docs.docker.com/engine/install/debian/), según el sistema del servidor. No ejecutes instrucciones de Ubuntu en Amazon Linux o Windows Server. Esta guía parte de un servidor con Docker operativo.

## 2. Elegir la dirección de la API

**Ejemplo completo para la misma red doméstica:** servidor `192.168.1.100`, puerto `8080`. Sustituye esa IP por la dirección real del servidor, con una reserva DHCP para mantenerla estable.

```bash
cd ~/iauso
sudo python3 scripts/init_server.py --bind 192.168.1.100
```

El inicializador crea carpetas privadas y una clave aleatoria. No muestra la clave, no borra sesiones y no reemplaza archivos existentes. En una segunda ejecución, cambia la IP editando `.env`:

```bash
nano .env
```

Contenido para este ejemplo:

```dotenv
API_BIND_HOST=192.168.1.100
API_PORT=8080
```

HTTP transmite la clave del panel y las cuotas sin cifrado. Utiliza este ejemplo solo en una LAN de confianza o sobre una VPN cifrada. Para un servidor por Internet, publica la API mediante HTTPS o una VPN; no abras el puerto HTTP directamente en el router.

Para un proxy HTTPS que ya funciona en el host, inicia con `sudo python3 scripts/init_server.py` sin `--bind`: la API queda en `127.0.0.1:8080`. Configura tu proxy para reenviar el dominio y la cabecera `Authorization` a esa dirección, sin cachear `/v1/usage`. Si el proxy está en otro contenedor, su `127.0.0.1` es distinto: conecta ambos a una red Docker y usa `http://api:8080` dentro de esa red. El paquete no instala un dominio, un certificado ni modifica tu proxy existente.

## 3. Construir e iniciar sesión en el servidor

```bash
cd ~/iauso
sudo docker compose build collector api
sudo docker compose --profile auth build auth
sudo docker compose --profile auth run --rm auth codex login --device-auth
sudo docker compose --profile auth run --rm auth claude auth login
```

En Codex, abre la URL indicada en tu computador o teléfono y completa el código con tu cuenta ChatGPT. Este método puede requerir habilitar la autenticación por dispositivo en la seguridad de tu cuenta.

En Claude, abre la URL indicada y elige tu suscripción Claude. Si no funciona el retorno automático al contenedor, copia el código que entrega el navegador en la terminal cuando la herramienta lo solicite. No elijas Console/API billing ni agregues `--console` para este monitor de suscripción.

El contenedor `auth` se elimina al terminar cada comando, pero las sesiones permanecen en `server-data/home/`. Su configuración fuerza el almacenamiento de Codex en archivo. No copies esa carpeta a la Raspberry ni la incluyas en un repositorio.

Comprueba que el recolector puede leer las sesiones:

```bash
sudo docker compose run --rm collector python -m iauso doctor --config /app/docker/config.collector.json
```

`sesion local legible` significa que el archivo está disponible; la aceptación por el proveedor se comprueba en el siguiente paso.

Arranca los servicios permanentes:

```bash
sudo docker compose up -d collector api refresher
sudo docker compose ps
sudo docker compose logs --tail=30 collector api
```

Busca `Claude=ok, Codex=ok` en el registro del recolector. Puede aparecer otro estado si la cuenta no devuelve cuotas o la sesión necesita renovación. Los servicios se reinician con Docker tras reiniciar el servidor; no hace falta mantener una terminal abierta.

La imagen de autenticación instala los paquetes oficiales disponibles cuando se construye. Puedes fijar versiones con `--build-arg CODEX_VERSION=... --build-arg CLAUDE_VERSION=...`. La imagen del monitor fija Gunicorn 26.2.0 y no instala Pillow, GPIO ni las CLI.

## 4. Entregar a la Raspberry la clave del panel

En el servidor crea una copia privada temporal, legible por tu usuario SSH:

```bash
cd ~/iauso
sudo install -o "$(id -un)" -g "$(id -gn)" -m 600 secrets/api-token "$HOME/iauso-api-token.txt"
```

En la Raspberry, cambia `usuario_servidor` y la IP por tus valores:

```bash
umask 077
mkdir -p ~/.config/iauso
scp usuario_servidor@192.168.1.100:~/iauso-api-token.txt ~/.config/iauso/api-token
chmod 600 ~/.config/iauso/api-token
```

Verifica la identidad SSH del servidor cuando se solicite. Este paso usa SSH cifrado y no imprime la clave ni la incluye en la línea de comandos. Utiliza en la Raspberry el mismo usuario que instalará el servicio de pantalla.

Cuando la copia termine correctamente, en el servidor elimina únicamente la copia temporal:

```bash
rm ~/iauso-api-token.txt
```

El original `secrets/api-token` debe permanecer en el servidor. No es una contraseña de ChatGPT/Claude; autoriza la lectura de este panel.

## 5. Instalar y configurar la Raspberry

Con Raspberry Pi OS Lite y el HAT ya montado, desde tu usuario habitual:

```bash
cd ~/iauso
bash scripts/install_pi.sh
sudo reboot
```

Si ya habías instalado esta versión del servicio, no hace falta repetir el montaje ni la prueba física. Después del reinicio, vuelve a conectarte por SSH. Guarda la configuración anterior y crea la de API:

```bash
cd ~/iauso
cp config.json config.previous.json
cp config.api.example.json config.json
nano config.json
```

Para el servidor de ejemplo en la LAN:

```json
{
  "source": "api",
  "api_url": "http://192.168.1.100:8080/v1/usage",
  "api_token_file": "~/.config/iauso/api-token",
  "api_allow_http": true,
  "timezone": "America/Santiago",
  "poll_seconds": 300,
  "stale_after_seconds": 900,
  "display": "epd"
}
```

Con un dominio HTTPS, utiliza `"api_url": "https://tu-dominio/v1/usage"` y `"api_allow_http": false`. La Raspberry verifica el certificado. No se siguen redirecciones: utiliza directamente la URL final. Conserva tu `rotation` si habías invertido la orientación del panel.

Prueba la conexión sin refrescar la pantalla:

```bash
python3 -m iauso doctor --config config.json
```

Debe indicar `API accesible` y el estado de ambos proveedores. Esto sí realiza una consulta HTTP a tu servidor, pero no provoca una consulta adicional a los proveedores.

Para la primera prueba física:

```bash
python3 -m iauso refresh --config config.json --demo
```

Espera al menos tres minutos después del intento de refresco antes de la prueba con datos reales:

```bash
python3 -m iauso refresh --config config.json
sudo systemctl enable --now iauso.timer
```

Si aparece `deferred`, el programa está respetando el intervalo de la pantalla. El siguiente ciclo automático reintentará. El panel usa refresco completo y entra en reposo al terminar.

## 6. Comprobar y mantener

En la Raspberry:

```bash
systemctl list-timers iauso.timer
journalctl -u iauso.service -n 30 --no-pager
```

En el servidor:

```bash
cd ~/iauso
sudo docker compose ps
sudo docker compose logs --tail=50 collector api
```

Cada equipo tiene su propio ciclo de unos cinco minutos. Una lectura puede demorarse cerca de dos ciclos en llegar al panel. Se marca antigua después de 15 minutos sin una consulta correcta. La hora del JSON no se reemplaza por la hora de la petición HTTP. Si falta Internet, se conservan los valores previos con su fecha y estado de error; no se reemplazan por 0 %.

### Mantener las sesiones vivas

**Las sesiones no se renuevan por el solo hecho de tener Docker encendido.** El recolector solo las lee; renovarlas es tarea de las CLI oficiales, y en un servidor dedicado nadie las ejecuta nunca. El access token de Claude dura unas **8 horas** (el de Codex, unos 10 días), así que sin ayuda el panel queda mostrando `RENOVAR SESION` pocas horas después de cada login.

El servicio **`refresher`** cierra ese hueco, y arranca junto con el resto del stack:

```bash
sudo docker compose up -d collector api refresher
```

Ejecuta `scripts/refresh_loop.sh` dentro de la misma imagen que tiene las CLI, con el mismo volumen de credenciales, así que **no necesita el socket de Docker ni un planificador en el host** — funciona igual en Linux, macOS o Windows. Cada 30 minutos lee la expiración local (gratis, sin red) y solo cuando a un token le queda poco ejecuta una vez la CLI oficial, que refresca el token como efecto secundario. Después relee el archivo para confirmar que ocurrió. No se reimplementa nada: los archivos de credenciales los sigue escribiendo únicamente su propia CLI.

```bash
sudo docker compose logs refresher
```

```
2026-09-08T13:49:20Z claude: 7 h left, nothing to do
2026-09-08T13:49:20Z codex: 225 h left, nothing to do
```

Para comprobarlo a mano sin esperar a la próxima pasada:

```bash
sudo docker compose run --rm -T refresher bash /app/scripts/refresh_loop.sh --once
```

El refresco de Claude ejecuta un prompt de una palabra, porque es la única llamada que se comprobó que dispara la renovación (`claude auth status` lee el archivo sin renovar nada). Cuesta una porción despreciable de cuota, unas pocas veces al día. El de Codex usa `codex exec`, por lo mismo: `codex login status` también resultó ser de solo lectura. Codex no se pudo probar cerca de la expiración (su token dura ~10 días), así que esa parte es por analogía; si alguna vez no renueva, el log lo dice. El ritmo se ajusta con `REFRESH_INTERVAL_SECONDS`, `CLAUDE_MARGIN_HOURS` y `CODEX_MARGIN_HOURS`.

Cuando caduca el propio refresh token, ninguna automatización sirve: el log dice `sign in again` y hay que volver a iniciar sesión con los comandos de abajo.

Cuando aparezca `RENOVAR SESION`, repite el login del proveedor correspondiente en el servidor:

```bash
sudo docker compose --profile auth run --rm auth codex login --device-auth
sudo docker compose --profile auth run --rm auth claude auth login
```

Ejecuta solo el comando de la cuenta que lo necesite. Las CLI oficiales administran esos inicios de sesión. El monitor no implementa un flujo OAuth alternativo, no ejecuta prompts para mantener sesiones vivas y no promete renovación indefinida. El próximo ciclo leerá las nuevas credenciales; si existe un plazo por HTTP 429, se mantiene.

Para actualizar las CLI del contenedor temporal:

```bash
sudo docker compose --profile auth build --pull --no-cache auth
```

Para detener el monitor del servidor conservando sesiones y caché:

```bash
sudo docker compose down
```

No borres `server-data/` para resolver un HTTP 429: ahí también se conserva la espera del proveedor. Para rotar la clave propia del panel (por ejemplo si sospechás que se filtró):

```bash
cd ~/iauso
sudo python3 scripts/init_server.py --rotate-token
sudo docker compose up -d --force-recreate api
```

La clave anterior deja de servir en cuanto `api` se recrea. Copiá la nueva a cada Raspberry (reemplazando `~/.config/iauso/api-token`) antes o inmediatamente después — mientras tanto esas Raspberries van a recibir HTTP 401.

## 7. Referencia de la API

| Ruta / respuesta | Significado |
|---|---|
| `GET /v1/usage`, `Authorization: Bearer …` | Devuelve esquema JSON v1 con cuotas, estados y fechas |
| HTTP 200 | JSON válido; revisa los estados de cada proveedor para saber si hay datos recientes |
| HTTP 401 | Clave propia del panel ausente o incorrecta; es independiente del login de Claude/Codex |
| HTTP 503 | No existe todavía un snapshot válido o falta configurar la clave de la API |
| HTTP 405 | Solo se permite GET |
| `GET /healthz` | Comprueba que el proceso HTTP responde; no verifica cuotas ni sesiones |

Ejemplo ilustrativo parcial, **no una lectura real**:

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

No se envían tokens de sesión, IDs de cuenta ni archivos de autenticación. La Raspberry mantiene su caché privada y rechaza JSON malformado, snapshots DEMO y fechas fuera de orden. La API no acepta credenciales en la URL ni dispone de rutas de escritura.

**Validación realizada:** pruebas HTTP locales de autenticación, API, cliente, errores y renderizado con datos simulados. Consulta [VALIDACION.md](VALIDACION.md) para el resultado exacto. No se construyeron las imágenes Docker en este entorno ni se ejecutaron logins reales o pruebas sobre el HAT físico.

Fuentes: [Codenotch](https://github.com/vinzdg/codenotch), [autenticación de Codex](https://learn.chatgpt.com/docs/auth), [instalación de Codex](https://github.com/openai/codex), [CLI Claude](https://code.claude.com/docs/en/cli-reference), [sesiones de Claude](https://code.claude.com/docs/en/authentication), [instalación de Claude](https://code.claude.com/docs/en/setup), [secretos Compose](https://docs.docker.com/compose/how-tos/use-secrets/) y [Gunicorn](https://pypi.org/project/gunicorn/).
