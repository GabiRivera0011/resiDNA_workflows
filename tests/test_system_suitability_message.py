"""Tests for the System Suitability PASS/FAIL message in app/app.py —
confirms a FAIL identifies which category (STD Curve, ERC/PC, NTC, NEC)
actually failed, rather than just reporting FAIL with no detail, and that a
PASS stays a plain PASS with no trailing category list.
"""
from pathlib import Path

import pytest

from streamlit_stub import run_app

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "Data"


def _require_data_file(fname):
    path = DATA_DIR / fname
    if not path.exists():
        pytest.skip(f"{fname} not present locally (real data, not committed — see Data Privacy in README)")
    return path


@pytest.fixture(autouse=True)
def _restore_streamlit_module():
    import sys
    original = sys.modules.get("streamlit")
    yield
    if original is not None:
        sys.modules["streamlit"] = original
    else:
        sys.modules.pop("streamlit", None)


def test_fail_message_identifies_failed_category():
    # Real-world case: sample_data_001.xls fails NEC specifically, everything
    # else passes — the message must name NEC, not just say FAIL.
    path = _require_data_file("sample_data_001.xls")
    ns = run_app(REPO_ROOT, path)
    assert ns["status"] == "FAIL"
    assert ns["_status_detail"] == "FAIL — NEC"


def test_pass_message_has_no_category_detail():
    path = _require_data_file("sample_data_003.xls")
    ns = run_app(REPO_ROOT, path)
    assert ns["status"] == "PASS"
    assert ns["_status_detail"] == "PASS"


def test_failed_categories_list_matches_detail_string():
    path = _require_data_file("sample_data_001.xls")
    ns = run_app(REPO_ROOT, path)
    assert ns["_failed_categories"] == ["NEC"]
