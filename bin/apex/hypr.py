"""Hyprland workspace helpers."""

from __future__ import annotations

import json
import subprocess


def _hypr(*args, timeout=0.3):
    try:
        return subprocess.check_output(["hyprctl", *args], text=True, timeout=timeout, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return ""


def active():
    ws = {}
    win = {}
    try:
        ws = json.loads(_hypr("activeworkspace", "-j") or "{}")
    except json.JSONDecodeError:
        ws = {}
    try:
        win = json.loads(_hypr("activewindow", "-j") or "{}")
    except json.JSONDecodeError:
        win = {}
    name = str(ws.get("name") or ws.get("id") or "")
    title = str(win.get("title") or "")
    klass = str(win.get("class") or "")
    return {"workspace": name, "window": title, "class": klass}


def active_pid():
    try:
        return int(json.loads(_hypr("activewindow", "-j") or "{}").get("pid") or 0)
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0


def dispatch(lua, legacy):
    """Run a dispatcher. Hyprland 0.56+ (Lua config) evaluates `dispatch` as
    hl.dispatch(<lua>); older releases take the classic "name args" form."""
    out = _hypr("dispatch", lua).strip()
    if out != "ok":
        _hypr("dispatch", *legacy.split())


def focus_workspace(relative):
    """relative is e.g. "e+1": the next workspace that has windows."""
    dispatch(f'hl.dsp.focus({{ workspace = "{relative}" }})', f"workspace {relative}")


def toggle_special(name):
    dispatch(f'hl.dsp.workspace.toggle_special("{name}")', f"togglespecialworkspace {name}")
