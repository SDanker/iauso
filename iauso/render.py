"""Render the quota snapshot for any supported Waveshare panel.

The original design targeted 296x160 (the 2.15G panel, 4 colors). For every
other panel each coordinate is scaled proportionally to its real size, so a
panel with a different resolution keeps the same composition without needing
its own layout. At 1:1 scale (panel "2.15g") the result is identical to the
original. The other panels are not validated on physical hardware; use
"display": "png" to review the layout before installing the HAT (see
docs/PANELS.md).
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from .i18n import strings
from .panels import panel_info

BLACK, WHITE, YELLOW, RED = (0, 0, 0), (255, 255, 255), (255, 255, 0), (255, 0, 0)
BASE_SIZE = (296, 160)
# mono: no color of its own (black/white only). duo: a single ink color
# besides black (red or yellow depending on the physical panel). quad: the
# 2.15G, the only one with black/white/yellow/red in the same buffer.
ACCENTS = {"mono": None, "duo": RED, "quad": {"warn": YELLOW, "crit": RED}}
PALETTE = {BLACK, WHITE, YELLOW, RED}  # Colores exactos que puede pintar el panel 2.15G.


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    candidates = [Path("/usr/share/fonts/truetype/dejavu") / name, Path(name)]
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size)
        except OSError:
            pass
    return ImageFont.load_default()


def text(draw, xy, value, size=10, color=BLACK, bold=False, width=None):
    value = str(value).replace("\n", " ").replace("\r", " ")
    face = font(size, bold)
    if width is not None:
        while len(value) > 1 and draw.textbbox((0, 0), value, font=face)[2] > width:
            value = value[:-2] + "~"
    draw.text(xy, value, fill=color, font=face, anchor="lt")


def reset_label(reset, now, zone, words=None):
    words = words or strings()
    if reset is None:
        return words["reset_unknown"]
    if reset <= now:
        # Do not invent a reset to 0% until the server confirms it.
        return words["reset_pending"]
    current, target = datetime.fromtimestamp(now, zone), datetime.fromtimestamp(reset, zone)
    if target.date() == current.date():
        return words["reset"] + target.strftime("%H:%M")
    return words["reset"] + target.strftime("%d/%m %H:%M")


def status_label(item, zone, words=None):
    words = words or strings()
    status = item["status"]
    updated = item.get("updated_at")
    hhmm = datetime.fromtimestamp(updated, zone).strftime("%d/%m %H:%M") if updated is not None else ""
    labels = words["status"]
    if status in ("ok", "stale"):
        return labels[status] + hhmm
    return labels.get(status, labels["unknown"])


def _usage_color(usage, accent, warn=70, crit=90):
    """Bar color for a given percentage used.

    CUSTOMIZE: the thresholds come from "warn_percent"/"crit_percent" in
    config.json (70 and 90 by default) - there is no need to touch this file
    to move them. To change the colors themselves, edit ACCENTS above: a
    "mono" panel has no color of its own, a "duo" panel has exactly one, and
    the 2.15G is the only one that tells warning and critical apart.
    """
    if accent is None:
        return BLACK  # Panel without color: the bar is always black.
    if isinstance(accent, dict):
        return accent["crit"] if usage >= crit else accent["warn"] if usage >= warn else BLACK
    return accent if usage >= warn else BLACK


def _accent_fill(accent):
    if accent is None:
        return BLACK
    return accent["warn"] if isinstance(accent, dict) else accent


def _highlight(draw, box, accent):
    """Highlight a warning strip; returns the text color to use on top of it."""
    draw.rectangle(box, fill=_accent_fill(accent))
    return WHITE if accent is None else BLACK


def _window(draw, x, y, window, now, zone, old, accent, X, Y, F, warn=70, crit=90, words=None):
    words = words or strings()
    if window is None:
        text(draw, (x, y + Y(3)), words["window_missing"], size=F(11))
        draw.rectangle((x, y + Y(19), x + X(122), y + Y(25)), outline=BLACK)
        text(draw, (x, y + Y(29)), words["reset_unknown"], size=F(9))
        return
    usage = window["used_percent"]
    color = _usage_color(usage, accent, warn, crit)
    label = window["label"] + (" *" if old else "")
    text(draw, (x, y + Y(3)), label, size=F(10), width=X(68))
    value = f"{usage:.0f}%" if usage in (0, 100) or 1 <= usage < 99.5 else f"{usage:.1f}%"
    face = font(F(16), True)
    vw = draw.textbbox((0, 0), value, font=face)[2]
    text(draw, (x + X(123) - vw, y), value, size=F(16), bold=True)
    draw.rectangle((x, y + Y(19), x + X(122), y + Y(25)), outline=BLACK, fill=WHITE)
    fill_width = int(round(X(120) * usage / 100))
    if fill_width:
        draw.rectangle((x + 1, y + Y(20), x + fill_width, y + Y(24)), fill=color)
    text(draw, (x, y + Y(29)), reset_label(window.get("resets_at"), now, zone, words), size=F(9), width=X(124))


def render(snapshot, config, now):
    zone = ZoneInfo(config["timezone"])
    words = strings(config["language"])
    panel = panel_info(config["panel"])
    size = panel["size"]
    accent = ACCENTS[panel["colors"]]
    sx, sy = size[0] / BASE_SIZE[0], size[1] / BASE_SIZE[1]
    sf = (sx * sy) ** 0.5

    def X(v):
        return round(v * sx)

    def Y(v):
        return round(v * sy)

    def F(v):
        return max(6, round(v * sf))

    image = Image.new("RGB", size, WHITE)
    draw = ImageDraw.Draw(image)
    draw.fontmode = "1"  # No grays or dithering on small text.
    draw.rectangle((0, 0, size[0] - 1, Y(20)), fill=BLACK)
    text(draw, (X(8), Y(4)), words["title"], size=F(13), color=WHITE, bold=True)
    if snapshot.get("demo"):
        draw.rectangle((size[0] - X(51), Y(3), size[0] - X(6), Y(17)), fill=_accent_fill(accent))
        text(draw, (size[0] - X(47), Y(5)), words["demo"], size=F(10), bold=True,
             color=WHITE if accent is None else BLACK)
    else:
        text(draw, (X(197), Y(5)), words["header"], size=F(10), color=WHITE)
    old = False
    col_w = X(138)
    for provider, x, title in (("claude", X(6), "CLAUDE"), ("codex", X(6) + col_w + X(7), "CODEX")):
        item = snapshot["providers"][provider]
        stale = item["status"] != "ok"
        old |= stale and bool(item.get("windows"))
        draw.rectangle((x, Y(25), x + col_w, Y(142)), outline=BLACK)
        text(draw, (x + X(7), Y(29)), title, size=F(13), bold=True)
        text_color = BLACK
        if stale:
            text_color = _highlight(draw, (x + 1, Y(44), x + col_w - 1, Y(55)), accent)
        text(draw, (x + X(5), Y(46)), status_label(item, zone, words), size=F(9), width=col_w - X(9), color=text_color)
        windows = {w["id"]: w for w in item.get("windows", [])}
        for identifier, y in zip(config[provider + "_windows"], (Y(59), Y(101))):
            _window(draw, x + X(7), y, windows.get(identifier), now, zone, stale, accent, X, Y, F,
                    config["warn_percent"], config["crit_percent"], words)
    footer = (words["footer_demo"] if snapshot.get("demo") else
              words["footer_stale"] if old else words["footer"])
    text(draw, (X(6), size[1] - Y(12)), footer, size=F(9), width=size[0] - X(12))
    if config["rotation"] == 180:
        image = image.rotate(180)
    return image
