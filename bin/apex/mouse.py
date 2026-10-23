"""Logitech mouse lighting over HID++ 2.0 (G502 Lightspeed and friends).

The mouse is reached through its own hidraw node: behind a Lightspeed receiver
that is the logitech-hidpp-device child (the kernel fills in the paired slot),
on a cable it is the USB interface that carries HID++ reports 0x10 / 0x11.

Lighting is feature 0x8070 (Color LED Effects): each zone (primary / logo)
lists the effects it supports, and setZoneEffect takes the zone, the *index*
of an effect in that list, ten effect parameters and a persistence byte. We
write RAM only, so the mouse's own profile comes back after a power cycle.

The mouse is wireless, so it is written only when the wanted lighting changes,
from a background thread: a sleeping mouse makes requests time out, and that
must never stall the daemon's 24 fps keyboard loop.
"""

from __future__ import annotations

import os
import select
import threading
import time

VENDOR = 0x046D
SHORT, LONG = 0x10, 0x11
SHORT_LEN, LONG_LEN = 7, 20
SW_ID = 0x0A  # identifies our requests among the mouse's other reports
TIMEOUT = 0.6

ROOT = 0x0000
DEVICE_NAME = 0x0005
BATTERY_VOLTAGE = 0x1001
ADJUSTABLE_DPI = 0x2201
MOUSE_BUTTON_SPY = 0x8110
COLOR_LED_EFFECTS = 0x8070

# 0x8070 effect IDs and where their parameters go (Solaar's LEDEffects table).
EFFECT_OFF = 0x00
EFFECT_STATIC = 0x01
EFFECT_CYCLE = 0x03
EFFECT_BREATHE = 0x0A

ZONE_NAMES = {1: "primary", 2: "logo", 3: "left", 4: "right", 5: "combined", 6: "primary1",
              7: "primary2", 8: "primary3", 9: "primary4", 10: "primary5", 11: "primary6"}

PING_SECONDS = 20.0  # how often to check the mouse is still there (and re-apply if it came back)
RETRY_SECONDS = 5.0


class HidppError(OSError):
    pass


def _uevent(sys_path):
    out = {}
    try:
        with open(os.path.join(sys_path, "device", "uevent"), encoding="utf-8") as fh:
            for line in fh:
                key, _, value = line.strip().partition("=")
                out[key] = value
    except OSError:
        pass
    return out


def _has_hidpp_reports(sys_path):
    """The report descriptor declares HID++ long reports (Report ID 0x11)."""
    try:
        with open(os.path.join(sys_path, "device", "report_descriptor"), "rb") as fh:
            return b"\x85\x11" in fh.read()
    except OSError:
        return False


def find_mice(root="/sys/class/hidraw"):
    """[(name, /dev/hidrawN)] for Logitech HID++ devices that are not receivers."""
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return []
    found = []
    for name in names:
        sys_path = os.path.join(root, name)
        info = _uevent(sys_path)
        parts = info.get("HID_ID", "").split(":")
        try:
            vid = int(parts[1], 16)
        except (IndexError, ValueError):
            continue
        if vid != VENDOR or info.get("DRIVER") == "logitech-djreceiver":
            continue
        if "receiver" in info.get("HID_NAME", "").lower() or not _has_hidpp_reports(sys_path):
            continue
        found.append((info.get("HID_NAME", "Logitech mouse"), os.path.join("/dev", name)))
    return found


def effect_params(effect, color=(0, 0, 0), period=0, intensity=0):
    """The ten parameter bytes for one effect."""
    p = bytearray(10)
    r, g, b = (max(0, min(255, int(c))) for c in color)
    if effect == EFFECT_STATIC:
        p[0:3] = bytes((r, g, b))  # p[3] = ramp: 0 = device default
    elif effect == EFFECT_BREATHE:
        p[0:3] = bytes((r, g, b))
        p[3:5] = int(period).to_bytes(2, "big")
        p[6] = max(0, min(100, int(intensity)))  # p[5] = waveform: 0 = default
    elif effect == EFFECT_CYCLE:
        p[5:7] = int(period).to_bytes(2, "big")
        p[7] = max(0, min(100, int(intensity)))
    return bytes(p)


class Hidpp:
    """Blocking HID++ 2.0 requests on one hidraw node."""

    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self.features = {}

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _drain(self):
        # Mouse movement and button reports pile up between requests; drop them.
        while True:
            try:
                if not os.read(self.fd, 64):
                    return
            except BlockingIOError:
                return

    def request(self, feature_index, function, params=b"", timeout=TIMEOUT):
        msg = bytearray(LONG_LEN)
        msg[0], msg[1], msg[2] = LONG, 0xFF, feature_index
        msg[3] = (function << 4) | SW_ID
        msg[4:4 + len(params)] = params
        self._drain()
        os.write(self.fd, bytes(msg))
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise HidppError(f"no reply from mouse ({self.path})")
            ready, _, _ = select.select([self.fd], [], [], left)
            if not ready:
                continue
            try:
                data = os.read(self.fd, 64)
            except BlockingIOError:
                continue
            if len(data) < 4 or data[0] not in (SHORT, LONG):
                continue
            if data[2] == 0xFF and data[3] == feature_index and data[4] == msg[3]:
                raise HidppError(f"HID++ error {data[5]:#04x} on feature {feature_index} fn {function}")
            if data[2] == 0x8F and data[3] == feature_index:
                raise HidppError(f"mouse unreachable (HID++ 1.0 error {data[5]:#04x})")
            if data[2] == feature_index and data[3] == msg[3]:
                return data[4:]

    def feature(self, feature_id):
        """Index of a feature, or None when the mouse lacks it."""
        if feature_id not in self.features:
            reply = self.request(0, 0, feature_id.to_bytes(2, "big"))
            self.features[feature_id] = reply[0] or None
        return self.features[feature_id]

    def name(self):
        idx = self.feature(DEVICE_NAME)
        if not idx:
            return None
        length = self.request(idx, 0)[0]
        out = b""
        while len(out) < length:
            out += bytes(self.request(idx, 1, bytes([len(out)])))[:length - len(out)]
        return out.rstrip(b"\0").decode("utf-8", "replace")


# Li-ion voltage (mV) to charge (%), as Solaar approximates it for 0x1001.
_BATTERY_CURVE = ((4186, 100), (4067, 90), (3989, 80), (3922, 70), (3859, 60), (3811, 50),
                  (3778, 40), (3751, 30), (3717, 20), (3671, 10), (3646, 5), (3579, 2), (3500, 0))


def battery_percent(mv):
    if mv >= _BATTERY_CURVE[0][0]:
        return 100
    for (hi_mv, hi_pct), (lo_mv, lo_pct) in zip(_BATTERY_CURVE, _BATTERY_CURVE[1:]):
        if mv >= lo_mv:
            return round(lo_pct + (hi_pct - lo_pct) * (mv - lo_mv) / (hi_mv - lo_mv))
    return 0


def is_wireless(path, root="/sys/class/hidraw"):
    """The hidraw node belongs to a mouse paired through a receiver, not a cable."""
    parent = os.path.realpath(os.path.join(root, os.path.basename(path), "device", ".."))
    return os.path.basename(os.path.realpath(os.path.join(parent, "driver"))) == "logitech-djreceiver"


def parse_dpi_list(values):
    """(min, max, step) from a 0x2201 DPI list: plain values, or low, 0xE000|step, high."""
    out, step = [], None
    values = list(values)
    i = 0
    while i < len(values) and values[i]:
        v = values[i]
        if v >> 13 == 0x7 and out and i + 1 < len(values):
            step = v & 0x1FFF
            out.append(values[i + 1])
            i += 2
            continue
        out.append(v)
        i += 1
    if not out:
        return None
    if step is None:
        gaps = [b - a for a, b in zip(out, out[1:]) if b > a]
        step = min(gaps) if gaps else 50
    return min(out), max(out), step


class Zone:
    def __init__(self, index, location, effects):
        self.index = index
        self.location = location
        self.name = ZONE_NAMES.get(location, f"zone{index}")
        self.effects = effects  # effect ID -> index in this zone's list


class Mouse:
    """One mouse's lighting zones and effects, discovered once."""

    def __init__(self, path):
        self.dev = Hidpp(path)
        self.path = path
        try:
            self.leds = self.dev.feature(COLOR_LED_EFFECTS)
            if not self.leds:
                raise HidppError("this mouse has no Color LED Effects (0x8070) lighting")
            self.name = self.dev.name() or "Logitech mouse"
            self.zones = []
            for z in range(self.dev.request(self.leds, 0)[0]):
                info = self.dev.request(self.leds, 1, bytes([z]))
                location = int.from_bytes(info[1:3], "big")
                effects = {}
                for i in range(info[3]):
                    e = self.dev.request(self.leds, 2, bytes([z, i]))
                    effects[int.from_bytes(e[2:4], "big")] = i
                self.zones.append(Zone(z, location, effects))
            self.dpi_feature = self.dev.feature(ADJUSTABLE_DPI)
            self.dpi_range = None
            if self.dpi_feature:
                raw = bytes(self.dev.request(self.dpi_feature, 1, b"\x00"))[1:]
                self.dpi_range = parse_dpi_list(int.from_bytes(raw[i:i + 2], "big") for i in range(0, len(raw) - 1, 2))
        except OSError:
            self.dev.close()
            raise

    def close(self):
        self.dev.close()

    def ping(self):
        self.dev.request(0, 0, ROOT.to_bytes(2, "big"))

    def battery(self):
        """{"percent", "charging", "full"} from 0x1001, or None without it."""
        idx = self.dev.feature(BATTERY_VOLTAGE)
        if not idx:
            return None
        reply = bytes(self.dev.request(idx, 0))
        mv, flags = int.from_bytes(reply[0:2], "big"), reply[2]
        external = bool(flags & 0x80)  # on the cable / charging
        return {"percent": battery_percent(mv), "charging": external and flags & 0x07 == 0,
                "full": external and flags & 0x07 == 1, "mv": mv}

    def get_dpi(self):
        if not self.dpi_feature:
            return None
        return int.from_bytes(self.dev.request(self.dpi_feature, 2, b"\x00")[1:3], "big")

    def set_dpi(self, dpi):
        if not self.dpi_range:
            return None
        low, high, step = self.dpi_range
        dpi = max(low, min(high, low + round((int(dpi) - low) / step) * step))
        self.dev.request(self.dpi_feature, 3, b"\x00" + dpi.to_bytes(2, "big"))
        return dpi

    def set_effect(self, effect, color=(0, 0, 0), period=0, intensity=0, zones=None):
        """Apply one effect to every zone (or the named ones) that supports it."""
        params = effect_params(effect, color, period, intensity)
        for zone in self.zones:
            if zones and zone.name not in zones:
                continue
            target = effect
            if target not in zone.effects and effect == EFFECT_BREATHE:
                target = EFFECT_STATIC  # a zone that cannot breathe still shows the colour
            if target not in zone.effects:
                continue
            zone_params = params if target == effect else effect_params(target, color)
            self.dev.request(self.leds, 3, bytes([zone.index, zone.effects[target]]) + zone_params + b"\x00")

    def describe(self):
        return {
            "name": self.name,
            "path": self.path,
            "zones": [{"index": z.index, "name": z.name, "effects": sorted(z.effects)} for z in self.zones],
            "dpi_range": list(self.dpi_range) if self.dpi_range else None,
            "wireless": is_wireless(self.path),
        }


def open_mouse():
    """The first Logitech mouse with controllable lighting, or raise OSError."""
    mice = find_mice()
    if not mice:
        raise HidppError("no Logitech HID++ mouse found")
    errors = []
    for _name, path in mice:
        if not os.access(path, os.R_OK | os.W_OK):
            errors.append(f"{path} is not accessible (install the Logitech udev rule)")
            continue
        try:
            return Mouse(path)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    raise HidppError("; ".join(errors))


def apply(mouse, spec):
    """Write one spec from wanted() to the mouse."""
    kind = spec[0]
    if kind == "off":
        mouse.set_effect(EFFECT_OFF)
    elif kind == "static":
        mouse.set_effect(EFFECT_STATIC, spec[1])
    elif kind == "breathe":
        mouse.set_effect(EFFECT_BREATHE, spec[1], period=spec[2], intensity=100)
    elif kind == "cycle":
        mouse.set_effect(EFFECT_CYCLE, period=spec[1], intensity=spec[2])


MODES = ("match", "solid", "breathe", "cycle", "off", "device")
BREATHE_MS = 4000
CYCLE_MS = 10000
CLAUDE_BREATHE_MS = 1600
DPI_PRESETS = (400, 800, 1600, 3200, 6400)
IDENTIFY_SECONDS = 10.0  # how long "press a button" waits
IDENTIFIED_SECONDS = 4.0  # how long status reports the answer


def spec_hex(spec):
    """A spec as the panel draws it: "#rrggbb", "cycle", "off", or None (hands off)."""
    if spec is None:
        return None
    if spec[0] in ("static", "breathe"):
        return "#%02x%02x%02x" % tuple(spec[1])
    return spec[0]


def previews(cfg, palette):
    """(keyboard, mouse) colours at full brightness, for the panel's status cards."""
    full = {**cfg, "mouse": {**cfg.get("mouse", {}), "brightness": 100}}
    keyboard = wanted({**full, "mouse": {"mode": "match", "brightness": 100}}, palette)
    return spec_hex(keyboard), spec_hex(wanted(full, palette))


def wanted(cfg, palette, away=False, claude_waiting=False):
    """What the mouse should show, as a hashable spec; None leaves it alone.

    ("static", rgb) | ("breathe", rgb, period_ms) | ("cycle", period_ms, intensity) | ("off",)
    """
    from . import rgb as rgbmod
    mcfg, kb = cfg.get("mouse", {}), cfg["rgb"]
    mode = mcfg.get("mode", "match")
    if mode == "device":
        return None
    if away:
        return ("off",)
    if claude_waiting and mcfg.get("claude", True) and kb.get("claude_esc", True):
        alert = rgbmod.parse_hex(kb.get("claude_esc_color"), rgbmod.CLAUDE_ALERT)
        return ("breathe", alert, CLAUDE_BREATHE_MS)
    brightness = mcfg.get("brightness")
    accent = palette.get("accent", (137, 180, 250))
    if mode == "match":
        kb_mode = kb.get("mode", "theme")
        brightness = kb.get("brightness", 80) if brightness is None else brightness
        if kb_mode == "off":
            return ("off",)
        if kb_mode in ("wave", "rainbow"):
            period = int(CYCLE_MS * 45 / max(1, kb.get("speed", 45)))
            return ("cycle", max(1000, min(60000, period)), max(1, int(brightness)))
        if kb_mode == "solid":
            color = rgbmod.parse_hex(kb.get("solid"), accent)
        elif kb_mode == "gradient":
            color = next(rgbmod.profile_colors(kb.get("profile")))
        else:  # theme, breathe, reactive
            color = accent
        color = rgbmod.scale_color(color, brightness)
        return ("breathe", color, BREATHE_MS) if kb_mode == "breathe" else ("static", color)
    brightness = 100 if brightness is None else brightness
    if mode == "off":
        return ("off",)
    if mode == "cycle":
        return ("cycle", CYCLE_MS, max(1, int(brightness)))
    color = rgbmod.scale_color(rgbmod.resolve_color(mcfg.get("color", "accent"), palette, accent), brightness)
    if mode == "breathe":
        return ("breathe", color, BREATHE_MS)
    return ("static", color)


class MouseLights:
    """Keeps the mouse showing the latest wanted lighting and DPI, from a worker thread.

    DPI also changes on the mouse itself (its DPI buttons). Each check reads it
    back; a change made there shows up as `dpi_moved`, for the daemon to adopt
    into the config so the mouse gets that DPI back after a power cycle.
    """

    def __init__(self, opener=open_mouse, ping_seconds=PING_SECONDS, retry_seconds=RETRY_SECONDS):
        self.opener = opener
        self.ping_seconds = ping_seconds
        self.retry_seconds = retry_seconds
        self.spec = None
        self.applied = None
        self.dpi_wanted = None
        self.dpi_applied = None
        self.dpi = None
        self.dpi_moved = False
        self.battery = None
        self.identifying = False
        self.identified = None  # (slot, monotonic time)
        self.buttons = None
        self.mouse = None
        self.info = None
        self.error = None
        self.wake = threading.Event()
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._run, name="apex-mouse", daemon=True)
        self.thread.start()

    def want(self, spec, dpi=None):
        if spec != self.spec or dpi != self.dpi_wanted:
            self.spec = spec
            self.dpi_wanted = dpi
            self.wake.set()

    def status(self):
        info = self.info or {}
        out = {"present": self.mouse is not None, "name": info.get("name"),
               "zones": [z["name"] for z in info.get("zones", [])], "error": self.error}
        if self.mouse is not None:
            out["connection"] = "wireless" if info.get("wireless") else "wired"
            if self.battery:
                out["battery"] = self.battery
        if self.mouse is not None and info.get("dpi_range"):
            low, high, step = info["dpi_range"]
            out.update(dpi=self.dpi, dpi_min=low, dpi_max=high, dpi_step=step,
                       dpi_presets=[d for d in DPI_PRESETS if low <= d <= high])
        found = self.identified
        out["identify"] = {"active": self.identifying,
                           "slot": found[0] if found and time.monotonic() - found[1] < IDENTIFIED_SECONDS else None}
        if self.mouse is not None and self.buttons:
            from . import onboard
            out["buttons"] = [{"id": slot, "label": onboard.SLOTS[slot], "action": action}
                              for slot, action in sorted(self.buttons.items())]
            out["button_actions"] = [{"value": name, "label": label} for name, (label, _b) in onboard.ACTIONS.items()]
        return out

    def _profiles(self):
        from . import onboard
        if self.mouse is None:
            raise HidppError(self.error or "no mouse connected")
        return onboard.Profiles(self.mouse.dev)

    def set_buttons(self, changes):
        """Remap buttons in the mouse's active onboard profile (writes its flash)."""
        with self.lock:
            self.buttons = self._profiles().set_buttons(changes)
        return self.buttons

    def identify(self, seconds=IDENTIFY_SECONDS):
        """Wait (on a thread) for the next button press and report its slot.

        Button spy makes the mouse report raw presses over HID++ (bit n = slot
        n) instead of acting on them, so it is only on for this short wait.
        """
        if self.identifying or self.mouse is None:
            return False
        self.identifying = True
        self.identified = None
        threading.Thread(target=self._identify, args=(seconds,), name="apex-identify", daemon=True).start()
        return True

    def _identify(self, seconds):
        try:
            with self.lock:
                if self.mouse is None:
                    return
                dev = self.mouse.dev
                spy = dev.feature(MOUSE_BUTTON_SPY)
                if not spy:
                    return
                dev.request(spy, 1)
                try:
                    deadline = time.monotonic() + seconds
                    while self.running and time.monotonic() < deadline:
                        ready, _, _ = select.select([dev.fd], [], [], 0.2)
                        if not ready:
                            continue
                        try:
                            data = os.read(dev.fd, 64)
                        except BlockingIOError:
                            continue
                        if len(data) < 6 or data[0] not in (SHORT, LONG) or data[2] != spy:
                            continue
                        bits = int.from_bytes(data[4:6], "big") & ~0b11  # left / right click don't count
                        if bits:
                            self.identified = ((bits & -bits).bit_length() - 1, time.monotonic())
                            return
                finally:
                    dev.request(spy, 2)
        except OSError:
            pass
        finally:
            self.identifying = False

    def restore_buttons(self):
        with self.lock:
            profiles = self._profiles()
            profiles.restore()
            self.buttons = profiles.buttons()
        return self.buttons

    def _drop(self, exc):
        self.error = str(exc)
        if self.mouse:
            self.mouse.close()
        self.mouse = None
        self.applied = None
        self.dpi_applied = None

    def _sync(self, spec, dpi):
        m = self.mouse
        if spec is not None and spec != self.applied:
            apply(m, spec)
            self.applied = spec
        if dpi is not None and dpi != self.dpi_applied:
            self.dpi = self.dpi_applied = m.set_dpi(dpi)
            return
        try:
            self.battery = m.battery()
        except HidppError:
            self.battery = None
        current = m.get_dpi() if m.dpi_feature else None
        if current is None:
            m.ping()
            return
        if self.dpi_applied is not None and current != self.dpi_applied:
            self.dpi_moved = True  # changed with the mouse's own buttons
        self.dpi = self.dpi_applied = current

    def _run(self):
        while self.running:
            spec, dpi = self.spec, self.dpi_wanted
            with self.lock:
                try:
                    if self.mouse is None:
                        self.mouse = self.opener()
                        self.info = self.mouse.describe()
                        self.error = None
                        try:
                            self.buttons = self._profiles().buttons()
                        except (OSError, ValueError):
                            self.buttons = None  # no onboard profiles: lighting and DPI only
                        try:
                            self.battery = self.mouse.battery()
                        except HidppError:
                            self.battery = None
                    self._sync(spec, dpi)
                except OSError as exc:
                    # Asleep, switched off, unplugged (or moved between cable and
                    # receiver) or not permitted: try again later. A mouse that
                    # comes back shows its own lighting and DPI, so forgetting
                    # what was applied makes the next success re-send ours.
                    self._drop(exc)
            if self.mouse is not None and (self.spec, self.dpi_wanted) != (spec, dpi):
                continue
            self.wake.wait(self.ping_seconds if self.mouse is not None else self.retry_seconds)
            self.wake.clear()

    def stop(self):
        self.running = False
        self.wake.set()
        self.thread.join(timeout=2)
        with self.lock:
            if self.mouse:
                self.mouse.close()
                self.mouse = None
