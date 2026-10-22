"""App wheel: rule order, shortcuts, per-app volume, feedback."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))

from apex import wheelapp  # noqa: E402

NO_CLAUDE = staticmethod(lambda pid: False)
STREAMS = [
    {"index": 41, "pid": 900, "volume": 60, "mute": False, "name": "Discord", "binary": "Discord"},
    {"index": 42, "pid": 0, "volume": 30, "mute": False, "name": "Spotify", "binary": "spotify"},
]


class Rules(unittest.TestCase):
    def setUp(self):
        self._desc = wheelapp.descendants
        wheelapp.descendants = lambda pid, depth=5: {pid, pid + 1}

    def tearDown(self):
        wheelapp.descendants = self._desc

    def test_claude_window_always_gets_system_volume(self):
        # Even a browser-classed window falls back to volume if it runs claude.
        kind, _ = wheelapp.classify("chromium", 123, STREAMS, runs_claude=lambda pid: True)
        self.assertEqual(kind, "volume")

    def test_browser_playing_media_gets_its_own_volume(self):
        streams = [{"index": 7, "pid": 51, "volume": 80, "mute": False, "corked": False,
                    "name": "Chromium", "binary": "chromium"}]
        self.assertEqual(wheelapp.classify("chromium", 50, streams, NO_CLAUDE), ("app-volume", "Chromium volume"))

    def test_paused_browser_media_goes_back_to_tabs(self):
        streams = [{"index": 7, "pid": 51, "volume": 80, "mute": False, "corked": True,
                    "name": "Chromium", "binary": "chromium"}]
        self.assertEqual(wheelapp.classify("chromium", 50, streams, NO_CLAUDE), ("tabs", "Tabs"))

    def test_browser_and_terminal(self):
        self.assertEqual(wheelapp.classify("chromium", 5, [], NO_CLAUDE), ("tabs", "Tabs"))
        self.assertEqual(wheelapp.classify("com.mitchellh.ghostty", 5, [], NO_CLAUDE), ("zoom", "Font size"))

    def test_app_playing_sound_gets_its_own_volume(self):
        # Discord's audio comes from a child process of the window (pid 899 -> 900).
        self.assertEqual(wheelapp.classify("discord", 899, STREAMS, NO_CLAUDE), ("app-volume", "Discord volume"))

    def test_match_by_name_when_pid_unknown(self):
        self.assertEqual(wheelapp.classify("spotify", 7, STREAMS, NO_CLAUDE), ("app-volume", "Spotify volume"))

    def test_fallback_is_system_volume(self):
        self.assertEqual(wheelapp.classify("org.gnome.Calculator", 7, STREAMS, NO_CLAUDE), ("volume", "Volume"))


class Actions(unittest.TestCase):
    def setUp(self):
        self.hypr_calls, self.run_calls, self.toasts = [], [], []
        self._hypr, self._run_fn = wheelapp.hypr._hypr, wheelapp._run
        self._streams, self._sleep = wheelapp.playback_streams, wheelapp.time.sleep
        wheelapp.time.sleep = lambda s: None
        self.hypr_reply = "ok"

        def fake_hypr(*args, **kw):
            self.hypr_calls.append(args)
            if args[:2] == ("activewindow", "-j"):
                return '{"class": "%s", "pid": %d}' % self.focused
            return self.hypr_reply
        wheelapp.hypr._hypr = fake_hypr
        wheelapp._run = lambda argv, timeout=2: self.run_calls.append(argv) or ""
        wheelapp.playback_streams = lambda: [dict(s) for s in STREAMS]
        self.wheel = wheelapp.AppWheel.__new__(wheelapp.AppWheel)
        self.wheel.toast = lambda t, s="": self.toasts.append((t, s))
        self.wheel.last_kind = None

    def tearDown(self):
        wheelapp.hypr._hypr, wheelapp._run = self._hypr, self._run_fn
        wheelapp.playback_streams, wheelapp.time.sleep = self._streams, self._sleep

    def dispatches(self):
        return [c[1] for c in self.hypr_calls if c[0] == "dispatch"]

    def test_browser_scroll_sends_ctrl_tab_down_and_up(self):
        self.focused = ("chromium", 0)
        self.wheel._act(steps=1)
        sent = self.dispatches()
        self.assertEqual(len(sent), 2)
        self.assertIn('mods = "CTRL", key = "Tab", state = "down"', sent[0])
        self.assertIn('state = "up"', sent[1])
        self.assertEqual(self.toasts[-1], ("Tabs", "Next tab →"))

    def test_falls_back_to_classic_sendshortcut(self):
        self.focused = ("chromium", 0)
        self.hypr_reply = "error: unknown"
        self.wheel._act(steps=-1)
        self.assertIn(("dispatch", "sendshortcut", "CTRL SHIFT, Tab, activewindow"), self.hypr_calls)

    def test_terminal_click_resets_font(self):
        self.focused = ("com.mitchellh.ghostty", 0)
        self.wheel._act(click=True)
        self.assertIn('mods = "CTRL", key = "0"', self.dispatches()[0])

    def test_app_volume_is_clamped_and_set(self):
        self.focused = ("spotify", 0)
        self.wheel._act(steps=30)  # 30% + 150% clamps to 100%
        self.assertIn(["pactl", "set-sink-input-volume", "42", "100%"], self.run_calls)
        self.assertEqual(self.toasts[-1], ("Spotify", "100%"))

    def test_app_click_mutes_only_that_app(self):
        self.focused = ("spotify", 0)
        self.wheel._act(click=True)
        self.assertIn(["pactl", "set-sink-input-mute", "42", "toggle"], self.run_calls)

    def test_claude_window_never_sends_shortcuts(self):
        self.focused = ("org.omarchy.agent", 4242)
        orig = wheelapp.claude.window_runs_claude
        wheelapp.claude.window_runs_claude = lambda pid: True
        try:
            self.wheel._act(steps=2)
        finally:
            wheelapp.claude.window_runs_claude = orig
        self.assertEqual(self.dispatches(), [])
        self.assertIn(["omarchy", "audio", "output", "volume", "raise"], self.run_calls)

    def test_focus_toast_only_when_the_mapping_changes(self):
        jobs = []
        self.wheel.jobs = type("Q", (), {"put": lambda _self, job: jobs.append(job)})()
        self.focused = ("chromium", 0)
        self.wheel.focus_changed(); jobs.pop()()
        self.wheel.focus_changed(); jobs.pop()()   # another browser window: same mapping
        self.focused = ("com.mitchellh.ghostty", 0)
        self.wheel.focus_changed(); jobs.pop()()
        self.assertEqual(self.toasts, [("Wheel", "Tabs"), ("Wheel", "Font size")])


if __name__ == "__main__":
    unittest.main()
