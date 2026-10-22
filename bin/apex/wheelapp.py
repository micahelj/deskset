"""The "app" wheel mode: what the wheel does follows the focused window.

Rules, first match wins:
  1. A window running Claude Code -> system volume (scrolling must never
     answer a prompt).
  2. A browser playing audio or video -> the browser's own volume; click
     mutes it. A quiet browser -> previous / next tab; click reopens the
     last closed tab.
  3. A terminal -> font size; click resets it.
  4. Any other app that is playing sound -> that app's own volume; click
     mutes just that app.
  5. Anything else -> system volume; click mutes.

Actions run on a worker thread: sending a shortcut needs a short key-down /
key-up pause and pactl / wpctl take a few ms, which would stall the RGB loop.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time

from . import claude, hypr

BROWSERS = {"chromium", "google-chrome", "brave-browser", "firefox", "librewolf", "zen", "vivaldi-stable"}
# class -> (increase, decrease, reset) as (mods, key)
TERMINALS = {
    "com.mitchellh.ghostty": (("CTRL", "equal"), ("CTRL", "minus"), ("CTRL", "0")),
    "Alacritty": (("CTRL", "equal"), ("CTRL", "minus"), ("CTRL", "0")),
    "foot": (("CTRL", "equal"), ("CTRL", "minus"), ("CTRL", "0")),
    "kitty": (("CTRL SHIFT", "equal"), ("CTRL SHIFT", "minus"), ("CTRL SHIFT", "BackSpace")),
}
VOLUME_STEP = 5  # percent per wheel notch


def _run(argv, timeout=2):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def send_shortcut(mods, key, window="activewindow"):
    """Press and release a shortcut in a window (Lua dispatch on Hyprland 0.56+)."""
    def lua(state):
        return f'hl.dsp.send_key_state({{ mods = "{mods}", key = "{key}", state = "{state}", window = "{window}" }})'
    if hypr._hypr("dispatch", lua("down")).strip() == "ok":
        time.sleep(0.05)
        hypr._hypr("dispatch", lua("up"))
    else:
        hypr._hypr("dispatch", "sendshortcut", f"{mods}, {key}, {window}")


def descendants(pid, depth=5):
    """pid plus its child processes (audio often plays from a helper process)."""
    out, frontier = {pid}, [pid]
    for _ in range(depth):
        nxt = [c for p in frontier for c in claude._children(p)]
        out.update(nxt)
        frontier = nxt
        if not frontier:
            break
    return out


def playback_streams():
    """PipeWire playback streams as [{index, pid, name, binary, volume, mute}]."""
    try:
        data = json.loads(_run(["pactl", "-f", "json", "list", "sink-inputs"]) or "[]")
    except json.JSONDecodeError:
        return []
    out = []
    for s in data:
        props = s.get("properties", {})
        vols = [v.get("value_percent", "0%") for v in (s.get("volume") or {}).values()]
        try:
            vol = int(str(vols[0]).rstrip("%")) if vols else 0
        except ValueError:
            vol = 0
        try:
            pid = int(props.get("application.process.id", 0))
        except (TypeError, ValueError):
            pid = 0
        out.append({
            "index": s.get("index"), "pid": pid, "volume": vol, "mute": bool(s.get("mute")),
            "corked": bool(s.get("corked")),  # paused players keep a corked stream
            "name": props.get("application.name", ""), "binary": props.get("application.process.binary", ""),
        })
    return out


def streams_for(window_class, pid, streams):
    """Streams belonging to the window: by process tree, else by app/binary name."""
    pids = descendants(pid) if pid else set()
    mine = [s for s in streams if s["pid"] and s["pid"] in pids]
    if not mine and window_class:
        key = window_class.lower().rsplit(".", 1)[-1]
        mine = [s for s in streams if key and (key in s["name"].lower() or key in s["binary"].lower())]
    # Prefer streams that are actually playing.
    return sorted(mine, key=lambda s: s.get("corked", False))


def classify(window_class, pid, streams, runs_claude=None):
    """(kind, label) for the focused window. Kinds: volume, tabs, zoom, app-volume."""
    runs_claude = runs_claude or claude.window_runs_claude
    if pid and runs_claude(pid):
        return "volume", "Volume"
    if window_class in BROWSERS:
        playing = [s for s in streams_for(window_class, pid, streams) if not s.get("corked")]
        if playing:
            return "app-volume", (playing[0]["name"] or "Browser") + " volume"
        return "tabs", "Tabs"
    if window_class in TERMINALS:
        return "zoom", "Font size"
    mine = streams_for(window_class, pid, streams)
    if mine:
        return "app-volume", (mine[0]["name"] or window_class or "App") + " volume"
    return "volume", "Volume"


def system_volume():
    out = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])  # "Volume: 0.85 [MUTED]"
    try:
        level = round(float(out.split()[1]) * 100)
    except (IndexError, ValueError):
        return ""
    return f"{level}%" + (" muted" if "MUTED" in out else "")


class AppWheel:
    """Resolves the focused window's wheel action and runs it on a worker thread."""

    def __init__(self, toast):
        self.toast = toast  # toast(title, subtitle): OLED feedback
        self.jobs = queue.Queue()
        self.last_kind = None
        threading.Thread(target=self._work, name="apex-wheel", daemon=True).start()

    def _work(self):
        while True:
            job = self.jobs.get()
            try:
                job()
            except Exception as exc:  # noqa: BLE001 - one bad action must not kill the worker
                print(f"apexctl: wheel action failed: {exc}", flush=True)

    def _focused(self):
        info = {}
        try:
            info = json.loads(hypr._hypr("activewindow", "-j") or "{}")
        except json.JSONDecodeError:
            pass
        return str(info.get("class") or ""), int(info.get("pid") or 0)

    def focus_changed(self):
        """Show what the wheel now does, but only when that actually changes."""
        def job():
            wclass, pid = self._focused()
            kind, label = classify(wclass, pid, playback_streams())
            if (kind, label) != self.last_kind:
                self.last_kind = (kind, label)
                self.toast("Wheel", label)
        self.jobs.put(job)

    def turn(self, steps):
        self.jobs.put(lambda: self._act(steps=steps))

    def click(self):
        self.jobs.put(lambda: self._act(click=True))

    def _act(self, steps=0, click=False):
        wclass, pid = self._focused()
        streams = playback_streams()
        kind, label = classify(wclass, pid, streams)
        if kind == "tabs":
            if click:
                send_shortcut("CTRL SHIFT", "t")
                self.toast("Tabs", "Reopened tab")
            else:
                for _ in range(abs(steps)):
                    send_shortcut("CTRL SHIFT" if steps < 0 else "CTRL", "Tab")
                self.toast("Tabs", "Next tab →" if steps > 0 else "← Previous tab")
        elif kind == "zoom":
            up, down, reset = TERMINALS[wclass]
            if click:
                send_shortcut(*reset)
                self.toast("Font size", "Reset")
            else:
                for _ in range(abs(steps)):
                    send_shortcut(*(up if steps > 0 else down))
                self.toast("Font size", "Bigger" if steps > 0 else "Smaller")
        elif kind == "app-volume":
            stream = streams_for(wclass, pid, streams)[0]
            name = label.removesuffix(" volume")
            if click:
                _run(["pactl", "set-sink-input-mute", str(stream["index"]), "toggle"])
                self.toast(name, "Unmuted" if stream["mute"] else "Muted")
            else:
                level = max(0, min(100, stream["volume"] + steps * VOLUME_STEP))
                _run(["pactl", "set-sink-input-volume", str(stream["index"]), f"{level}%"])
                self.toast(name, f"{level}%")
        else:
            if click:
                _run(["omarchy", "audio", "output", "volume", "mute-toggle"])
            else:
                action = "raise" if steps > 0 else "lower"
                for _ in range(abs(steps)):
                    _run(["omarchy", "audio", "output", "volume", action])
            self.toast("Volume", system_volume())
