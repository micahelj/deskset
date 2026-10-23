"""A chosen OLED page announces itself and beats the auto Claude page for a while."""

import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))

from apex import daemon  # noqa: E402


def fake(page="clock"):
    d = types.SimpleNamespace(
        cfg={"oled": {"page": page, "pages": ["clock", "system"], "claude_auto": True}},
        toast_state=None,
        page_pin_until=0.0,
        _claude_summary=lambda: {"state": "working", "count": 1},
        _claude_focused=lambda: True,
    )
    d._page_changed = lambda: daemon.Daemon._page_changed(d)
    return d


class PagePin(unittest.TestCase):
    def test_busy_claude_takes_over_normally(self):
        d = fake()
        self.assertEqual(daemon.Daemon._effective_page(d)[0], "claude")

    def test_chosen_page_is_announced_then_pinned(self):
        d = fake()
        with mock.patch.object(daemon.time, "monotonic", return_value=100.0):
            daemon.Daemon._cycle_oled(d, 1)
            self.assertEqual(d.cfg["oled"]["page"], "system")
            self.assertEqual(d.toast_state[1:], ("System", "OLED page"))
            self.assertEqual(daemon.Daemon._effective_page(d)[0], "system")
        with mock.patch.object(daemon.time, "monotonic", return_value=100.0 + daemon.PAGE_PIN_SECONDS + 0.1):
            self.assertEqual(daemon.Daemon._effective_page(d)[0], "claude")

    def test_titles(self):
        d = fake("now-playing")
        daemon.Daemon._page_changed(d)
        self.assertEqual(d.toast_state[1], "Now playing")


if __name__ == "__main__":
    unittest.main()
