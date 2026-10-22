"""Claude Code activity for the OLED, fed by Claude Code hooks.

`apexctl claude-hook` runs on each hook event with the event JSON on stdin and
writes one small state file per session into $XDG_RUNTIME_DIR/apex-claude/.
The daemon reads those files, drops sessions whose claude process is gone,
and shows the most urgent one. Command text and file contents are never
stored: only the tool name and a file's base name.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

STATE_DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "apex-claude")
USAGE_PATH = os.path.expanduser("~/.local/state/omarchy/agents/usage/claude.json")

# Most urgent first.
PRIORITY = ("waiting", "working", "thinking", "done", "idle")
ACTIVE = ("waiting", "working", "thinking")
DONE_SECONDS = 20      # "Done" shows this long after a reply, then idle
STALE_SECONDS = 6 * 3600


def _short_tool(name):
    # mcp__server__tool -> tool
    return name.rsplit("__", 1)[-1] if name.startswith("mcp__") else name


def describe_tool(name, tool_input):
    """Tool name plus a file's base name; never command text."""
    name = _short_tool(name or "")
    path = ""
    if isinstance(tool_input, dict):
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    return f"{name}: {os.path.basename(path)}" if path else name


def state_for_event(event):
    """Map one hook payload to (state, detail), or None to leave the file alone."""
    name = event.get("hook_event_name", "")
    tool = event.get("tool_name", "")
    if name == "SessionStart":
        return "idle", ""
    if name == "UserPromptSubmit":
        return "thinking", ""
    if name == "PreToolUse":
        return "working", describe_tool(tool, event.get("tool_input"))
    if name in ("PostToolUse", "PostToolUseFailure", "PermissionDenied"):
        return "thinking", ""
    if name == "PermissionRequest":
        return "waiting", f"Allow {_short_tool(tool)}?" if tool else "Permission?"
    if name == "Notification" and event.get("notification_type") == "permission_prompt":
        return "waiting", "Permission?"
    if name == "Stop":
        return "done", ""
    if name == "StopFailure":
        return "done", "Error"
    return None


def _path(session_id):
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "unknown"
    return os.path.join(STATE_DIR, safe + ".json")


def _parent(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            # comm may contain spaces; the ppid is the 2nd field after ")".
            return int(fh.read().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return 0


def claude_ancestor(pid=None):
    """Nearest ancestor named `claude` (hooks may run under a helper), else the parent."""
    start = pid or os.getppid()
    p = start
    for _ in range(8):
        if p <= 1:
            break
        if _comm(p) == "claude":
            return p
        p = _parent(p)
    return start


def handle_hook(raw, pid=None):
    """Hook entry point. Never raises: a broken hook must not disturb Claude Code."""
    try:
        event = json.loads(raw or "{}")
        session = str(event.get("session_id") or "")
        if not session:
            return
        path = _path(session)
        if event.get("hook_event_name") == "SessionEnd":
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            return
        mapped = state_for_event(event)
        if mapped is None:
            return
        state, detail = mapped
        os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
        record = {"state": state, "detail": detail, "ts": time.time(), "pid": claude_ancestor(pid)}
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 - see docstring
        pass


def _alive(pid):
    try:
        return pid > 0 and os.path.exists(f"/proc/{int(pid)}")
    except (TypeError, ValueError):
        return False


def sessions(now=None, state_dir=STATE_DIR):
    """Live sessions as dicts with an effective state (done decays to idle)."""
    now = now or time.time()
    out = []
    try:
        names = os.listdir(state_dir)
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(state_dir, name)
        try:
            with open(path, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        age = now - float(rec.get("ts", 0))
        if age > STALE_SECONDS or not _alive(rec.get("pid")):
            try:
                os.unlink(path)
            except OSError:
                pass
            continue
        if rec.get("state") == "done" and age > DONE_SECONDS:
            rec["state"] = "idle"
        out.append(rec)
    return out


def summary(now=None, state_dir=STATE_DIR):
    """Most urgent session plus counts: {state, detail, count, busy}."""
    live = sessions(now, state_dir)
    if not live:
        return {"state": "none", "detail": "", "count": 0, "busy": 0}
    live.sort(key=lambda r: (PRIORITY.index(r.get("state", "idle")) if r.get("state") in PRIORITY else len(PRIORITY), -r.get("ts", 0)))
    top = live[0]
    busy = sum(1 for r in live if r.get("state") in ACTIVE)
    return {"state": top.get("state", "idle"), "detail": top.get("detail", ""), "count": len(live), "busy": busy}


def session_usage(path=USAGE_PATH, now=None):
    """Fraction of the 5-hour window used, from the Omarchy Agents record, or None."""
    try:
        with open(path, encoding="utf-8") as fh:
            limits = json.load(fh).get("limits") or []
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    now = now or datetime.now(timezone.utc)
    for entry in limits:
        if "5-hour" not in str(entry.get("label", "")):
            continue
        try:
            resets = datetime.fromisoformat(str(entry.get("resetsAt")))
            if resets <= now:
                return 0.0
        except ValueError:
            pass
        try:
            return max(0.0, min(1.0, float(entry.get("percent"))))
        except (TypeError, ValueError):
            return None
    return None


def _children(pid):
    out = []
    try:
        for tid in os.listdir(f"/proc/{pid}/task"):
            with open(f"/proc/{pid}/task/{tid}/children", encoding="utf-8") as fh:
                out.extend(int(c) for c in fh.read().split())
    except (OSError, ValueError):
        pass
    return out


def _comm(pid):
    try:
        with open(f"/proc/{pid}/comm", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def window_runs_claude(pid, depth=4):
    """True when a `claude` process sits under the window's process (a few levels deep)."""
    frontier = [pid]
    for _ in range(depth):
        nxt = []
        for p in frontier:
            for child in _children(p):
                if _comm(child) == "claude":
                    return True
                nxt.append(child)
        frontier = nxt
        if not frontier:
            break
    return False
