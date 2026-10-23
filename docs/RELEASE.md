# Release process

1. Update `version` in `manifest.json` and this repository's tagged state.
2. Run `./tests/run` and `omarchy plugin validate .` on a real Omarchy host;
   record results and the installed `omarchy-version` in docs/ACCEPTANCE.json.
3. Verify the documented install command actually works on a clean clone:

   ```bash
   omarchy plugin add https://github.com/micahelj/deskset.git --enable
   ```

4. Draft outcome-focused release notes (what changed for the user, not the diff).
5. Tag the release on `main` after CI is green.
