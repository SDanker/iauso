"""Send the rendered image to the configured Waveshare panel.

The official drivers live in vendor/waveshare_epd (see docs/SOURCES.md for
the exact commit). Mono panels use a single buffer; "duo" panels (black +
one ink color) use two, one per layer - see panels.py.
"""

import hashlib
import importlib
import logging
import sys
import time
from pathlib import Path

from PIL import Image

from .panels import panel_info
from .storage import write_json

LOG = logging.getLogger(__name__)
BLACK = (0, 0, 0)


def _split_layers(image, accent):
    """Split a black/white/accent image into two 1-bit layers (black and accent)."""
    pixels = list(image.convert("RGB").getdata())
    black_layer = Image.new("L", image.size, 255)
    accent_layer = Image.new("L", image.size, 255)
    black_layer.putdata([0 if p == BLACK else 255 for p in pixels])
    accent_layer.putdata([0 if p == accent else 255 for p in pixels])
    return black_layer, accent_layer


def send_to_panel(image, timeout, panel_id="2.15g"):
    info = panel_info(panel_id)
    # A single child process per refresh releases every GPIO on exit.
    vendor = Path(__file__).resolve().parent.parent / "vendor"
    sys.path.insert(0, str(vendor))
    module = importlib.import_module("waveshare_epd." + info["module"])

    class TimedEPD(module.EPD):
        def ReadBusy(self):
            start = time.monotonic()
            module.epdconfig.delay_ms(100)
            # Same criterion as the official driver (the GPIO abstraction may
            # invert the physical level; do not change it based on the comment).
            while module.epdconfig.digital_read(self.busy_pin) == 0:
                if time.monotonic() - start >= timeout:
                    raise TimeoutError("BUSY never released the panel; check model, HAT and power")
                module.epdconfig.delay_ms(5)

    epd = TimedEPD()
    expected = info["size"]
    try:
        native = {(epd.width, epd.height), (epd.height, epd.width)}
        if expected not in native or image.size != expected:
            raise ValueError("Driver or image does not match panel " + panel_id)
        if epd.init() != 0:
            raise RuntimeError("Could not initialize SPI")
        if info["colors"] == "duo":
            from .render import ACCENTS
            black_layer, accent_layer = _split_layers(image, ACCENTS["duo"])
            epd.display(epd.getbuffer(black_layer), epd.getbuffer(accent_layer))
        else:
            # getbuffer rotates to the native orientation and packs the pixels.
            epd.display(epd.getbuffer(image))
        epd.sleep()
    finally:
        module.epdconfig.module_exit(cleanup=True)


def display_image(image, config, state, state_path, now, sender=None):
    digest = hashlib.sha256(image.tobytes()).hexdigest()
    state_dir = Path(config["state_dir"])
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    preview = state_dir / "preview.png"
    image.save(preview)
    if config["display"] == "png":
        return "png"
    last = state.get("last_display_attempt", 0)
    elapsed = now - last
    if last and (elapsed < config["min_refresh_seconds"]):
        LOG.info("Panel resting; minimum interval not met or clock adjusted")
        return "deferred"
    if digest == state.get("display_digest") and now - state.get("last_display_success", 0) < 86400:
        return "unchanged"
    # Persist BEFORE touching the panel: a failure or restart must not cause a
    # refresh loop. The digest is only confirmed once the driver finishes well.
    state["last_display_attempt"] = now
    write_json(state_path, state)
    if sender is not None:
        sender(image, config["busy_timeout_seconds"], config["panel"])
    else:
        import subprocess
        try:
            subprocess.run(
                [sys.executable, "-m", "iauso", "panel-worker", str(preview),
                 str(config["busy_timeout_seconds"]), config["panel"]],
                check=True, timeout=config["busy_timeout_seconds"] + 40,
                cwd=Path(__file__).resolve().parent.parent,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("The driver timed out; check HAT and power before retrying") from None
    state["display_digest"] = digest
    state["last_display_success"] = now
    write_json(state_path, state)
    return "displayed"
