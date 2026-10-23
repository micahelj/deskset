# Develop and test the plugin

Run `./tests/run` from the repository root (requires Node.js 22+; no npm
install needed). On the target Omarchy machine run `omarchy plugin validate .`
and record the installed `omarchy-version`.

Portable checks validate a deliberately narrow structural subset; the
installed host's validator is authoritative.

Live checks to perform before releasing:

- horizontal and vertical bar layouts
- disable/re-enable via `omarchy plugin disable|enable io.github.micahelj.deskset`
- shell reload and `omarchy-shell shell rescanPlugins`
- monitor connect/disconnect and theme changes
- `apexctl` daemon start/stop/restart under the user systemd service
- removal: `omarchy plugin remove io.github.micahelj.deskset --yes` must not leave the
  `apexctl` service running or orphaned hooks behind

Use your current Omarchy plugin development/linking workflow or Plugin
Workbench after inspecting its current commands. The included
`.omarchy-workbench.json` proposes checks; it does not grant trust or execute
them automatically.

Before a public release, document the exact verified install command and the
installed host version in README.md and docs/ACCEPTANCE.json.
