"""Editing the panel's Favorites tab."""

import os
import sys
import unittest
from copy import deepcopy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))

from apex import config  # noqa: E402


class Favorites(unittest.TestCase):
    def cfg(self):
        return deepcopy(config.DEFAULT)

    def test_edit_normalises(self):
        cfg = self.cfg()
        fav = config.set_favorites(cfg, {
            "sections": ["wheel", "lighting", "wheel"],
            "colors": ["#ff0000", "theme", "#FF0000"],
            "dpi": [3200, 800, 800],
            "oled": ["claude"],
        })
        self.assertEqual(fav["sections"], ["lighting", "wheel"])  # canonical order, no repeats
        self.assertEqual(fav["colors"], ["#FF0000", "theme"])
        self.assertEqual(fav["dpi"], [800, 3200])
        self.assertEqual(fav["oled"], ["claude"])
        self.assertEqual(fav["wheel"], config.DEFAULT["favorites"]["wheel"])  # untouched

    def test_rejects_bad_values_without_changing_anything(self):
        cfg = self.cfg()
        for req in ({"colors": ["#12345"]}, {"oled": ["tetris"]}, {"sections": ["bogus"]}, {"dpi": [10]},
                    {"oled": ["gpu"], "wheel": ["nope"]}):
            with self.assertRaises(ValueError):
                config.set_favorites(cfg, req)
        self.assertEqual(cfg["favorites"], config.DEFAULT["favorites"])

    def test_reset(self):
        cfg = self.cfg()
        config.set_favorites(cfg, {"oled": ["gpu"]})
        config.set_favorites(cfg, {"reset": True})
        self.assertEqual(cfg["favorites"], config.DEFAULT["favorites"])


if __name__ == "__main__":
    unittest.main()
