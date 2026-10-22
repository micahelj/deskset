"""Whether the user is away: the Omarchy lock screen is up.

The lock screen is a Wayland session lock, not a window, so Hyprland's event
socket never mentions it; ask the Omarchy shell instead. The query takes
~35 ms, so it runs on a background thread every couple of seconds. (The idle
screensaver *is* a window and is tracked from Hyprland events in
workspaces.Tracker.)
"""

from __future__ import annotations

import subprocess
import threading
import time

LOCK_QUERY = ["omarchy-shell", "lock", "isLocked"]
INTERVAL = 2.0


def query_locked(command=LOCK_QUERY):
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return out.strip() == "true"


class LockWatch:
    def __init__(self, query=query_locked, interval=INTERVAL):
        self.query = query
        self.interval = interval
        self.locked = False
        threading.Thread(target=self._run, name="apex-lock", daemon=True).start()

    def _run(self):
        while True:
            self.locked = self.query()
            time.sleep(self.interval)
