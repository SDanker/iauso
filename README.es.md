# iauso — cuotas de IA en una pantalla e-ink

*[Read this in English](README.md)*

**iauso** ("IA · uso") muestra cuánto llevás consumido de tus cuotas de
**Claude** y **Codex** en una pantalla e-ink conectada a una Raspberry Pi:
porcentaje usado, cuándo se reinicia cada ventana y si alguna sesión
necesita atención. Sin escritorio, sin proceso pesado corriendo — un
refresco corto cada cinco minutos.

También podés leer los mismos datos desde una web o un bot de Telegram
(ver [docs/es/INTEGRACIONES.md](docs/es/INTEGRACIONES.md)), o dejar las consultas
en un servidor y que la pantalla solo las lea.

Adaptación en Python de las consultas de uso de [vinzdg/codenotch](https://github.com/vinzdg/codenotch). Nació para el **Waveshare 2.15inch e-Paper HAT+ (G)** (**296 × 160**, negro, blanco, rojo y amarillo) y es el único panel probado en hardware físico. Desde la versión 1.2 también admite otros paneles Waveshare comunes (2.13", 2.9", 4.2", 7.5", con y sin segundo color) reutilizando sus controladores oficiales — ver [docs/es/PANELES.md](docs/es/PANELES.md). Incluye los controladores oficiales vendorizados; no hay que descargar todo el repositorio de Waveshare.

![Panel con datos ficticios](docs/panel-demo.png)

El programa muestra **porcentaje utilizado**, dos cuotas por proveedor y la fecha/hora de reinicio. Amarillo desde 70 %; rojo desde 90 % — y esos dos umbrales se cambian con `warn_percent`/`crit_percent` en `config.json`, sin tocar código ([ver cómo](docs/es/CONFIGURACION.md#pantalla)). La hora predeterminada es `America/Santiago`, con cambio de horario según la base de zonas horarias del sistema.

## Por dónde empezar

| Quiero... | Leer |
|---|---|
| Entender qué hace y montar la Raspberry | Este README, desde [1. Montaje e instalación](#1-montaje-e-instalación) |
| **Cambiar algo** (colores, umbrales, ventanas, tiempos) | **[docs/es/CONFIGURACION.md](docs/es/CONFIGURACION.md)** — todas las opciones + recetas copiables |
| Usar otro panel e-ink, no el 2.15G | [docs/es/PANELES.md](docs/es/PANELES.md) |
| Dejar las consultas en un servidor con Docker | [docs/es/DOCKER_API.md](docs/es/DOCKER_API.md) |
| Lo mismo, pero servidor y Raspberry en redes distintas | [docs/es/DOCKER_REDES_DISTINTAS.md](docs/es/DOCKER_REDES_DISTINTAS.md) |
| Un servidor sin Docker, solo Python + systemd | [docs/es/SIN_DOCKER.md](docs/es/SIN_DOCKER.md) |
| Leer las cuotas desde una web o un bot de Telegram | [docs/es/INTEGRACIONES.md](docs/es/INTEGRACIONES.md) |
| Saber de dónde salen los datos y qué se probó | [docs/es/FUENTES.md](docs/es/FUENTES.md), [docs/es/VALIDACION.md](docs/es/VALIDACION.md) |

**Novedades de la 1.2:** más paneles Waveshare, idioma del panel configurable (`language`, inglés por defecto — poné `"es"` para mantenerlo en español), umbrales de color configurables (`warn_percent`/`crit_percent`), servidor sin Docker, integraciones web/Telegram, CORS en la API y `scripts/init_server.py --rotate-token` para rotar la clave del panel sin reinstalar.

## Qué incluye y qué está probado

- Programa Python ligero en la Raspberry, sin escritorio gráfico.
- Consulta de Claude y Codex, caché privada y espera persistente ante HTTP 429.
- Modo receptor por SSH: las credenciales pueden permanecer en otro computador.
- Modo API: servidor Docker permanente y lectura HTTP/HTTPS desde la Raspberry.
- Vista previa PNG y modo DEMO sin Internet ni cuentas.
- Instalador para Raspberry Pi OS, servicio y temporizador systemd.
- Pruebas automáticas del procesamiento, errores, antigüedad y empaquetado real de los cuatro colores.
- Soporte para otros paneles Waveshare comunes además del 2.15G (ver [docs/es/PANELES.md](docs/es/PANELES.md); solo el 2.15G está probado en hardware físico).
- Servidor y API sin depender de Docker, con las mismas unidades systemd que la Raspberry (ver [docs/es/SIN_DOCKER.md](docs/es/SIN_DOCKER.md)).
- La API acepta CORS (`Access-Control-Allow-Origin: *`) y se puede consultar desde una página web o un bot de Telegram además de la pantalla (ver [docs/es/INTEGRACIONES.md](docs/es/INTEGRACIONES.md)).

**Se probó el software con respuestas simuladas y el método `getbuffer()` del controlador oficial. No se probó físicamente tu pantalla ni se consultaron tus cuentas.** La primera prueba en la Raspberry debe ser el modo DEMO.

Esta versión muestra cuotas. No incluye los indicadores de agentes trabajando/esperando, otros proveedores ni el monitor de actividad local de la aplicación de Mac.

## Obtener el proyecto

En cada equipo donde lo vayas a usar (la Raspberry, y el servidor si usás
el modo `api`), la carpeta tiene que quedar como `~/iauso/`.

Con git:

```bash
cd ~
git clone https://github.com/TU_USUARIO/iauso.git
cd iauso
```

O, si recibiste el ZIP en vez del repositorio:

```bash
cd ~
python3 -m zipfile -e iauso.zip "$HOME"
cd iauso
```

Para **actualizar** una instalación existente, `git pull` (o volver a
extraer el ZIP) es seguro: tu `config.json`, `secrets/` y `server-data/`
no están versionados y no se tocan.

### Venís de la versión 1.1 (`codenotch-eink`)

En la 1.2 el proyecto pasó a llamarse **iauso**: cambia el nombre del
comando, de las unidades systemd y de las carpetas de configuración y
estado. En la Raspberry, `scripts/install_pi.sh` hace la migración solo:
desactiva y borra las unidades viejas, mueve `~/.config/codenotch-eink` y
`~/.local/state/codenotch-eink` a sus nombres nuevos (conservando la clave
del panel y el estado) y corrige las rutas que hayan quedado escritas
dentro de tu `config.json`, dejando una copia en `config.json.bak`.

```bash
cd ~/iauso                     # el proyecto nuevo, junto al viejo
cp ~/codenotch-eink/config.json .
bash scripts/install_pi.sh
sudo systemctl enable --now iauso.timer
python3 -m iauso doctor --config config.json
```

Cuando `doctor` responda bien podés borrar `~/codenotch-eink`.

En el servidor con Docker, el proyecto y la imagen de Compose también
cambian de nombre: bajá el stack viejo (`docker compose -p codenotch-eink
down`) antes de levantar el nuevo, y llevate `.env`, `secrets/` y
`server-data/` a la carpeta nueva para conservar las sesiones y la clave.

## 1. Montaje e instalación

Necesitas Raspberry Pi OS Lite con Python 3.9 o superior, microSD, Wi-Fi configurado, alimentación estable y el cabezal GPIO de 40 pines instalado. Para una instalación nueva, Raspberry Pi OS Lite de 64 bits permite además evaluar las CLI oficiales ARM64. El programa de pantalla funciona también con un sistema de 32 bits compatible.

1. **Apaga y desconecta la Raspberry antes de montar el HAT.** Alinea el pin 1 y asienta el conector de 40 pines. Por defecto el programa espera un **2.15 / G**; si tu panel es otro (2.13", 2.9", 4.2", 7.5"...) configuralo con `"panel"` en `config.json` — ver [docs/es/PANELES.md](docs/es/PANELES.md) antes de continuar.
2. Poné el proyecto en la carpeta personal de la Raspberry (ver [Obtener el proyecto](#obtener-el-proyecto)). Debe quedar `~/iauso/README.md`.
3. Entra por SSH y ejecuta, con tu usuario habitual:

```bash
cd ~/iauso
bash scripts/install_pi.sh
sudo reboot
```

El instalador usa `sudo` para instalar los paquetes de Raspberry Pi OS, habilitar SPI, asignar grupos `gpio`/`spi` y crear las unidades systemd. No inicia las consultas todavía. La ruta de instalación debe mantenerse, porque el servicio la utiliza. Si mueves la carpeta, ejecuta de nuevo el instalador.

El programa usa el bus **SPI0, CE0**, que aparece como `/dev/spidev0.0`. Todos los paneles soportados (ver [docs/es/PANELES.md](docs/es/PANELES.md)) usan la misma asignación BCM estándar de Waveshare:

| Señal | GPIO BCM | Pin físico |
|---|---:|---:|
| MOSI / DIN | 10 | 19 |
| SCLK / CLK | 11 | 23 |
| CS | 8 | 24 |
| DC | 25 | 22 |
| RST | 17 | 11 |
| BUSY | 24 | 18 |
| Control PWR | 18 | 12 |

Con el HAT montado directamente no necesitas cablear estas señales. La tabla describe el controlador; sigue el manual de Waveshare para una conexión por cables y para alimentación.

## 2. Primera prueba de pantalla

Después del reinicio, vuelve a conectarte por SSH:

```bash
cd ~/iauso
python3 -m iauso doctor --config config.json
python3 -m iauso refresh --config config.json --demo
```

Verás un panel con la etiqueta **DEMO** y valores ficticios. El refresco completo de esta pantalla es lento: puede parpadear y tardar alrededor de 20 segundos. Al terminar, el programa pone el controlador en reposo y la imagen permanece visible.

No ejecutes ejemplos de otros paneles. El programa impone **180 segundos entre intentos de refresco**, incluso después de reiniciarlo. Si ejecutas dos pruebas seguidas, la segunda puede indicar `deferred`: espera a que transcurra ese intervalo. Si la imagen no cambió, indica `unchanged`; aun así programa un refresco de mantenimiento aproximadamente diario mientras el servicio está habilitado.

Para invertir el panel, cambia `"rotation": 0` por `"rotation": 180` en `config.json`.

## 3. Elige de dónde vendrán las cuotas

| Modo | Dónde se consultan las cuotas | Dónde permanecen las credenciales |
|---|---|---|
| `local` | En la Raspberry, usando las sesiones que existan allí | En la Raspberry |
| `file` | En un computador; envía un JSON por SSH a la Raspberry | En ese computador |
| `api` | En un servidor Docker; la Raspberry lee `GET /v1/usage` | En el servidor |

**Para tu servidor encendido permanentemente, utiliza `api` y sigue [DOCKER_API.md](docs/es/DOCKER_API.md).** El modo `file` también permite aprovechar las sesiones del computador donde ya trabajas con las CLI. En ese caso, el computador debe estar encendido y conectado para actualizar. Ambos modos evitan instalar las herramientas de IA en la Raspberry.

### A. Raspberry como receptor; computador como recolector

En la Raspberry:

```bash
cd ~/iauso
cp config.receiver.example.json config.json
```

En tu computador, extrae también el proyecto. Instala Python 3.9 o superior y el cliente OpenSSH si no los tienes. El recolector no necesita Pillow ni el controlador GPIO. En Windows instala los datos de zona horaria:

```powershell
python -m pip install tzdata
```

Inicia sesión en **Codex con tu suscripción ChatGPT** y en **Claude Code con tu suscripción Claude**. Tener solo las sesiones abiertas en un navegador no crea los archivos que lee este programa.

El recolector reconoce estos archivos (si las herramientas guardan allí la sesión):

| Herramienta | Linux/macOS con archivo | Windows con archivo |
|---|---|---|
| Codex | `~/.codex/auth.json` | `%USERPROFILE%\.codex\auth.json` |
| Claude Code | `~/.claude/.credentials.json` | `%USERPROFILE%\.claude\.credentials.json` |

Si ejecutas Claude Code en WSL, ejecuta también el recolector dentro de WSL para que vea su sesión.

En macOS, Claude suele usar el llavero. Crea `config.collector.json` con:

```json
{
  "source": "local",
  "claude": {"keychain_service": "Claude Code-credentials"}
}
```

Ese nombre corresponde al perfil predeterminado; para perfiles separados indica el servicio correcto. El sistema puede solicitar acceso al llavero. El programa captura la credencial internamente y no la imprime.

Si Codex utiliza el almacén seguro del sistema en lugar de `auth.json`, la lectura por archivo no funcionará. En un equipo personal sin una política que lo prohíba, puedes configurar **`cli_auth_credentials_store = "file"`** en `~/.codex/config.toml` y volver a iniciar sesión con `codex login`. Eso guarda tokens en un archivo privado; no lo compartas ni lo incluyas en el proyecto. El monitor nunca cambia esa configuración por su cuenta.

Comprueba primero las sesiones y crea una lectura, desde la raíz del proyecto en el computador:

```bash
python3 -m iauso doctor
python3 -m iauso collect --output snapshot.json
```

En Mac, agrega `--config config.collector.json` a ambos comandos. En Windows puedes utilizar `python` en lugar de `python3`.

Configura acceso SSH por clave a la Raspberry. Primero prueba una conexión interactiva para verificar su identidad y configurar el acceso; cambia `usuario` y el nombre del equipo por los tuyos:

```bash
ssh usuario@raspberrypi.local
```

Después, el recolector exige acceso por clave sin preguntas (`BatchMode=yes`). No desactiva la verificación del servidor. Si tu SSH usa otro puerto, define un alias en `~/.ssh/config` y pásalo como destino. Inicia el envío periódico:

```bash
python3 -m iauso collect --loop --push usuario@raspberrypi.local
```

Para Mac con llavero:

```bash
python3 -m iauso collect --config config.collector.json --loop --push usuario@raspberrypi.local
```

El destino recibido es `~/.local/state/iauso/inbox.json`, bajo el usuario SSH. Usa **el mismo usuario que instaló el servicio** en la Raspberry. Se transmite exclusivamente una lista de cuotas, fechas y estados, cifrada por SSH, con reemplazo atómico del archivo. No se instala ningún servidor HTTP ni se abren puertos nuevos.

El comando `--loop` debe seguir ejecutándose. En Windows puedes iniciarlo al iniciar sesión con el Programador de tareas; en Linux/Mac, con el mecanismo de inicio de tu sistema. Esa automatización del computador no se instala desde este paquete.

### B. Consulta local en la Raspberry

Mantén `"source": "local"` en `config.json`. El programa requiere sesiones de suscripción creadas por las herramientas oficiales bajo **el mismo usuario que ejecuta el servicio**.

La instalación de las CLI oficiales queda separada porque sus requisitos de arquitectura y memoria son distintos a los del panel, especialmente en una Zero 2 W de 512 MB. Si no funcionan en tu sistema, utiliza el modo receptor anterior; este paquete no instala versiones no oficiales.

Si Codex ya está instalado, el inicio de sesión sin pantalla puede hacerse con:

```bash
codex login --device-auth
```

Abre la dirección indicada en otro dispositivo y completa el inicio de sesión. Puede requerir habilitar ese método en la configuración de seguridad de la cuenta. El monitor debe poder leer `~/.codex/auth.json`; si se usa keyring, consulta la configuración de almacenamiento descrita arriba.

En Claude Code, ejecuta `claude` y completa el inicio de sesión con tu cuenta de suscripción, o usa `/login` dentro de la herramienta. En Linux, sus credenciales se almacenan en `~/.claude/.credentials.json`.

También puedes fijar las rutas en `config.json`:

```json
{
  "source": "local",
  "claude": {"enabled": true, "credentials_file": "/home/usuario/.claude/.credentials.json"},
  "codex": {"enabled": true, "credentials_file": "/home/usuario/.codex/auth.json"}
}
```

Los valores vacíos usan las rutas predeterminadas y, en una terminal, respetan `CLAUDE_CONFIG_DIR` y `CODEX_HOME`. El servicio systemd no hereda las variables de tu terminal: utiliza rutas explícitas si tienes perfiles personalizados.

**Renovación de sesiones:** igual que Codenotch, el monitor solo lee los tokens. No los renueva ni modifica. Cuando caduquen mostrará `RENOVAR SESION`; abre la herramienta oficial correspondiente para que renueve su sesión. Por eso no prometemos una Raspberry autónoma indefinidamente con una copia de credenciales. El modo receptor aprovecha las sesiones del computador donde trabajas.

## 4. Iniciar las actualizaciones automáticas

Con la pantalla probada y uno de los modos configurado:

```bash
cd ~/iauso
python3 -m iauso refresh --config config.json
sudo systemctl enable --now iauso.timer
```

El temporizador ejecuta un proceso corto aproximadamente cada cinco minutos; no deja un proceso gráfico consumiendo memoria. Después de un reinicio arranca automáticamente. Con el modo receptor, habrá además el desfase entre el envío y la lectura; son dos ciclos independientes.

Comandos de operación:

```bash
systemctl list-timers iauso.timer
journalctl -u iauso.service -n 50 --no-pager
sudo systemctl start iauso.service
sudo systemctl disable --now iauso.timer
```

Si cambias `poll_seconds`, vuelve a ejecutar el instalador para regenerar el temporizador y después `sudo systemctl restart iauso.timer`. Cambiar solamente el JSON no cambia la periodicidad de systemd. Nunca reduzcas los límites de reposo para forzar una animación en esta pantalla.

## Qué significan los datos

| Indicador | Significado |
|---|---|
| `5 h`, `7 d` | Ventanas de cuota; en Codex se usa la duración que devuelve el servicio |
| `74%` | Porcentaje consumido de esa ventana, no porcentaje restante |
| `R:` | Fecha/hora local de reinicio informada por el proveedor |
| `Dato DD/MM HH:MM` | Última consulta correcta de ese proveedor |
| `INICIAR SESION` / `RENOVAR SESION` | Falta una sesión legible o ha vencido |
| `SIN CONEXION` / `ANT.` / asterisco | Lectura anterior; no se presenta como recién consultada |
| `ESPERAR / 429` | Espera exigida por el proveedor; se conserva entre ejecuciones |
| `Sin dato` | Cuota no informada; no se reemplaza por 0 % |
| `R: por confirmar` | Pasó la fecha de reinicio; hace falta una nueva lectura para conocer el uso |

El panel muestra por defecto sesión y cuota semanal general. El JSON conserva otras ventanas informadas por Claude. Para mostrar, por ejemplo, la semanal de Sonnet, cambia `claude_windows` a `["session", "weekly_sonnet"]`. Si el proveedor no entrega esa cuota, aparecerá `Sin dato`.

**Claude:** lee las cuotas de suscripción que entrega el endpoint de Claude Code. **Codex:** lee las cuotas principales de Codex asociadas a la cuenta ChatGPT; no es un medidor global de todas las funciones de ChatGPT Pro. Este programa no usa una API key de pago por tokens.

Ambas consultas reutilizan interfaces internas de los servicios, como hace Codenotch. Pueden cambiar de esquema o rechazar accesos. La existencia de este código no garantiza disponibilidad del endpoint para todas las cuentas.

## Previsualizar sin Raspberry

```bash
python3 -m pip install -r requirements-preview.txt
python3 -m iauso preview --demo --output panel.png
python3 -m unittest discover -s tests -v
```

`--demo` nunca lee credenciales ni hace consultas. El DEMO tampoco se acepta como snapshot real en modo receptor.

## Resolver problemas

- **No existe `/dev/spidev0.0`:** verifica SPI en `sudo raspi-config`, reinicia y comprueba que no se haya deshabilitado en la configuración de arranque.
- **Permiso denegado en GPIO/SPI:** vuelve a iniciar sesión después del instalador; revisa `id` y los grupos `gpio` y `spi`. Para pruebas manuales puedes usar `GPIOZERO_PIN_FACTORY=lgpio python3 -m iauso refresh --config config.json --demo`.
- **BUSY no libera o pantalla en blanco:** detén el temporizador, apaga la Raspberry, comprueba el modelo 2.15 G, la alineación y la alimentación. El controlador tiene tiempo máximo de espera. No repitas refrescos continuamente.
- **Sesión legible pero HTTP 401/403:** abre la herramienta oficial para renovar o iniciar sesión. `doctor` verifica lectura local, no que el servidor acepte la sesión. Una API key o una sesión solo en navegador no reemplazan esa sesión de suscripción.
- **No cambia tras renovar sesión:** espera el siguiente ciclo; las consultas respetan el plazo persistido. HTTP 429 puede exigir esperar más de cinco minutos.
- **No llega el JSON:** prueba SSH con el mismo usuario/alias del recolector. El envío automático requiere clave sin interacción y el computador encendido. Después de 15 minutos sin datos recientes se marcan como antiguos.
- **Falla el modo API:** ejecuta `doctor --config config.json`, comprueba la URL final y la clave propia del panel. HTTP 401 de esta API no es lo mismo que una sesión de proveedor caducada. Comprueba los registros de `collector` en el servidor. La API entrega datos en caché y no hace consultas a proveedores por cada petición.
- **Fecha u hora incorrecta:** comprueba `timedatectl status` y activa la sincronización con `sudo timedatectl set-ntp true`. Mantén `tzdata` actualizado. La Raspberry y el computador deben tener la hora correcta.
- **Estado corrupto:** detén el temporizador y espera al menos tres minutos desde el último intento de refresco. Renombra `~/.local/state/iauso/state.json` a `state.backup.json`, revisa el problema y vuelve a iniciar el temporizador. Esa recuperación elimina la caché y los plazos de espera: no la uses para saltarte un HTTP 429.
- **El servicio termina:** `Type=oneshot` termina después de cada lectura; es normal que no quede `active (running)`. Comprueba el temporizador y los registros.

## Organización y referencias

`iauso/` contiene los módulos de consulta, estado, renderizado y pantalla. `vendor/waveshare_epd/` contiene los dos archivos oficiales de Waveshare. `scripts/` instala las dependencias y genera systemd. `tests/` permite verificar el software sin equipos ni cuentas.

Consulta [docs/es/FUENTES.md](docs/es/FUENTES.md) para los commits exactos y los orígenes. Se conserva la licencia MIT original de Codenotch en `LICENSE-CODENOTCH`; los archivos Waveshare conservan su aviso de licencia. La adaptación se entrega con licencia MIT en `LICENSE`.
