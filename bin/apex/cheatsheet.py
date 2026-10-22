"""Keybinding cheat sheet: light the keys bound under one modifier set.

Bindings come from `omarchy menu keybindings --print`, which already
resolves Hyprland `code:` binds (shown without a key by `hyprctl binds` on
Lua configs). Each line looks like `SUPER SHIFT + W  → Close window`.
While open, every bound key lights in its category colour, unbound keys go
dark, the held modifiers glow white, the wheel steps through the bindings
(the selected key pulses and the OLED names it) and a wheel click moves to
the next modifier set. It closes by itself after a quiet spell.
"""

from __future__ import annotations

import math
import re
import subprocess
import time

from .layout import LEDS, XY

IDLE_CLOSE = 30.0
LIST_COMMAND = ["omarchy", "menu", "keybindings", "--print"]

MODIFIER_LED = {"SUPER": "Left Windows", "SHIFT": "Left Shift", "CTRL": "Left Control", "ALT": "Left Alt"}
MOD_ORDER = ("SUPER", "SHIFT", "CTRL", "ALT")

# Key names as Omarchy prints them -> layout.LEDS names. Mouse and XF86 media
# keys have no LED and are left out.
KEY_TO_LED = {
    "RETURN": "Enter", "ENTER": "Enter", "SPACE": "Space", "ESCAPE": "Escape",
    "TAB": "Tab", "BACKSPACE": "Backspace", "MINUS": "-", "EQUAL": "=",
    "BRACKETLEFT": "[", "BRACKETRIGHT": "]", "BACKSLASH": r"\ (ANSI)",
    "SEMICOLON": ";", "APOSTROPHE": "'", "GRAVE": "`", "COMMA": ",",
    "PERIOD": ".", "SLASH": "/", "CAPS_LOCK": "Caps Lock",
    "LEFT": "Left Arrow", "RIGHT": "Right Arrow", "UP": "Up Arrow", "DOWN": "Down Arrow",
    "HOME": "Home", "END": "End", "INSERT": "Insert", "DELETE": "Delete",
    "PRIOR": "Page Up", "PAGE_UP": "Page Up", "NEXT": "Page Down", "PAGE_DOWN": "Page Down",
    "PRINT": "Print Screen", "SCROLL_LOCK": "Scroll Lock", "PAUSE": "Pause/Break",
}
KEY_TO_LED.update({c: c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"})
KEY_TO_LED.update({f"F{i}": f"F{i}" for i in range(1, 13)})

# Saturated colours: theme pastels wash out on the LEDs.
CATEGORY_COLORS = {
    "workspace": (0, 255, 64),    # green
    "window": (255, 200, 0),      # yellow
    "system": (255, 0, 200),      # magenta
    "apps": (0, 200, 255),        # cyan
}
MODIFIER_COLOR = (255, 255, 255)
CATEGORY_RULES = (
    ("workspace", re.compile(r"workspace", re.I)),
    ("window", re.compile(r"window|focus|group|float|full ?(screen|width)|split|resize|expand|shrink|"
                          r"pin|pseudo|transparen|layout|scratchpad|swap", re.I)),
    ("system", re.compile(r"menu|lock|screenshot|screenrecord|record|picker|clipboard|emoji|volume|"
                          r"brightness|mute|notification|monitor|scaling|night|idle|theme|power|"
                          r"system|keybind|copy|paste|cut|password|calculator|toggle", re.I)),
)


def category(description):
    for name, rule in CATEGORY_RULES:
        if rule.search(description):
            return name
    return "apps"


def parse(text, absent=()):
    """Lines of `MODS + KEY → description` -> list of (mods tuple, led name, description).

    Bindings on keys in `absent` (ones this keyboard physically lacks) are dropped.
    """
    out = []
    for line in text.splitlines():
        if "→" not in line:
            continue
        combo, desc = (part.strip() for part in line.split("→", 1))
        if " + " in combo:
            mods_text, key = combo.rsplit(" + ", 1)
            mods = tuple(m for m in MOD_ORDER if m in mods_text.upper().split())
        else:
            mods, key = (), combo
        led = KEY_TO_LED.get(key.strip().upper())
        if led and led in LEDS and led not in absent:
            out.append((mods, led, desc))
    return out


def group_label(mods):
    return " + ".join(m.title() for m in mods) or "No modifier"


def groups(bindings):
    """Modifier sets in browsing order: Super first, then by number of bindings."""
    by_mods = {}
    for mods, led, desc in bindings:
        by_mods.setdefault(mods, []).append((led, desc))
    order = sorted(by_mods, key=lambda m: (m != ("SUPER",), "SUPER" not in m, -len(by_mods[m]), m))
    # Within a set, browse in physical keyboard order: row by row, left to right.
    def position(entry):
        x, y = XY[entry[0]]
        return (y, x)
    return [(mods, sorted(by_mods[mods], key=position)) for mods in order]


def load(command=LIST_COMMAND, absent=None):
    if absent is None:
        from . import devices
        absent = devices.current().absent
    try:
        text = subprocess.run(command, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return groups(parse(text, absent))


class CheatSheet:
    def __init__(self, loader=load):
        self.loader = loader
        self.active = False
        self.sets = []
        self.set_index = 0
        self.cursor = None
        self.last_activity = 0.0

    def open(self):
        self.sets = self.loader()
        self.active = bool(self.sets)
        self.set_index = 0
        self.cursor = None
        self.touch()
        return self.active

    def close(self):
        self.active = False
        self.cursor = None

    def toggle(self):
        return self.close() if self.active else self.open()

    def touch(self):
        self.last_activity = time.monotonic()

    def expired(self, now=None):
        return self.active and (now or time.monotonic()) - self.last_activity > IDLE_CLOSE

    def current(self):
        return self.sets[self.set_index] if self.active else ((), [])

    def next_set(self, delta=1):
        if self.sets:
            self.set_index = (self.set_index + delta) % len(self.sets)
            self.cursor = None
        self.touch()

    def step(self, delta):
        _mods, entries = self.current()
        if entries:
            start = -1 if self.cursor is None and delta > 0 else (0 if self.cursor is None else self.cursor)
            self.cursor = (start + delta) % len(entries)
        self.touch()

    def selected(self):
        _mods, entries = self.current()
        if self.cursor is None or not entries:
            return None
        return entries[self.cursor]

    def colors(self, t, brightness=100):
        """Full LED list: bound keys by category, held modifiers white, the rest dark."""
        mods, entries = self.current()
        scale = brightness / 100.0
        out = [(0, 0, 0)] * len(LEDS)
        index = {name: i for i, name in enumerate(LEDS)}
        for led, desc in entries:
            out[index[led]] = tuple(int(c * scale) for c in CATEGORY_COLORS[category(desc)])
        for mod in mods:
            led = MODIFIER_LED[mod]
            if led in index:
                out[index[led]] = tuple(int(c * scale) for c in MODIFIER_COLOR)
        picked = self.selected()
        if picked:
            pulse = 0.55 + 0.45 * math.sin(t * 2 * math.pi * 2.0)  # 2 Hz breathing on the selection
            out[index[picked[0]]] = tuple(int(255 * pulse) for _ in range(3))
        return out

    def oled_state(self):
        mods, entries = self.current()
        picked = self.selected()
        return {
            "label": group_label(mods),
            "position": f"{self.set_index + 1}/{len(self.sets)}",
            "count": len(entries),
            "key": picked[0] if picked else "",
            "description": picked[1] if picked else "",
        }
