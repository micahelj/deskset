"""GPU monitor: device discovery, power-safe polling, parsing, page states."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))

from apex import gpu, render  # noqa: E402


def pci(root, addr, vendor, klass, runtime="active"):
    d = os.path.join(root, addr)
    os.makedirs(os.path.join(d, "power"))
    for name, value in (("vendor", vendor), ("class", klass), ("power/runtime_status", runtime)):
        with open(os.path.join(d, name), "w") as fh:
            fh.write(value + "\n")
    return d


class Discovery(unittest.TestCase):
    def test_finds_nvidia_display_controller_only(self):
        root = tempfile.mkdtemp()
        pci(root, "0000:00:02.0", "0x8086", "0x030000")         # Intel iGPU
        pci(root, "0000:02:00.1", "0x10de", "0x040300")         # NVIDIA HDMI audio
        d = pci(root, "0000:02:00.0", "0x10de", "0x030000")     # NVIDIA GPU
        self.assertEqual(gpu.find_nvidia(root), d)

    def test_no_nvidia(self):
        root = tempfile.mkdtemp()
        pci(root, "0000:00:02.0", "0x8086", "0x030000")
        self.assertIsNone(gpu.find_nvidia(root))
        mon = gpu.GpuMonitor(dev=None)
        self.assertFalse(mon.present)
        mon.want()  # must not start a poller without a GPU
        self.assertIsNone(mon.thread)


class Polling(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self._orig = gpu.subprocess.run

        class Out:
            stdout = "NVIDIA GeForce RTX 5080 Laptop GPU, 37, 4076, 16303, 61\n"

        def fake_run(*args, **kwargs):
            self.calls.append(args)
            return Out()
        gpu.subprocess.run = fake_run

    def tearDown(self):
        gpu.subprocess.run = self._orig

    def test_suspended_gpu_is_never_queried(self):
        d = pci(tempfile.mkdtemp(), "0000:02:00.0", "0x10de", "0x030000", runtime="suspended")
        mon = gpu.GpuMonitor(dev=d)
        mon.poll()
        self.assertEqual(self.calls, [])
        self.assertTrue(mon.snapshot()["asleep"])

    def test_active_gpu_is_sampled(self):
        d = pci(tempfile.mkdtemp(), "0000:02:00.0", "0x10de", "0x030000")
        mon = gpu.GpuMonitor(dev=d)
        mon.poll()
        snap = mon.snapshot()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(snap["asleep"])
        self.assertAlmostEqual(snap["util"][-1], 0.37)
        self.assertAlmostEqual(snap["vram"][-1], 4076 / 16303)
        self.assertEqual(snap["temp"][-1], 61.0)

    def test_parse_rejects_garbage(self):
        self.assertIsNone(gpu.parse("NVIDIA, [N/A], 1, 2, 3"))
        self.assertIsNone(gpu.parse(""))


class Page(unittest.TestCase):
    def test_states_render(self):
        for stats in ({"present": False},
                      {"present": True, "asleep": True, "name": "RTX"},
                      {"present": True, "util": [0.2, 0.9], "vram": [0.25], "temp": [61.0]}):
            im = render.render("gpu", {"gpu": stats, "t": 0})
            self.assertEqual(im.size, (128, 40))
            self.assertTrue(any(im.getdata()))


if __name__ == "__main__":
    unittest.main()
