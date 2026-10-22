# Architecture

`Panel.qml` is the bar widget entry point (manifest kind: `bar-widget` only).
It renders the Apex status in the Omarchy bar and shells out to `bin/apexctl`
(a Python CLI) for all device work. No QML-side device I/O.

Ownership map:

- `bin/apex/` — Python package: `daemon.py` (long-running control daemon),
  `cli.py` (`apexctl` command surface), `devices.py` (detects the
  connected keyboard and picks its OLED format and RGB transport),
  `rgb.py` (effects, OpenRGB SDK on 127.0.0.1:6742, backend selection),
  `hidrgb.py` (direct per-key HID RGB for the Apex Pro TKL Gen 3),
  `oled.py` (USB HID interface 1), `cheatsheet.py` (keybinding cheat sheet
  from `omarchy menu keybindings --print`), `workspaces.py` (Hyprland socket2
  workspace state), `claude.py` (Claude Code hook state
  and session summary for the `claude` OLED page), `wheel.py`, `hypr.py`
  (Hyprland integration), `mpris.py` (media titles for the OLED),
  `config.py`, `layout.py`, `render.py` (OLED frame rendering).
- `hooks/` — post-boot and theme-set hooks so lighting follows
  `omarchy theme set`.
- `systemd/apexctl.service` — user service for the daemon.
- `udev/99-steelseries-apex.rules` — hidraw permissions for the Apex 7 OLED.
- `udev/70-steelseries-apex-pro-tkl-gen3.rules` — Gen 3 control interface
  and wheel only; keystroke interfaces stay root-only.
- `install/`, `uninstall/` — opt-in install (the panel's Set up button) and
  clean removal.

State: device state lives in the `apexctl` daemon, not in QML. The panel is
stateless across reloads and re-reads state on demand. Destroying the widget
does not stop the daemon (documented deliberate choice; the daemon is owned
by the user systemd service).

External text rendered on the OLED or in tooltips uses explicit
`Text.PlainText` content. No Qt AutoText.

Node and Python/Pillow are development/runtime dependencies respectively;
Node is used only by portable checks, never by the runtime widget.

Do not declare additional manifest kinds (panel/overlay/menu/service) until
their entry points exist.
