"""Claude Code activity: hook mapping, session aggregation, usage meter, page."""

import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))

from apex import claude, render  # noqa: E402


class HookMapping(unittest.TestCase):
    def test_states(self):
        f = claude.state_for_event
        self.assertEqual(f({"hook_event_name": "UserPromptSubmit"}), ("thinking", ""))
        self.assertEqual(f({"hook_event_name": "PermissionRequest", "tool_name": "Bash"}), ("waiting", "Allow Bash?"))
        self.assertEqual(f({"hook_event_name": "Stop"}), ("done", ""))
        self.assertIsNone(f({"hook_event_name": "Notification", "notification_type": "idle_prompt"}))

    def test_detail_never_includes_command_text(self):
        event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "cat ~/.ssh/id_rsa"}}
        self.assertEqual(claude.state_for_event(event), ("working", "Bash"))

    def test_detail_uses_file_basename(self):
        event = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": "/home/x/secret/plan.md"}}
        self.assertEqual(claude.state_for_event(event), ("working", "Edit: plan.md"))

    def test_mcp_tool_names_are_shortened(self):
        self.assertEqual(claude.describe_tool("mcp__claude_ai_Gmail__search_threads", {}), "search_threads")


class Sessions(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._orig = claude.STATE_DIR
        claude.STATE_DIR = self.dir

    def tearDown(self):
        claude.STATE_DIR = self._orig

    def hook(self, session, **event):
        claude.handle_hook(json.dumps({"session_id": session, **event}), pid=os.getpid())

    def test_most_urgent_session_wins(self):
        self.hook("a", hook_event_name="UserPromptSubmit")
        self.hook("b", hook_event_name="PermissionRequest", tool_name="Edit")
        s = claude.summary(state_dir=self.dir)
        self.assertEqual((s["state"], s["detail"], s["count"], s["busy"]), ("waiting", "Allow Edit?", 2, 2))

    def test_session_end_removes_file(self):
        self.hook("a", hook_event_name="SessionStart")
        self.hook("a", hook_event_name="SessionEnd")
        self.assertEqual(claude.summary(state_dir=self.dir)["count"], 0)

    def test_dead_process_is_dropped(self):
        with open(os.path.join(self.dir, "x.json"), "w") as fh:
            json.dump({"state": "working", "detail": "", "ts": time.time(), "pid": 2 ** 22 + 7}, fh)
        self.assertEqual(claude.summary(state_dir=self.dir)["count"], 0)

    def test_done_decays_to_idle(self):
        self.hook("a", hook_event_name="Stop")
        later = time.time() + claude.DONE_SECONDS + 1
        self.assertEqual(claude.summary(now=later, state_dir=self.dir)["state"], "idle")

    def test_malformed_input_is_ignored(self):
        claude.handle_hook("not json")
        claude.handle_hook("{}")
        self.assertEqual(os.listdir(self.dir), [])


class Usage(unittest.TestCase):
    def write(self, limits):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as fh:
            json.dump({"limits": limits}, fh)
        return path

    def test_reads_five_hour_window(self):
        path = self.write([
            {"label": "Weekly (7-day)", "percent": 0.5, "resetsAt": "2099-01-01T00:00:00+00:00"},
            {"label": "Session (5-hour)", "percent": 0.19, "resetsAt": "2099-01-01T00:00:00+00:00"},
        ])
        self.assertAlmostEqual(claude.session_usage(path), 0.19)

    def test_expired_window_reads_zero(self):
        path = self.write([{"label": "Session (5-hour)", "percent": 0.8, "resetsAt": "2000-01-01T00:00:00+00:00"}])
        self.assertEqual(claude.session_usage(path, now=datetime.now(timezone.utc)), 0.0)

    def test_missing_record(self):
        self.assertIsNone(claude.session_usage("/nonexistent/claude.json"))


class EscAlert(unittest.TestCase):
    def setUp(self):
        from apex import layout, rgb
        self.layout, self.rgb = layout, rgb
        self.base = [(10, 20, 30)] * len(layout.LEDS)
        self.esc = layout.LEDS.index("Escape")

    def test_flashes_escape_only_while_waiting(self):
        on = self.rgb.apply_claude_alert(self.base, True, t=0.0)
        off = self.rgb.apply_claude_alert(self.base, True, t=0.6)
        self.assertEqual(on[self.esc], self.rgb.CLAUDE_ALERT)
        self.assertNotEqual(off[self.esc], self.rgb.CLAUDE_ALERT)
        others = [c for i, c in enumerate(on) if i != self.esc]
        self.assertEqual(others, [(10, 20, 30)] * (len(self.base) - 1))

    def test_custom_color(self):
        out = self.rgb.apply_claude_alert(self.base, True, t=0.0, color=(1, 2, 3))
        self.assertEqual(out[self.esc], (1, 2, 3))

    def test_default_is_the_chosen_orange(self):
        from apex import config
        self.assertEqual(self.rgb.parse_hex(config.DEFAULT["rgb"]["claude_esc_color"]), self.rgb.CLAUDE_ALERT)

    def test_no_change_when_not_waiting(self):
        self.assertEqual(self.rgb.apply_claude_alert(self.base, False, t=0.0), self.base)

    def test_escape_reaches_the_keyboard(self):
        from apex import hidrgb
        colors = self.rgb.apply_claude_alert(self.base, True, t=0.0)
        report = hidrgb.build_report(colors)
        entries = [report[3 + i * 4:7 + i * 4] for i in range(report[2])]
        self.assertIn(bytes([0x29, *self.rgb.CLAUDE_ALERT]), entries)  # Escape = HID 0x29


class Page(unittest.TestCase):
    def test_renders_every_state(self):
        for state in ("waiting", "working", "thinking", "done", "idle", "none"):
            im = render.claude_page({"state": state, "detail": "Edit: x.py", "count": 1, "busy": 1}, 0.4, t=1.0)
            self.assertEqual(im.size, (128, 40))
            self.assertTrue(any(im.getdata()))


if __name__ == "__main__":
    unittest.main()
