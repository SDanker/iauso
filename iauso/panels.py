"""Registry of supported Waveshare panels.

Each entry describes the vendored driver module, the image size render()
produces (always landscape) and its color mode. The official driver rotates
the image internally when needed: it accepts both (width, height) and
(height, width) of the native EPD.

Only "2.15g" was tested on physical hardware. The rest use the same official
Waveshare patterns (same commit, see docs/SOURCES.md) but could not be
verified on a real panel; use "display": "png" to review the layout before
installing the HAT.
"""

PANELS = {
    "2.15g": {"module": "epd2in15g", "size": (296, 160), "colors": "quad"},
    "2.13": {"module": "epd2in13_V4", "size": (250, 122), "colors": "mono"},
    "2.13b": {"module": "epd2in13b_V4", "size": (250, 122), "colors": "duo"},
    "2.9": {"module": "epd2in9_V2", "size": (296, 128), "colors": "mono"},
    "2.9b": {"module": "epd2in9b_V4", "size": (296, 128), "colors": "duo"},
    "4.2": {"module": "epd4in2_V2", "size": (400, 300), "colors": "mono"},
    "7.5": {"module": "epd7in5_V2", "size": (800, 480), "colors": "mono"},
    "7.5b": {"module": "epd7in5b_V2", "size": (800, 480), "colors": "duo"},
}


def panel_info(panel_id):
    try:
        return PANELS[panel_id]
    except KeyError:
        raise ValueError("panel must be one of: " + ", ".join(sorted(PANELS))) from None
