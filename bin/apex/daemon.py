"""Long-running Apex controller: RGB effects, OLED pages, wheel actions."""

from __future__ import annotations

import json
import os
import select
import signal
import socket
import subprocess
import sys
import time

from . import cheatsheet
from . import claude
from . import config as cfgmod
from . import devices
from . import gpu as gpumod
from . import hypr
from . import mouse as mousemod
from . import mpris
from . import oled
from . import presence
from . import render
from . import rgb as rgbmod
from . import sysmon
from . import wheelapp
from . import wheel as wheelmod
from . import workspaces
from .layout import KEYCODE_TO_LED, LEDS, OLED_PAGES, RGB_MODES, WHEEL_MODES

RGB_FPS = 24
TOAST_SECONDS = 1.5  # OLED feedback for the app wheel
# A chosen OLED page announces itself, then stays up this long even where the
# Claude page would take over, so the change is visible.
PAGE_TOAST_SECONDS = 0.9
PAGE_PIN_SECONDS = 4.0
PAGE_TITLES = {"now-playing": "Now playing", "gpu": "GPU", "oled": "OLED"}
SYSTEM_CYCLE = 6.0  # seconds per CPU / GPU half of the system page
OLED_MIN_DT = 0.12


def _run(argv):
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


class Daemon:
    def __init__(self):
        self.cfg = cfgmod.load()
        self.running = True
        self.openrgb = None
        self.palette = rgbmod.load_palette()
        self.reactive = {}
        self.t0 = time.monotonic()
        self.last_rgb = 0.0
        self.last_oled = 0.0
        self.last_palette = 0.0
        self.last_rgb_retry = 0.0
        self.rgb_error = None
        self.claude_focused = False
        self.claude_focus_checked = 0.0
        self.claude_cache = None
        self.workspaces = None
        self.cheat = cheatsheet.CheatSheet()
        self.sysmon = sysmon.Monitor()
        self.gpu = gpumod.GpuMonitor()
        self.last_sample = 0.0
        self.toast_state = None  # (until, title, subtitle)
        self.page_pin_until = 0.0
        self.appwheel = wheelapp.AppWheel(self._toast)
        self.lockwatch = presence.LockWatch()
        self.mouse = None
        self.was_away = False
        self.oled_hash = None
        self.wheel_devs = []
        self.key_devs = []
        self.server = None
        self.clients = []
        self.buf = {}

    def start(self):
        self._connect_rgb()
        self._open_inputs()
        self.workspaces = workspaces.Tracker()
        self.mouse = mousemod.MouseLights()
        self._listen()
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        self._apply_wheel_grab()
        self._push_oled(force=True)
        self._push_rgb(force=True)

    def _stop(self, *_args):
        self.running = False

    def _connect_rgb(self):
        try:
            self.openrgb = rgbmod.connect()
            self.rgb_error = None
        except (OSError, RuntimeError) as exc:
            if str(exc) != self.rgb_error:
                print(f"apexctl: RGB unavailable ({exc})", file=sys.stderr)
            self.rgb_error = str(exc)
            self.openrgb = None

    def _open_inputs(self):
        nodes = wheelmod.apex_event_nodes()
        for path in nodes["wheel"]:
            try:
                self.wheel_devs.append(wheelmod.Evdev(path, grab=False))
            except OSError as exc:
                print(f"apexctl: wheel {path}: {exc}", file=sys.stderr)
        for path in nodes["keys"]:
            try:
                self.key_devs.append(wheelmod.Evdev(path, grab=False))
            except OSError:
                pass

    def _listen(self):
        sock_path = cfgmod.SOCKET_PATH
        try:
            os.unlink(sock_path)
        except OSError:
            pass
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(sock_path)
        self.server.listen(8)
        self.server.setblocking(False)
        os.chmod(sock_path, 0o600)

    def _apply_wheel_grab(self):
        # The cheat sheet borrows the wheel to browse bindings.
        grab = self.cfg["wheel"]["mode"] != "volume" or self.cheat.active
        for dev in self.wheel_devs:
            dev.set_grab(grab)

    def fds(self):
        out = [self.server] + self.clients
        out.extend(self.wheel_devs)
        out.extend(self.key_devs)
        if self.workspaces and self.workspaces.sock is not None:
            out.append(self.workspaces)
        return out

    def loop(self):
        while self.running:
            timeout = 1.0 / RGB_FPS
            readable, _, _ = select.select(self.fds(), [], [], timeout)
            now = time.monotonic()
            for fd in readable:
                if fd is self.server:
                    self._accept()
                elif fd in self.clients:
                    self._on_client(fd)
                elif fd in self.wheel_devs:
                    self._on_wheel(fd)
                elif fd in self.key_devs:
                    self._on_keys(fd)
                elif fd is self.workspaces:
                    self.workspaces.on_readable()
            if now - self.last_palette > 2.0:
                self.palette = rgbmod.load_palette()
                self.last_palette = now
            self._decay_reactive(now)
            away = self._away()
            if away != self.was_away:
                self.was_away = away
                if away and self.cheat.active:
                    self.cheat.close()
                    self._apply_wheel_grab()
                self._push_oled(force=True)
                self._push_rgb(force=True)
            if self.workspaces and self.workspaces.focus_changed:
                self.workspaces.focus_changed = False
                if self.cfg["wheel"]["mode"] == "app":
                    self.appwheel.focus_changed()
            # Always sample, so the system page has history the moment it is shown.
            if now - self.last_sample >= 1.0:
                self.sysmon.sample()
                self.last_sample = now
            if self.cheat.expired(now):
                self.cheat.close()
                self._apply_wheel_grab()
                self._push_oled(force=True)
            if now - self.last_rgb >= 1.0 / RGB_FPS:
                self._push_rgb()
                self._push_mouse()
                self.last_rgb = now
            interval = max(OLED_MIN_DT, self.cfg["oled"].get("interval_ms", 250) / 1000.0)
            page = self.cfg["oled"]["page"]
            # Static pages redraw slowly, unless the animated Claude page may take over.
            if page in ("clock", "logo", "clear") and not self.cfg["oled"].get("claude_auto", True):
                interval = max(interval, 0.5)
            if now - self.last_oled >= interval:
                self._push_oled()
                self.last_oled = now
        self.shutdown()

    def _accept(self):
        try:
            conn, _ = self.server.accept()
        except OSError:
            return
        conn.setblocking(False)
        self.clients.append(conn)
        self.buf[conn] = b""

    def _on_client(self, conn):
        try:
            chunk = conn.recv(4096)
        except OSError:
            chunk = b""
        if not chunk:
            self._drop(conn)
            return
        self.buf[conn] += chunk
        while b"\n" in self.buf[conn]:
            line, self.buf[conn] = self.buf[conn].split(b"\n", 1)
            if not line.strip():
                continue
            try:
                req = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                self._reply(conn, {"ok": False, "error": "invalid json"})
                continue
            self._reply(conn, self.handle(req))

    def _drop(self, conn):
        try:
            self.clients.remove(conn)
        except ValueError:
            pass
        self.buf.pop(conn, None)
        try:
            conn.close()
        except OSError:
            pass

    def _reply(self, conn, payload):
        try:
            conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        except OSError:
            self._drop(conn)

    def status(self):
        profile = devices.current()
        preview = mousemod.previews(self.cfg, self.palette)
        rgb_dev = None
        if self.openrgb:
            rgb_dev = self.openrgb.device[1]
        return {
            "ok": True,
            "connected": bool(self.openrgb) or bool(oled.find_oled_hidraw()),
            "device": rgb_dev or profile.name,
            "short": profile.short,
            "rgb_backend": profile.rgb,
            "rgb": dict(self.cfg["rgb"]),
            "oled": dict(self.cfg["oled"]),
            "wheel": dict(self.cfg["wheel"]),
            "openrgb": bool(self.openrgb),
            "oled_hid": oled.find_oled_hidraw(),
            "rgb_preview": preview[0],
            "mouse": {**self.cfg["mouse"], **(self.mouse.status() if self.mouse else {"present": False}),
                      "preview": preview[1]},
        }

    def handle(self, req):
        cmd = req.get("cmd")
        if cmd == "status":
            return self.status()
        if cmd == "rgb":
            return self._cmd_rgb(req)
        if cmd == "oled":
            return self._cmd_oled(req)
        if cmd == "wheel":
            return self._cmd_wheel(req)
        if cmd == "mouse":
            return self._cmd_mouse(req)
        if cmd == "reload":
            self.cfg = cfgmod.load()
            self.palette = rgbmod.load_palette()
            self._apply_wheel_grab()
            self._push_oled(force=True)
            self._push_rgb(force=True)
            return self.status()
        if cmd == "cheatsheet":
            action = req.get("action", "toggle")
            if action == "open" or (action == "toggle" and not self.cheat.active):
                opened = self.cheat.open()
            else:
                self.cheat.close()
                opened = False
            self._apply_wheel_grab()
            self._push_oled(force=True)
            self._push_rgb(force=True)
            return {"ok": True, "cheatsheet": opened, **(self.cheat.oled_state() if opened else {})}
        if cmd == "stop":
            self.running = False
            return {"ok": True}
        return {"ok": False, "error": f"unknown cmd {cmd}"}

    def _cmd_rgb(self, req):
        rgb = self.cfg["rgb"]
        if "mode" in req and req["mode"] in RGB_MODES:
            rgb["mode"] = req["mode"]
        if "solid" in req:
            rgb["solid"] = req["solid"]
        if "profile" in req and req["profile"] in rgbmod.PROFILES:
            rgb["profile"] = req["profile"]
        if "brightness" in req:
            rgb["brightness"] = int(max(0, min(100, int(req["brightness"]))))
        if "speed" in req:
            rgb["speed"] = int(max(1, min(100, int(req["speed"]))))
        if "keys" in req and isinstance(req["keys"], dict):
            rgb.setdefault("keys", {}).update(req["keys"])
        if req.get("clear_keys"):
            rgb["keys"] = {}
        cfgmod.save(self.cfg)
        self._push_rgb(force=True)
        return self.status()

    def _cmd_oled(self, req):
        oled_cfg = self.cfg["oled"]
        if req.get("next"):
            self._cycle_oled(1)
        elif req.get("prev"):
            self._cycle_oled(-1)
        elif "page" in req:
            oled_cfg["page"] = req["page"]
        if "text" in req:
            oled_cfg["text"] = req["text"]
            if "page" not in req and not req.get("next") and not req.get("prev"):
                oled_cfg["page"] = "text"
        if "image" in req:
            oled_cfg["image"] = req["image"]
            if "page" not in req:
                oled_cfg["page"] = "logo"
        if any(k in req for k in ("page", "next", "prev", "text", "image")):
            self._page_changed()
        cfgmod.save(self.cfg)
        self._push_oled(force=True)
        return self.status()

    def _cmd_wheel(self, req):
        if "mode" in req and req["mode"] in WHEEL_MODES:
            self.cfg["wheel"]["mode"] = req["mode"]
        if "invert" in req:
            self.cfg["wheel"]["invert"] = bool(req["invert"])
        cfgmod.save(self.cfg)
        self._apply_wheel_grab()
        return self.status()

    def _cmd_mouse(self, req):
        mcfg = self.cfg["mouse"]
        if req.get("mode") in mousemod.MODES:
            mcfg["mode"] = req["mode"]
        if "color" in req:
            mcfg["color"] = req["color"]
        if "brightness" in req:
            value = req["brightness"]
            mcfg["brightness"] = None if value is None else int(max(0, min(100, int(value))))
        if "claude" in req:
            mcfg["claude"] = bool(req["claude"])
        if "dpi" in req:
            mcfg["dpi"] = None if req["dpi"] is None else int(req["dpi"])
        if req.get("buttons") or req.get("restore_buttons"):
            from . import onboard
            try:
                if req.get("restore_buttons"):
                    self.mouse.restore_buttons()
                else:
                    changes = {int(slot): action for slot, action in req["buttons"].items()}
                    self.mouse.set_buttons(changes)
                    if any(a in onboard.DESKTOP_ACTIONS for a in changes.values()):
                        onboard.ensure_hypr_block(os.path.join(cfgmod.PLUGIN_ROOT, "bin", "apexctl"))
            except (OSError, ValueError) as exc:
                return {**self.status(), "ok": False, "error": str(exc)}
        cfgmod.save(self.cfg)
        self._push_mouse()
        return self.status()

    def _cycle_oled(self, delta):
        pages = self.cfg["oled"].get("pages") or list(OLED_PAGES[:4])
        current = self.cfg["oled"]["page"]
        if current not in pages:
            pages = [current, *pages]
        idx = pages.index(current) if current in pages else 0
        self.cfg["oled"]["page"] = pages[(idx + delta) % len(pages)]
        self._page_changed()

    def _page_changed(self):
        page = self.cfg["oled"]["page"]
        now = time.monotonic()
        title = PAGE_TITLES.get(page, page.replace("-", " ").capitalize())
        self.toast_state = (now + PAGE_TOAST_SECONDS, title, "OLED page")
        self.page_pin_until = now + PAGE_PIN_SECONDS

    def _cycle_rgb(self, delta):
        modes = [m for m in RGB_MODES if m != "off"]
        current = self.cfg["rgb"]["mode"]
        idx = modes.index(current) if current in modes else 0
        self.cfg["rgb"]["mode"] = modes[(idx + delta) % len(modes)]
        cfgmod.save(self.cfg)

    def _on_wheel(self, dev):
        events = dev.read()
        rel_steps, key_steps, clicked = wheelmod.decode_wheel(
            events, invert=self.cfg["wheel"]["invert"]
        )
        if self.cheat.active:
            steps = rel_steps or key_steps
            if clicked:
                self.cheat.next_set()
            if steps:
                self.cheat.step(steps)
            if clicked or steps:
                self._push_oled(force=True)
            return
        mode = self.cfg["wheel"]["mode"]
        if mode == "app":
            steps = rel_steps or key_steps
            if clicked:
                self.appwheel.click()
            if steps:
                self.appwheel.turn(steps)
            return
        # Volume mode does not grab the device, so KEY_VOLUME*/MUTE already
        # reach Hyprland. Only map leftover REL events so the roller still
        # works if the firmware does not emit media keys.
        if mode == "volume":
            if rel_steps:
                self._wheel_steps(mode, rel_steps)
            return
        steps = rel_steps or key_steps
        if clicked:
            self._wheel_click(mode)
        if steps:
            self._wheel_steps(mode, steps)

    def _wheel_click(self, mode):
        if mode == "volume":
            _run(["omarchy", "audio", "output", "volume", "mute-toggle"])
        elif mode == "oled":
            self._cycle_oled(1)
            cfgmod.save(self.cfg)
            self._push_oled(force=True)
        elif mode == "rgb":
            self._cycle_rgb(1)
            self._push_rgb(force=True)
        elif mode == "workspace":
            hypr.toggle_special("scratchpad")  # same scratchpad as Super+S
        elif mode == "brightness":
            _run(["omarchy", "brightness", "display", "off"])

    def _wheel_steps(self, mode, steps):
        if mode == "volume":
            action = "raise" if steps > 0 else "lower"
            for _ in range(abs(steps)):
                _run(["omarchy", "audio", "output", "volume", action])
        elif mode == "workspace":
            relative = "e+1" if steps > 0 else "e-1"
            for _ in range(abs(steps)):
                hypr.focus_workspace(relative)
        elif mode == "brightness":
            delta = f"+{5 * abs(steps)}%" if steps > 0 else f"{5 * abs(steps)}%-"
            _run(["omarchy", "brightness", "display", delta])
        elif mode == "oled":
            self._cycle_oled(1 if steps > 0 else -1)
            cfgmod.save(self.cfg)
            self._push_oled(force=True)
        elif mode == "rgb":
            self._cycle_rgb(1 if steps > 0 else -1)
            self._push_rgb(force=True)

    def _on_keys(self, dev):
        now = time.monotonic()
        for etype, code, value in dev.read():
            if etype != 0x01 or value == 0:
                continue
            name = KEYCODE_TO_LED.get(code)
            if name:
                self.reactive[name] = now

    def _decay_reactive(self, now):
        stale = [k for k, ts in self.reactive.items() if now - ts > 0.4]
        for key in stale:
            del self.reactive[key]

    def _rgb_time(self):
        speed = self.cfg["rgb"]["speed"] / 45.0
        return (time.monotonic() - self.t0) * speed

    def _push_rgb(self, force=False):
        if not self.openrgb:
            # Retry now and then so a replugged keyboard picks its lighting back up.
            now = time.monotonic()
            if force or now - self.last_rgb_retry > 5.0:
                self.last_rgb_retry = now
                self._connect_rgb()
            if not self.openrgb:
                return
        mode = self.cfg["rgb"]["mode"]
        ages = {k: time.monotonic() - ts for k, ts in self.reactive.items()}
        try:
            if self._away():
                # Locked or screensaver: dark keyboard, nothing on top.
                self.openrgb.set_colors([(0, 0, 0)] * len(LEDS))
                return
            if self.cheat.active:
                # The cheat sheet owns the whole board while it is open.
                colors = self.cheat.colors(time.monotonic() - self.t0, self.cfg["rgb"]["brightness"])
            else:
                colors = rgbmod.effect_colors(
                    mode,
                    self._rgb_time(),
                    self.palette,
                    self.cfg["rgb"]["solid"],
                    self.cfg["rgb"]["brightness"],
                    reactive_keys=ages if mode == "reactive" else (ages if ages and mode == "theme" else {}),
                    profile=self.cfg["rgb"].get("profile"),
                )
                if self.cfg["rgb"].get("workspace_keys", True) and self.workspaces:
                    colors = rgbmod.apply_workspace_keys(
                        colors, self.workspaces.poll(), self.palette, self.cfg["rgb"]["brightness"],
                        self.cfg["rgb"].get("workspace_colors"),
                    )
                colors = rgbmod.apply_key_overrides(colors, self.cfg["rgb"].get("keys"))
            if self.cfg["rgb"].get("claude_esc", True):
                waiting = self._claude_summary()["state"] == "waiting"
                alert = rgbmod.parse_hex(self.cfg["rgb"].get("claude_esc_color"), rgbmod.CLAUDE_ALERT)
                colors = rgbmod.apply_claude_alert(colors, waiting, time.monotonic() - self.t0, alert)
            self.openrgb.set_colors(colors)
        except (OSError, RuntimeError) as exc:
            print(f"apexctl: rgb update failed: {exc}", file=sys.stderr)
            self.openrgb.close()
            self.openrgb = None

    def _push_mouse(self):
        # Cheap: the worker thread only talks to the mouse when this changes.
        if not self.mouse:
            return
        mcfg = self.cfg["mouse"]
        if self.mouse.dpi_moved:
            # DPI changed with the mouse's own buttons: keep it.
            self.mouse.dpi_moved = False
            if self.mouse.dpi and self.mouse.dpi != mcfg.get("dpi"):
                mcfg["dpi"] = self.mouse.dpi
                cfgmod.save(self.cfg)
        waiting = self._claude_summary()["state"] == "waiting"
        self.mouse.want(mousemod.wanted(self.cfg, self.palette, self._away(), waiting), mcfg.get("dpi"))

    def _claude_focused(self):
        # Polling hyprctl and /proc at frame rate is wasteful; once a second is plenty.
        now = time.monotonic()
        if now - self.claude_focus_checked >= 1.0:
            pid = hypr.active_pid()
            self.claude_focused = bool(pid) and claude.window_runs_claude(pid)
            self.claude_focus_checked = now
        return self.claude_focused

    def _claude_summary(self):
        # Shared by the OLED and the 24 fps RGB loop; the state files change far slower.
        now = time.monotonic()
        if self.claude_cache is None or now - self.claude_cache[0] >= 0.25:
            self.claude_cache = (now, claude.summary())
        return self.claude_cache[1]

    def _effective_page(self):
        """The saved page, or the Claude page while a session is busy or focused."""
        page = self.cfg["oled"]["page"]
        if page == "claude" or not self.cfg["oled"].get("claude_auto", True):
            return page, None
        if time.monotonic() < self.page_pin_until:
            return page, None  # just chosen: show it before Claude takes over again
        summary = self._claude_summary()
        if summary["state"] in claude.ACTIVE or (summary["count"] and self._claude_focused()):
            return "claude", summary
        return page, None

    def _away(self):
        """Idle screensaver up, or locked with the screen blanked (and the feature is on)."""
        if not self.cfg["rgb"].get("away_dark", True):
            return False
        screensaver = bool(self.workspaces and self.workspaces.screensavers)
        return screensaver or self.lockwatch.dark

    def _toast(self, title, subtitle=""):
        # Called from the wheel worker thread; a tuple swap is atomic.
        self.toast_state = (time.monotonic() + TOAST_SECONDS, title, subtitle)

    def _oled_state(self):
        if self._away():
            return "clear", {"t": time.monotonic() - self.t0}
        if self.cheat.active:
            return "cheatsheet", {"cheatsheet": self.cheat.oled_state(), "t": time.monotonic() - self.t0}
        toast = self.toast_state
        if toast and time.monotonic() < toast[0]:
            return "toast", {"title": toast[1], "subtitle": toast[2]}
        page, summary = self._effective_page()
        state = {
            "t": time.monotonic() - self.t0,
            "text": self.cfg["oled"].get("text", ""),
            "image": self.cfg["oled"].get("image"),
        }
        if page == "now-playing":
            state.update(mpris.now_playing())
        elif page == "workspace":
            state.update(hypr.active())
        elif page == "system":
            # Alternate CPU and GPU every SYSTEM_CYCLE seconds; skip a sleeping GPU.
            # Asking for GPU data keeps a laptop GPU awake while this page is shown.
            self.gpu.want()
            gpu = self.gpu.snapshot()
            if gpu["present"] and not gpu["asleep"] and int(state["t"] / SYSTEM_CYCLE) % 2:
                page = "gpu"
                state["gpu"] = gpu
            else:
                state["system"] = self.sysmon.snapshot()
        elif page == "gpu":
            self.gpu.want()
            state["gpu"] = self.gpu.snapshot()
        elif page == "claude":
            state["claude"] = summary or claude.summary()
            state["usage"] = claude.session_usage()
        return page, state

    def _push_oled(self, force=False):
        page, state = self._oled_state()
        try:
            frame = render.render(page, state)
            digest = frame.tobytes()
            if not force and digest == self.oled_hash:
                return
            oled.send_image(frame)
            self.oled_hash = digest
        except (OSError, FileNotFoundError) as exc:
            if force:
                print(f"apexctl: oled update failed: {exc}", file=sys.stderr)

    def shutdown(self):
        for dev in self.wheel_devs + self.key_devs:
            dev.close()
        if self.workspaces:
            self.workspaces.close()
        if self.mouse:
            self.mouse.stop()
        for conn in list(self.clients):
            self._drop(conn)
        if self.server:
            try:
                self.server.close()
            except OSError:
                pass
        try:
            os.unlink(cfgmod.SOCKET_PATH)
        except OSError:
            pass
        if self.openrgb:
            if hasattr(self.openrgb, "restore"):
                self.openrgb.restore()
            self.openrgb.close()
        # Gen 3 firmware ignores "reset to default screen", so blank it rather
        # than leave a frozen page behind.
        if devices.current().oled == "gen3":
            try:
                oled.clear()
            except OSError:
                pass


def run():
    daemon = Daemon()
    daemon.start()
    print("apexctl daemon ready", cfgmod.SOCKET_PATH, flush=True)
    daemon.loop()
