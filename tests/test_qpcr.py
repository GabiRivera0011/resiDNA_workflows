"""Unit tests for the pure functions in Scripts/qpcr.py.

These are the functions shared between the notebook and app.py — a
regression here means both consumers silently drift or break together.
"""
import numpy as np
import pandas as pd
import pytest

from qpcr import (
    classify_sample, recovery_bounds, combined_suitability, compute_sigma_ct,
    compute_loq_and_range, resolve_sample_replicates, compute_range_suitability,
    compute_dilutional_linearity, aggregate_sample_results,
)


# --- classify_sample ---------------------------------------------------

@pytest.mark.parametrize("name,task,expected_group,expected_control", [
    ("STD 300", "STANDARD", "Reference Standard", "STD"),
    ("anything", "STANDARD", "Reference Standard", "STD"),  # task alone is enough
    ("NTC", "UNKNOWN", "Control", "NTC"),
    ("NEC", "UNKNOWN", "Control", "NEC"),
    ("ERC", "UNKNOWN", "Control", "ERC"),
    ("HPC", "UNKNOWN", "Control", "HPC"),
    ("MPC", "UNKNOWN", "Control", "MPC"),
    ("LPC", "UNKNOWN", "Control", "LPC"),
    ("S1 D1", "UNKNOWN", "Sample", "Sample"),
    ("  ntc  ", "UNKNOWN", "Control", "NTC"),  # case/whitespace insensitive
])
def test_classify_sample(name, task, expected_group, expected_control):
    group, control = classify_sample(name, task)
    assert group == expected_group
    assert control == expected_control


def test_classify_sample_blank_non_standard_is_unclassified():
    # A blank well that isn't a Reference Standard must not fall through to
    # "Sample" — that would corrupt every sample_name-keyed groupby downstream.
    group, control = classify_sample(np.nan, "UNKNOWN")
    assert group == "Unclassified"
    assert control is None


def test_classify_sample_blank_standard_task_is_reference_standard():
    group, control = classify_sample(np.nan, "STANDARD")
    assert group == "Reference Standard"
    assert control == "STD"


# --- recovery_bounds -----------------------------------------------------

@pytest.mark.parametrize("control_type", ["HPC", "MPC", "LPC"])
def test_recovery_bounds_pc(control_type):
    assert recovery_bounds(control_type, 80.0, 125.0, 50.0, 150.0) == (80.0, 125.0)


def test_recovery_bounds_erc():
    assert recovery_bounds("ERC", 80.0, 125.0, 50.0, 150.0) == (50.0, 150.0)


# --- combined_suitability -------------------------------------------------

@pytest.mark.parametrize("statuses,expected", [
    (["Pass", "Pass", "Pass"], "Pass"),
    (["Pass", "Fail", "Pass"], "Fail"),
    (["Pass", "N/A", "Pass"], "N/A"),
    (["Fail", "N/A"], "Fail"),  # Fail wins over N/A
])
def test_combined_suitability(statuses, expected):
    assert combined_suitability(statuses) == expected


# --- compute_sigma_ct ------------------------------------------------------

def test_compute_sigma_ct():
    # Ct = slope * (sigma * std_error / |slope|) + intercept
    result = compute_sigma_ct(std_error=0.1, slope=-3.3, intercept=40.0, sigma_multiplier=10.0)
    expected = -3.3 * (10.0 * 0.1 / 3.3) + 40.0
    assert result == pytest.approx(expected)


# --- compute_loq_and_range -------------------------------------------------

def test_compute_loq_and_range_picks_highest_and_lowest_quantity():
    std_suitability = pd.DataFrame({
        "sample_name": ["STD1", "STD2", "STD6"],
        "Quantity": [300.0, 30.0, 0.003],
        "Back-Calc Mean": [288.2, 28.5, 0.0028],
        "Ct Mean": [15.0, 20.0, 29.7],
    })
    result = compute_loq_and_range(std_suitability)
    assert result["std1_backcalc_mean"] == 288.2
    assert result["std6_backcalc_mean"] == 0.0028
    assert result["loq_quantity"] == 0.0028
    assert result["loq_ct"] == 29.7


def test_compute_loq_and_range_is_nan_safe():
    # A missing Quantity must not be picked as "highest"/"lowest" — idxmax/idxmin
    # skip NaN, unlike sort_values + iloc[0]/iloc[-1] (ascending sort puts NaN last).
    std_suitability = pd.DataFrame({
        "sample_name": ["STD1", "STDx", "STD6"],
        "Quantity": [300.0, np.nan, 0.003],
        "Back-Calc Mean": [288.2, np.nan, 0.0028],
        "Ct Mean": [15.0, np.nan, 29.7],
    })
    result = compute_loq_and_range(std_suitability)
    assert result["std1_backcalc_mean"] == 288.2
    assert result["std6_backcalc_mean"] == 0.0028


# --- resolve_sample_replicates ---------------------------------------------

def _triplicate_df(quantities, cv, dilution_factor=1.0, protein_concentration=1.0, sample_name="S1 D1"):
    return pd.DataFrame({
        "sample_name": [sample_name] * len(quantities),
        "quantity": quantities,
        "dilution_factor": [dilution_factor] * len(quantities),
        "protein_concentration": [protein_concentration] * len(quantities),
        "quantity_percent_cv": [cv] * len(quantities),
        "quantity_mean": [np.mean(quantities)] * len(quantities),
        "dilution_adjusted": [np.mean(quantities) * dilution_factor] * len(quantities),
        "total_dna_per_ml": [np.mean(quantities) * dilution_factor] * len(quantities),
        "total_dna_per_protein_concentration": [
            np.mean(quantities) * dilution_factor / protein_concentration
        ] * len(quantities),
    })


def test_resolve_sample_replicates_passthrough_when_cv_already_passes():
    df = _triplicate_df([10.0, 10.5, 9.8], cv=3.5)
    result = resolve_sample_replicates(df, cv_max=25.0)
    row = result.iloc[0]
    assert row["replicates_used"] == 3
    assert row["quantity_percent_cv"] == pytest.approx(3.5)


def test_resolve_sample_replicates_rescues_two_of_three():
    # One clear outlier; dropping it should bring the remaining pair's %CV under 25%
    df = _triplicate_df([10.0, 10.2, 50.0], cv=140.0)
    result = resolve_sample_replicates(df, cv_max=25.0)
    row = result.iloc[0]
    assert row["replicates_used"] == 2
    assert row["quantity_mean"] == pytest.approx((10.0 + 10.2) / 2)


def test_resolve_sample_replicates_still_fails_with_best_pair():
    # No pair of these three has a %CV under 25% — stays a 3-well fail
    df = _triplicate_df([1.0, 10.0, 100.0], cv=150.0)
    result = resolve_sample_replicates(df, cv_max=25.0)
    row = result.iloc[0]
    assert row["replicates_used"] == 3
    assert row["quantity_percent_cv"] == pytest.approx(150.0)


# --- compute_range_suitability ----------------------------------------------

def test_compute_range_suitability_classifies_in_out_and_undetermined():
    unspiked_samples = pd.DataFrame({
        "base_sample": ["S1", "S1", "S1"],
        "sample_name": ["S1 D1", "S1 D2", "S1 D3"],
    })
    resolved_replicates = pd.DataFrame({
        "sample_name": ["S1 D1", "S1 D2", "S1 D3"],
        "quantity_mean": [5.0, 0.0001, np.nan],
    })
    range_df = compute_range_suitability(
        unspiked_samples, resolved_replicates, std6_backcalc_mean=0.001, std1_backcalc_mean=100.0,
    )
    statuses = range_df.set_index("sample_name")["Range Status"]
    assert statuses["S1 D1"] == "In Range"
    assert statuses["S1 D2"] == "Out of Range"  # below std6_backcalc_mean
    assert statuses["S1 D3"] == "Undetermined"

    passes = range_df.set_index("sample_name")["Pass"]
    assert passes["S1 D1"] is True
    assert passes["S1 D2"] is False
    assert pd.isna(passes["S1 D3"])


# --- compute_dilutional_linearity -------------------------------------------

def _dilutions_df():
    return pd.DataFrame({
        "base_sample": ["S1", "S1", "S1"],
        "sample_name": ["S1 D1", "S1 D2", "S1 D3"],
        "ct_cv_percent": [2.0, 5.0, 1.0],
        "quantity_percent_cv": [3.0, 6.0, 2.0],
        "dilution_adjusted": [100.0, 110.0, 300.0],
    })


def test_compute_dilutional_linearity_backward_compatible_no_mask():
    # No eligible_mask (app.py's original call shape) — every dilution eligible,
    # reference is the one with the lowest combined CV: S1 D3 (1.0 + 2.0 = 3.0)
    result = compute_dilutional_linearity(_dilutions_df(), bias_max=20.0)
    assert (result["Reference Dilution Adjusted"] == 300.0).all()


def test_compute_dilutional_linearity_restricted_reference():
    # Excluding S1 D3 (the best dilution) should fall back to the next-best eligible: S1 D1
    dilutions = _dilutions_df()
    eligible_mask = pd.Series([True, True, False])
    result = compute_dilutional_linearity(dilutions, bias_max=20.0, eligible_mask=eligible_mask)
    assert (result["Reference Dilution Adjusted"] == 100.0).all()


def test_compute_dilutional_linearity_zero_eligible_yields_na():
    dilutions = _dilutions_df()
    eligible_mask = pd.Series([False, False, False])
    result = compute_dilutional_linearity(dilutions, bias_max=20.0, eligible_mask=eligible_mask)
    assert result["% Bias"].isna().all()
    assert result["Pass"].isna().all()


# --- aggregate_sample_results ------------------------------------------------

def test_aggregate_sample_results_averages_only_passing_dilutions():
    final_results = pd.DataFrame({
        "Sample #": ["S1", "S1", "S1"],
        "Sample": ["S1 D1", "S1 D2", "S1 D3"],
        "Suitability": ["Pass", "Fail", "Pass"],
        "Total DNA (ng/mL)": [10.0, 999.0, 20.0],
        "Protein Concentration (mg/mL)": [1.0, 1.0, 1.0],
        "DNA per Protein (ng/mg)": [10.0, 999.0, 20.0],
        "Quantity Mean": [1.0, 999.0, 2.0],
    })
    reportable_results, status_col = aggregate_sample_results(
        final_results, sample_id_map={"S1": ""}, sample_display_names={"S1": ""},
        dna_per_protein_limit=15.0,
    )
    row = reportable_results.iloc[0]
    assert row["Total DNA (ng/mL)"] == pytest.approx(15.0)  # mean of the two Pass rows only
    assert row["Sample Passed"] == True  # noqa: E712
    assert row["Dilutions Averaged"] == "S1 D1, S1 D3 (n=2)"
    assert row[status_col] == "Above"  # 15.0 is not < 15.0


def test_aggregate_sample_results_fallback_averages_all_when_none_pass():
    final_results = pd.DataFrame({
        "Sample #": ["S1", "S1"],
        "Sample": ["S1 D1", "S1 D2"],
        "Suitability": ["Fail", "Fail"],
        "Total DNA (ng/mL)": [10.0, 20.0],
        "Protein Concentration (mg/mL)": [1.0, 1.0],
        "DNA per Protein (ng/mg)": [10.0, 20.0],
        "Quantity Mean": [1.0, 2.0],
    })
    reportable_results, status_col = aggregate_sample_results(
        final_results, sample_id_map={"S1": ""}, sample_display_names={"S1": ""},
        dna_per_protein_limit=15.0,
    )
    row = reportable_results.iloc[0]
    assert row["Total DNA (ng/mL)"] == pytest.approx(15.0)  # fallback: mean of ALL rows
    assert row["Sample Passed"] == False  # noqa: E712
    assert row["Dilutions Averaged"] == "S1 D1, S1 D2 (n=2)"
