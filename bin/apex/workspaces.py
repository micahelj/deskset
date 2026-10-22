"""Hyprland workspace state for the number-row indicator.

Listens on Hyprland's event socket (socket2) and, when a workspace-related
event arrives, re-reads `hyprctl monitors` / `hyprctl workspaces`. Title
and focus events (which a busy terminal emits several times a second) are
ignored, and refreshes are throttled.
"""

from __future__ import annotations

import json
import os
import socket
import time

from . import hypr

# Events that can change which workspaces exist, hold windows, or are shown.
RELEVANT = {
    "workspace", "workspacev2", "focusedmon", "focusedmonv2",
    "createworkspace", "createworkspacev2", "destroyworkspace", "destroyworkspacev2",
    "moveworkspace", "moveworkspacev2", "renameworkspace",
    "openwindow", "closewindow", "movewindow", "movewindowv2",
    "monitoradded", "monitoraddedv2", "monitorremoved", "monitorremovedv2",
}
MIN_REFRESH = 0.05
RECONNECT = 5.0

# Omarchy's idle screensaver runs as a window of this class.
SCREENSAVER_CLASS = "org.omarchy.screensaver"

# Number-row LED name for workspaces 1-10.
KEY_FOR = {i: str(i) for i in range(1, 10)}
KEY_FOR[10] = "0"


def socket_path():
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return os.path.join(runtime, "hypr", sig, ".socket2.sock") if sig else ""


def levels(monitors, workspaces):
    """Map workspace id (1-10) -> "active" | "visible" | "occupied".

    active   = shown on the focused monitor
    visible  = shown on another monitor
    occupied = has windows but is not on screen
    Empty, special and out-of-range workspaces are left out.
    """
    out = {}
    for ws in workspaces or []:
        wid = ws.get("id")
        if isinstance(wid, int) and 1 <= wid <= 10 and ws.get("windows", 0) > 0:
            out[wid] = "occupied"
    for mon in monitors or []:
        wid = (mon.get("activeWorkspace") or {}).get("id")
        if isinstance(wid, int) and 1 <= wid <= 10:
            out[wid] = "active" if mon.get("focused") else "visible"
    return out


def _json(*args):
    try:
        return json.loads(hypr._hypr(*args, "-j") or "[]")
    except json.JSONDecodeError:
        return []


class Tracker:
    def __init__(self):
        self.sock = None
        self.buf = b""
        self.dirty = True
        self.last_refresh = 0.0
        self.last_connect = 0.0
        self.state = {}
        self.active_address = None
        self.focus_changed = False
        self.screensavers = set()  # addresses of open screensaver windows
        self.connect()

    def connect(self):
        self.last_connect = time.monotonic()
        path = socket_path()
        if not path:
            return
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(path)
            s.setblocking(False)
            self.sock = s
            self.dirty = True
        except OSError:
            self.sock = None

    def fileno(self):
        return self.sock.fileno()

    def on_readable(self):
        try:
            chunk = self.sock.recv(65536)
        except BlockingIOError:
            return
        except OSError:
            chunk = b""
        if not chunk:  # Hyprland restarted or the socket closed
            self.close()
            return
        self.buf += chunk
        *lines, self.buf = self.buf.split(b"\n")
        for line in lines:
            event, _, data = line.decode(errors="replace").partition(">>")
            if event in RELEVANT:
                self.dirty = True
            if event == "openwindow":  # ADDRESS,WORKSPACE,CLASS,TITLE
                parts = data.split(",", 3)
                if len(parts) >= 3 and parts[2] == SCREENSAVER_CLASS:
                    self.screensavers.add(parts[0])
            elif event == "closewindow":
                self.screensavers.discard(data)
            elif event == "activewindowv2" and data != self.active_address:
                # By address: title changes (a busy terminal) repeat the same window.
                self.active_address = data
                self.focus_changed = True

    def poll(self, now=None):
        """Reconnect if needed and refresh the state when an event asked for it."""
        now = now or time.monotonic()
        if self.sock is None and now - self.last_connect >= RECONNECT:
            self.connect()
        if self.dirty and now - self.last_refresh >= MIN_REFRESH:
            self.state = levels(_json("monitors"), _json("workspaces"))
            self.dirty = False
            self.last_refresh = now
        return self.state

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
