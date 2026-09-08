# Paneles Waveshare soportados

El proyecto nacio para el **Waveshare 2.15inch e-Paper HAT+ (G)** (296x160,
negro/blanco/amarillo/rojo) y es el unico panel **probado en hardware
fisico**. A partir de la version 1.2 tambien admite otros paneles Waveshare
comunes reutilizando sus drivers oficiales — el mismo commit documentado en
[FUENTES.md](FUENTES.md) — pero **sin haberlos probado en un panel real**.

## Paneles disponibles

| `"panel"` en config.json | Tamano | Colores | Probado en hardware |
|---|---|---|---|
| `2.15g` (por defecto) | 296x160 | negro/blanco/amarillo/rojo | Si |
| `2.13` | 250x122 | negro/blanco | No |
| `2.13b` | 250x122 | negro/blanco + rojo | No |
| `2.9` | 296x128 | negro/blanco | No |
| `2.9b` | 296x128 | negro/blanco + rojo o amarillo | No |
| `4.2` | 400x300 | negro/blanco | No |
| `7.5` | 800x480 | negro/blanco | No |
| `7.5b` | 800x480 | negro/blanco + rojo | No |

Los paneles "mono" (sin sufijo) solo pueden pintar negro y blanco: los
porcentajes de uso se muestran igual, pero la barra nunca cambia de color
segun el nivel de uso. Los paneles "b" tienen un segundo color de tinta
(rojo, o amarillo en algunas variantes fisicas del 2.9"); la barra usa ese
color a partir de `warn_percent` (70% por defecto). Solo el 2.15G distingue
ademas un umbral critico, `crit_percent` (90% por defecto), con un segundo
color (rojo sobre amarillo). Ambos umbrales se configuran — ver
[CONFIGURACION.md](CONFIGURACION.md#pantalla).

## Como elegir un panel

En tu `config.json`:

```json
{
  "panel": "7.5"
}
```

El resto de la configuracion no cambia. `python3 -m iauso doctor
--config config.json` valida que el nombre sea uno de los soportados y
muestra la resolucion elegida.

## Revisar el layout antes de instalar el HAT

No hace falta tener el panel fisico para ver como va a quedar: cualquier
computador con Python y Pillow (`pip install -r requirements-preview.txt`)
puede generar una vista previa:

```bash
python3 -m iauso preview --config config.json --demo --output preview.png
```

Abri `preview.png` y confirma que el texto se lea bien y nada se corte
antes de instalar el HAT y ejecutar `refresh` contra hardware real.

## Cableado

Todos los paneles de esta lista usan el mismo pinout estandar de Waveshare
(el mismo HAT de 40 pines que el 2.15G): `RST=GPIO17, DC=GPIO25, CS=GPIO8
(SPI0 CE0), BUSY=GPIO24, PWR=GPIO18, MOSI=GPIO10, SCLK=GPIO11`. Si tu panel
viene como HAT (se enchufa directo al header de 40 pines) no hay que
cablear nada. Si viene como placa driver suelta con cable plano, respeta
esa distribucion de pines.

`scripts/install_pi.sh` habilita SPI y los permisos de GPIO igual para
todos los paneles de esta lista; no depende del modelo elegido.

## Si un panel no probado no funciona

1. Confirma con `preview --demo` que el render se ve bien (ese paso no
   toca hardware).
2. Revisa `journalctl -u iauso.service -n 30` — un `TimeoutError`
   de BUSY suele ser alimentacion insuficiente o el HAT mal encajado.
3. Compara el driver vendorizado (`vendor/waveshare_epd/`) contra la
   version actual en el
   [repositorio oficial](https://github.com/waveshareteam/e-Paper/tree/master/RaspberryPi_JetsonNano/python/lib/waveshare_epd)
   por si Waveshare publico una correccion despues del commit citado en
   FUENTES.md.
4. Abri un issue con el modelo exacto de tu panel y la salida de
   `doctor`/`journalctl`; los drivers "b" (negro + un color) comparten la
   misma logica de separacion de capas en `iauso/display.py`, asi
   que un problema ahi probablemente afecta a los tres por igual.

## Agregar un panel que no esta en la lista

1. Confirma el nombre exacto del archivo en el
   [repositorio oficial de Waveshare](https://github.com/waveshareteam/e-Paper/tree/master/RaspberryPi_JetsonNano/python/lib/waveshare_epd)
   y copialo (sin modificar) a `vendor/waveshare_epd/`.
2. Agrega una entrada en `iauso/panels.py` con su modulo, su
   tamano en orientacion paisaje (`EPD_HEIGHT x EPD_WIDTH` si el panel es
   nativamente vertical, o `EPD_WIDTH x EPD_HEIGHT` si ya es horizontal) y
   `"colors"`: `"mono"` si solo pinta negro/blanco, `"duo"` si tiene un
   segundo color de tinta y su `display()` recibe dos buffers
   (`display(imagen_negra, imagen_color)`).
3. Genera una vista previa (`preview --demo`) para revisar el layout antes
   de probar en hardware real.
