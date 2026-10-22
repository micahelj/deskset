"""Load and save ~/.config/omarchy/apex.json."""

from __future__ import annotations

import json
import os
from copy import deepcopy

CONFIG_PATH = os.path.expanduser("~/.config/omarchy/apex.json")
PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_BUNDLED_LOGO = os.path.join(PLUGIN_ROOT, "assets", "omarchy_oled.png")
_LEGACY_LOGO = os.path.expanduser("~/.config/omarchy/scripts/omarchy_oled.png")
LOGO_PATH = _BUNDLED_LOGO if os.path.isfile(_BUNDLED_LOGO) else _LEGACY_LOGO
THEME_COLORS = os.path.expanduser("~/.local/state/omarchy/current/theme/colors.toml")
SOCKET_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "apexctl.sock")

DEFAULT = {
    "rgb": {
        "mode": "theme",
        "solid": "#89b4fa",
        "profile": "sunset",
        "brightness": 80,
        "speed": 45,
        "keys": {},
    },
    "oled": {
        "page": "clock",
        "pages": ["clock", "now-playing", "workspace", "logo"],
        "text": "",
        "image": LOGO_PATH,
        "interval_ms": 250,
    },
    "wheel": {
        "mode": "volume",
        "invert": False,
    },
}


def _merge(base, overlay):
    out = deepcopy(base)
    if not isinstance(overlay, dict):
        return out
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path=CONFIG_PATH):
    cfg = deepcopy(DEFAULT)
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = _merge(cfg, json.load(fh))
    except (OSError, json.JSONDecodeError):
        pass
    cfg["rgb"]["brightness"] = int(max(0, min(100, cfg["rgb"]["brightness"])))
    cfg["rgb"]["speed"] = int(max(1, min(100, cfg["rgb"]["speed"])))
    return cfg


def save(cfg, path=CONFIG_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
