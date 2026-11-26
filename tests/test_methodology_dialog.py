"""Tests for app/app.py's "How the Analysis Works" dialog — a read-only
methodology reference (companion to Edit Acceptance Criteria) covering the
math/pass-condition behind each suitability check. Confirms it only renders
when opened, that every section is present, and that displayed thresholds
track this session's active criteria (including overrides) rather than
always showing the shipped defaults — the same guarantee Edit Acceptance
Criteria gives the actual pass/fail checks.
"""
from pathlib import Path

import pytest

from streamlit_stub import run_app

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = REPO_ROOT / "Data" / "sample_data_001.xls"

METHODOLOGY_BUTTON = "📖 How the Analysis Works"


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


def _tables_with_columns(tables, columns):
    """Rendered tables whose columns exactly match `columns` — identifies a
    dialog section by its content shape rather than list position, since
    position shifts depending on where the button happens to fire relative
    to the main page's own tables."""
    return [t.data for t in tables if list(t.data.columns) == columns]


def test_dialog_not_rendered_unless_opened():
    _require_data_file()
    ns = run_app(REPO_ROOT, DATA_FILE)
    assert _tables_with_columns(ns["st"].tables, ["Step", "Rule"]) == []


def test_every_section_renders():
    _require_data_file()
    ns = run_app(REPO_ROOT, DATA_FILE, button_clicks=[METHODOLOGY_BUTTON])
    tables = ns["st"].tables

    criteria_tables = _tables_with_columns(tables, ["Check", "Formula", "Pass"])
    assert len(criteria_tables) == 3  # STD, Controls (ERC & PC), Spike Recovery
    checks_shown = {check for t in criteria_tables for check in t["Check"]}
    assert "R²" in checks_shown
    assert "PC %Recovery" in checks_shown
    assert "% Recovery" in checks_shown  # Spike Recovery's own row

    range_tables = _tables_with_columns(tables, ["Value", "Source", "Used For"])
    assert len(range_tables) == 1
    assert set(range_tables[0]["Value"]) == {"LOQ (Quantity)", "LOQ (Ct)", "STD Range"}

    steps_tables = _tables_with_columns(tables, ["Step", "Rule"])
    assert len(steps_tables) == 1
    # style_table() renders every cell to its display string (see
    # Scripts/plotting.py's format_value) — "Step" comes through as "1".."5",
    # not the int 1..5 it started as.
    assert list(steps_tables[0]["Step"]) == ["1", "2", "3", "4", "5"]

    next_step_tables = _tables_with_columns(tables, ["Next Step", "Meaning"])
    assert len(next_step_tables) == 1
    assert set(next_step_tables[0]["Next Step"]) == {
        "Reportable", "LOQ - Spike Test", "ULOQ - Adjust Dilution", "Retest",
    }


def test_thresholds_reflect_session_override():
    _require_data_file()
    ns = run_app(
        REPO_ROOT, DATA_FILE,
        session_state={"criteria_override_SAMPLE_QTY_CV_MAX": 18.5},
        button_clicks=[METHODOLOGY_BUTTON],
    )
    steps_table = _tables_with_columns(ns["st"].tables, ["Step", "Rule"])[0]
    rules = dict(zip(steps_table["Step"], steps_table["Rule"]))

    assert "18.5%" in rules["1"]  # triplicate rescue bound — overridden
    assert "18.5%" in rules["2"]  # Quantity %CV check — overridden
    assert "20%" in rules["4"]    # Linearity %Bias — left at its default

    criteria_tables = _tables_with_columns(ns["st"].tables, ["Check", "Formula", "Pass"])
    spike_table = next(t for t in criteria_tables if "% Recovery" in set(t["Check"]))
    spike_cv_row = spike_table[spike_table["Check"] == "Quantity %CV (triplicate)"].iloc[0]
    assert spike_cv_row["Pass"] == "≤ 18.5%"  # Spike Recovery reuses the same criterion
