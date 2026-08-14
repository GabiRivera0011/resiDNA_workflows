"""Golden-value regression test: runs the real app/app.py against the local
`Data/` sample files and checks final_results / reportable_results against
known-good values, so a future change to the Sample Suitability pipeline
(qpcr.py, or app.py's own assembly of it) that silently changes a result gets
caught automatically instead of requiring a manual re-verification pass.

`Data/*.xls` / `*.xlsx` are real (scrubbed) company assay data and are
deliberately NOT committed to the repo (see README's Data Privacy section and
git history) — only present locally. Every test here is skipped, not failed,
when its file isn't present, so this suite still passes in a fresh clone/CI.

Golden values were captured from a verified-correct run (see git history for
the Sample Suitability methodology this pipeline implements) via
`tests/streamlit_stub.run_app` against each file in `Data/`. If a change
*intentionally* moves these numbers, re-capture and update GOLDEN below —
don't just loosen the tolerance.
"""
from pathlib import Path

import pytest

from streamlit_stub import StopExec, run_app

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "Data"

# sample_name -> (total_dna_ng_per_ml, dna_per_protein_ng_per_mg, sample_passed)
GOLDEN = {
    "sample_data_001.xls": {
        "S1": (24471.731166666665, 26892.012300000002, True),
        "S2": (18915.958566666668, 15254.805300000002, True),
        "S3": (28300.51833333333, 19790.572266666666, True),
        "S4": (2.7433, 3.919, True),
        "S5": (16181.3186, 19733.315366666666, True),
        "S6": (37847.0709, 31022.189266666664, True),
    },
    "sample_data_002.xls": {
        "S1": (8.767133333333334, 1.0791666666666668, True),
        "S2": (0.0028, 0.0002, False),
        "S3": (0.0102, 0.0007, True),
        "S4": (6.473533333333333, 1.1979333333333333, True),
        "S5": (0.0122, 0.001, True),
        "S6": (0.0023, 0.00016666666666666666, False),
    },
    "sample_data_003.xls": {
        "S1": (1.3238333333333334, 0.20183333333333334, True),
        "S2": (0.0086, 0.0008, True),
        "S3": (0.0020333333333333336, 0.00016666666666666666, False),
        "S4": (6.248, 1.2520666666666667, True),
        "S5": (0.0037, 0.0003, True),
        "S6": (0.0131, 0.0011, True),
    },
    "sample_data_004.xls": {
        "S1": (0.0012000000000000001, 9.237288135593221e-05, False),
        "S2": (0.0075, 0.0008, True),
        "S3": (0.0027, 0.0003, False),
        "S4": (0.0031, 0.0007, True),
        "S5": (0.0072, 0.0008, True),
        "S6": (0.0354, 0.0035, True),
        "S7": (0.0063, 0.0006, True),
        "S8": (41697.09365, 25581.03905, True),
    },
    "experiment_001.xlsx": {
        "S1": (0.000375, 0.0002, False),
    },
}


def _require_data_file(fname):
    path = DATA_DIR / fname
    if not path.exists():
        pytest.skip(f"{fname} not present locally (real data, not committed — see Data Privacy in README)")
    return path


@pytest.fixture(autouse=True)
def _restore_streamlit_module():
    # run_app() replaces sys.modules["streamlit"] with a fake; make sure that
    # doesn't leak into other tests run in the same process.
    import sys
    original = sys.modules.get("streamlit")
    yield
    if original is not None:
        sys.modules["streamlit"] = original
    else:
        sys.modules.pop("streamlit", None)


@pytest.mark.parametrize("fname", list(GOLDEN))
def test_reportable_results_matches_golden_values(fname):
    path = _require_data_file(fname)
    try:
        ns = run_app(REPO_ROOT, path)
    except StopExec:
        pytest.fail(f"{fname}: app called st.stop() — file is missing a required column")

    reportable_results = ns["reportable_results"].set_index("Sample #")
    expected = GOLDEN[fname]

    assert sorted(reportable_results.index) == sorted(expected), (
        f"{fname}: sample set changed — expected {sorted(expected)}, "
        f"got {sorted(reportable_results.index)}"
    )
    for sample, (total_dna, dna_per_protein, sample_passed) in expected.items():
        row = reportable_results.loc[sample]
        assert row["Total DNA (ng/mL)"] == pytest.approx(total_dna, rel=1e-6), (
            f"{fname}/{sample}: Total DNA (ng/mL) regressed"
        )
        assert row["DNA per Protein (ng/mg)"] == pytest.approx(dna_per_protein, rel=1e-6), (
            f"{fname}/{sample}: DNA per Protein (ng/mg) regressed"
        )
        assert bool(row["Sample Passed"]) == sample_passed, (
            f"{fname}/{sample}: Sample Passed regressed"
        )


@pytest.mark.parametrize("fname", list(GOLDEN))
def test_final_results_suitability_is_binary(fname):
    path = _require_data_file(fname)
    try:
        ns = run_app(REPO_ROOT, path)
    except StopExec:
        pytest.fail(f"{fname}: app called st.stop() — file is missing a required column")

    suitability_values = set(ns["final_results"]["Suitability"].unique())
    assert suitability_values <= {"Pass", "Fail"}, (
        f"{fname}: Suitability must be binary (Pass/Fail only), got {suitability_values}"
    )


@pytest.mark.parametrize("fname", list(GOLDEN))
def test_all_base_samples_are_reported(fname):
    path = _require_data_file(fname)
    try:
        ns = run_app(REPO_ROOT, path)
    except StopExec:
        pytest.fail(f"{fname}: app called st.stop() — file is missing a required column")

    base_sample_ids = sorted(ns["samples_df"]["base_sample"].unique())
    reported_ids = sorted(ns["reportable_results"]["Sample #"])
    assert reported_ids == base_sample_ids, (
        f"{fname}: every detected sample must be reported, even ones that failed every "
        f"dilution — expected {base_sample_ids}, got {reported_ids}"
    )
