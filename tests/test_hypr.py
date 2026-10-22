"""Hyprland dispatch: Lua form first (0.56+), classic form as fallback."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))

from apex import hypr  # noqa: E402


class Dispatch(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.replies = []
        self._orig = hypr._hypr
        hypr._hypr = lambda *args, **_kw: (self.calls.append(args), self.replies.pop(0))[1]

    def tearDown(self):
        hypr._hypr = self._orig

    def test_lua_focus_succeeds(self):
        self.replies = ["ok\n"]
        hypr.focus_workspace("e+1")
        self.assertEqual(self.calls, [("dispatch", 'hl.dsp.focus({ workspace = "e+1" })')])

    def test_falls_back_to_classic_dispatcher(self):
        self.replies = ["Invalid dispatcher\n", "ok\n"]
        hypr.focus_workspace("e-1")
        self.assertEqual(self.calls[1], ("dispatch", "workspace", "e-1"))

    def test_toggle_special(self):
        self.replies = ["ok\n"]
        hypr.toggle_special("scratchpad")
        self.assertEqual(self.calls, [("dispatch", 'hl.dsp.workspace.toggle_special("scratchpad")')])


if __name__ == "__main__":
    unittest.main()
