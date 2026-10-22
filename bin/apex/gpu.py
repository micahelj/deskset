"""NVIDIA GPU load, video memory and temperature for the OLED.

`nvidia-smi` takes ~35 ms, so it runs on a background thread instead of the
daemon's frame loop. Polling a laptop GPU every second keeps it from runtime-
suspending, so this only polls while a GPU reading is on screen (`want()`),
and never queries a GPU that is already suspended: it reports "asleep".
"""

from __future__ import annotations

import glob
import os
import subprocess
import threading
import time
from collections import deque

from .sysmon import HISTORY

NVIDIA_VENDOR = "0x10de"
QUERY = ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
         "--format=csv,noheader,nounits"]
WANT_SECONDS = 3.0  # keep polling this long after the page was last shown


def find_nvidia(root="/sys/bus/pci/devices"):
    """sysfs path of the first NVIDIA display controller, or None."""
    for dev in sorted(glob.glob(os.path.join(root, "*"))):
        try:
            with open(os.path.join(dev, "vendor"), encoding="utf-8") as fh:
                vendor = fh.read().strip()
            with open(os.path.join(dev, "class"), encoding="utf-8") as fh:
                klass = fh.read().strip()
        except OSError:
            continue
        if vendor == NVIDIA_VENDOR and klass.startswith("0x03"):
            return dev
    return None


def suspended(dev):
    try:
        with open(os.path.join(dev, "power", "runtime_status"), encoding="utf-8") as fh:
            return fh.read().strip() == "suspended"
    except OSError:
        return False


def parse(line):
    """'NAME, util, mem used, mem total, temp' -> dict, or None."""
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 5:
        return None
    try:
        util, used, total, temp = (float(p) for p in parts[1:5])
    except ValueError:
        return None
    return {"name": parts[0], "util": util / 100.0, "vram": used / total if total else 0.0, "temp": temp}


AUTO = object()  # detect the GPU; pass dev=None for "no GPU"


class GpuMonitor:
    def __init__(self, dev=AUTO):
        self.dev = find_nvidia() if dev is AUTO else dev
        self.present = self.dev is not None
        self.name = ""
        self.asleep = False
        self.util = deque(maxlen=HISTORY)
        self.vram = deque(maxlen=HISTORY)
        self.temp = deque(maxlen=HISTORY)
        self.wanted_until = 0.0
        self.lock = threading.Lock()
        self.thread = None

    def want(self):
        """Ask for fresh samples for the next few seconds (starts the poller lazily)."""
        if not self.present:
            return
        self.wanted_until = time.monotonic() + WANT_SECONDS
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name="apex-gpu", daemon=True)
            self.thread.start()

    def _run(self):
        while True:
            if time.monotonic() < self.wanted_until:
                self.poll()
            time.sleep(1.0)

    def poll(self):
        if suspended(self.dev):
            with self.lock:
                self.asleep = True
            return
        try:
            out = subprocess.run(QUERY, capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            return
        sample = parse(out.splitlines()[0]) if out.strip() else None
        if sample is None:
            return
        with self.lock:
            self.asleep = False
            self.name = sample["name"]
            self.util.append(sample["util"])
            self.vram.append(sample["vram"])
            self.temp.append(sample["temp"])

    def snapshot(self):
        with self.lock:
            return {
                "present": self.present,
                "asleep": self.asleep,
                "name": self.name,
                "util": list(self.util),
                "vram": list(self.vram),
                "temp": list(self.temp),
            }
