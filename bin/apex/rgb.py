"""RGB backends (OpenRGB SDK, direct HID) and color helpers for Apex keyboards."""

from __future__ import annotations

import colorsys
import math
import os
import socket
import struct
import tomllib

from .config import THEME_COLORS
from .layout import ALPHA, FNROW, HIGHLIGHT, LEDS, MODS, PUNCT, XY, MAX_X, MAX_Y

MAGIC = b"ORGB"
HEADER = struct.Struct("ccccIII")
CMD_COUNT = 0
CMD_DATA = 1
CMD_VERSION = 40
CMD_NAME = 50
CMD_UPDATEZONE = 1051


def parse_hex(value, fallback=(0, 0, 0)):
    if not value:
        return fallback
    text = str(value).strip().lstrip("#")
    if len(text) != 6:
        return fallback
    try:
        return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError:
        return fallback


def scale_color(color, brightness):
    factor = max(0, min(100, brightness)) / 100.0
    return tuple(int(c * factor) for c in color)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def load_palette(path=THEME_COLORS):
    palette = {}
    try:
        with open(path, "rb") as fh:
            palette = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        palette = {}

    def get(name, fallback):
        value = palette.get(name)
        if isinstance(value, str):
            return parse_hex(value, parse_hex(fallback))
        return parse_hex(fallback)

    # Every hex colour the theme defines (magenta, blue, yellow, ...) by name,
    # so settings can refer to them; the curated keys below take precedence.
    named = {k: parse_hex(v) for k, v in palette.items()
             if isinstance(v, str) and len(v.strip().lstrip("#")) == 6}
    return {
        **named,
        "accent": get("accent", "#89b4fa"),
        "foreground": get("foreground", "#cdd6f4"),
        "muted": get("muted", "#45475a"),
        "selection": get("selection", "#353543"),
        "background": get("background", "#1e1e2e"),
        "highlight": get("orange", get("red", "#f38ba8")),
        "cyan": get("cyan", "#94e2d5"),
        "green": get("green", "#a6e3a1"),
        "magenta": get("magenta", "#cba6f7"),
        "theme": os.path.basename(os.path.dirname(path)) or "current",
    }


def resolve_color(value, palette, fallback):
    """A "#RRGGBB" hex, or the name of a theme colour such as "accent" or "green"."""
    text = str(value or "").strip()
    if text.startswith("#"):
        return parse_hex(text, fallback)
    color = palette.get(text)
    return color if isinstance(color, tuple) else fallback


# Named multi-color profiles for the `gradient` mode. Each list is sampled
# cyclically across the keyboard width and drifts slowly over time.
PROFILES = {
    "sunset": ("#f97316", "#ec4899", "#8b5cf6"),
    "ocean": ("#0ea5e9", "#06b6d4", "#14b8a6"),
    "fire": ("#facc15", "#f97316", "#dc2626"),
    "matrix": ("#166534", "#22c55e", "#86efac"),
    "cyberpunk": ("#22d3ee", "#e879f9", "#a21caf"),
    "aurora": ("#34d399", "#22d3ee", "#818cf8"),
    "candy": ("#f472b6", "#c084fc", "#60a5fa"),
    "ice": ("#e0f2fe", "#7dd3fc", "#38bdf8"),
    "vaporwave": ("#ff71ce", "#01cdfe", "#05ffa1"),
    "gold": ("#fef08a", "#f59e0b", "#78350f"),
}


def profile_colors(name):
    """Hex list for a profile name; falls back to sunset."""
    for hexes in PROFILES.get(name, PROFILES["sunset"]):
        yield parse_hex(hexes)


def sample_gradient(colors, p):
    """Sample a cyclic multi-stop gradient at position p in [0, 1)."""
    n = len(colors)
    p = p % 1.0
    f = p * n
    i = int(f)
    j = (i + 1) % n
    return mix(colors[i], colors[j], f - i)


def theme_color_for(key, palette):
    if key in MODS or key in FNROW:
        return palette["accent"]
    if key in HIGHLIGHT:
        return palette["highlight"]
    if key in ALPHA or key in PUNCT:
        return palette["muted"]
    return palette["selection"]


# Red-leaning orange: on Apex LEDs this reads closest to Claude's orange
# (picked side by side against #FF5A00, #FF7800 and #D97757).
CLAUDE_ALERT = (255, 60, 0)
CLAUDE_ALERT_HZ = 1.25


def apply_claude_alert(colors, waiting, t, color=CLAUDE_ALERT):
    """Flash Escape while a Claude Code session needs you; other keys untouched."""
    if not waiting or "Escape" not in LEDS:
        return colors
    out = list(colors)
    on = (t * CLAUDE_ALERT_HZ) % 1.0 < 0.55
    out[LEDS.index("Escape")] = color if on else scale_color(color, 12)
    return out


# Theme colour names (or "#RRGGBB") per workspace state. Every key stays lit at
# the same brightness; only the hue changes. Orange/yellow are avoided because
# Escape, beside the 1 key, flashes orange for Claude.
WORKSPACE_COLORS = {"active": "accent", "visible": "magenta", "occupied": "green", "empty": "foreground"}


def apply_workspace_keys(colors, ws_levels, palette, brightness=100, scheme=None):
    """Turn the number row into a workspace strip; other keys untouched.

    ws_levels maps workspace id (1-10) to "active" | "visible" | "occupied";
    any other workspace uses the "empty" colour.
    """
    from .workspaces import KEY_FOR
    scheme = {**WORKSPACE_COLORS, **(scheme or {})}
    fallback = palette.get("foreground", (200, 200, 200))
    hues = {state: resolve_color(value, palette, fallback) for state, value in scheme.items()}
    index = {name: i for i, name in enumerate(LEDS)}
    out = list(colors)
    for wid, key in KEY_FOR.items():
        if key in index:
            out[index[key]] = scale_color(hues[ws_levels.get(wid, "empty")], brightness)
    return out


def apply_key_overrides(colors, overrides):
    if not overrides:
        return colors
    index = {name: i for i, name in enumerate(LEDS)}
    out = list(colors)
    for name, value in overrides.items():
        if name in index:
            out[index[name]] = parse_hex(value, out[index[name]])
    return out


class OpenRGB:
    def __init__(self, host="127.0.0.1", port=6742, name="apexctl"):
        self.s = socket.create_connection((host, port), timeout=3)
        self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.ver = 0
        try:
            self.s.settimeout(1)
            self._send(0, CMD_VERSION, struct.pack("I", 4))
            _dev, _cmd, vdata = self._recv()
            if vdata:
                self.ver = min(struct.unpack("I", vdata)[0], 4)
        except OSError:
            self.ver = 0
        self.s.settimeout(2)
        payload = name.encode("utf-8") + b"\0"
        self._send(0, CMD_NAME, payload)
        self.device = self._find_device()

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass

    def _send(self, dev, cmd, data=b""):
        self.s.sendall(MAGIC + struct.pack("III", dev, cmd, len(data)) + data)

    def _recv(self):
        hdr = b""
        while len(hdr) < 16:
            chunk = self.s.recv(16 - len(hdr))
            if not chunk:
                raise ConnectionError("OpenRGB connection closed")
            hdr += chunk
        parts = list(HEADER.unpack(hdr))
        dev, cmd, size = parts[4:7]
        data = b""
        while len(data) < size:
            chunk = self.s.recv(size - len(data))
            if not chunk:
                break
            data += chunk
        return dev, cmd, data

    def drain(self):
        self.s.setblocking(False)
        try:
            while True:
                if not self.s.recv(4096):
                    break
        except (BlockingIOError, OSError):
            pass
        finally:
            self.s.setblocking(True)
            self.s.settimeout(2)

    def dev_count(self):
        self._send(0, CMD_COUNT)
        _dev, _cmd, data = self._recv()
        return struct.unpack("I", data)[0]

    def dev_name(self, idx):
        self._send(idx, CMD_DATA)
        _dev, _cmd, data = self._recv()
        off = 8  # data_size + type
        n = struct.unpack_from("<H", data, off)[0]
        off += 2
        return data[off:off + n].decode("utf-8", "replace").rstrip("\x00")

    def _find_device(self):
        count = self.dev_count()
        for i in range(count):
            try:
                name = self.dev_name(i)
            except Exception:
                name = ""
            if "steelseries" in name.lower() or "apex" in name.lower():
                return i, name
        if count:
            return 0, self.dev_name(0)
        raise RuntimeError("No OpenRGB devices found")

    def set_colors(self, colors, zone=0):
        idx = self.device[0]
        num = len(colors)
        payload = struct.pack("I", 0) + struct.pack("I", zone) + struct.pack("H", num)
        payload += b"".join(struct.pack("BBBx", *c) for c in colors)
        data_size = len(payload)
        payload = struct.pack("I", data_size) + payload[4:]
        self._send(idx, CMD_UPDATEZONE, payload)
        self.drain()


def connect():
    """RGB backend for the connected keyboard: direct HID on Gen 3, else OpenRGB."""
    from . import devices
    if devices.current().rgb == "hid":
        from .hidrgb import HidRGB
        return HidRGB()
    return OpenRGB()


def effect_colors(mode, t, palette, solid, brightness, reactive_keys=None, profile=None):
    """Return per-LED RGB tuples for the given effect at time t (seconds)."""
    solid_c = parse_hex(solid, palette["accent"])
    reactive_keys = reactive_keys or {}
    profile_c = list(profile_colors(profile)) if profile else list(profile_colors("sunset"))
    colors = []
    for name in LEDS:
        x, y = XY[name]
        if mode == "off":
            color = (0, 0, 0)
        elif mode == "solid":
            color = solid_c
        elif mode == "gradient":
            p = x / max(MAX_X, 1) - t * 0.06 - y / max(MAX_Y, 1) * 0.15
            color = sample_gradient(profile_c, p)
        elif mode == "theme":
            color = theme_color_for(name, palette)
        elif mode == "wave":
            hue = (x / max(MAX_X, 1) - t * 0.25) % 1.0
            color = hsv(hue, 0.85, 1.0)
        elif mode == "rainbow":
            hue = (x / max(MAX_X, 1) * 0.7 + y / max(MAX_Y, 1) * 0.3 + t * 0.08) % 1.0
            color = hsv(hue, 0.9, 1.0)
        elif mode == "breathe":
            base = theme_color_for(name, palette) if solid_c == palette["accent"] else solid_c
            pulse = (1 + math.sin(t * 2.2)) * 0.5
            color = mix(palette["background"], base, 0.25 + 0.75 * pulse)
        elif mode == "reactive":
            color = mix(palette["background"], palette["muted"], 0.35)
        else:
            color = theme_color_for(name, palette)

        if name in reactive_keys:
            age = reactive_keys[name]
            color = mix(palette["accent"], color, min(1.0, age / 0.35))
        colors.append(scale_color(color, brightness))
    return colors
