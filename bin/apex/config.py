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
        # Flash Escape orange while a Claude Code session needs you.
        "claude_esc": True,
        "claude_esc_color": "#FF3C00",
        # Number row 1-0 shows Hyprland workspaces 1-10 by colour: theme colour
        # names or "#RRGGBB" for active / visible / occupied / empty.
        "workspace_keys": True,
        # Keyboard lights and OLED go dark while the idle screensaver is up or
        # the lock screen has blanked the displays.
        "away_dark": True,
        # Holding Super lights the keys bound under the held modifiers (needs
        # the [apex-super] binds in bindings.lua); delay in seconds.
        "super_peek": True,
        "super_peek_delay": 0.25,
        "workspace_colors": {"active": "#FFFFFF", "visible": "#FF00C8", "occupied": "#00FF40", "empty": "#0030FF"},
        "speed": 45,
        "keys": {},
    },
    "oled": {
        "page": "clock",
        "pages": ["clock", "now-playing", "workspace", "logo"],
        "text": "",
        "image": LOGO_PATH,
        "interval_ms": 250,
        # Switch to the Claude page while a session is busy or a Claude window is focused.
        "claude_auto": True,
    },
    "wheel": {
        "mode": "volume",
        "invert": False,
    },
    # Logitech mouse lighting (HID++). "match" follows the keyboard; "solid" /
    # "breathe" use `color` (theme colour name or "#RRGGBB"); "cycle" rotates
    # hues on the mouse; "device" leaves the mouse's own lighting alone.
    # brightness None = the keyboard's brightness in match mode, else 100.
    "mouse": {
        "mode": "match",
        "color": "accent",
        "brightness": None,
        # Breathe the Claude alert colour while a session needs you.
        "claude": True,
        # Sensor DPI, re-applied when the mouse reconnects; None = leave the
        # mouse's own. Tracks changes made with the mouse's DPI buttons.
        "dpi": None,
    },
    # The panel's Favorites tab: which sections it shows, in this order, and
    # what each offers. Colours are "#RRGGBB", "theme" or "rainbow".
    "favorites": {
        "sections": ["brightness", "lighting", "dpi", "oled", "wheel"],
        "colors": ["theme", "#4A1C90", "#00806A", "#7DD3FC", "#00FF40", "#FF00C8",
                   "#FF3C00", "#FFC800", "#FFFFFF", "rainbow"],
        "dpi": [400, 800, 1600, 3200, 6400],
        "oled": ["clock", "system", "claude", "now-playing"],
        "wheel": ["volume", "app", "workspace"],
    },
}
FAVORITE_SECTIONS = ("brightness", "lighting", "dpi", "oled", "wheel")


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
    if cfg["mouse"].get("brightness") is not None:
        cfg["mouse"]["brightness"] = int(max(0, min(100, cfg["mouse"]["brightness"])))
    return cfg


def set_favorites(cfg, req):
    """Apply a favorites edit ({key: list} or {"reset": True}); raises ValueError."""
    from .layout import OLED_PAGES, WHEEL_MODES
    fav = cfg.setdefault("favorites", deepcopy(DEFAULT["favorites"]))
    if req.get("reset"):
        cfg["favorites"] = deepcopy(DEFAULT["favorites"])
        return cfg["favorites"]
    checks = {
        "sections": lambda v: v in FAVORITE_SECTIONS,
        "oled": lambda v: v in OLED_PAGES,
        "wheel": lambda v: v in WHEEL_MODES,
        "colors": lambda v: v in ("theme", "rainbow") or (
            isinstance(v, str) and len(v) == 7 and v[0] == "#"
            and all(c in "0123456789abcdefABCDEF" for c in v[1:])),
        "dpi": lambda v: isinstance(v, int) and 50 <= v <= 64000,
    }
    updates = {}
    for key, ok in checks.items():
        if key not in req:
            continue
        values = req[key]
        if key == "dpi":
            values = sorted({int(v) for v in values})
        elif key == "colors":
            values = [v.upper() if v.startswith("#") else v for v in values]
        bad = [v for v in values if not ok(v)]
        if bad:
            raise ValueError(f"invalid favorites {key}: {', '.join(map(str, bad))}")
        if key == "sections":
            values = [s for s in FAVORITE_SECTIONS if s in values]  # canonical order
        updates[key] = list(dict.fromkeys(values))
    fav.update(updates)  # all or nothing
    return fav


def save(cfg, path=CONFIG_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
