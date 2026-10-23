"""Logitech mouse lighting: HID++ framing, discovery, effects and the worker."""

import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from copy import deepcopy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))

from apex import config, mouse, onboard  # noqa: E402

PALETTE = {"accent": (10, 20, 30), "green": (0, 200, 0)}


class FakeMouse:
    """A HID++ 2.0 mouse with 0x8070: zone 0 primary, zone 1 logo (no breathe)."""

    FEATURES = {0x0000: 0, 0x0005: 3, 0x2201: 5, 0x8070: 9, 0x8100: 11}
    dpi = 1600

    @staticmethod
    def default_sectors():
        from apex import onboard
        directory = bytearray(b"\xff" * 255)
        directory[0:8] = bytes([0, 1, 1, 0xFF, 0, 2, 0, 0xFF])
        profile = bytearray(b"\xff" * 255)
        profile[0:3] = bytes([1, 1, 1])
        defaults = ["80010001", "80010002", "80010004", "80010008", "80010010",
                    "90070000", "90040000", "90030000", "900c0000", "90020000", "90010000"]
        for i, hexes in enumerate(defaults):
            profile[32 + 4 * i:36 + 4 * i] = bytes.fromhex(hexes)
        return {0: onboard.seal(bytes(directory)), 1: onboard.seal(bytes(profile)), 2: onboard.seal(bytes(profile))}
    ZONES = [(1, [0x00, 0x01, 0x03, 0x0A]), (2, [0x00, 0x01])]
    NAME = b"G502 LIGHTSPEED"

    def __init__(self, noise=True):
        self.ours, self.theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.noise = noise
        self.writes = []
        self.sectors = self.default_sectors()
        self.sector_writes = 0
        threading.Thread(target=self._serve, daemon=True).start()

    def _reply(self, msg, params):
        out = bytearray(20)
        out[0:4] = bytes([0x11, 0x01, msg[2], msg[3]])
        out[4:4 + len(params)] = params
        if self.noise:
            self.theirs.send(bytes([0x02, 0, 0, 5, 0, 0, 0, 0]))  # mouse movement
        self.theirs.send(bytes(out))

    def _serve(self):
        while True:
            try:
                msg = self.theirs.recv(64)
            except OSError:
                return
            if not msg:
                return
            feat, fn = msg[2], msg[3] >> 4
            p = msg[4:]
            if feat == 0:
                fid = int.from_bytes(p[0:2], "big")
                self._reply(msg, bytes([self.FEATURES.get(fid, 0), 0, 1]))
            elif feat == 3 and fn == 0:
                self._reply(msg, bytes([len(self.NAME)]))
            elif feat == 3 and fn == 1:
                self._reply(msg, self.NAME[p[0]:p[0] + 16])
            elif feat == 9 and fn == 0:
                self._reply(msg, bytes([len(self.ZONES)]))
            elif feat == 9 and fn == 1:
                loc, effects = self.ZONES[p[0]]
                self._reply(msg, bytes([p[0], 0, loc, len(effects)]))
            elif feat == 9 and fn == 2:
                effect = self.ZONES[p[0]][1][p[1]]
                self._reply(msg, bytes([p[0], p[1], 0, effect]))
            elif feat == 11 and fn == 0:
                self._reply(msg, bytes.fromhex("0103010501 0b 10 00ff 0a04".replace(" ", "")))
            elif feat == 11 and fn == 4:
                self._reply(msg, bytes([0, 1]))
            elif feat == 11 and fn == 5:
                sector, off = int.from_bytes(p[0:2], "big"), int.from_bytes(p[2:4], "big")
                self._reply(msg, self.sectors[sector][off:off + 16])
            elif feat == 11 and fn == 6:
                self.pending = [int.from_bytes(p[0:2], "big"), int.from_bytes(p[4:6], "big"), b""]
                self._reply(msg, b"")
            elif feat == 11 and fn == 7:
                self.pending[2] += bytes(p[:16])
                self._reply(msg, b"")
            elif feat == 11 and fn == 8:
                sector, size, data = self.pending
                self.sectors[sector] = data[:size]
                self.sector_writes += 1
                self._reply(msg, b"")
            elif feat == 5 and fn == 1:
                self._reply(msg, bytes([0, 0x00, 0x64, 0xE0, 0x32, 0x64, 0x00, 0, 0]))  # 100..25600 step 50
            elif feat == 5 and fn == 2:
                self._reply(msg, bytes([0]) + self.dpi.to_bytes(2, "big") + (1600).to_bytes(2, "big"))
            elif feat == 5 and fn == 3:
                self.dpi = int.from_bytes(p[1:3], "big")
                self._reply(msg, p[:3])
            elif feat == 9 and fn == 3:
                self.writes.append(bytes(p[:13]))
                self._reply(msg, p[:13])
            else:
                err = bytearray(20)
                err[0:6] = bytes([0x11, 0x01, 0xFF, feat, msg[3], 0x07])
                self.theirs.send(bytes(err))

    def open(self):
        dev = mouse.Hidpp.__new__(mouse.Hidpp)
        dev.path, dev.fd, dev.features = "fake", os.dup(self.ours.fileno()), {}
        os.set_blocking(dev.fd, False)
        m = mouse.Mouse.__new__(mouse.Mouse)
        orig = mouse.Hidpp
        mouse.Hidpp = lambda _path: dev
        try:
            m.__init__("fake")
        finally:
            mouse.Hidpp = orig
        return m


class Protocol(unittest.TestCase):
    def test_discovery(self):
        m = FakeMouse().open()
        self.assertEqual(m.name, "G502 LIGHTSPEED")
        self.assertEqual([z.name for z in m.zones], ["primary", "logo"])
        self.assertEqual(m.zones[0].effects, {0x00: 0, 0x01: 1, 0x03: 2, 0x0A: 3})

    def test_static_uses_effect_index(self):
        fake = FakeMouse()
        m = fake.open()
        mouse.apply(m, ("static", (74, 28, 144)))
        self.assertEqual(fake.writes, [
            bytes([0, 1, 74, 28, 144]) + bytes(8),
            bytes([1, 1, 74, 28, 144]) + bytes(8),
        ])

    def test_breathe_falls_back_to_static(self):
        fake = FakeMouse()
        m = fake.open()
        mouse.apply(m, ("breathe", (255, 60, 0), 1600))
        primary, logo = fake.writes
        self.assertEqual(primary[:7], bytes([0, 3, 255, 60, 0, 0x06, 0x40]))  # index 3 = breathe
        self.assertEqual(primary[8], 100)
        self.assertEqual(logo[:5], bytes([1, 1, 255, 60, 0]))  # logo cannot breathe

    def test_cycle_skips_zones_without_it(self):
        fake = FakeMouse()
        mouse.apply(fake.open(), ("cycle", 10000, 80))
        self.assertEqual(len(fake.writes), 1)
        self.assertEqual(fake.writes[0][:2], bytes([0, 2]))
        self.assertEqual(fake.writes[0][7:10], bytes([0x27, 0x10, 80]))

    def test_errors_raise(self):
        m = FakeMouse().open()
        with self.assertRaises(mouse.HidppError):
            m.dev.request(9, 7)

    def test_timeout(self):
        a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        dev = mouse.Hidpp.__new__(mouse.Hidpp)
        dev.path, dev.fd, dev.features = "silent", os.dup(a.fileno()), {}
        os.set_blocking(dev.fd, False)
        with self.assertRaises(mouse.HidppError):
            dev.request(0, 0, timeout=0.05)
        dev.close()
        a.close()
        b.close()


class Wanted(unittest.TestCase):
    def cfg(self, **mouse_cfg):
        cfg = deepcopy(config.DEFAULT)
        cfg["rgb"].update(mode="solid", solid="#4A1C90", brightness=80)
        cfg["mouse"].update(mouse_cfg)
        return cfg

    def test_match_follows_keyboard(self):
        self.assertEqual(mouse.wanted(self.cfg(), PALETTE), ("static", (59, 22, 115)))
        cfg = self.cfg()
        cfg["rgb"]["mode"] = "theme"
        self.assertEqual(mouse.wanted(cfg, PALETTE), ("static", (8, 16, 24)))
        cfg["rgb"]["mode"] = "rainbow"
        self.assertEqual(mouse.wanted(cfg, PALETTE)[0], "cycle")
        cfg["rgb"]["mode"] = "off"
        self.assertEqual(mouse.wanted(cfg, PALETTE), ("off",))

    def test_own_colour(self):
        self.assertEqual(mouse.wanted(self.cfg(mode="solid", color="green"), PALETTE), ("static", (0, 200, 0)))
        self.assertEqual(mouse.wanted(self.cfg(mode="breathe", color="#FF0000", brightness=50), PALETTE),
                         ("breathe", (127, 0, 0), mouse.BREATHE_MS))

    def test_away_claude_and_device(self):
        self.assertEqual(mouse.wanted(self.cfg(), PALETTE, away=True), ("off",))
        self.assertEqual(mouse.wanted(self.cfg(), PALETTE, claude_waiting=True),
                         ("breathe", (255, 60, 0), mouse.CLAUDE_BREATHE_MS))
        self.assertEqual(mouse.wanted(self.cfg(claude=False), PALETTE, claude_waiting=True)[0], "static")
        self.assertIsNone(mouse.wanted(self.cfg(mode="device"), PALETTE, away=True))


class Worker(unittest.TestCase):
    def wait_for(self, cond):
        deadline = time.monotonic() + 2
        while not cond() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(cond())

    def test_applies_changes_once_and_recovers(self):
        fake = FakeMouse(noise=False)
        attempts = []

        def opener():
            attempts.append(1)
            if len(attempts) == 1:
                raise mouse.HidppError("asleep")
            return fake.open()

        lights = mouse.MouseLights(opener, ping_seconds=60, retry_seconds=0.05)
        lights.want(("static", (1, 2, 3)))
        self.wait_for(lambda: len(fake.writes) == 2)
        lights.want(("static", (1, 2, 3)))
        lights.want(("off",))
        self.wait_for(lambda: len(fake.writes) == 4)
        time.sleep(0.1)
        self.assertEqual(len(fake.writes), 4)
        self.assertTrue(lights.status()["present"])
        self.assertEqual(lights.status()["zones"], ["primary", "logo"])
        lights.stop()


class Dpi(unittest.TestCase):
    def test_parse_list(self):
        self.assertEqual(mouse.parse_dpi_list([100, 0xE032, 25600, 0]), (100, 25600, 50))
        self.assertEqual(mouse.parse_dpi_list([400, 800, 1600, 0, 99]), (400, 1600, 400))
        self.assertIsNone(mouse.parse_dpi_list([0]))

    def test_set_snaps_to_step_and_range(self):
        fake = FakeMouse()
        m = fake.open()
        self.assertEqual(m.dpi_range, (100, 25600, 50))
        self.assertEqual(m.set_dpi(1234), 1250)
        self.assertEqual(fake.dpi, 1250)
        self.assertEqual(m.set_dpi(99999), 25600)
        self.assertEqual(m.get_dpi(), 25600)

    def test_worker_applies_and_notices_button_changes(self):
        fake = FakeMouse(noise=False)
        lights = mouse.MouseLights(fake.open, ping_seconds=0.05)
        lights.want(None, 3200)
        deadline = time.monotonic() + 2
        while fake.dpi != 3200 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(fake.dpi, 3200)
        self.assertFalse(lights.dpi_moved)
        fake.dpi = 800  # the DPI-down button
        while not lights.dpi_moved and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(lights.dpi_moved)
        self.assertEqual(lights.status()["dpi"], 800)
        self.assertEqual(lights.status()["dpi_presets"], [400, 800, 1600, 3200, 6400])
        lights.stop()


class Buttons(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.backup = os.path.join(self.tmp.name, "profile.bak")
        self.fake = FakeMouse(noise=False)
        self.profiles = onboard.Profiles(self.fake.open().dev)

    def tearDown(self):
        self.tmp.cleanup()

    def test_decodes_g502_defaults(self):
        self.assertEqual(self.profiles.buttons(), {
            2: "middle", 3: "back", 4: "forward", 5: "sniper", 6: "dpi-down",
            7: "dpi-up", 8: "battery", 9: "tilt-right", 10: "tilt-left"})

    def test_remap_backs_up_seals_and_restores(self):
        original = self.fake.sectors[1]
        buttons = self.profiles.set_buttons({8: "play-pause", 7: "workspace-next"}, backup_path=self.backup)
        self.assertEqual((buttons[8], buttons[7], buttons[3]), ("play-pause", "workspace-next", "back"))
        sector = self.fake.sectors[1]
        self.assertTrue(onboard.sealed(sector))
        self.assertEqual(sector[32 + 4 * 8:36 + 4 * 8], bytes.fromhex("800300cd"))
        self.assertEqual(sector[32 + 4 * 7:36 + 4 * 7], bytes([0x80, 0x02, 0, 0x69]))  # F14
        self.assertEqual(sector[:32], original[:32])  # DPI, lighting etc. untouched
        self.profiles.set_buttons({8: "copy"}, backup_path=self.backup)
        with open(self.backup, "rb") as fh:
            self.assertEqual(fh.read()[2:], original)  # the backup is the first original
        self.profiles.restore(self.backup)
        self.assertEqual(self.fake.sectors[1], original)

    def test_unchanged_mapping_writes_nothing(self):
        self.profiles.set_buttons({3: "back"}, backup_path=self.backup)
        self.assertEqual(self.fake.sector_writes, 0)

    def test_refuses_left_right_and_bad_crc(self):
        with self.assertRaises(ValueError):
            self.profiles.set_buttons({0: "back"}, backup_path=self.backup)
        with self.assertRaises(ValueError):
            self.profiles.set_buttons({3: "self-destruct"}, backup_path=self.backup)
        self.fake.sectors[1] = self.fake.sectors[1][:-1] + b"\x00"
        with self.assertRaises(OSError):
            self.profiles.set_buttons({3: "forward"}, backup_path=self.backup)
        self.assertEqual(self.fake.sector_writes, 0)

    def test_aliases(self):
        self.assertEqual(onboard.slot_for("G9"), 8)
        self.assertEqual(onboard.slot_for("tilt-left"), 10)
        self.assertIsNone(onboard.slot_for("0"))  # left click stays put

    def test_hypr_block_added_once(self):
        path = os.path.join(self.tmp.name, "bindings.lua")
        with open(path, "w") as fh:
            fh.write("-- mine\n")
        self.assertTrue(onboard.ensure_hypr_block("/x/apexctl", path))
        self.assertFalse(onboard.ensure_hypr_block("/x/apexctl", path))
        text = open(path).read()
        self.assertTrue(text.startswith("-- mine\n"))
        self.assertEqual(text.count("[apex-mouse]"), 1)
        self.assertIn('"/x/apexctl cheatsheet"', text)
        self.assertEqual(open(path + ".bak.apex-mouse").read(), "-- mine\n")
        self.assertFalse(onboard.ensure_hypr_block("/x/apexctl", os.path.join(self.tmp.name, "missing.lua")))


class Discovery(unittest.TestCase):
    def test_find_mice_skips_receivers_and_others(self):
        with tempfile.TemporaryDirectory() as root:
            def node(name, hid_id, hid_name, driver, descriptor):
                d = os.path.join(root, name, "device")
                os.makedirs(d)
                with open(os.path.join(d, "uevent"), "w") as fh:
                    fh.write(f"DRIVER={driver}\nHID_ID={hid_id}\nHID_NAME={hid_name}\n")
                with open(os.path.join(d, "report_descriptor"), "wb") as fh:
                    fh.write(descriptor)
            node("hidraw7", "0003:0000046D:0000C539", "Logitech USB Receiver", "logitech-djreceiver", b"\x85\x11")
            node("hidraw12", "0003:0000046D:0000407F", "Logitech G502", "logitech-hidpp-device", b"\x85\x10\x85\x11")
            node("hidraw2", "0003:00001038:00001642", "SteelSeries Apex", "hid-generic", b"\x85\x11")
            node("hidraw3", "0003:0000046D:0000C08B", "Logitech webcam", "hid-generic", b"\x85\x01")
            self.assertEqual(mouse.find_mice(root), [("Logitech G502", "/dev/hidraw12")])


if __name__ == "__main__":
    unittest.main()
