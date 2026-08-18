"""Audit logging for the resiDNA Streamlit app — app.py-only (the notebook is a
local, single-user prototype tool, not a shared server, so it has no audit
concern to log). Appends one JSON-Lines record per PDF report a user actually
generates, for compliance traceability of who ran what against what upload.

Deliberately excludes analytical results/quantities: only identity/
traceability metadata is recorded (who, when, which file, pass/fail), keeping
the same "don't persist sensitive lab data" posture the app already has for
everything else — see README's Data Privacy & Security section.

**Off by default.** Set the RESIDNA_AUDIT_LOG environment variable (any of
"1"/"true"/"yes", case-insensitive) to enable. This means the public
Streamlit Community Cloud demo keeps its current documented behavior (nothing
written to disk) unless someone deliberately opts it in, while the on-prem
Option A deployment (see IT_Deployment_Guide.md) sets the variable as part of
its service setup. See IT_Setup_Guide_OptionA.md for the exact step.

Logs one event per report actually generated/downloaded, not every upload the
app processes — see app.py's "Download PDF Report" button for the single call
site. An exploratory upload that's never downloaded as a PDF isn't logged; if
your compliance policy requires logging every upload regardless of whether a
report is downloaded, this needs a second call site at the upload/parse step.

Also records which acceptance criteria (if any) differed from their shipped
defaults for this report — see app.py's "Edit Acceptance Criteria" dialog.
Those overrides are session-only (never persisted, never shared across
users), so this log entry is the only durable record that a report was
generated with non-default thresholds.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "Logs"
LOG_FILE = LOG_DIR / "audit.log"


def is_enabled():
    """Reads the env var fresh on every call (rather than once at import time)
    so tests can flip it with monkeypatch without reloading the module."""
    return os.environ.get("RESIDNA_AUDIT_LOG", "").strip().lower() in ("1", "true", "yes")


def _authenticated_identity():
    """Returns the logged-in user's identity if `st.login()` has been
    configured (IT_Deployment_Guide.md Option A step 4), else None. Safe to
    call even when auth isn't set up — `st.user` (and this function) return no
    identity rather than raising, so this file needs no change when
    authentication is added later; it starts returning a real value
    automatically.
    """
    try:
        import streamlit as st
        user = st.user
        if getattr(user, "is_logged_in", False):
            return getattr(user, "email", None) or getattr(user, "name", None)
    except Exception:
        pass
    return None


def log_report_generated(
    *, uploaded_filename, file_bytes, assay_name, run_number,
    submitter_name, reviewer_name, system_suitability_status, sample_count,
    changed_criteria=None,
):
    """Appends one audit record for a generated/downloaded PDF report. No-op
    (returns False) if audit logging isn't enabled; returns True if a record
    was written.

    `file_bytes` is hashed (SHA-256), not stored — this makes the log
    traceable to a specific upload (two records with the same hash are
    provably the same file) without persisting the uploaded data itself.

    `changed_criteria`, if given, is a list of {"Criterion", "Default",
    "Used"} dicts (app.py's `changed_criteria`) — acceptance criteria that
    differed from their shipped default for this report. Recorded as-is
    (criteria/threshold values, not analytical results, so this doesn't
    conflict with the "no analytical data" rule above); an empty list when
    every criterion was left at its default.
    """
    if not is_enabled():
        return False

    LOG_DIR.mkdir(exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "report_generated",
        "uploaded_filename": uploaded_filename,
        "uploaded_file_sha256": hashlib.sha256(file_bytes).hexdigest(),
        "assay_name": assay_name or None,
        "run_number": run_number or None,
        "submitter_name": submitter_name or None,
        "reviewer_name": reviewer_name or None,
        "authenticated_user": _authenticated_identity(),
        "system_suitability_status": system_suitability_status,
        "sample_count": sample_count,
        "changed_criteria": changed_criteria or [],
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return True
