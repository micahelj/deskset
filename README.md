<h1 align="center">Apex Keyboard</h1>

<p align="center">Omarchy shell plugin for SteelSeries Apex keyboards:
per-key RGB, the 128×40 OLED, and the OLED scroll wheel.</p>

## Supported keyboards

| Keyboard | USB ID | OLED | RGB | Wheel |
|---|---|---|---|---|
| Apex 7 TKL | `1038:1618` | yes | via OpenRGB | yes |
| Apex 7 | `1038:1612` | yes | via OpenRGB | yes |
| Apex Pro TKL Gen 3 | `1038:1642` | yes | direct HID (no OpenRGB) | yes |

The connected keyboard is detected automatically. On the Apex Pro TKL Gen 3
the `reactive` lighting mode is hidden, because it needs read access to the
keystroke interfaces, which the Gen 3 udev rule deliberately withholds.

## Install

```bash
omarchy plugin add https://github.com/davidzu/sonic.apex.git --enable
```

That clones the plugin, validates it, and enables the bar widget. Nothing
else is installed until you open the widget and click **Set up background
service**, which:

- puts `apexctl` on `PATH` (`~/.local/bin`)
- enables the `apexctl` user systemd service
- installs theme-set and post-boot hooks so lighting follows `omarchy theme set`

### Requirements

- Omarchy (Hyprland + Quickshell)
- Python 3 with Pillow (`omarchy pkg add python-pillow` if it is missing)
- Apex 7 / Apex 7 TKL only: [OpenRGB](https://openrgb.org/) for RGB
  (`omarchy pkg add openrgb`), with its SDK server on `127.0.0.1:6742`

Start OpenRGB once (Apex 7 / Apex 7 TKL):

```bash
systemctl --user enable --now openrgb.service
```

If that unit does not exist yet:

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/openrgb.service <<'EOF'
[Unit]
Description=OpenRGB SDK server
After=graphical-session.target

[Service]
ExecStart=/usr/bin/openrgb --server --server-port 6742
Restart=on-failure

[Install]
WantedBy=graphical-session.target
EOF
systemctl --user enable --now openrgb.service
```

### HID permissions

The OLED (and Gen 3 RGB) talk to USB HID interface 1. Install the udev rule
for your keyboard if `apexctl status` shows the OLED as missing:

```bash
# Apex 7 / Apex 7 TKL
sudo cp ~/.config/omarchy/plugins/io.github.davidzu.sonic_apex/udev/99-steelseries-apex.rules /etc/udev/rules.d/
# Apex Pro TKL Gen 3 (control interface and wheel only, not keystrokes)
sudo cp ~/.config/omarchy/plugins/io.github.davidzu.sonic_apex/udev/70-steelseries-apex-pro-tkl-gen3.rules /etc/udev/rules.d/

sudo udevadm control --reload && sudo udevadm trigger
```

Unplug/replug the keyboard if it still cannot open the device.

## Use it

Click the **Apex Keyboard** widget in the bar (right section) to open the
panel: RGB effects, OLED pages (clock, media, workspace, logo), and wheel
modes.

CLI examples:

```bash
apexctl status
apexctl rgb wave --speed 60
apexctl oled clock
apexctl wheel workspace
```

## Remove

```bash
~/.config/omarchy/plugins/io.github.davidzu.sonic_apex/uninstall
omarchy plugin remove io.github.davidzu.sonic_apex
```

`uninstall` stops the service and removes the `apexctl` link and hooks; your
settings in `~/.config/omarchy/apex.json` are kept. Remove any udev rule you
copied into `/etc/udev/rules.d/` by hand.

## Development

Run the portable checks from the repository root:

```bash
./tests/run
```

On the target Omarchy machine also run `omarchy plugin validate .` and record
the installed `omarchy-version`. Portable validation covers structure and
metadata only; it does not establish live desktop compatibility. Record
actual tests in [docs/ACCEPTANCE.json](docs/ACCEPTANCE.json).

[Architecture](ARCHITECTURE.md) · [Developing](docs/DEVELOPMENT.md) · [Release process](docs/RELEASE.md) · [Contributing](CONTRIBUTING.md)

## Credits

Apex Keyboard is by [David Zúñiga](https://github.com/davidzu), built from
[omarchy-plugin-template](https://github.com/tcballard/omarchy-plugin-template)
guidance and the Omarchy template set. The Apex Pro TKL Gen 3 OLED and RGB
protocol comes from
[apex-pro-tkl-gen3-linux](https://github.com/SilasDaSilva/apex-pro-tkl-gen3-linux)
by [@SilasDaSilva](https://github.com/SilasDaSilva) (MIT). See [CREDITS.md](CREDITS.md).

## Licence

[MIT](LICENSE).
