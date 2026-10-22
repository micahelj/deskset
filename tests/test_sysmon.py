"""System monitor: sensor choice, /proc parsing, CPU %, page rendering."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))

from apex import render, sysmon  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def hwmon(root, n, name, sensors):
    d = os.path.join(root, f"hwmon{n}")
    write(os.path.join(d, "name"), name + "\n")
    for i, (label, millideg) in enumerate(sensors, 1):
        write(os.path.join(d, f"temp{i}_input"), f"{millideg}\n")
        if label:
            write(os.path.join(d, f"temp{i}_label"), label + "\n")
    return d


class Sensors(unittest.TestCase):
    def test_prefers_intel_package_over_acpi(self):
        root = tempfile.mkdtemp()
        hwmon(root, 0, "acpitz", [(None, 27000)])
        d = hwmon(root, 1, "coretemp", [("Core 0", 50000), ("Package id 0", 56000)])
        self.assertEqual(sysmon.find_temp_input(root), os.path.join(d, "temp2_input"))

    def test_amd_tctl(self):
        root = tempfile.mkdtemp()
        d = hwmon(root, 0, "k10temp", [("Tctl", 61000), ("Tccd1", 55000)])
        self.assertEqual(sysmon.find_temp_input(root), os.path.join(d, "temp1_input"))

    def test_no_sensor(self):
        root = tempfile.mkdtemp()
        hwmon(root, 0, "nvme", [("Composite", 33000)])
        self.assertIsNone(sysmon.find_temp_input(root))


class Proc(unittest.TestCase):
    def test_cpu_times(self):
        path = os.path.join(tempfile.mkdtemp(), "stat")
        write(path, "cpu  100 0 50 800 50 0 0 0 0 0\ncpu0 1 2 3 4\n")
        self.assertEqual(sysmon.read_cpu_times(path), (150, 1000))

    def test_memory_counts_available_as_free(self):
        path = os.path.join(tempfile.mkdtemp(), "meminfo")
        write(path, "MemTotal:       1000 kB\nMemFree:         100 kB\nMemAvailable:    750 kB\n")
        self.assertAlmostEqual(sysmon.read_memory(path), 0.25)

    def test_cpu_percent_from_two_samples(self):
        d = tempfile.mkdtemp()
        stat = os.path.join(d, "stat")
        orig = sysmon.read_cpu_times
        try:
            write(stat, "cpu  100 0 0 900 0 0 0 0\n")
            sysmon.read_cpu_times = lambda path=stat: orig(stat)
            m = sysmon.Monitor(temp_path="/nonexistent")
            m.sample()
            self.assertEqual(m.cpu, sysmon.deque([], maxlen=sysmon.HISTORY))  # needs a delta first
            write(stat, "cpu  400 0 0 1600 0 0 0 0\n")  # +300 busy of +1000
            m.sample()
            self.assertAlmostEqual(m.cpu[-1], 0.3)
        finally:
            sysmon.read_cpu_times = orig


class Page(unittest.TestCase):
    def test_renders_with_and_without_data(self):
        full = {"cpu": [0.1, 0.9] * 50, "mem": [0.4] * 100, "temp": [45.0, 95.0] * 50}
        for stats in (full, {}):
            im = render.render("system", {"system": stats})
            self.assertEqual(im.size, (128, 40))
            self.assertTrue(any(im.getdata()))

    def test_sparkline_clamps_and_keeps_baseline(self):
        im = render.blank()
        from PIL import ImageDraw
        render._sparkline(ImageDraw.Draw(im), [-5.0, 0.0, 2.0], 0, 0, 10, 10)
        px = im.load()
        self.assertTrue(all(px[x, 9] for x in range(10)))  # baseline
        self.assertTrue(px[9, 0])                          # 2.0 clamps to full height
        self.assertFalse(px[7, 5])                         # -5 clamps to empty


if __name__ == "__main__":
    unittest.main()
