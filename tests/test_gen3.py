"""Apex Pro TKL Gen 3 packet formats (no hardware needed)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))

from PIL import Image  # noqa: E402

from apex import hidrgb, layout, oled  # noqa: E402


class OledGen3(unittest.TestCase):
    def test_header_and_length(self):
        report = oled.image_to_gen3_report(Image.new("L", (128, 40), 0))
        self.assertEqual(len(report), 644)
        self.assertEqual(report[:3], bytes([0x00, 0x1F, 0x81]))
        self.assertEqual(report[3:], bytes(641))

    def test_column_packed_lsb_first(self):
        im = Image.new("L", (128, 40), 0)
        im.putpixel((0, 0), 255)    # page 0, column 0, bit 0
        im.putpixel((5, 9), 255)    # page 1, column 5, bit 1
        im.putpixel((127, 39), 255)  # page 4, column 127, bit 7
        report = oled.image_to_gen3_report(im)
        self.assertEqual(report[3 + 0], 0x01)
        self.assertEqual(report[3 + 128 + 5], 0x02)
        self.assertEqual(report[3 + 4 * 128 + 127], 0x80)
        self.assertEqual(sum(1 for b in report[3:] if b), 3)

    def test_apex7_format_unchanged(self):
        report = oled.image_to_report(Image.new("L", (128, 40), 255))
        self.assertEqual(len(report), 642)
        self.assertEqual(report[0], 0x61)
        self.assertEqual(report[1:641], bytes([0xFF]) * 640)


class HidRgb(unittest.TestCase):
    def test_every_tkl_key_has_a_usage(self):
        missing = [name for name in layout._XY if hidrgb._NAMED.get(name) is None]
        self.assertEqual(missing, [])

    def test_usages_are_unique(self):
        used = [u for u in hidrgb.USAGES if u is not None]
        self.assertEqual(len(used), len(set(used)))

    def test_report_layout(self):
        colors = [(0, 0, 0)] * len(layout.LEDS)
        colors[layout.LEDS.index("W")] = (255, 0, 0)
        report = hidrgb.build_report(colors)
        self.assertEqual(len(report), 643)
        self.assertEqual(report[:2], bytes([0x00, 0x40]))
        count = report[2]
        self.assertEqual(count, sum(1 for u in hidrgb.USAGES if u is not None))
        entries = [report[3 + i * 4:7 + i * 4] for i in range(count)]
        self.assertIn(bytes([0x1A, 255, 0, 0]), entries)  # W is usage 0x1A


if __name__ == "__main__":
    unittest.main()
