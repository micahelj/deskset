"""Mouse button mapping in a Logitech onboard profile (HID++ 0x8100).

The mouse runs one of the profiles stored in its flash: a 255-byte sector per
profile with a CRC-CCITT trailer. The button table is 16 four-byte bindings
from offset 32 (alternate G-shift bindings follow at 96):

  80 01 <mask BE>     mouse button (1 left, 2 right, 4 middle, 8 back, 0x10 forward)
  80 02 <mods> <key>  keyboard usage with modifier bits (1 ctrl, 2 shift, 4 alt, 8 super)
  80 03 <usage BE>    consumer control (media keys)
  90 <code> 00 00     mouse function: 1/2 tilt left/right, 3/4 DPI up/down,
                      7 DPI shift (sniper), 0x0c battery level
  ff ff ff ff         disabled

Desktop actions send F13-F18, which Hyprland binds (see HYPR_BLOCK). Left and
right click are never touched. The first write backs up the original sector.
"""

from __future__ import annotations

import os

from .config import CONFIG_PATH

ONBOARD_PROFILES = 0x8100
BUTTONS_OFFSET = 32
BACKUP_PATH = os.path.join(os.path.dirname(CONFIG_PATH), "apex-mouse-profile.bak")

# Remappable slots of the G502 layout, named after their default function.
# Remappable slots of the G502 layout, named by where the button sits
# (confirmed on hardware with the mouse's button spy).
SLOTS = {
    2: "Wheel click",
    3: "Thumb rear",
    4: "Thumb front",
    5: "Sniper (red)",
    6: "Left of click, rear",
    7: "Left of click, front",
    8: "Behind wheel",
    9: "Tilt right",
    10: "Tilt left",
}
ALIASES = {"wheel": 2, "thumb-rear": 3, "thumb-front": 4, "sniper": 5, "left-rear": 6, "left-front": 7,
           "behind-wheel": 8, "tilt-right": 9, "tilt-left": 10,
           # Older G-number names.
           "g4": 3, "g5": 4, "g6": 5, "g8": 6, "g7": 7, "g9": 8}


def slot_for(name):
    """Slot number for "g9", "tilt-left", "8", ...; None if unknown."""
    text = str(name).strip().lower()
    slot = ALIASES.get(text, int(text) if text.isdigit() else None)
    return slot if slot in SLOTS else None


def _key(key, mods=0):
    return bytes([0x80, 0x02, mods, key])


def _consumer(usage):
    return bytes([0x80, 0x03]) + usage.to_bytes(2, "big")


def _mouse(mask):
    return bytes([0x80, 0x01]) + mask.to_bytes(2, "big")


def _special(code):
    return bytes([0x90, code, 0, 0])


F13 = 0x68  # HID usage; F13..F18 = 0x68..0x6D

# action -> (label, binding). Order is the panel's dropdown order.
ACTIONS = {
    "back": ("Back", _mouse(0x08)),
    "forward": ("Forward", _mouse(0x10)),
    "middle": ("Middle click", _mouse(0x04)),
    "dpi-up": ("DPI up", _special(0x03)),
    "dpi-down": ("DPI down", _special(0x04)),
    "sniper": ("DPI shift (sniper)", _special(0x07)),
    "tilt-left": ("Scroll left", _special(0x01)),
    "tilt-right": ("Scroll right", _special(0x02)),
    "battery": ("Show battery", _special(0x0C)),
    "workspace-prev": ("Previous workspace", _key(F13)),
    "workspace-next": ("Next workspace", _key(F13 + 1)),
    "screenshot": ("Screenshot", _key(F13 + 2)),
    "mic-mute": ("Mute microphone", _key(F13 + 3)),
    "cheatsheet": ("Keyboard cheat sheet", _key(F13 + 4)),
    "menu": ("Omarchy menu", _key(F13 + 5)),
    "play-pause": ("Play / pause", _consumer(0x00CD)),
    "next-track": ("Next track", _consumer(0x00B5)),
    "prev-track": ("Previous track", _consumer(0x00B6)),
    "volume-up": ("Volume up", _consumer(0x00E9)),
    "volume-down": ("Volume down", _consumer(0x00EA)),
    "mute": ("Mute", _consumer(0x00E2)),
    "copy": ("Copy", _key(0x06, 0x01)),
    "paste": ("Paste", _key(0x19, 0x01)),
    "undo": ("Undo", _key(0x1D, 0x01)),
    "disabled": ("Do nothing", b"\xff\xff\xff\xff"),
}
_BY_BINDING = {binding: name for name, (_label, binding) in ACTIONS.items()}

# Hyprland bindings for the F13-F18 desktop actions (xkb keycodes 191-196).
HYPR_MARK = "apex-mouse"
HYPR_BLOCK = f"""-- [{HYPR_MARK}] G502 buttons mapped to desktop actions send F13-F18 (apexctl mouse --button).
o.bind("code:191", "Mouse: previous workspace", hl.dsp.focus({{ workspace = "e-1" }}))
o.bind("code:192", "Mouse: next workspace", hl.dsp.focus({{ workspace = "e+1" }}))
o.bind("code:193", "Mouse: screenshot", "omarchy-capture-screenshot")
o.bind("code:194", "Mouse: mute microphone", "omarchy-audio-input-mute", {{ locked = true }})
o.bind("code:195", "Mouse: keyboard cheat sheet", "{{apexctl}} cheatsheet")
o.bind("code:196", "Mouse: Omarchy menu", "omarchy-menu toggle")
-- [/{HYPR_MARK}]
"""


def decode(binding):
    return _BY_BINDING.get(bytes(binding), "custom")


def crc_ccitt(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def seal(sector):
    """The sector with its CRC trailer recomputed."""
    body = bytes(sector[:-2])
    return body + crc_ccitt(body).to_bytes(2, "big")


def sealed(sector):
    return crc_ccitt(sector[:-2]) == int.from_bytes(sector[-2:], "big")


class Profiles:
    """The active onboard profile of one mouse (a mouse.Hidpp)."""

    def __init__(self, dev):
        self.dev = dev
        self.idx = dev.feature(ONBOARD_PROFILES)
        if not self.idx:
            raise OSError("this mouse has no onboard profiles (0x8100)")
        info = bytes(dev.request(self.idx, 0))
        self.size = int.from_bytes(info[7:9], "big")
        self.button_count = info[5]

    def read_sector(self, sector):
        out = bytearray(self.size)
        for off in range(0, self.size, 16):
            at = min(off, self.size - 16)  # the last read overlaps instead of overrunning
            chunk = bytes(self.dev.request(self.idx, 5, sector.to_bytes(2, "big") + at.to_bytes(2, "big")))
            out[at:at + 16] = chunk[:16]
        return bytes(out)

    def write_sector(self, sector, data):
        data = seal(data)
        self.dev.request(self.idx, 6, sector.to_bytes(2, "big") + b"\x00\x00" + self.size.to_bytes(2, "big"))
        for off in range(0, self.size, 16):
            self.dev.request(self.idx, 7, data[off:off + 16].ljust(16, b"\x00"))
        self.dev.request(self.idx, 8)
        back = self.read_sector(sector)
        if back != data:
            raise OSError(f"profile sector {sector:#06x} did not read back as written")

    def active_sector(self):
        """The sector of the profile the mouse is running (a user profile, never ROM)."""
        current = int.from_bytes(bytes(self.dev.request(self.idx, 4))[0:2], "big")
        directory = self.read_sector(0)  # 4-byte entries: sector BE, enabled, reserved
        if not 1 <= current <= self.size // 4 or not sealed(directory):
            raise OSError(f"the active profile ({current:#06x}) is not a writable user profile")
        sector = int.from_bytes(directory[4 * (current - 1):4 * current - 2], "big")
        if not 1 <= sector < 0x100:  # 0x01xx sectors are read-only ROM defaults
            raise OSError(f"the active profile lives in {sector:#06x}, not a writable user sector")
        return sector

    def buttons(self):
        """{slot: action} for the remappable slots of the active profile."""
        data = self.read_sector(self.active_sector())
        if not sealed(data):
            raise OSError("the active profile fails its CRC check; not touching it")
        return {slot: decode(data[BUTTONS_OFFSET + 4 * slot:BUTTONS_OFFSET + 4 * slot + 4]) for slot in SLOTS}

    def set_buttons(self, changes, backup_path=BACKUP_PATH):
        """Write {slot: action} into the active profile; returns the new buttons()."""
        for slot, action in changes.items():
            if slot not in SLOTS:
                raise ValueError(f"button slot {slot} cannot be remapped")
            if action not in ACTIONS:
                raise ValueError(f"unknown button action {action}")
        sector = self.active_sector()
        data = self.read_sector(sector)
        if not sealed(data):
            raise OSError("the active profile fails its CRC check; not touching it")
        if backup_path and not os.path.exists(backup_path):
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            with open(backup_path, "wb") as fh:
                fh.write(sector.to_bytes(2, "big") + data)
        new = bytearray(data)
        for slot, action in changes.items():
            new[BUTTONS_OFFSET + 4 * slot:BUTTONS_OFFSET + 4 * slot + 4] = ACTIONS[action][1]
        if bytes(new) != data:
            self.write_sector(sector, bytes(new))
        return self.buttons()

    def restore(self, backup_path=BACKUP_PATH):
        """Write the backed-up profile sector back."""
        with open(backup_path, "rb") as fh:
            raw = fh.read()
        sector, data = int.from_bytes(raw[:2], "big"), raw[2:]
        if len(data) != self.size or not sealed(data):
            raise OSError(f"{backup_path} is not a valid profile backup")
        self.write_sector(sector, data)


HYPR_BINDINGS = os.path.expanduser("~/.config/hypr/bindings.lua")
DESKTOP_ACTIONS = ("workspace-prev", "workspace-next", "screenshot", "mic-mute", "cheatsheet", "menu")


def ensure_hypr_block(apexctl, path=HYPR_BINDINGS):
    """Add the F13-F18 bindings to the user's Hyprland config once; True if added."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return False  # not an Omarchy Lua config; desktop actions stay unbound
    if f"[{HYPR_MARK}]" in text:
        return False
    backup = path + ".bak.apex-mouse"
    if not os.path.exists(backup):
        with open(backup, "w", encoding="utf-8") as fh:
            fh.write(text)
    block = HYPR_BLOCK.replace("{apexctl}", apexctl)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.rstrip("\n") + "\n\n" + block)
    return True
