"""Workspace keys: level mapping, number-row colours, event filtering."""

import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))

from apex import layout, rgb, workspaces  # noqa: E402

MONITORS = [
    {"name": "DP-2", "focused": True, "activeWorkspace": {"id": 1}},
    {"name": "eDP-1", "focused": False, "activeWorkspace": {"id": 2}},
]
WORKSPACES = [
    {"id": 1, "windows": 2}, {"id": 2, "windows": 1}, {"id": 4, "windows": 3},
    {"id": 6, "windows": 0}, {"id": -98, "windows": 1}, {"id": 12, "windows": 1},
]


class Levels(unittest.TestCase):
    def test_two_monitors(self):
        self.assertEqual(workspaces.levels(MONITORS, WORKSPACES),
                         {1: "active", 2: "visible", 4: "occupied"})

    def test_empty_visible_workspace_still_shows(self):
        mons = [{"focused": True, "activeWorkspace": {"id": 7}}]
        self.assertEqual(workspaces.levels(mons, []), {7: "active"})

    def test_special_and_out_of_range_ignored(self):
        mons = [{"focused": True, "activeWorkspace": {"id": -98}}]
        self.assertEqual(workspaces.levels(mons, [{"id": 11, "windows": 1}]), {})


class Colours(unittest.TestCase):
    def setUp(self):
        self.base = [(9, 9, 9)] * len(layout.LEDS)
        self.idx = {n: i for i, n in enumerate(layout.LEDS)}

    PALETTE = {"accent": (10, 20, 250), "magenta": (200, 0, 200), "green": (0, 200, 0),
               "foreground": (180, 180, 190)}

    def test_every_key_lit_and_coloured_by_state(self):
        out = rgb.apply_workspace_keys(self.base, {1: "active", 2: "visible", 10: "occupied"}, self.PALETTE)
        self.assertEqual(out[self.idx["1"]], (255, 255, 255))  # active: white
        self.assertEqual(out[self.idx["2"]], (255, 0, 200))    # visible: magenta
        self.assertEqual(out[self.idx["0"]], (0, 255, 64))     # workspace 10 occupied: green
        self.assertEqual(out[self.idx["5"]], (0, 48, 255))     # empty: deep blue, still lit
        self.assertEqual(out[self.idx["Q"]], (9, 9, 9))        # other keys untouched

    def test_theme_names_still_work(self):
        out = rgb.apply_workspace_keys(self.base, {1: "active"}, self.PALETTE,
                                       scheme={"active": "accent", "empty": "foreground"})
        self.assertEqual(out[self.idx["1"]], (10, 20, 250))
        self.assertEqual(out[self.idx["5"]], (180, 180, 190))

    def test_custom_scheme_accepts_hex_and_theme_names(self):
        out = rgb.apply_workspace_keys(self.base, {3: "active"}, self.PALETTE,
                                       scheme={"active": "#FF0000", "empty": "green"})
        self.assertEqual(out[self.idx["3"]], (255, 0, 0))
        self.assertEqual(out[self.idx["4"]], (0, 200, 0))

    def test_unknown_name_falls_back_to_foreground(self):
        out = rgb.apply_workspace_keys(self.base, {}, self.PALETTE, scheme={"empty": "nope"})
        self.assertEqual(out[self.idx["7"]], (180, 180, 190))

    def test_respects_brightness(self):
        out = rgb.apply_workspace_keys(self.base, {3: "active"}, {}, brightness=50,
                                       scheme={"active": "#C8C8C8"})
        self.assertEqual(out[self.idx["3"]], (100, 100, 100))

    def test_theme_palette_exposes_named_colours(self):
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".toml")
        with os.fdopen(fd, "w") as fh:
            fh.write('accent = "#7aa2f7"\nmagenta = "#ad8ee6"\nbright_cyan = "#0db9d7"\nmode = "dark"\n')
        pal = rgb.load_palette(path)
        self.assertEqual(pal["magenta"], (0xAD, 0x8E, 0xE6))
        self.assertEqual(pal["bright_cyan"], (0x0D, 0xB9, 0xD7))
        self.assertNotIn("mode", pal)


class Events(unittest.TestCase):
    def tracker(self):
        t = workspaces.Tracker.__new__(workspaces.Tracker)
        t.sock, peer = socket.socketpair()
        t.sock.setblocking(False)
        t.buf, t.dirty, t.state = b"", False, {}
        t.last_refresh = t.last_connect = 0.0
        t.active_address, t.focus_changed = None, False
        t.screensavers = set()
        return t, peer

    def test_focus_change_by_address_not_title(self):
        t, peer = self.tracker()
        peer.sendall(b"activewindowv2>>55b6\nwindowtitlev2>>55b6,spinner 1\nactivewindowv2>>55b6\n")
        t.on_readable()
        self.assertTrue(t.focus_changed)
        t.focus_changed = False
        peer.sendall(b"windowtitlev2>>55b6,spinner 2\nactivewindowv2>>55b6\n")  # same window
        t.on_readable()
        self.assertFalse(t.focus_changed)
        peer.sendall(b"activewindowv2>>9a10\n")  # a different window
        t.on_readable()
        self.assertTrue(t.focus_changed)

    def test_title_spam_is_ignored(self):
        t, peer = self.tracker()
        peer.sendall(b"windowtitle>>55b6\nactivewindow>>x,y\nactivewindowv2>>55b6\n")
        t.on_readable()
        self.assertFalse(t.dirty)

    def test_workspace_event_marks_dirty(self):
        t, peer = self.tracker()
        peer.sendall(b"windowtitle>>55b6\nworkspacev2>>3,3\n")
        t.on_readable()
        self.assertTrue(t.dirty)

    def test_partial_lines_are_buffered(self):
        t, peer = self.tracker()
        peer.sendall(b"workspa")
        t.on_readable()
        self.assertFalse(t.dirty)
        peer.sendall(b"cev2>>3,3\n")
        t.on_readable()
        self.assertTrue(t.dirty)

    def test_closed_socket_disconnects(self):
        t, peer = self.tracker()
        peer.close()
        t.on_readable()
        self.assertIsNone(t.sock)


if __name__ == "__main__":
    unittest.main()
