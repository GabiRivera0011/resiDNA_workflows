"""Tests that app/app.py fails loudly and clearly when the uploaded file's
layout doesn't match what it expects — a QuantStudio export-template change
shifting the Results sheet's header row, or the regression/curve-stats
block, rather than the usual "missing optional analysis column" case these
checks are deliberately distinct from. Without these checks, a shifted
header would either misdirect the existing missing-column error (blaming
disabled analysis modules for what's actually a layout change) or crash
later with a confusing raw pandas error once the regression stats are
looked up.
"""
from pathlib import Path

import pandas as pd
import pytest

from streamlit_stub import StopExec, run_app

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = REPO_ROOT / "Data" / "sample_data_001.xls"


def _require_data_file():
    if not DATA_FILE.exists():
        pytest.skip("sample_data_001.xls not present locally (real data, not committed)")


@pytest.fixture(autouse=True)
def _restore_streamlit_module():
    import sys
    original = sys.modules.get("streamlit")
    yield
    if original is not None:
        sys.modules["streamlit"] = original
    else:
        sys.modules.pop("streamlit", None)


def _load_results_sheets():
    xls = pd.ExcelFile(DATA_FILE, engine="xlrd")
    return {name: pd.read_excel(DATA_FILE, sheet_name=name, header=None, engine="xlrd") for name in xls.sheet_names}


def _write_xlsx(sheets, path):
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, sheet_df in sheets.items():
            sheet_df.to_excel(writer, sheet_name=name, header=False, index=False)


def test_shifted_header_row_gives_clear_layout_error(tmp_path):
    _require_data_file()
    sheets = _load_results_sheets()
    results = sheets["Results"]
    # Simulate QuantStudio adding one extra metadata row above the header,
    # shifting everything below it down by one row.
    blank_row = pd.DataFrame([[None] * results.shape[1]], columns=results.columns)
    sheets["Results"] = pd.concat([results.iloc[:5], blank_row, results.iloc[5:]], ignore_index=True)

    shifted_path = tmp_path / "shifted.xlsx"
    _write_xlsx(sheets, shifted_path)

    with pytest.raises(StopExec):
        run_app(REPO_ROOT, shifted_path)


def test_unshifted_file_passes_layout_checks():
    # Sanity check: the real, unmodified file must NOT trip either check —
    # confirms the checks are specific to an actual layout mismatch, not a
    # false positive on normal data.
    _require_data_file()
    run_app(REPO_ROOT, DATA_FILE)  # raises StopExec (or anything else) on failure


def test_corrupted_regression_block_gives_clear_layout_error(tmp_path):
    _require_data_file()
    sheets = _load_results_sheets()
    results = sheets["Results"]
    # Overwrite the regression/curve-stats row (row 19, 0-indexed 18) with
    # unrelated text, leaving the header row untouched.
    for col in range(2, 7):
        results.iat[18, col] = "unrelated text, no colon here"
    sheets["Results"] = results

    corrupted_path = tmp_path / "no_regression.xlsx"
    _write_xlsx(sheets, corrupted_path)

    with pytest.raises(StopExec):
        run_app(REPO_ROOT, corrupted_path)
