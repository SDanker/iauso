# Supported Waveshare panels

The project was born for the **Waveshare 2.15inch e-Paper HAT+ (G)** (296 × 160,
black/white/yellow/red) and that is the only panel **tested on physical
hardware**. Since version 1.2 it also supports other common Waveshare panels by
reusing their official drivers — the same commit documented in
[SOURCES.md](SOURCES.md) — but **without having tested them on a real panel**.

## Available panels

| `"panel"` in config.json | Size | Colors | Tested on hardware |
|---|---|---|---|
| `2.15g` (default) | 296x160 | black/white/yellow/red | Yes |
| `2.13` | 250x122 | black/white | No |
| `2.13b` | 250x122 | black/white + red | No |
| `2.9` | 296x128 | black/white | No |
| `2.9b` | 296x128 | black/white + red or yellow | No |
| `4.2` | 400x300 | black/white | No |
| `7.5` | 800x480 | black/white | No |
| `7.5b` | 800x480 | black/white + red | No |

The "mono" panels (no suffix) can only paint black and white: the usage
percentages are still shown, but the bar never changes color with the usage
level. The "b" panels have a second ink color (red, or yellow on some physical
variants of the 2.9"); the bar uses that color from `warn_percent` on. Only the
2.15G additionally distinguishes a critical threshold, `crit_percent`, with a
second color. Both thresholds are configurable — see
[CONFIGURATION.md](CONFIGURATION.md#display).

## Choosing a panel

In your `config.json`:

```json
{
  "panel": "7.5"
}
```

Nothing else changes. `python3 -m iauso doctor --config config.json` validates
that the name is one of the supported ones and prints the chosen resolution.

## Reviewing the layout before installing the HAT

You do not need the physical panel to see how it will look: any computer with
Python and Pillow (`pip install -r requirements-preview.txt`) can generate a
preview:

```bash
python3 -m iauso preview --config config.json --demo --output preview.png
```

Open `preview.png` and confirm the text is readable and nothing is cut off
before installing the HAT and running `refresh` against real hardware.

## Wiring

Every panel in this list uses the same standard Waveshare pinout (the same
40-pin HAT as the 2.15G): `RST=GPIO17, DC=GPIO25, CS=GPIO8 (SPI0 CE0),
BUSY=GPIO24, PWR=GPIO18, MOSI=GPIO10, SCLK=GPIO11`. If your panel comes as a
HAT (plugs straight into the 40-pin header) there is nothing to wire. If it
comes as a separate driver board with a ribbon cable, follow that pin layout.

`scripts/install_pi.sh` enables SPI and the GPIO permissions the same way for
every panel in this list; it does not depend on the chosen model.

## If an untested panel does not work

1. Confirm with `preview --demo` that the render looks right (that step does not
   touch hardware).
2. Check `journalctl -u iauso.service -n 30` — a BUSY `TimeoutError` is usually
   insufficient power or a badly seated HAT.
3. Compare the vendored driver (`vendor/waveshare_epd/`) against the current
   version in the
   [official repository](https://github.com/waveshareteam/e-Paper/tree/master/RaspberryPi_JetsonNano/python/lib/waveshare_epd)
   in case Waveshare published a fix after the commit cited in SOURCES.md.
4. Open an issue with the exact panel model and the output of
   `doctor`/`journalctl`; the "b" drivers (black + one color) share the same
   layer-splitting logic in `iauso/display.py`, so a problem there probably
   affects all three equally.

## Adding a panel that is not in the list

1. Confirm the exact file name in the
   [official Waveshare repository](https://github.com/waveshareteam/e-Paper/tree/master/RaspberryPi_JetsonNano/python/lib/waveshare_epd)
   and copy it, unmodified, into `vendor/waveshare_epd/`.
2. Add an entry in `iauso/panels.py` with its module, its landscape size
   (`EPD_HEIGHT x EPD_WIDTH` if the panel is natively portrait, or
   `EPD_WIDTH x EPD_HEIGHT` if it is already landscape) and its `"colors"`:
   `"mono"` if it only paints black/white, `"duo"` if it has a second ink color
   and its `display()` takes two buffers (`display(black_image, color_image)`).
3. Generate a preview (`preview --demo`) to review the layout before testing on
   real hardware.
