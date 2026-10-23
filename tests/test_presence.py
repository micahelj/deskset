"""Away detection: screensaver windows, lock state, and the daemon's verdict."""

import os
import socket
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))

from apex import daemon, presence, workspaces  # noqa: E402


class Screensaver(unittest.TestCase):
    def tracker(self):
        t = workspaces.Tracker.__new__(workspaces.Tracker)
        t.sock, peer = socket.socketpair()
        t.sock.setblocking(False)
        t.buf, t.dirty, t.state = b"", False, {}
        t.last_refresh = t.last_connect = 0.0
        t.active_address, t.focus_changed = None, False
        t.screensavers = set()
        return t, peer

    def test_open_and_close(self):
        t, peer = self.tracker()
        peer.sendall(b"openwindow>>a1,1,com.mitchellh.ghostty,shell\n"
                     b"openwindow>>b2,2,org.omarchy.screensaver,Screensaver\n")
        t.on_readable()
        self.assertEqual(t.screensavers, {"b2"})
        peer.sendall(b"closewindow>>a1\ncloseWindow>>zz\nclosewindow>>b2\n")
        t.on_readable()
        self.assertEqual(t.screensavers, set())

    def test_titles_with_commas(self):
        t, peer = self.tracker()
        peer.sendall(b"openwindow>>c3,1,org.omarchy.screensaver,tte, rain, beams\n")
        t.on_readable()
        self.assertEqual(t.screensavers, {"c3"})


class Lock(unittest.TestCase):
    def test_query(self):
        self.assertTrue(presence.query_locked(["echo", "true"]))
        self.assertFalse(presence.query_locked(["echo", "false"]))
        self.assertFalse(presence.query_locked(["/nonexistent/omarchy-shell"]))  # never dark by mistake

    def test_screen_off(self):
        off = '[{"disabled": false, "dpmsStatus": false}, {"disabled": true, "dpmsStatus": true}]'
        on = '[{"disabled": false, "dpmsStatus": false}, {"disabled": false, "dpmsStatus": true}]'
        self.assertTrue(presence.query_screen_off(["echo", off]))
        self.assertFalse(presence.query_screen_off(["echo", on]))
        self.assertFalse(presence.query_screen_off(["echo", "[]"]))
        self.assertFalse(presence.query_screen_off(["echo", "garbage"]))
        self.assertFalse(presence.query_screen_off(["/nonexistent/hyprctl"]))


class Verdict(unittest.TestCase):
    def fake(self, screensavers=(), dark=False, enabled=True):
        return types.SimpleNamespace(
            cfg={"rgb": {"away_dark": enabled}},
            workspaces=types.SimpleNamespace(screensavers=set(screensavers)),
            lockwatch=types.SimpleNamespace(dark=dark),
        )

    def test_away_states(self):
        away = daemon.Daemon._away
        self.assertFalse(away(self.fake()))
        self.assertTrue(away(self.fake(screensavers={"b2"})))
        self.assertTrue(away(self.fake(dark=True)))
        self.assertFalse(away(self.fake(dark=True, enabled=False)))

    def test_lit_on_wake(self):
        watch = presence.LockWatch.__new__(presence.LockWatch)
        watch.locked, watch.screen_off = True, False  # unlock screen showing
        self.assertFalse(watch.dark)
        watch.screen_off = True
        self.assertTrue(watch.dark)


if __name__ == "__main__":
    unittest.main()
