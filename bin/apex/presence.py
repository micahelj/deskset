"""Whether the user is away: the Omarchy lock screen is up with the screen off.

The lock screen is a Wayland session lock, not a window, so Hyprland's event
socket never mentions it; ask the Omarchy shell instead. The query takes
~35 ms, so it runs on a background thread every couple of seconds. While
locked, the lock screen blanks the displays (DPMS) a few seconds after the last
keypress and wakes them on the next one, so the displays' power state is
polled quickly then: the keyboard should light up with the unlock screen, not
after the password. (The idle screensaver *is* a window and is tracked from
Hyprland events in workspaces.Tracker.)
"""

from __future__ import annotations

import json
import subprocess
import threading
import time

LOCK_QUERY = ["omarchy-shell", "lock", "isLocked"]
MONITORS_QUERY = ["hyprctl", "monitors", "-j"]
INTERVAL = 2.0
LOCKED_INTERVAL = 0.4


def query_locked(command=LOCK_QUERY):
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return out.strip() == "true"


def query_screen_off(command=MONITORS_QUERY):
    """True when every enabled display is powered off (DPMS)."""
    try:
        out = subprocess.run(command, capture_output=True, text=True, timeout=3).stdout
        monitors = [m for m in json.loads(out) if not m.get("disabled")]
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        return False
    return bool(monitors) and not any(m.get("dpmsStatus", True) for m in monitors)


class LockWatch:
    def __init__(self, query=query_locked, screen_query=query_screen_off, interval=INTERVAL,
                 locked_interval=LOCKED_INTERVAL):
        self.query = query
        self.screen_query = screen_query
        self.interval = interval
        self.locked_interval = locked_interval
        self.locked = False
        self.screen_off = False
        threading.Thread(target=self._run, name="apex-lock", daemon=True).start()

    @property
    def dark(self):
        """Locked and the screen is blanked."""
        return self.locked and self.screen_off

    def _run(self):
        while True:
            locked = self.query()
            self.screen_off = locked and self.screen_query()
            self.locked = locked
            time.sleep(self.locked_interval if locked else self.interval)
