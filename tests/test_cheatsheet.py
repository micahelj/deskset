"""Keybinding cheat sheet: parsing, grouping, colours, browsing, page."""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))

from apex import cheatsheet as cs, layout, render  # noqa: E402

SAMPLE = """\
SUPER + RETURN                      → Terminal
SUPER + W                           → Close window
SUPER + 1                           → Switch to workspace 1
SUPER + MINUS                       → Expand window left
SUPER + SPACE                       → Omarchy menu
SUPER SHIFT + 1                     → Move window to workspace 1
SUPER SHIFT + RETURN                → Browser
PRINT                               → Screenshot
SUPER + mouse_down                  → Scroll active workspace forward
XF86AudioMute                       → Mute
"""
IDX = {n: i for i, n in enumerate(layout.LEDS)}


class Parsing(unittest.TestCase):
    def test_parse_maps_keys_and_skips_mouse_and_media(self):
        parsed = cs.parse(SAMPLE)
        self.assertIn((("SUPER",), "Enter", "Terminal"), parsed)
        self.assertIn((("SUPER",), "-", "Expand window left"), parsed)
        self.assertIn(((), "Print Screen", "Screenshot"), parsed)
        self.assertEqual(len(parsed), 8)  # mouse_down and XF86AudioMute dropped

    def test_keys_the_keyboard_lacks_are_skipped(self):
        parsed = cs.parse(SAMPLE, absent=("Print Screen",))
        self.assertNotIn("Print Screen", [led for _m, led, _d in parsed])
        self.assertEqual(len(parsed), 7)

    def test_gen3_profile_lacks_the_print_screen_cluster(self):
        from apex import devices
        gen3 = next(p for p in devices.PROFILES if p.product == 0x1642)
        self.assertEqual(set(gen3.absent), {"Print Screen", "Scroll Lock", "Pause/Break"})

    def test_super_set_comes_first(self):
        sets = cs.groups(cs.parse(SAMPLE))
        self.assertEqual(sets[0][0], ("SUPER",))
        self.assertEqual(sets[1][0], ("SUPER", "SHIFT"))

    def test_browse_order_is_physical(self):
        _mods, entries = cs.groups(cs.parse(SAMPLE))[0]
        self.assertEqual([led for led, _ in entries], ["1", "-", "W", "Enter", "Space"])

    def test_categories(self):
        self.assertEqual(cs.category("Switch to workspace 3"), "workspace")
        self.assertEqual(cs.category("Close window"), "window")
        self.assertEqual(cs.category("Omarchy menu"), "system")
        self.assertEqual(cs.category("Terminal"), "apps")


class Browsing(unittest.TestCase):
    def sheet(self):
        s = cs.CheatSheet(loader=lambda: cs.groups(cs.parse(SAMPLE)))
        self.assertTrue(s.open())
        return s

    def test_colours_light_bound_keys_and_modifier_only(self):
        colors = self.sheet().colors(t=0.0)
        self.assertEqual(colors[IDX["W"]], cs.CATEGORY_COLORS["window"])
        self.assertEqual(colors[IDX["1"]], cs.CATEGORY_COLORS["workspace"])
        self.assertEqual(colors[IDX["Left Windows"]], cs.MODIFIER_COLOR)
        self.assertEqual(colors[IDX["Q"]], (0, 0, 0))

    def test_wheel_steps_and_wraps(self):
        s = self.sheet()
        s.step(1)
        first = s.selected()
        for _ in range(len(s.current()[1])):
            s.step(1)
        self.assertEqual(s.selected(), first)
        s.step(-1)
        self.assertNotEqual(s.selected(), first)

    def test_selected_key_pulses_white(self):
        s = self.sheet()
        s.step(1)
        led = s.selected()[0]
        r, g, b = s.colors(t=0.125)[IDX[led]]  # sine peak at 2 Hz
        self.assertEqual(r, g)
        self.assertEqual(g, b)
        self.assertGreater(r, 200)

    def test_click_moves_to_next_set(self):
        s = self.sheet()
        s.step(1)
        s.next_set()
        self.assertEqual(s.current()[0], ("SUPER", "SHIFT"))
        self.assertIsNone(s.selected())

    def test_idle_close(self):
        s = self.sheet()
        self.assertFalse(s.expired())
        self.assertTrue(s.expired(now=time.monotonic() + cs.IDLE_CLOSE + 1))

    def test_no_bindings_does_not_open(self):
        self.assertFalse(cs.CheatSheet(loader=lambda: []).open())

    def test_page_renders(self):
        s = self.sheet()
        for _ in range(2):
            im = render.render("cheatsheet", {"cheatsheet": s.oled_state()})
            self.assertEqual(im.size, (128, 40))
            self.assertTrue(any(im.getdata()))
            s.step(1)


class HeldSuper(unittest.TestCase):
    def peek(self):
        self.loads = 0

        def loader():
            self.loads += 1
            return cs.groups(cs.parse(SAMPLE))
        return cs.Peek(loader=loader)

    def test_shows_only_after_the_delay(self):
        p = self.peek()
        p.key("SUPER", True, now=100.0)
        self.assertFalse(p.visible(now=100.1))
        self.assertTrue(p.visible(now=100.0 + cs.PEEK_DELAY))
        p.key("SUPER", False)
        self.assertFalse(p.visible(now=101.0))

    def test_held_modifiers_pick_the_set(self):
        p = self.peek()
        p.key("SUPER", True)
        colors = p.colors()
        self.assertEqual(colors[IDX["W"]], cs.CATEGORY_COLORS["window"])
        self.assertEqual(colors[IDX["Left Windows"]], cs.MODIFIER_COLOR)
        p.key("SHIFT", True)
        colors = p.colors()
        self.assertEqual(colors[IDX["W"]], (0, 0, 0))
        self.assertEqual(colors[IDX["1"]], cs.CATEGORY_COLORS["workspace"])
        self.assertEqual(colors[IDX["Left Shift"]], cs.MODIFIER_COLOR)
        p.key("SHIFT", False)
        self.assertEqual(p.mods(), ("SUPER",))

    def test_releasing_super_forgets_the_other_modifiers(self):
        p = self.peek()
        p.key("SUPER", True)
        p.key("SHIFT", True)
        p.key("SUPER", False)
        p.key("SUPER", True)
        self.assertEqual(p.mods(), ("SUPER",))

    def test_other_modifiers_alone_do_nothing(self):
        p = self.peek()
        p.key("SHIFT", True, now=100.0)
        self.assertFalse(p.visible(now=105.0))

    def test_a_missed_release_times_out(self):
        p = self.peek()
        p.key("SUPER", True, now=100.0)
        self.assertFalse(p.visible(now=100.0 + cs.PEEK_MAX))
        self.assertEqual(p.mods(), ())

    def test_bindings_are_cached_between_presses(self):
        p = self.peek()
        p.key("SUPER", True, now=100.0)
        p.key("SUPER", True, now=100.5)  # key repeat
        p.key("SUPER", False)
        p.key("SUPER", True, now=110.0)
        self.assertEqual(self.loads, 1)
        p.key("SUPER", False)
        p.key("SUPER", True, now=100.0 + cs.PEEK_RELOAD + 1)
        self.assertEqual(self.loads, 2)

    def test_page_shows_the_legend(self):
        p = self.peek()
        p.key("SUPER", True)
        state = p.oled_state()
        self.assertEqual((state["label"], state["position"]), ("Super", "5 keys"))
        im = render.render("cheatsheet", {"cheatsheet": state})
        self.assertTrue(any(im.getdata()))


if __name__ == "__main__":
    unittest.main()
