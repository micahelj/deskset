"""Supported keyboards and how to reach their control interface.

Each profile names the OLED frame format and the RGB transport:
- "apex7": OLED report 0x61 + row-major MSB-first bitmap; RGB via OpenRGB.
- "gen3":  OLED report 00 1F 81 + column-packed LSB-first pages; RGB via
           direct HID feature reports on the same interface.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

VENDOR = 0x1038


@dataclass(frozen=True)
class Profile:
    product: int
    name: str
    short: str
    oled: str
    rgb: str
    control_interface: int = 1
    # layout.LEDS names this keyboard physically lacks.
    absent: tuple = ()


PROFILES = (
    Profile(0x1618, "SteelSeries Apex 7 TKL", "Apex 7 TKL", "apex7", "openrgb"),
    Profile(0x1612, "SteelSeries Apex 7", "Apex 7", "apex7", "openrgb"),
    # No Print Screen / Scroll Lock / Pause cluster: confirmed on hardware by
    # lighting each nav-cluster key in a distinct colour.
    Profile(0x1642, "SteelSeries Apex Pro TKL Gen 3", "Apex Pro Gen 3", "gen3", "hid",
            absent=("Print Screen", "Scroll Lock", "Pause/Break")),
)

DEFAULT = PROFILES[0]


def _hid_id(sys_path):
    try:
        with open(os.path.join(sys_path, "device", "uevent"), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("HID_ID="):
                    parts = line.strip().split("=")[1].split(":")
                    return int(parts[1], 16), int(parts[2], 16)
    except (OSError, ValueError, IndexError):
        pass
    return None, None


def _interface_number(sys_path):
    iface = os.path.join(sys_path, "device", "..", "bInterfaceNumber")
    try:
        with open(iface, encoding="utf-8") as fh:
            return int(fh.read().strip(), 16)
    except (OSError, ValueError):
        return None


def detect():
    """Return (profile, /dev/hidrawN) for the first connected keyboard, else (None, None)."""
    try:
        names = sorted(os.listdir("/sys/class/hidraw"))
    except OSError:
        return None, None
    by_product = {p.product: p for p in PROFILES}
    for name in names:
        sys_path = os.path.join("/sys/class/hidraw", name)
        vid, pid = _hid_id(sys_path)
        profile = by_product.get(pid) if vid == VENDOR else None
        if profile and _interface_number(sys_path) == profile.control_interface:
            return profile, os.path.join("/dev", name)
    return None, None


def current():
    """The connected profile, or the Apex 7 TKL default when nothing is plugged in."""
    profile, _path = detect()
    return profile or DEFAULT
