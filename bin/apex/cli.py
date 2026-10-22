#!/usr/bin/env python3
"""apexctl — SteelSeries Apex RGB, OLED, and scroll-wheel control."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys

from . import __version__
from . import config as cfgmod
from . import devices
from . import oled
from . import render
from . import rgb as rgbmod
from .layout import LEDS, OLED_PAGES, RGB_MODES, WHEEL_MODES


def _talk(req, timeout=2.0):
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(cfgmod.SOCKET_PATH)
        sock.sendall((json.dumps(req) + "\n").encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        sock.close()
        if not buf:
            return None
        return json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _print_status(data, as_json=False):
    if as_json:
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return
    rgb = data.get("rgb", {})
    oled_cfg = data.get("oled", {})
    wheel = data.get("wheel", {})
    print(f"device     {data.get('device', '?')}")
    print(f"rgb via    {data.get('rgb_backend', 'openrgb')}  ({'connected' if data.get('openrgb') else 'not connected'})")
    print(f"oled       {data.get('oled_hid') or 'missing'}")
    print(f"rgb        {rgb.get('mode')}  brightness={rgb.get('brightness')}  speed={rgb.get('speed')}")
    if rgb.get("mode") == "solid":
        print(f"solid      {rgb.get('solid')}")
    if rgb.get("mode") == "gradient":
        print(f"profile    {rgb.get('profile')}")
    print(f"oled page  {oled_cfg.get('page')}")
    print(f"wheel      {wheel.get('mode')}")


def cmd_status(args):
    data = _talk({"cmd": "status"})
    if data is None:
        cfg = cfgmod.load()
        profile = devices.current()
        data = {
            "ok": True,
            "connected": bool(oled.find_oled_hidraw()),
            "device": profile.name,
            "short": profile.short,
            "rgb_backend": profile.rgb,
            "rgb": cfg["rgb"],
            "oled": cfg["oled"],
            "wheel": cfg["wheel"],
            "openrgb": profile.rgb == "hid" and bool(oled.find_oled_hidraw()),
            "oled_hid": oled.find_oled_hidraw(),
            "daemon": False,
        }
        if not args.json:
            print("daemon     offline (one-shot commands still work)")
    else:
        data["daemon"] = True
    _print_status(data, as_json=args.json)


def _dispatch_or_local(req, local_fn):
    data = _talk(req)
    if data is not None:
        return data
    cfg = cfgmod.load()
    local_fn(cfg, req)
    cfgmod.save(cfg)
    return {"ok": True, "daemon": False, **cfg}


def _local_rgb(cfg, req):
    rgb = cfg["rgb"]
    if "mode" in req:
        rgb["mode"] = req["mode"]
    if "solid" in req:
        rgb["solid"] = req["solid"]
    if "profile" in req:
        rgb["profile"] = req["profile"]
    if "brightness" in req:
        rgb["brightness"] = int(req["brightness"])
    if "speed" in req:
        rgb["speed"] = int(req["speed"])
    if "keys" in req:
        rgb.setdefault("keys", {}).update(req["keys"])
    if req.get("clear_keys"):
        rgb["keys"] = {}
    palette = rgbmod.load_palette()
    colors = rgbmod.effect_colors(rgb["mode"], 0, palette, rgb["solid"], rgb["brightness"], profile=rgb.get("profile"))
    colors = rgbmod.apply_key_overrides(colors, rgb.get("keys"))
    client = rgbmod.connect()
    try:
        client.set_colors(colors)
        print(f"applied {rgb['mode']} to {client.device[1]}")
    finally:
        client.close()


def _local_oled(cfg, req):
    from . import hypr, mpris
    oled_cfg = cfg["oled"]
    if "page" in req:
        oled_cfg["page"] = req["page"]
    if "text" in req:
        oled_cfg["text"] = req["text"]
        if "page" not in req:
            oled_cfg["page"] = "text"
    if "image" in req:
        oled_cfg["image"] = req["image"]
        if "page" not in req:
            oled_cfg["page"] = "logo"
    state = {
        "text": oled_cfg.get("text", ""),
        "image": oled_cfg.get("image"),
        "t": 0,
    }
    page = oled_cfg["page"]
    if page == "now-playing":
        state.update(mpris.now_playing())
    elif page == "workspace":
        state.update(hypr.active())
    elif page == "gpu":
        from . import gpu
        mon = gpu.GpuMonitor()
        if mon.present:
            mon.poll()
        state["gpu"] = mon.snapshot()
    elif page == "system":
        import time as _time
        from . import sysmon
        mon = sysmon.Monitor()
        mon.sample()
        _time.sleep(0.5)  # CPU % needs two samples
        mon.sample()
        state["system"] = mon.snapshot()
    elif page == "claude":
        from . import claude
        state["claude"] = claude.summary()
        state["usage"] = claude.session_usage()
    frame = render.render(page, state)
    path = oled.send_image(frame)
    print(f"oled {page} -> {path}")


def cmd_rgb(args):
    req = {"cmd": "rgb"}
    if args.mode:
        if args.mode not in RGB_MODES:
            raise SystemExit(f"unknown mode {args.mode}; choose from {', '.join(RGB_MODES)}")
        req["mode"] = args.mode
    if args.color:
        req["solid"] = args.color
        req.setdefault("mode", "solid")
    if args.profile:
        if args.profile not in rgbmod.PROFILES:
            raise SystemExit(f"unknown profile {args.profile}; choose from {', '.join(rgbmod.PROFILES)}")
        req["profile"] = args.profile
        req.setdefault("mode", "gradient")
    if args.brightness is not None:
        req["brightness"] = args.brightness
    if args.speed is not None:
        req["speed"] = args.speed
    if args.key:
        keys = {}
        for item in args.key:
            if "=" not in item:
                raise SystemExit("key override must be Name=#RRGGBB")
            name, color = item.split("=", 1)
            if name not in LEDS:
                raise SystemExit(f"unknown key {name}")
            keys[name] = color
        req["keys"] = keys
    if args.clear_keys:
        req["clear_keys"] = True
    data = _dispatch_or_local(req, _local_rgb)
    if args.json:
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")


def cmd_oled(args):
    req = {"cmd": "oled"}
    if args.next:
        req["next"] = True
    elif args.prev:
        req["prev"] = True
    elif args.page:
        req["page"] = args.page
    if args.text is not None:
        req["text"] = args.text
    if args.image:
        req["image"] = os.path.abspath(os.path.expanduser(args.image))
    if args.next or args.prev:
        data = _talk(req)
        if data is None:
            raise SystemExit("oled next/prev needs the apexctl daemon")
    else:
        data = _dispatch_or_local(req, _local_oled)
    if args.json:
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")


def cmd_wheel(args):
    req = {"cmd": "wheel"}
    if args.mode:
        if args.mode not in WHEEL_MODES:
            raise SystemExit(f"unknown wheel mode {args.mode}; choose from {', '.join(WHEEL_MODES)}")
        req["mode"] = args.mode
    if args.invert is not None:
        req["invert"] = args.invert
    data = _talk(req)
    if data is None:
        cfg = cfgmod.load()
        if args.mode:
            cfg["wheel"]["mode"] = args.mode
        if args.invert is not None:
            cfg["wheel"]["invert"] = args.invert
        cfgmod.save(cfg)
        print("saved wheel config; start the daemon to apply (systemctl --user start apexctl)")
        return
    print(f"wheel mode {data.get('wheel', {}).get('mode')}")


def cmd_keys(_args):
    for name in LEDS:
        print(name)


def cmd_profiles(_args):
    for name, hexes in rgbmod.PROFILES.items():
        print(f"{name:10s} {' '.join(hexes)}")


def cmd_daemon(_args):
    from .daemon import run
    run()


def cmd_cheatsheet(args):
    data = _talk({"cmd": "cheatsheet", "action": args.action})
    if data is None:
        print("apexctl: the daemon is not running (start it from the panel's Set up button)", file=sys.stderr)
        sys.exit(1)
    if data.get("cheatsheet"):
        print(f"cheat sheet open: {data.get('label')} ({data.get('count')} keys)")
    else:
        print("cheat sheet closed")


def cmd_claude_hook(_args):
    # Claude Code hook entry point: event JSON on stdin, never fails or prints.
    from . import claude
    claude.handle_hook(sys.stdin.read())


def build_parser():
    p = argparse.ArgumentParser(prog="apexctl", description="Control a SteelSeries Apex keyboard")
    p.add_argument("--version", action="version", version=f"apexctl {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    st = sub.add_parser("status", help="show RGB / OLED / wheel state")
    st.add_argument("--json", action="store_true")
    st.set_defaults(func=cmd_status)

    rg = sub.add_parser("rgb", help="set lighting mode, color, or per-key overrides")
    rg.add_argument("mode", nargs="?", choices=RGB_MODES)
    rg.add_argument("-c", "--color", help="solid hex color, e.g. #89b4fa")
    rg.add_argument("-p", "--profile", help="color profile for gradient mode (see: apexctl profiles)")
    rg.add_argument("-b", "--brightness", type=int)
    rg.add_argument("-s", "--speed", type=int)
    rg.add_argument("-k", "--key", action="append", help="Key=#RRGGBB (repeatable)")
    rg.add_argument("--clear-keys", action="store_true")
    rg.add_argument("--json", action="store_true")
    rg.set_defaults(func=cmd_rgb)

    ol = sub.add_parser("oled", help="draw on the 128x40 OLED")
    ol.add_argument("page", nargs="?", choices=OLED_PAGES)
    ol.add_argument("--text")
    ol.add_argument("--image")
    ol.add_argument("--next", action="store_true")
    ol.add_argument("--prev", action="store_true")
    ol.add_argument("--json", action="store_true")
    ol.set_defaults(func=cmd_oled)

    wh = sub.add_parser("wheel", help="bind the OLED scroll wheel")
    wh.add_argument("mode", nargs="?", choices=WHEEL_MODES)
    wh.add_argument("--invert", action="store_true", default=None)
    wh.add_argument("--no-invert", dest="invert", action="store_false")
    wh.set_defaults(func=cmd_wheel)

    ky = sub.add_parser("keys", help="list LED names for per-key overrides")
    ky.set_defaults(func=cmd_keys)

    pf = sub.add_parser("profiles", help="list gradient color profiles")
    pf.set_defaults(func=cmd_profiles)

    da = sub.add_parser("daemon", help="run the RGB / OLED / wheel daemon")
    da.set_defaults(func=cmd_daemon)
    cs = sub.add_parser("cheatsheet", help="light the keys bound under each modifier set")
    cs.add_argument("action", nargs="?", default="toggle", choices=("toggle", "open", "close"))
    cs.set_defaults(func=cmd_cheatsheet)
    ch = sub.add_parser("claude-hook", help="record Claude Code activity (run by a Claude Code hook)")
    ch.set_defaults(func=cmd_claude_hook)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
