# IT Update Checklist — resiDNA Streamlit App

For delivering an **update** to a resiDNA installation IT already has running (set up per [IT_Setup_Guide_OptionA.md](IT_Setup_Guide_OptionA.md)). This is a different, smaller process than a first-time handoff — if IT doesn't have this running yet, use [IT_Handoff_Checklist.md](IT_Handoff_Checklist.md) instead.

Company policy doesn't allow this folder to sync itself over the network — updates travel by copying files onto a USB drive. That means there's no CI catching a regression before it reaches the server; the step below is what stands in for that, and it's required every time, not just when something feels risky.

## 1. Verify before you copy anything

- [ ] Double-click `Verify_Before_Handoff.bat` and confirm it reports **"ALL TESTS PASSED."** If it reports a failure, stop — do not proceed with this update. Fix the issue, run it again, and only continue once it passes.
- [ ] If it reports some tests **skipped**, that's expected — the real company data files (`Data/*.xls`/`.xlsx`) aren't part of this folder, so the tests needing them can't run here. A skip is not a pass; it just means that particular check didn't execute in this environment. It's normal and not a reason to stop.

## 2. Check what actually changed

- [ ] Open `CHANGELOG.md` and read the entries newer than the version currently running on the server (visible in the app itself, under the title, and in the footer of any PDF it's generated — compare against `APP_VERSION` in `app/app.py` here). This tells you what the update actually does, not just that one exists.

## 3. What to copy onto the USB drive

Replace the whole `app/` and `Scripts/` folders on the server with the current versions here, rather than copying individual files — safer than guessing which specific files changed, and avoids ending up with a mismatched mix of old and new code.

- [ ] `app/` (whole folder) — but **not** `app/assets/logo.png` if the server's copy is the real company logo and this copy is still the placeholder; check before overwriting.
- [ ] `Scripts/` (whole folder)
- [ ] `tests/` (whole folder), if IT is carrying tests along — for their own post-update verification, see step 5
- [ ] Anything new called out in `CHANGELOG.md` that isn't already part of the running install (e.g. the first time `Run_resiDNA_App.bat` / `Create_Desktop_Shortcut.ps1` / `app/assets/resiDNA.ico` are introduced)

**Do not copy** `.streamlit/secrets.toml`, `Data/`, `Logs/`, or `Results/` — those are server-specific state, not part of the app's code, and copying over `secrets.toml` in particular would overwrite the server's real credentials with whatever (or nothing) is in this folder.

## 4. What IT does with it

- [ ] Stop the service: `sudo systemctl stop residna` (Linux) or the equivalent for however it's running (see [IT_Setup_Guide_OptionA.md](IT_Setup_Guide_OptionA.md) step 4).
- [ ] Replace the files from step 3 in the server's install directory.
- [ ] If `app/requirements.txt` changed (check `CHANGELOG.md`), reinstall dependencies into the server's existing `.venv` before restarting: `.venv/bin/pip install -r app/requirements.txt`.
- [ ] Restart the service: `sudo systemctl start residna` (or `restart`, if it never fully stopped). Streamlit does not hot-reload code changes — the service must actually restart for an update to take effect.

## 5. Confirm the update actually took

- [ ] Open the app and check the version shown under the title matches what you just delivered (the same `APP_VERSION` from `CHANGELOG.md`'s newest entry). If it still shows the old version, the restart didn't pick up the new files — check the service status and the install directory before assuming anything else is wrong.
- [ ] Spot-check whatever `CHANGELOG.md` says actually changed — e.g., if this update touched the ERC/PC rescue logic, upload a real file and confirm that section of the report looks right, rather than just confirming the app loads at all.
- [ ] If `tests/` was carried along and IT wants their own independent check: `pytest tests -v` from the server (same skip caveat as step 1 — `Data/` won't be present there either, by design).
