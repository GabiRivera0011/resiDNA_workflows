# IT Update Checklist — resiDNA Streamlit App

This checklist governs installation of an **update** delivered on a USB drive, onto a resiDNA installation already running (set up per [IT_Setup_Guide_OptionA.md](IT_Setup_Guide_OptionA.md)). It is a smaller, separate process from a first-time handoff. If the installation does not yet exist, use [IT_Handoff_Checklist.md](IT_Handoff_Checklist.md) instead.

The delivered folder has already been verified by the preparer before handoff, so this checklist covers installation and confirmation only.

## 1. Installation steps

- [ ] Stop the service: `sudo systemctl stop residna` (Linux), or the equivalent for the hosting environment in use (see [IT_Setup_Guide_OptionA.md](IT_Setup_Guide_OptionA.md), Step 4).
- [ ] Replace the `app/` and `Scripts/` folders in the server's install directory with the delivered versions, in their entirety rather than file by file — excluding `app/assets/logo.png` if the server holds the real logo and the delivered copy is still the placeholder; confirm before overwriting.
- [ ] Do not overwrite `.streamlit/secrets.toml`, `Data/`, `Logs/`, or `Results/` with anything from the delivered folder. These hold server-specific state rather than application code; overwriting `secrets.toml` in particular would replace the server's real credentials with whatever the delivered folder contains, or nothing at all.
- [ ] If `app/requirements.txt` changed (per the delivered `CHANGELOG.md`), reinstall dependencies into the existing `.venv` before restarting: `.venv/bin/pip install -r app/requirements.txt`.
- [ ] Restart the service: `sudo systemctl start residna` (or `restart`, if it did not fully stop). Streamlit does not hot-reload code changes; the service must restart for the update to take effect.

## 2. Confirm the update took effect

- [ ] Open the app and confirm the version shown under the title matches the delivered version (the `APP_VERSION` from the newest `CHANGELOG.md` entry). A persisting old version indicates the restart did not pick up the new files; check service status and the install directory before investigating further.
- [ ] Spot-check the specific change described in `CHANGELOG.md` — for example, if the update touched ERC/PC rescue logic, upload a real file and confirm that section of the report, rather than confirming only that the app loads.
- [ ] Optional, for independent verification: if `tests/` was included in the delivered folder, run `pytest tests -v` from the server. Some tests will report as skipped, since the data files (`Data/*.xls`/`.xlsx`) are not part of the delivered folder; a skip is distinct from a failure and does not indicate a problem.
