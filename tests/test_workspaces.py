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

    def test_strip(self):
        accent = (200, 100, 0)
        out = rgb.apply_workspace_keys(self.base, {1: "active", 2: "visible", 10: "occupied"}, accent)
        self.assertEqual(out[self.idx["1"]], accent)
        self.assertEqual(out[self.idx["2"]], rgb.scale_color(accent, 55))
        self.assertEqual(out[self.idx["0"]], rgb.scale_color(accent, 22))  # workspace 10
        self.assertEqual(out[self.idx["5"]], (0, 0, 0))                    # empty goes dark
        self.assertEqual(out[self.idx["Q"]], (9, 9, 9))                    # other keys untouched

    def test_respects_brightness(self):
        out = rgb.apply_workspace_keys(self.base, {3: "active"}, (200, 200, 200), brightness=50)
        self.assertEqual(out[self.idx["3"]], (100, 100, 100))


class Events(unittest.TestCase):
    def tracker(self):
        t = workspaces.Tracker.__new__(workspaces.Tracker)
        t.sock, peer = socket.socketpair()
        t.sock.setblocking(False)
        t.buf, t.dirty, t.state = b"", False, {}
        t.last_refresh = t.last_connect = 0.0
        return t, peer

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
