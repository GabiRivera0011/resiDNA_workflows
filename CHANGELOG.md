# Changelog

All notable changes to the resiDNA Sample Analysis Tool, by version. The
version shown here matches `APP_VERSION` in `app/app.py` — visible on-screen
under the app's title and in the footer of every generated PDF report, so a
specific running copy or a specific report can always be traced back to the
entry below that produced it.

## 2026.11.27

- Added a read-only **"How the Analysis Works"** popup explaining the math/logic behind every pass/fail check.
- Added an outlier flag (`(?)`) on the STD Curve Points table, identifying a single well driving an out-of-range Ct %CV, for manual review. Diagnostic only — never changes a reported value.
- ERC/PC controls now get the same single-outlier-exclusion rescue Samples already had; % Recovery is recomputed from the rescued quantity instead of read from the instrument.
- Fixed Spike Recovery's % Recovery: real export data showed the instrument's own value doesn't subtract the unspiked baseline. Now genuinely computed, with an Undetermined/missing unspiked counterpart treated as a zero baseline.
- System Suitability FAIL now names which category failed (STD Curve, ERC/PC, NTC, or NEC) instead of a bare FAIL, on-screen and in the PDF.
- Raised the STD/ERC-PC Quantity %CV threshold from 20% to 25%, for consistency with the Sample threshold.
- Fixed `resolve_sample_replicates()` returning a columnless DataFrame when given zero rows, which could break downstream lookups.
- Fixed `style_table()`'s underlying table having no explicit width, which could cause long cell text to wrap unnecessarily.
- Fixed `st.plotly_chart(..., use_container_width=False)` across all chart calls — Streamlit deprecated this parameter (removed after 2025-12-31); replaced with `width="content"`.
- Added `Run_resiDNA_App.bat` (double-click launcher, no terminal needed) and `Create_Desktop_Shortcut.ps1` (one-time Desktop icon setup), plus the icon itself (`app/assets/resiDNA.ico`). The launcher now also re-installs dependencies automatically whenever `app/requirements.txt` changes, not just on first run.
- Added this version indicator (`APP_VERSION`), shown on-screen and in the PDF footer.
- Added validation of the uploaded file's layout before parsing proceeds: confirms the Results sheet's header is where expected (row 23) and the regression/curve-stats block parses to the expected keys, failing with a clear "export template may have changed" message instead of a confusing crash or a misleading "missing analysis module" error.

## Earlier history

Not retroactively versioned — see `git log` for the full commit history prior to this changelog's introduction.
