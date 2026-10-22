"""CPU, memory and CPU temperature with a short history for the OLED.

Sampled once a second by the daemon from /proc and hwmon; nothing to install.
"""

from __future__ import annotations

import glob
import os
from collections import deque

HISTORY = 72  # samples, one per second: the sparkline width on the OLED

# (hwmon name, label prefix) in order of preference; label None = temp1.
TEMP_SOURCES = (
    ("coretemp", "Package id"),   # Intel
    ("k10temp", "Tctl"),          # AMD
    ("k10temp", "Tdie"),
    ("zenpower", "Tdie"),
    ("cpu_thermal", None),        # many ARM boards
    ("acpitz", None),             # generic fallback
)


def find_temp_input(root="/sys/class/hwmon"):
    """Path of the best CPU temperature input, or None."""
    found = {}
    for hw in sorted(glob.glob(os.path.join(root, "hwmon*"))):
        try:
            with open(os.path.join(hw, "name"), encoding="utf-8") as fh:
                name = fh.read().strip()
        except OSError:
            continue
        for path in sorted(glob.glob(os.path.join(hw, "temp*_input"))):
            try:
                with open(path.replace("_input", "_label"), encoding="utf-8") as fh:
                    label = fh.read().strip()
            except OSError:
                label = None
            found.setdefault(name, []).append((label, path))
    for name, prefix in TEMP_SOURCES:
        for label, path in found.get(name, []):
            if prefix is None or (label or "").startswith(prefix):
                return path
    return None


def read_cpu_times(path="/proc/stat"):
    """(busy, total) jiffies for all CPUs."""
    with open(path, encoding="utf-8") as fh:
        fields = [int(v) for v in fh.readline().split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)  # idle + iowait
    total = sum(fields[:8])  # guest time is already counted in user/nice
    return total - idle, total


def read_memory(path="/proc/meminfo"):
    """Fraction of memory in use (0..1), counting reclaimable cache as free."""
    info = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0])
    total = info.get("MemTotal", 0)
    return 1.0 - info.get("MemAvailable", total) / total if total else 0.0


def read_temp(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return int(fh.read().strip()) / 1000.0
    except (OSError, ValueError, TypeError):
        return None


class Monitor:
    def __init__(self, temp_path=None):
        self.temp_path = temp_path or find_temp_input()
        self.cpu = deque(maxlen=HISTORY)
        self.mem = deque(maxlen=HISTORY)
        self.temp = deque(maxlen=HISTORY)
        self._prev = None

    def sample(self):
        try:
            busy, total = read_cpu_times()
            if self._prev:
                dbusy, dtotal = busy - self._prev[0], total - self._prev[1]
                self.cpu.append(max(0.0, min(1.0, dbusy / dtotal)) if dtotal > 0 else 0.0)
            self._prev = (busy, total)
        except (OSError, ValueError, IndexError):
            pass
        try:
            self.mem.append(read_memory())
        except (OSError, ValueError, IndexError):
            pass
        temp = read_temp(self.temp_path) if self.temp_path else None
        if temp is not None:
            self.temp.append(temp)

    def snapshot(self):
        return {"cpu": list(self.cpu), "mem": list(self.mem), "temp": list(self.temp)}
