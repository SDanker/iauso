# Referencia de `config.json`

Todas las opciones, sus valores por defecto y qué hacen. El archivo es un
JSON plano: solo hace falta escribir las opciones que querés cambiar, el
resto toma el valor por defecto. Una opción con nombre desconocido hace
fallar el arranque a propósito (para que un typo no pase silencioso).

Los valores por defecto viven en `iauso/config.py`, en el
diccionario `DEFAULT` — es el lugar a mirar si tenés dudas.

## Origen de los datos

| Opción | Por defecto | Valores | Qué hace |
|---|---|---|---|
| `source` | `"local"` | `local`, `file`, `api` | De dónde salen las cuotas: leídas acá mismo, recibidas por SSH, o consultadas a tu servidor |
| `api_url` | `""` | URL terminada en `/v1/usage` | Solo con `source: "api"`. Se rechaza si tiene query, fragmento o usuario/contraseña |
| `api_token_file` | `"~/.config/iauso/api-token"` | ruta | Clave del panel; 32 a 128 caracteres URL-safe |
| `api_allow_http` | `false` | `true`/`false` | Permitir `http://` sin cifrar. Dejalo en `false` salvo en una LAN de confianza |
| `snapshot_file` | `"~/.local/state/iauso/inbox.json"` | ruta | Solo con `source: "file"`: el JSON que deja el recolector por SSH |
| `state_dir` | `"~/.local/state/iauso"` | ruta | Caché, estado y `preview.png`. Debe ser escribible por el usuario del servicio |

## Pantalla

| Opción | Por defecto | Valores | Qué hace |
|---|---|---|---|
| `language` | `"en"` | `en`, `es` | Idioma de los textos del panel (`AI QUOTA` / `CUOTAS IA`, `NO CONNECTION` / `SIN CONEXION`...). No afecta a los registros ni a los mensajes de error, que siempre están en inglés |
| `display` | `"epd"` | `epd`, `png` | `epd` dibuja en el panel físico; `png` solo guarda la imagen en `state_dir` (útil para probar sin hardware) |
| `panel` | `"2.15g"` | ver [PANELES.md](PANELES.md) | Modelo de panel Waveshare. Define resolución y colores disponibles |
| `rotation` | `0` | `0`, `180` | Girar la imagen si montaste el panel al revés |
| `warn_percent` | `70` | `0` a `100` | Desde este uso la barra pasa al color de advertencia |
| `crit_percent` | `90` | `0` a `100`, ≥ `warn_percent` | Desde este uso la barra pasa al color crítico |

El mismo panel con tres configuraciones de umbrales (mismos datos, 74 % y
92 % en Claude, 42 % y 18 % en Codex):

![Comparación de umbrales](../thresholds.png)

Los colores según el uso dependen de lo que el panel pueda pintar:

| Modo del panel | Debajo de `warn_percent` | Desde `warn_percent` | Desde `crit_percent` |
|---|---|---|---|
| `mono` (2.13, 2.9, 4.2, 7.5) | negro | negro | negro |
| `duo` (2.13b, 2.9b, 7.5b) | negro | color de tinta | color de tinta |
| `quad` (2.15g) | negro | amarillo | rojo |

Un panel monocromo no puede cambiar de color: los umbrales no lo rompen,
simplemente no se notan. Uno "duo" tiene un solo color además del negro,
así que `warn_percent` y `crit_percent` se ven igual entre sí.

## Ventanas de cuota

| Opción | Por defecto | Qué hace |
|---|---|---|
| `claude_windows` | `["session", "weekly_all"]` | Las **dos** ventanas de Claude a mostrar |
| `codex_windows` | `["primary", "secondary"]` | Las **dos** ventanas de Codex a mostrar |

Identificadores disponibles:

- **Claude:** `session` (5 h), `weekly_all` (7 d), `weekly_opus`, `weekly_sonnet`
- **Codex:** `primary`, `secondary`

Siempre son exactamente dos por proveedor (es lo que entra en el diseño).
Si el proveedor no informa esa ventana, aparece `Sin dato` en vez de un 0 %
inventado.

## Cuentas

| Opción | Por defecto | Qué hace |
|---|---|---|
| `claude.enabled` / `codex.enabled` | `true` | Poné `false` para ocultar ese proveedor; con `false` ni siquiera se leen sus credenciales |
| `claude.credentials_file` | `""` | Ruta explícita. Vacío usa `~/.claude/.credentials.json` (respeta `CLAUDE_CONFIG_DIR` en una terminal) |
| `codex.credentials_file` | `""` | Vacío usa `~/.codex/auth.json` (respeta `CODEX_HOME`) |
| `claude.keychain_service` | `""` | Solo macOS: nombre del servicio en el llavero, p. ej. `"Claude Code-credentials"` |

El servicio systemd **no** hereda las variables de tu terminal: si usás
perfiles con `CLAUDE_CONFIG_DIR` o `CODEX_HOME`, poné rutas explícitas acá.

## Tiempos

| Opción | Por defecto | Rango | Qué hace |
|---|---|---|---|
| `poll_seconds` | `300` | 300 a 86400 | Cada cuánto se consulta. Cambiarlo exige volver a correr `install_pi.sh` para regenerar el timer de systemd |
| `min_refresh_seconds` | `180` | 180 a 86400 | Mínimo entre refrescos físicos del panel. **No lo bajes**: es el límite que protege la pantalla e-ink |
| `stale_after_seconds` | `900` | 300 a 86400 | Después de este tiempo sin lectura buena, el dato se marca como antiguo |
| `http_timeout_seconds` | `15` | 1 a 30 | Espera máxima de cada consulta HTTP |
| `busy_timeout_seconds` | `60` | 20 a 90 | Espera máxima a que el panel libere la señal BUSY antes de abortar |
| `timezone` | `"America/Santiago"` | zona IANA | Zona horaria para las horas de reinicio que se muestran |

---

# Recetas

Cambios concretos, copiables. Después de editar `config.json`:

```bash
python3 -m iauso doctor --config config.json     # valida la config
python3 -m iauso preview --config config.json --demo --output preview.png
```

`preview` no toca el hardware ni las cuentas: sirve para ver el resultado
antes de gastar un refresco del panel.

### Cambiar cuándo la barra cambia de color

Que avise antes (naranja/amarillo desde 50 %, rojo desde 80 %):

```json
{
  "warn_percent": 50,
  "crit_percent": 80
}
```

Que avise solo cuando queda poco:

```json
{
  "warn_percent": 85,
  "crit_percent": 95
}
```

Para dejar las barras casi siempre negras, poné ambos umbrales en `100`:
así solo se colorean al llegar exactamente al 100 % de uso.

Si además querés **otros colores** (no solo otros umbrales), eso sí es un
cambio de código: `ACCENTS` en `iauso/render.py`. Tené en cuenta
que un panel e-ink solo puede pintar los colores de su tinta física — no
sirve poner azul en un panel blanco/negro/rojo.

### Poner el panel en español

```json
{
  "language": "es"
}
```

**El idioma por defecto es inglés**, así que esta línea es la que necesitás si
querés el panel en español (`CUOTAS IA`, `SIN CONEXION`, `RENOVAR SESION`...).
Los registros y los mensajes de error quedan en inglés igual.

Para agregar otro idioma, copiá un bloque de `iauso/i18n.py` y traducí los
valores, manteniendo las claves. Una prueba verifica que todos los idiomas
definan las mismas claves, así una traducción incompleta falla en el test en
vez de aparecer como un hueco en la pantalla.

### Mostrar la cuota semanal de Sonnet en vez de la general

```json
{
  "claude_windows": ["session", "weekly_sonnet"]
}
```

### Mostrar un solo proveedor

```json
{
  "codex": {"enabled": false}
}
```

La columna de Codex queda con el rótulo `DESACTIVADO` y no se lee su
archivo de credenciales.

### Probar todo sin tener el panel conectado

```json
{
  "display": "png"
}
```

Cada ciclo guarda `preview.png` en `state_dir` en vez de dibujar. Útil para
dejarlo corriendo en un servidor y revisar la imagen por SSH, o para
desarrollar el layout.

### Montar el panel al revés

```json
{
  "rotation": 180
}
```

### Consultar cada 10 minutos en vez de cada 5

```json
{
  "poll_seconds": 600
}
```

En la Raspberry, además:

```bash
bash scripts/install_pi.sh          # regenera la unidad systemd
sudo systemctl restart iauso.timer
```

Cambiar solo el JSON no cambia la periodicidad de systemd — el timer se
genera a partir de `poll_seconds` al instalar.
