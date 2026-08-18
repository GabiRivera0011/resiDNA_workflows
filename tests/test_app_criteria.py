"""Tests for app/app.py's Edit Acceptance Criteria feature: session-only
threshold overrides (via st.session_state, seeded here to simulate the
dialog), and the changed-criteria reporting that surfaces on-screen, in the
PDF, and in the audit log whenever a report is generated with non-default
thresholds.
"""
from pathlib import Path

import pytest

from streamlit_stub import run_app

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


def test_no_overrides_uses_defaults_and_reports_no_changes():
    _require_data_file()
    ns = run_app(REPO_ROOT, DATA_FILE)
    assert ns["SAMPLE_QTY_CV_MAX"] == ns["DEFAULT_SAMPLE_QTY_CV_MAX"] == 25.0
    assert ns["changed_criteria"] == []
    assert ns["st"].warnings == []  # no "non-default criteria" notice shown


def test_single_override_is_applied_and_reported():
    _require_data_file()
    ns = run_app(
        REPO_ROOT, DATA_FILE,
        session_state={"criteria_override_SAMPLE_QTY_CV_MAX": 20.0},
    )
    assert ns["SAMPLE_QTY_CV_MAX"] == 20.0
    assert ns["changed_criteria"] == [
        {"Criterion": "Quantity %CV Max", "Default": 25.0, "Used": 20.0}
    ]
    # every other criterion stays at its default
    assert ns["STD_R2_MIN"] == ns["DEFAULT_STD_R2_MIN"]
    assert ns["SAMPLE_SPIKE_RECOVERY_MIN"] == ns["DEFAULT_SAMPLE_SPIKE_RECOVERY_MIN"]
    # on-screen notice fired
    assert len(ns["st"].warnings) == 1


def test_override_equal_to_default_is_not_reported_as_changed():
    _require_data_file()
    ns = run_app(
        REPO_ROOT, DATA_FILE,
        session_state={"criteria_override_SAMPLE_QTY_CV_MAX": 25.0},  # same as default
    )
    assert ns["SAMPLE_QTY_CV_MAX"] == 25.0
    assert ns["changed_criteria"] == []
    assert ns["st"].warnings == []


def test_multiple_overrides_across_groups():
    _require_data_file()
    ns = run_app(
        REPO_ROOT, DATA_FILE,
        session_state={
            "criteria_override_STD_R2_MIN": 0.95,
            "criteria_override_SAMPLE_SPIKE_RECOVERY_MAX": 130.0,
        },
    )
    assert ns["STD_R2_MIN"] == 0.95
    assert ns["SAMPLE_SPIKE_RECOVERY_MAX"] == 130.0
    criteria_names = {c["Criterion"] for c in ns["changed_criteria"]}
    assert criteria_names == {"R² Min", "%Recovery Max"}


def _pdf_text(ns):
    # doc.build(pdf_story) mutates/drains the story list in place as part of
    # reportlab's own pagination (a reportlab implementation detail, not
    # something app.py does) — so pdf_story is empty by the time exec()
    # returns. Reading the actually-generated PDF bytes instead sidesteps
    # that and verifies the real deliverable's content directly.
    from pypdf import PdfReader
    reader = PdfReader(ns["pdf_buffer"])
    return "".join(page.extract_text() for page in reader.pages)


def test_changed_criteria_included_in_pdf():
    _require_data_file()
    ns = run_app(
        REPO_ROOT, DATA_FILE,
        session_state={"criteria_override_SAMPLE_QTY_CV_MAX": 20.0},
    )
    assert "Modified Acceptance Criteria" in _pdf_text(ns)


def test_no_changed_criteria_section_in_pdf_when_nothing_overridden():
    _require_data_file()
    ns = run_app(REPO_ROOT, DATA_FILE)
    assert "Modified Acceptance Criteria" not in _pdf_text(ns)


def test_changed_criteria_reaches_audit_log(monkeypatch, tmp_path):
    _require_data_file()
    monkeypatch.setenv("RESIDNA_AUDIT_LOG", "1")

    # audit_log.log_report_generated() looks up LOG_DIR/LOG_FILE from its own
    # module globals at call time, so patching them here redirects the real
    # write even though app.py imports the function by name (`from audit_log
    # import log_report_generated`) rather than referencing the module.
    import audit_log
    log_dir = tmp_path / "Logs"
    monkeypatch.setattr(audit_log, "LOG_DIR", log_dir)
    monkeypatch.setattr(audit_log, "LOG_FILE", log_dir / "audit.log")

    run_app(
        REPO_ROOT, DATA_FILE,
        session_state={"criteria_override_SAMPLE_QTY_CV_MAX": 20.0},
        button_clicks=["Download PDF Report"],
    )

    log_file = log_dir / "audit.log"
    assert log_file.exists()
    import json
    record = json.loads(log_file.read_text().strip().splitlines()[-1])
    assert record["changed_criteria"] == [
        {"Criterion": "Quantity %CV Max", "Default": 25.0, "Used": 20.0}
    ]
