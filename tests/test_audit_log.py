"""Unit tests for app/audit_log.py — the opt-in (RESIDNA_AUDIT_LOG env var)
audit trail for generated PDF reports. Verifies the off-by-default behavior
(critical: this must stay off for the public demo deployment unless someone
deliberately opts it in), the on-behavior's record shape, and that raw
analytical data never ends up in the log.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import audit_log


@pytest.fixture
def isolated_log(tmp_path, monkeypatch):
    """Points LOG_DIR/LOG_FILE at a throwaway tmp_path dir instead of the
    real repo-root Logs/, so tests never touch (or depend on) real state."""
    log_dir = tmp_path / "Logs"
    monkeypatch.setattr(audit_log, "LOG_DIR", log_dir)
    monkeypatch.setattr(audit_log, "LOG_FILE", log_dir / "audit.log")
    return log_dir / "audit.log"


def _call(**overrides):
    kwargs = dict(
        uploaded_filename="experiment_001.xlsx",
        file_bytes=b"fake excel bytes",
        assay_name="Assay A",
        run_number="RUN-42",
        submitter_name="J. Doe",
        reviewer_name="A. Reviewer",
        system_suitability_status="PASS",
        sample_count=6,
    )
    kwargs.update(overrides)
    return audit_log.log_report_generated(**kwargs)


def test_disabled_by_default_is_a_noop(isolated_log, monkeypatch):
    monkeypatch.delenv("RESIDNA_AUDIT_LOG", raising=False)
    assert audit_log.is_enabled() is False
    result = _call()
    assert result is False
    assert not isolated_log.exists()


@pytest.mark.parametrize("value", ["1", "true", "True", "YES", "yes"])
def test_enabled_values(isolated_log, monkeypatch, value):
    monkeypatch.setenv("RESIDNA_AUDIT_LOG", value)
    assert audit_log.is_enabled() is True
    assert _call() is True
    assert isolated_log.exists()


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_disabled_values(isolated_log, monkeypatch, value):
    monkeypatch.setenv("RESIDNA_AUDIT_LOG", value)
    assert audit_log.is_enabled() is False
    assert _call() is False
    assert not isolated_log.exists()


def test_record_shape_and_content(isolated_log, monkeypatch):
    monkeypatch.setenv("RESIDNA_AUDIT_LOG", "1")
    _call(uploaded_filename="sample_data_001.xls", file_bytes=b"abc123")

    lines = isolated_log.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])

    assert record["event"] == "report_generated"
    assert record["uploaded_filename"] == "sample_data_001.xls"
    assert record["assay_name"] == "Assay A"
    assert record["run_number"] == "RUN-42"
    assert record["submitter_name"] == "J. Doe"
    assert record["reviewer_name"] == "A. Reviewer"
    assert record["system_suitability_status"] == "PASS"
    assert record["sample_count"] == 6
    # No st.login() configured in this test environment -> no authenticated identity
    assert record["authenticated_user"] is None
    # ISO 8601 timestamp, parseable
    from datetime import datetime
    datetime.fromisoformat(record["timestamp"])


def test_file_content_is_hashed_not_stored(isolated_log, monkeypatch):
    import hashlib

    monkeypatch.setenv("RESIDNA_AUDIT_LOG", "1")
    file_bytes = b"some uploaded excel file content"
    _call(file_bytes=file_bytes)

    record = json.loads(isolated_log.read_text().strip())
    assert record["uploaded_file_sha256"] == hashlib.sha256(file_bytes).hexdigest()
    # The raw bytes/content themselves must never appear in the log
    raw_log_text = isolated_log.read_text()
    assert file_bytes.decode() not in raw_log_text


def test_optional_fields_blank_become_none(isolated_log, monkeypatch):
    monkeypatch.setenv("RESIDNA_AUDIT_LOG", "1")
    _call(assay_name="", run_number="", submitter_name="", reviewer_name="")

    record = json.loads(isolated_log.read_text().strip())
    assert record["assay_name"] is None
    assert record["run_number"] is None
    assert record["submitter_name"] is None
    assert record["reviewer_name"] is None


def test_appends_multiple_records(isolated_log, monkeypatch):
    monkeypatch.setenv("RESIDNA_AUDIT_LOG", "1")
    _call(uploaded_filename="run1.xlsx")
    _call(uploaded_filename="run2.xlsx")

    lines = isolated_log.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["uploaded_filename"] == "run1.xlsx"
    assert json.loads(lines[1])["uploaded_filename"] == "run2.xlsx"


def test_no_quantitative_results_in_record(isolated_log, monkeypatch):
    """Privacy invariant: the audit record is identity/traceability metadata
    only — it must never grow a field carrying actual analytical results
    (DNA quantities, sample-level pass/fail detail, etc.)."""
    monkeypatch.setenv("RESIDNA_AUDIT_LOG", "1")
    _call()
    record = json.loads(isolated_log.read_text().strip())
    allowed_keys = {
        "timestamp", "event", "uploaded_filename", "uploaded_file_sha256",
        "assay_name", "run_number", "submitter_name", "reviewer_name",
        "authenticated_user", "system_suitability_status", "sample_count",
        "changed_criteria",
    }
    assert set(record.keys()) == allowed_keys


def test_changed_criteria_defaults_to_empty_list(isolated_log, monkeypatch):
    monkeypatch.setenv("RESIDNA_AUDIT_LOG", "1")
    _call()
    record = json.loads(isolated_log.read_text().strip())
    assert record["changed_criteria"] == []


def test_changed_criteria_recorded_when_given(isolated_log, monkeypatch):
    monkeypatch.setenv("RESIDNA_AUDIT_LOG", "1")
    overrides = [{"Criterion": "Quantity %CV Max", "Default": 25.0, "Used": 20.0}]
    _call(changed_criteria=overrides)
    record = json.loads(isolated_log.read_text().strip())
    assert record["changed_criteria"] == overrides
