# Project instructions

This is Deskset (`io.github.micahelj.deskset`), an Omarchy shell plugin for the
SteelSeries Apex 7 / Apex 7 TKL / Apex Pro TKL Gen 3 (per-key RGB, the
128×40 OLED, the OLED scroll wheel) and Logitech HID++ mice such as the G502. Per-device differences live in
`bin/apex/devices.py`. Read README.md and ARCHITECTURE.md before changes.

- Run `./tests/run`. On the target Omarchy machine also run
  `omarchy plugin validate .` and record the installed `omarchy-version`.
- Use [build-omarchy-plugins](https://github.com/tcballard/build-omarchy-plugins)
  guidance and verify current upstream contracts before relying on
  version-specific APIs.
- Preserve the centered README title, single category badge where applicable,
  and prominent original-project credit. Do not claim a screenshot, package
  listing or supported version without evidence.
- Keep settings owned by this project. Removal must preserve user data and
  unrelated desktop configuration.
- Use focused tests for changed behaviour. Portable checks do not establish
  live acceptance.
- SHA-pin workflow actions, minimize token permissions, keep authoring files
  out of installed runtime payloads.
- Keep release notes outcome-focused.
- Never edit `.template/blueprint` to change an initialized product; those
  files retain starter provenance. Edit product files directly.
- The `bin/apex` Python package, `hooks/`, `systemd/`, and `udev/` are runtime
  payloads installed by the panel on first load. Changing their interfaces
  requires matching changes in `Panel.qml` and this README.
