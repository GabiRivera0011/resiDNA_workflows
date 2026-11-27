# IT Update Checklist — resiDNA Streamlit App

This checklist governs delivery of an **update** to a resiDNA installation already running (set up per [IT_Setup_Guide_OptionA.md](IT_Setup_Guide_OptionA.md)). It is a smaller, separate process from a first-time handoff. If the installation does not yet exist, use [IT_Handoff_Checklist.md](IT_Handoff_Checklist.md) instead.

Because no CI pipeline catches a regression before it reaches the server, Step 1 serves that function and is required for every update, regardless of how minor the change appears.

Steps 1 through 3 are performed before handoff, by whoever is preparing the update. Step 4 is performed by IT, on the server. Step 5 is a joint confirmation: the version check can be done by either party, and the independent test run is IT's if chosen.

## 1. Verify before copying (preparer)

- [ ] Run `Verify_Before_Handoff.bat` and confirm it reports **"ALL TESTS PASSED."** A reported failure means the update must not proceed; resolve the issue, rerun the script, and continue only once it passes.
- [ ] A report of **skipped** tests is expected: the data files (`Data/*.xls`/`.xlsx`) are not part of this folder, so tests depending on them cannot run here. A skip is distinct from a pass and does not indicate a problem.

## 2. Review what changed (preparer)

- [ ] Open `CHANGELOG.md` and review entries newer than the version currently running on the server (shown under the app's title and in the footer of any generated PDF; compare against `APP_VERSION` in `app/app.py`). This identifies the scope of the update, not merely its existence.

## 3. Files to copy onto the USB drive (preparer)

The `app/` and `Scripts/` folders should be replaced in their entirety rather than copied file by file, which avoids guessing at individual changes and prevents a mismatched mix of old and new code.

- [ ] `app/` (entire folder) — excluding `app/assets/logo.png` if the server holds the logo and this copy is still the placeholder; confirm before overwriting.
- [ ] `Scripts/` (entire folder)
- [ ] `tests/` (entire folder), if IT intends to run its own post-update verification (see Step 5)
- [ ] Any new item identified in `CHANGELOG.md` that is not yet part of the running installation (for example, the first introduction of `Run_resiDNA_App.bat`, `Create_Desktop_Shortcut.ps1`, or `app/assets/resiDNA.ico`)

**Excluded from copying:** `.streamlit/secrets.toml`, `Data/`, `Logs/`, and `Results/`. These hold server-specific state rather than application code; overwriting `secrets.toml` in particular would replace the server's real credentials with whatever this folder contains, or nothing at all.

## 4. Installation steps (IT)

- [ ] Stop the service: `sudo systemctl stop residna` (Linux), or the equivalent for the hosting environment in use (see [IT_Setup_Guide_OptionA.md](IT_Setup_Guide_OptionA.md), Step 4).
- [ ] Replace the files identified in Step 3 within the server's install directory.
- [ ] If `app/requirements.txt` changed (per `CHANGELOG.md`), reinstall dependencies into the existing `.venv` before restarting: `.venv/bin/pip install -r app/requirements.txt`.
- [ ] Restart the service: `sudo systemctl start residna` (or `restart`, if it did not fully stop). Streamlit does not hot-reload code changes; the service must restart for the update to take effect.

## 5. Confirm the update took effect (joint)

- [ ] Open the app and confirm the version shown under the title matches the delivered version (the `APP_VERSION` from the newest `CHANGELOG.md` entry). A persisting old version indicates the restart did not pick up the new files; check service status and the install directory before investigating further.
- [ ] Spot-check the specific change described in `CHANGELOG.md` — for example, if the update touched ERC/PC rescue logic, upload a real file and confirm that section of the report, rather than confirming only that the app loads.
- [ ] If `tests/` was carried along and IT requires independent verification: run `pytest tests -v` from the server (the same skip caveat from Step 1 applies, since `Data/` will not be present there either, by design).
