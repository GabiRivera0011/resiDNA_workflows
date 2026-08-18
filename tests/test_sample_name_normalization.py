"""Regression test for whitespace normalization of Sample Name / Task,
applied once right after parsing in both app.py and the notebook (see
"Analysts sometimes type extra/inconsistent whitespace..." in each). Without
it, an analyst typo like "S1  D1" (double space) vs "S1 D1 S" (single space)
would silently fail every downstream exact-string-match grouping — including
compute_spike_suitability()'s spike-to-unspiked Dilution Factor lookup.
"""
import re

import numpy as np
import pandas as pd
import pytest

from qpcr import compute_spike_suitability


def _normalize(series):
    """The exact technique app.py/the notebook apply to sample_name and task
    right after parsing — duplicated here (not imported) since it's inline
    parsing-step logic in both files, not a Scripts/qpcr.py function."""
    return series.str.strip().str.replace(r"\s+", " ", regex=True)


@pytest.mark.parametrize("raw,expected", [
    ("S1  D1", "S1 D1"),           # double space in the middle
    ("S1 D1  S", "S1 D1 S"),        # double space right before the "S" suffix
    ("  S1 D1  ", "S1 D1"),         # leading/trailing whitespace
    ("S1 D1", "S1 D1"),             # already clean — unaffected
])
def test_normalize_collapses_whitespace(raw, expected):
    result = _normalize(pd.Series([raw]))
    assert result.iloc[0] == expected


def test_normalize_preserves_real_nan():
    # Blank/unused wells are real NaN, not the literal string "nan" — classify_sample()
    # depends on this (`pd.isna(sample_name)` for its Reference Standard fallback).
    result = _normalize(pd.Series(["S1 D1", None, float("nan")]))
    assert result.iloc[0] == "S1 D1"
    assert pd.isna(result.iloc[1])
    assert pd.isna(result.iloc[2])


def _well_rows(sample_name, quantities, percent_recovery, dilution_factor):
    return pd.DataFrame({
        "sample_name": [sample_name] * len(quantities),
        "quantity": quantities,
        "dilution_factor": [dilution_factor] * len(quantities),
        "protein_concentration": [np.nan] * len(quantities),
        "quantity_percent_cv": [np.std(quantities, ddof=1) / np.mean(quantities) * 100] * len(quantities),
        "quantity_mean": [np.mean(quantities)] * len(quantities),
        "dilution_adjusted": [np.mean(quantities) * dilution_factor] * len(quantities),
        "total_dna_per_ml": [np.mean(quantities) * dilution_factor] * len(quantities),
        "total_dna_per_protein_concentration": [np.nan] * len(quantities),
        "percent_recovery": [percent_recovery] * len(quantities),
    })


def test_typo_would_break_spike_lookup_without_normalization():
    # Reproduces the exact scenario reported: unspiked typed with a double
    # space ("S1  D2"), spiked typed normally ("S1 D2 S"). Fed to
    # compute_spike_suitability() WITHOUT normalizing first — confirms the
    # lookup silently fails (NaN Dilution Factor) so the regression above is
    # protecting something real, not a hypothetical.
    rows = pd.concat([
        _well_rows("S1 D2 S", [3.0, 3.1, 3.2], percent_recovery=100.0, dilution_factor=1.0),
        _well_rows("S1  D2", [1.0, 1.0, 1.0], percent_recovery=np.nan, dilution_factor=10.0),
    ])
    result = compute_spike_suitability(rows, 25.0, 80.0, 125.0)
    assert pd.isna(result.set_index("Sample").loc["S1 D2 S", "Dilution Factor"])


def test_typo_resolves_correctly_once_normalized():
    # Same scenario, but with sample_name normalized first, exactly as
    # app.py/the notebook now do right after parsing — the lookup succeeds.
    rows = pd.concat([
        _well_rows("S1 D2 S", [3.0, 3.1, 3.2], percent_recovery=100.0, dilution_factor=1.0),
        _well_rows("S1  D2", [1.0, 1.0, 1.0], percent_recovery=np.nan, dilution_factor=10.0),
    ])
    rows["sample_name"] = _normalize(rows["sample_name"])
    result = compute_spike_suitability(rows, 25.0, 80.0, 125.0)
    assert result.set_index("Sample").loc["S1 D2 S", "Dilution Factor"] == 10.0
