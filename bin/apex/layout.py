"""Apex 7 TKL LED names, visual coordinates, and evdev key mapping.

LED order matches OpenRGB's SteelSeries Apex RGB controller.
Coordinates are in key-unit space for wave/rainbow/ripple effects.
"""

# OpenRGB reports this exact list for the Apex 7 TKL.
LEDS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O",
    "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
    "Enter", "Escape", "Backspace", "Tab", "Space", "-", "=", "[", "]", "#",
    ";", "'", "`", ",", ".", "/", "Caps Lock",
    "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
    "Print Screen", "Scroll Lock", "Pause/Break",
    "Insert", "Home", "Page Up", "Delete", "End", "Page Down",
    "Right Arrow", "Left Arrow", "Down Arrow", "Up Arrow",
    r"\ (ISO)", "Left Control", "Left Shift", "Left Alt", "Left Windows",
    "Right Control", "Right Shift", "Right Alt", "Right Windows", "Right Fn",
    r"\ (ANSI)", "_", "かな", "¥", "変換", "無変換",
    "Num Lock", "Number Pad /", "Number Pad *", "Number Pad -", "Number Pad +",
    "Number Pad Enter", "Number Pad 1", "Number Pad 2", "Number Pad 3",
    "Number Pad 4", "Number Pad 5", "Number Pad 6", "Number Pad 7",
    "Number Pad 8", "Number Pad 9", "Number Pad 0", "Number Pad .",
    "Media Play/Pause",
]

ALPHA = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890")
PUNCT = {"-", "=", "[", "]", "#", ";", "'", "`", ",", ".", "/", "_"}
MODS = {
    "Left Control", "Left Shift", "Left Alt", "Left Windows",
    "Right Control", "Right Shift", "Right Alt", "Right Windows", "Right Fn",
}
FNROW = {f"F{i}" for i in range(1, 13)}
HIGHLIGHT = {
    "Enter", "Escape", "Backspace", "Tab", "Space", "Caps Lock",
    "Right Arrow", "Left Arrow", "Down Arrow", "Up Arrow", "Media Play/Pause",
}

# Visual (x, y) for TKL keys. Missing keys keep a far-right sentinel so they
# don't distort wave effects.
_XY = {
    "Escape": (0.0, 0.0),
    "F1": (2.0, 0.0), "F2": (3.0, 0.0), "F3": (4.0, 0.0), "F4": (5.0, 0.0),
    "F5": (6.5, 0.0), "F6": (7.5, 0.0), "F7": (8.5, 0.0), "F8": (9.5, 0.0),
    "F9": (11.0, 0.0), "F10": (12.0, 0.0), "F11": (13.0, 0.0), "F12": (14.0, 0.0),
    "Print Screen": (15.25, 0.0), "Scroll Lock": (16.25, 0.0),
    "Pause/Break": (17.25, 0.0), "Media Play/Pause": (18.4, 0.0),
    "`": (0.0, 1.25),
    "1": (1.0, 1.25), "2": (2.0, 1.25), "3": (3.0, 1.25), "4": (4.0, 1.25),
    "5": (5.0, 1.25), "6": (6.0, 1.25), "7": (7.0, 1.25), "8": (8.0, 1.25),
    "9": (9.0, 1.25), "0": (10.0, 1.25), "-": (11.0, 1.25), "=": (12.0, 1.25),
    "Backspace": (13.5, 1.25),
    "Insert": (15.25, 1.25), "Home": (16.25, 1.25), "Page Up": (17.25, 1.25),
    "Tab": (0.75, 2.25),
    "Q": (1.75, 2.25), "W": (2.75, 2.25), "E": (3.75, 2.25), "R": (4.75, 2.25),
    "T": (5.75, 2.25), "Y": (6.75, 2.25), "U": (7.75, 2.25), "I": (8.75, 2.25),
    "O": (9.75, 2.25), "P": (10.75, 2.25), "[": (11.75, 2.25), "]": (12.75, 2.25),
    r"\ (ANSI)": (14.0, 2.25), r"\ (ISO)": (14.0, 2.25), "#": (14.0, 2.25),
    "Delete": (15.25, 2.25), "End": (16.25, 2.25), "Page Down": (17.25, 2.25),
    "Caps Lock": (0.9, 3.25),
    "A": (2.0, 3.25), "S": (3.0, 3.25), "D": (4.0, 3.25), "F": (5.0, 3.25),
    "G": (6.0, 3.25), "H": (7.0, 3.25), "J": (8.0, 3.25), "K": (9.0, 3.25),
    "L": (10.0, 3.25), ";": (11.0, 3.25), "'": (12.0, 3.25),
    "Enter": (13.6, 3.25),
    "Left Shift": (1.15, 4.25),
    "Z": (2.5, 4.25), "X": (3.5, 4.25), "C": (4.5, 4.25), "V": (5.5, 4.25),
    "B": (6.5, 4.25), "N": (7.5, 4.25), "M": (8.5, 4.25), ",": (9.5, 4.25),
    ".": (10.5, 4.25), "/": (11.5, 4.25),
    "Right Shift": (13.4, 4.25),
    "Up Arrow": (16.25, 4.25),
    "Left Control": (0.7, 5.25), "Left Windows": (2.1, 5.25),
    "Left Alt": (3.4, 5.25), "Space": (7.4, 5.25),
    "Right Alt": (11.4, 5.25), "Right Windows": (12.6, 5.25),
    "Right Fn": (13.7, 5.25), "Right Control": (14.9, 5.25),
    "Left Arrow": (15.25, 5.25), "Down Arrow": (16.25, 5.25),
    "Right Arrow": (17.25, 5.25),
}

XY = {name: _XY.get(name, (20.0, 3.0)) for name in LEDS}
MAX_X = max(p[0] for p in XY.values())
MAX_Y = max(p[1] for p in XY.values())

# linux/input-event-codes.h → OpenRGB LED name (letters, mods, nav, function).
KEYCODE_TO_LED = {
    1: "Escape", 2: "1", 3: "2", 4: "3", 5: "4", 6: "5", 7: "6", 8: "7",
    9: "8", 10: "9", 11: "0", 12: "-", 13: "=", 14: "Backspace", 15: "Tab",
    16: "Q", 17: "W", 18: "E", 19: "R", 20: "T", 21: "Y", 22: "U", 23: "I",
    24: "O", 25: "P", 26: "[", 27: "]", 28: "Enter", 29: "Left Control",
    30: "A", 31: "S", 32: "D", 33: "F", 34: "G", 35: "H", 36: "J", 37: "K",
    38: "L", 39: ";", 40: "'", 41: "`", 42: "Left Shift", 43: r"\ (ANSI)",
    44: "Z", 45: "X", 46: "C", 47: "V", 48: "B", 49: "N", 50: "M", 51: ",",
    52: ".", 53: "/", 54: "Right Shift", 56: "Left Alt", 57: "Space",
    58: "Caps Lock", 59: "F1", 60: "F2", 61: "F3", 62: "F4", 63: "F5",
    64: "F6", 65: "F7", 66: "F8", 67: "F9", 68: "F10", 87: "F11", 88: "F12",
    97: "Right Control", 99: "Print Screen", 100: "Right Alt",
    102: "Home", 103: "Up Arrow", 104: "Page Up", 105: "Left Arrow",
    106: "Right Arrow", 107: "End", 108: "Down Arrow", 109: "Page Down",
    110: "Insert", 111: "Delete", 119: "Pause/Break", 125: "Left Windows",
    126: "Right Windows", 164: "Media Play/Pause",
}

RGB_MODES = ("theme", "solid", "gradient", "wave", "breathe", "rainbow", "reactive", "off")
OLED_PAGES = ("clock", "now-playing", "workspace", "logo", "text", "claude", "clear")
WHEEL_MODES = ("volume", "workspace", "brightness", "oled", "rgb")
