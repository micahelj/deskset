"""Direct per-key RGB over HID for keyboards without OpenRGB support (Gen 3).

Feature report (643 B): 00 40 <count> then <usage> <r> <g> <b> per key.
Keys left out keep their current lighting; 00 41 (output, 65 B) drops the
temporary colors and returns the keyboard to its own lighting.
"""

from __future__ import annotations

import fcntl
import os

from . import devices
from .layout import LEDS
from .oled import hidios_feature

FEATURE_LENGTH = 643
OUTPUT_LENGTH = 65
CMD_INIT = 0x4B
CMD_DIRECT = 0x40
CMD_CLEAR = 0x41
MAX_KEYS = (FEATURE_LENGTH - 3) // 4

# OpenRGB LED name (layout.LEDS) -> USB HID keyboard usage.
_NAMED = {
    "Enter": 0x28, "Escape": 0x29, "Backspace": 0x2A, "Tab": 0x2B, "Space": 0x2C,
    "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30, r"\ (ANSI)": 0x31, "#": 0x32,
    ";": 0x33, "'": 0x34, "`": 0x35, ",": 0x36, ".": 0x37, "/": 0x38,
    "Caps Lock": 0x39,
    "Print Screen": 0x46, "Scroll Lock": 0x47, "Pause/Break": 0x48,
    "Insert": 0x49, "Home": 0x4A, "Page Up": 0x4B, "Delete": 0x4C, "End": 0x4D,
    "Page Down": 0x4E, "Right Arrow": 0x4F, "Left Arrow": 0x50,
    "Down Arrow": 0x51, "Up Arrow": 0x52,
    "Num Lock": 0x53, "Number Pad /": 0x54, "Number Pad *": 0x55,
    "Number Pad -": 0x56, "Number Pad +": 0x57, "Number Pad Enter": 0x58,
    "Number Pad 0": 0x62, "Number Pad .": 0x63,
    r"\ (ISO)": 0x64,
    "_": 0x87, "かな": 0x88, "¥": 0x89, "変換": 0x8A, "無変換": 0x8B,
    "Left Control": 0xE0, "Left Shift": 0xE1, "Left Alt": 0xE2, "Left Windows": 0xE3,
    "Right Control": 0xE4, "Right Shift": 0xE5, "Right Alt": 0xE6, "Right Windows": 0xE7,
    "Right Fn": 0xF0, "Media Play/Pause": 0xFB,
}
_NAMED.update({chr(ord("A") + i): 0x04 + i for i in range(26)})
_NAMED.update({str(n): 0x1E + (n - 1) for n in range(1, 10)})
_NAMED["0"] = 0x27
_NAMED.update({f"F{n}": 0x3A + n - 1 for n in range(1, 13)})
_NAMED.update({f"Number Pad {n}": 0x59 + n - 1 for n in range(1, 10)})

USAGES = [_NAMED.get(name) for name in LEDS]


def build_report(colors):
    """Pack LEDS-ordered (r, g, b) tuples into one direct-write feature report."""
    entries = [(u, c) for u, c in zip(USAGES, colors) if u is not None][:MAX_KEYS]
    buf = bytearray(FEATURE_LENGTH)
    buf[1] = CMD_DIRECT
    buf[2] = len(entries)
    for i, (usage, (r, g, b)) in enumerate(entries):
        off = 3 + i * 4
        buf[off:off + 4] = bytes([usage, r & 0xFF, g & 0xFF, b & 0xFF])
    return bytes(buf)


class HidRGB:
    def __init__(self):
        profile, path = devices.detect()
        if not profile or profile.rgb != "hid" or not path:
            raise RuntimeError("no direct-HID Apex keyboard connected")
        self.path = path
        self.device = (0, profile.name)
        self.fd = os.open(path, os.O_RDWR)
        self.last = None
        self._feature(bytes([0x00, CMD_INIT]))

    def _feature(self, data):
        buf = bytearray(FEATURE_LENGTH)
        buf[:len(data)] = data
        fcntl.ioctl(self.fd, hidios_feature(FEATURE_LENGTH), buf, True)

    def set_colors(self, colors, zone=0):
        report = build_report(colors)
        if report == self.last:
            return
        self._feature(report)
        self.last = report

    def restore(self):
        """Hand lighting back to the keyboard's own profile."""
        if self.fd is None:
            return
        buf = bytearray(OUTPUT_LENGTH)
        buf[1] = CMD_CLEAR
        try:
            os.write(self.fd, buf)
        except OSError:
            pass
        self.last = None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
