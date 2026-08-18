import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import klib

# Scripts/ lives at the repo root, one level up from this file's app/ folder
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Scripts"))
# audit_log.py lives alongside this file — a normal `streamlit run`/`python`
# invocation puts a script's own directory on sys.path automatically, but the
# test suite exec()s this file's source directly (not a real script
# invocation), which doesn't; inserted explicitly so both paths work.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qpcr import (
    classify_sample, recovery_bounds, combined_suitability,
    compute_dilutional_linearity, resolve_sample_replicates, compute_loq_and_range,
    compute_range_suitability, aggregate_sample_results, compute_sample_status,
    compute_spike_suitability,
)
from plotting import style_table, format_df_for_display, format_value
from audit_log import log_report_generated

# Must be the very first Streamlit command — widens the page from the default
# centered ~730px column to the full browser width, so wide tables (like Sample
# Suitability, with 11 columns) fit without horizontal scrolling
st.set_page_config(page_title="Residual DNA Sample Analysis Tool", layout="wide")

st.title("Residual DNA Sample Analysis Tool")


FINAL_RESULTS_PRECISION = {
    "Replicates Used": 0,
    "Linearity %Bias": 2,
}

# =========================================================================
# Acceptance Criteria — shipped defaults + session-only overrides via the
# "Edit Acceptance Criteria" dialog below. Session-only by design: an
# override is scoped to your browser tab and resets on reload, so trying a
# "what if this threshold were different" never silently changes results
# for anyone else, or leaves a stale override for the next person on a
# shared deployment. Any override still active when a report is generated
# is called out on-screen and in the PDF (see "changed criteria" below) so
# the record shows plainly that non-default thresholds were used.
# =========================================================================
DEFAULT_STD_R2_MIN = 0.99
DEFAULT_STD_CT_CV_MAX = 20.0
DEFAULT_STD_BACK_CALC_BIAS_MAX = 25.0
DEFAULT_STD_EFFICIENCY_MIN = 90.0
DEFAULT_STD_EFFICIENCY_MAX = 110.0
DEFAULT_CTRL_QTY_CV_MAX = 20.0
DEFAULT_PC_RECOVERY_MIN = 80.0
DEFAULT_PC_RECOVERY_MAX = 125.0
DEFAULT_ERC_RECOVERY_MIN = 50.0
DEFAULT_ERC_RECOVERY_MAX = 150.0
DEFAULT_SAMPLE_QTY_CV_MAX = 25.0
DEFAULT_SAMPLE_LINEARITY_BIAS_MAX = 20.0
DEFAULT_SAMPLE_DNA_PER_PROTEIN_LIMIT = 15.0
DEFAULT_SAMPLE_SPIKE_RECOVERY_MIN = 80.0
DEFAULT_SAMPLE_SPIKE_RECOVERY_MAX = 125.0

# (name, label, default, number_input format) grouped for the dialog's
# layout — also the single source of truth for which criteria are
# overridable, so the dialog, the resolution step below, and the
# changed-criteria report can't drift out of sync with each other.
CRITERIA_GROUPS = [
    ("STD Curve", [
        ("STD_R2_MIN", "R² Min", DEFAULT_STD_R2_MIN, "%.2f"),
        ("STD_CT_CV_MAX", "Ct %CV Max", DEFAULT_STD_CT_CV_MAX, "%.1f"),
        ("STD_BACK_CALC_BIAS_MAX", "Back-Calc %Bias Max", DEFAULT_STD_BACK_CALC_BIAS_MAX, "%.1f"),
        ("STD_EFFICIENCY_MIN", "Efficiency Min %", DEFAULT_STD_EFFICIENCY_MIN, "%.1f"),
        ("STD_EFFICIENCY_MAX", "Efficiency Max %", DEFAULT_STD_EFFICIENCY_MAX, "%.1f"),
    ]),
    ("ERC / PC Controls", [
        ("CTRL_QTY_CV_MAX", "Quantity %CV Max", DEFAULT_CTRL_QTY_CV_MAX, "%.1f"),
        ("PC_RECOVERY_MIN", "PC %Recovery Min", DEFAULT_PC_RECOVERY_MIN, "%.1f"),
        ("PC_RECOVERY_MAX", "PC %Recovery Max", DEFAULT_PC_RECOVERY_MAX, "%.1f"),
        ("ERC_RECOVERY_MIN", "ERC %Recovery Min", DEFAULT_ERC_RECOVERY_MIN, "%.1f"),
        ("ERC_RECOVERY_MAX", "ERC %Recovery Max", DEFAULT_ERC_RECOVERY_MAX, "%.1f"),
    ]),
    ("Sample Suitability", [
        ("SAMPLE_QTY_CV_MAX", "Quantity %CV Max", DEFAULT_SAMPLE_QTY_CV_MAX, "%.1f"),
        ("SAMPLE_LINEARITY_BIAS_MAX", "Linearity %Bias Max", DEFAULT_SAMPLE_LINEARITY_BIAS_MAX, "%.1f"),
        ("SAMPLE_DNA_PER_PROTEIN_LIMIT", "DNA per Protein Limit (ng/mg)", DEFAULT_SAMPLE_DNA_PER_PROTEIN_LIMIT, "%.1f"),
    ]),
    ("Spike Recovery", [
        ("SAMPLE_SPIKE_RECOVERY_MIN", "%Recovery Min", DEFAULT_SAMPLE_SPIKE_RECOVERY_MIN, "%.1f"),
        ("SAMPLE_SPIKE_RECOVERY_MAX", "%Recovery Max", DEFAULT_SAMPLE_SPIKE_RECOVERY_MAX, "%.1f"),
    ]),
]


def _active_criterion(name, default):
    """The value to actually use for criterion `name`: this session's
    override if one was entered in the Edit Acceptance Criteria dialog,
    otherwise the shipped default."""
    override = st.session_state.get(f"criteria_override_{name}")
    return default if override is None else override


@st.dialog("Edit Acceptance Criteria", width="large")
def _edit_criteria_dialog():
    st.caption(
        "Leave a box empty to keep the current value, shown grayed out as a "
        "placeholder. Overrides apply for this browser session only — they "
        "reset when you reload the page — and any still active when you "
        "generate a report are listed on-screen and in the PDF."
    )
    for group_name, criteria in CRITERIA_GROUPS:
        st.markdown(f"**{group_name}**")
        cols = st.columns(2)
        for i, (name, label, default, fmt) in enumerate(criteria):
            with cols[i % 2]:
                st.number_input(
                    label, value=None, placeholder=fmt % default,
                    key=f"criteria_override_{name}", format=fmt,
                )
    st.divider()
    if st.button("Reset all to defaults"):
        for _, criteria in CRITERIA_GROUPS:
            for name, _, _, _ in criteria:
                st.session_state.pop(f"criteria_override_{name}", None)
        st.rerun()


if st.button("⚙️ Edit Acceptance Criteria"):
    _edit_criteria_dialog()


st.header("Upload QuantStudio File")

uploaded_file = st.file_uploader(
    "Choose a QuantStudio Results file (.xlsx or .xls)",
    type=["xlsx", "xls"],
)

if uploaded_file is not None:
    engine = "xlrd" if uploaded_file.name.endswith(".xls") else "openpyxl"

    df = pd.read_excel(uploaded_file, sheet_name="Results", header=22, engine=engine)

    # The regression/curve-stats block lives in a separate fixed area of the same
    # sheet — re-read the file for it, seeking back to the start first since a
    # file-like object (unlike a path) remembers where the last read left off
    uploaded_file.seek(0)
    regression_df = pd.read_excel(
        uploaded_file, sheet_name="Results", header=None,
        skiprows=18, nrows=1, usecols="C:G", engine=engine,
    )
    regression_stats = []
    for item in regression_df.iloc[0]:
        if pd.notna(item):
            key, value = str(item).split(":", 1)
            regression_stats.append({"Metric": key.strip(), "Value": value.strip()})
    regression_table = pd.DataFrame(regression_stats)

    # --- Parse & clean (silent — same steps as the notebook) ---
    # "%" is normalized here (matching klib.clean_column_names' own "%" -> "_percent_"
    # rule below) so columns like "Ct CV%" already read as their final "ct_cv_percent"
    # name before klib ever sees them. That's what lets col_exclude, just below, name
    # the columns this pipeline depends on downstream: col_exclude is passed straight
    # through to klib's column-dropping step, which runs BEFORE klib's own name
    # cleanup — passing it the pre-cleanup spelling (e.g. "ct_cv%") would silently
    # fail to match and leave the column unprotected.
    df.columns = (
        df.columns.str.strip().str.lower()
        .str.replace(" ", "_").str.replace("-", "_")
        .str.replace("%", "_percent_", regex=False)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
    )
    numeric_columns = ["ct", "ct_mean", "ct_sd", "quantity", "quantity_mean", "quantity_sd"]
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Analysts sometimes type extra/inconsistent whitespace into Sample Name
    # or Task (e.g. "S1  D1" vs "S1 D1", or a trailing space before a spike
    # well's " S" suffix) — collapsed here, once, right after parsing, since
    # every downstream step (classification, triplicate grouping, the
    # spike/unspiked dilution-factor lookup, etc.) groups rows by exact
    # string equality and would otherwise silently split what's really the
    # same sample into separate groups. .str methods skip real NaN (unused
    # wells) rather than stringifying it to the literal text "nan", so this
    # is safe to apply unconditionally.
    df["sample_name"] = df["sample_name"].str.strip().str.replace(r"\s+", " ", regex=True)
    df["task"] = df["task"].str.strip().str.replace(r"\s+", " ", regex=True)

    # klib.data_cleaning() drops any column that's >=90% missing or single-valued
    # (including all-NaN, which counts as single-valued) FOR THIS PARTICULAR DATASET.
    # Which columns end up sparse/constant varies run to run (e.g. a run with only one
    # replicate per standard has no computed Ct %CV), so the columns this pipeline
    # depends on downstream must be pinned here — otherwise the same file that works
    # for one run's data can KeyError on another. See also the r2/slope/y_intercept
    # note further down, which hits the same klib behavior for the regression block.
    _required_column_labels = {
        "sample_name": "Sample Name", "task": "Task", "well": "Well",
        "ct": "Ct", "ct_mean": "Ct Mean", "ct_sd": "Ct SD",
        "quantity": "Quantity", "quantity_mean": "Quantity Mean", "quantity_sd": "Quantity SD",
        "quantity_percent_cv": "Quantity %CV", "ct_cv_percent": "Ct CV%",
        "percent_recovery": "% Recovery",
        "back_calculation_percent_difference_mean": "Back Calculation % difference Mean",
        "back_calculation_mean": "Back Calculation Mean",
        "dilution_adjusted": "Dilution Adjusted", "dilution_factor": "Dilution Factor",
        "total_dna_per_ml": "Total DNA per mL", "protein_concentration": "Protein Concentration",
        "total_dna_per_protein_concentration": "Total DNA per Protein Concentration",
    }
    _columns_required_downstream = list(_required_column_labels)

    # These aren't dropped by klib below — they're missing from the uploaded file itself,
    # meaning the QuantStudio export didn't compute them at all (e.g. Back Calculation /
    # Protein Concentration columns are absent when spike-recovery or protein-normalization
    # analysis wasn't enabled for the run). That's an incomplete export, not something this
    # app can safely fill in, so stop here rather than let a later step KeyError confusingly.
    _missing_from_source = [c for c in _columns_required_downstream if c not in df.columns]
    if _missing_from_source:
        _missing_labels = [_required_column_labels[c] for c in _missing_from_source]
        st.error(
            "This file is missing required column(s) that QuantStudio didn't export: "
            f"**{', '.join(_missing_labels)}**.\n\n"
            "Re-export the Results sheet with the corresponding analysis module(s) "
            "enabled (e.g. Back Calculation requires spike-recovery analysis; Protein "
            "Concentration requires protein normalization) and re-upload."
        )
        st.stop()

    # convert_dtypes=False: klib's default float32 downcast otherwise reintroduces
    # precision noise (e.g. 0.003 -> 0.003000000026077032) once display values are
    # shown at instrument sigfig instead of being rounded off (see format_value below).
    df = klib.data_cleaning(df, col_exclude=_columns_required_downstream, convert_dtypes=False)
    df["ct"] = df["ct"].replace("Undetermined", pd.NA)
    df["ct"] = pd.to_numeric(df["ct"])
    parsed_df = df.copy()

    # --- Classify wells (silent) ---
    parsed_df[["sample_group", "control_type"]] = parsed_df.apply(
        lambda row: classify_sample(row["sample_name"], row["task"]), axis=1
    )
    ref_std_df = parsed_df[parsed_df["sample_group"] == "Reference Standard"].copy()
    controls_df = parsed_df[parsed_df["sample_group"] == "Control"].copy()
    samples_df = parsed_df[parsed_df["sample_group"] == "Sample"].copy()
    samples_df["base_sample"] = samples_df["sample_name"].str.replace(
        r"\s+D\d+(?:\s+S)?$", "", regex=True
    )

    # -----------------------------------------------------------------------
    # Assay Run Information — the values you'd otherwise fill into the
    # notebook's #@param fields
    # -----------------------------------------------------------------------
    st.header("Assay Run Information")
    left, right = st.columns(2)
    with left:
        ASSAY_NAME = st.text_input("Assay Name")
        RUN_NUMBER = st.text_input("SA Run Number")
        ASSAY_DATE = st.text_input("Assay Date")
        REQUEST_NUMBER = st.text_input("Request Number")
    with right:
        TEST_METHOD = st.text_input("Test Method")
        NOTEBOOK_NUMBER = st.text_input("Notebook Number")
        LAB_NAME = st.text_input("Laboratory")
        LAB_ADDRESS = st.text_input("Laboratory Address")

    # --- Acceptance criteria: this session's active values (defaults, unless
    # overridden via the Edit Acceptance Criteria dialog above) ---
    STD_R2_MIN = _active_criterion("STD_R2_MIN", DEFAULT_STD_R2_MIN)
    STD_CT_CV_MAX = _active_criterion("STD_CT_CV_MAX", DEFAULT_STD_CT_CV_MAX)
    STD_BACK_CALC_BIAS_MAX = _active_criterion("STD_BACK_CALC_BIAS_MAX", DEFAULT_STD_BACK_CALC_BIAS_MAX)
    STD_EFFICIENCY_MIN = _active_criterion("STD_EFFICIENCY_MIN", DEFAULT_STD_EFFICIENCY_MIN)
    STD_EFFICIENCY_MAX = _active_criterion("STD_EFFICIENCY_MAX", DEFAULT_STD_EFFICIENCY_MAX)
    CTRL_QTY_CV_MAX = _active_criterion("CTRL_QTY_CV_MAX", DEFAULT_CTRL_QTY_CV_MAX)
    PC_RECOVERY_MIN = _active_criterion("PC_RECOVERY_MIN", DEFAULT_PC_RECOVERY_MIN)
    PC_RECOVERY_MAX = _active_criterion("PC_RECOVERY_MAX", DEFAULT_PC_RECOVERY_MAX)
    ERC_RECOVERY_MIN = _active_criterion("ERC_RECOVERY_MIN", DEFAULT_ERC_RECOVERY_MIN)
    ERC_RECOVERY_MAX = _active_criterion("ERC_RECOVERY_MAX", DEFAULT_ERC_RECOVERY_MAX)
    SAMPLE_QTY_CV_MAX = _active_criterion("SAMPLE_QTY_CV_MAX", DEFAULT_SAMPLE_QTY_CV_MAX)
    SAMPLE_LINEARITY_BIAS_MAX = _active_criterion("SAMPLE_LINEARITY_BIAS_MAX", DEFAULT_SAMPLE_LINEARITY_BIAS_MAX)
    SAMPLE_DNA_PER_PROTEIN_LIMIT = _active_criterion(
        "SAMPLE_DNA_PER_PROTEIN_LIMIT", DEFAULT_SAMPLE_DNA_PER_PROTEIN_LIMIT
    )
    SAMPLE_SPIKE_RECOVERY_MIN = _active_criterion("SAMPLE_SPIKE_RECOVERY_MIN", DEFAULT_SAMPLE_SPIKE_RECOVERY_MIN)
    SAMPLE_SPIKE_RECOVERY_MAX = _active_criterion("SAMPLE_SPIKE_RECOVERY_MAX", DEFAULT_SAMPLE_SPIKE_RECOVERY_MAX)

    # Every criterion whose active value differs from its shipped default —
    # surfaced on-screen and in the PDF (below) so a report generated with
    # non-default thresholds is never silently indistinguishable from one
    # generated with the shipped defaults.
    changed_criteria = [
        {"Criterion": label, "Default": default, "Used": _active_criterion(name, default)}
        for _, criteria in CRITERIA_GROUPS
        for name, label, default, _ in criteria
        if _active_criterion(name, default) != default
    ]

    # --- Standard curve stats (silent) ---
    reg_stats = regression_table.set_index("Metric")["Value"].astype(float)
    curve_r2 = reg_stats["R2"]
    curve_slope = reg_stats["Slope"]
    curve_intercept = reg_stats["y-Intercept"]
    curve_efficiency = reg_stats["Efficiency"]
    curve_std_error = reg_stats["Std error"]

    # --- STD Curve Point suitability (silent) ---
    std_suitability = (
        ref_std_df.groupby("sample_name", as_index=False)
        .agg(**{
            "Quantity": ("quantity", "first"),
            "Ct Mean": ("ct_mean", "first"),
            "Ct %CV": ("ct_cv_percent", "first"),
            "Back-Calc %Bias": ("back_calculation_percent_difference_mean", "first"),
            "Back-Calc Mean": ("back_calculation_mean", "first"),
        })
        .sort_values("Quantity")
        .reset_index(drop=True)
    )
    std_suitability["Ct %CV Pass"] = std_suitability["Ct %CV"] <= STD_CT_CV_MAX
    std_suitability["Back-Calc Pass"] = std_suitability["Back-Calc %Bias"].abs() <= STD_BACK_CALC_BIAS_MAX

    # --- Sample LOQ / STD Range (silent) — derived from the standard curve's own
    # back-calculated values at its highest (STD1) and lowest (STD6) calibrated
    # points, replacing the old ICH sigma-in-Ct-space LOQ formula.
    # compute_loq_and_range() (Scripts/qpcr.py) does the derivation, shared
    # with the notebook so both stay in sync.
    _loq_range = compute_loq_and_range(std_suitability)
    std1_backcalc_mean = _loq_range["std1_backcalc_mean"]
    std6_backcalc_mean = _loq_range["std6_backcalc_mean"]
    # STD6's own back-calculated concentration is now the sample LOQ.
    loq_quantity = _loq_range["loq_quantity"]
    # NTC/NEC typically don't report a Quantity at all, so their check (below)
    # stays in Ct space, anchored to STD6's own measured Ct Mean.
    loq_ct = _loq_range["loq_ct"]

    # --- ERC / PC suitability (silent) ---
    control_suitability = (
        controls_df[controls_df["control_type"].isin(["ERC", "HPC", "MPC", "LPC"])]
        .groupby(["control_type", "sample_name"], as_index=False)
        .agg(**{
            "Quantity %CV": ("quantity_percent_cv", "first"),
            "% Recovery": ("percent_recovery", "first"),
        })
    )

    control_suitability["CV Pass"] = control_suitability["Quantity %CV"] <= CTRL_QTY_CV_MAX
    control_suitability["Recovery Pass"] = control_suitability.apply(
        lambda row: recovery_bounds(
            row["control_type"], PC_RECOVERY_MIN, PC_RECOVERY_MAX, ERC_RECOVERY_MIN, ERC_RECOVERY_MAX
        )[0]
        <= row["% Recovery"]
        <= recovery_bounds(
            row["control_type"], PC_RECOVERY_MIN, PC_RECOVERY_MAX, ERC_RECOVERY_MIN, ERC_RECOVERY_MAX
        )[1],
        axis=1,
    )

    # --- NTC / NEC suitability (silent) ---
    negative_controls_df = controls_df[controls_df["control_type"].isin(["NTC", "NEC"])].copy()
    negative_controls_df["well_pass"] = (
        negative_controls_df["ct"].isna() | (negative_controls_df["ct"] >= loq_ct)
    )
    negative_control_summary = (
        negative_controls_df.groupby(["control_type", "sample_name"], as_index=False)
        .agg(**{
            "Wells Passing": ("well_pass", "sum"),
            "Total Wells": ("well_pass", "size"),
            # Mean Ct across the group's wells (Undetermined wells excluded via
            # pandas' default NaN-skipping mean; "Undetermined" only if every
            # well was), shown alongside LOQ Ct below so a Fail is traceable to
            # the value that drove it. Rounded here (4dp, matching the
            # instrument's own Ct precision) since — unlike most fields in this
            # pipeline — this mean is genuinely computed, not instrument-reported.
            "Ct": ("ct", lambda s: "Undetermined" if s.isna().all() else round(s.mean(), 4)),
        })
    )
    negative_control_summary["Pass"] = (
        negative_control_summary["Wells Passing"] == negative_control_summary["Total Wells"]
    )
    negative_control_summary = negative_control_summary.rename(
        columns={"control_type": "Control Type", "sample_name": "Sample"}
    )
    ntc_pass = bool(
        negative_control_summary.loc[negative_control_summary["Control Type"] == "NTC", "Pass"].all()
    )
    nec_summary = negative_control_summary[negative_control_summary["Control Type"] == "NEC"]

    # --- Overall System Suitability verdict ---
    system_suitability_pass = bool(
        (curve_r2 >= STD_R2_MIN)
        and (STD_EFFICIENCY_MIN <= curve_efficiency <= STD_EFFICIENCY_MAX)
        and std_suitability["Ct %CV Pass"].all()
        and std_suitability["Back-Calc Pass"].all()
        and control_suitability["CV Pass"].all()
        and control_suitability["Recovery Pass"].all()
        and ntc_pass
        and nec_summary["Pass"].all()
    )
    status = "PASS" if system_suitability_pass else "FAIL"

    # --- Wide summary tables for display (same shape as the PDF report) ---
    curve_fit_wide = pd.DataFrame([{
        "Item": "Curve Fit",
        "R²": f"{curve_r2:.2f}",
        "R² Pass": "Pass" if curve_r2 >= STD_R2_MIN else "Fail",
        "Efficiency %": f"{curve_efficiency:.2f}",
        "Efficiency Pass": "Pass" if STD_EFFICIENCY_MIN <= curve_efficiency <= STD_EFFICIENCY_MAX else "Fail",
    }])

    std_points_wide = std_suitability.rename(columns={"sample_name": "Item"})[[
        "Item", "Ct %CV", "Ct %CV Pass", "Back-Calc %Bias", "Back-Calc Pass"
    ]].copy()
    std_points_wide["Ct %CV Pass"] = std_points_wide["Ct %CV Pass"].map({True: "Pass", False: "Fail"})
    std_points_wide["Back-Calc Pass"] = std_points_wide["Back-Calc Pass"].map({True: "Pass", False: "Fail"})

    erc_pc_wide = control_suitability.copy()
    erc_pc_wide["Item"] = erc_pc_wide["sample_name"] + " (" + erc_pc_wide["control_type"] + ")"
    erc_pc_wide["CV Pass"] = erc_pc_wide["CV Pass"].map({True: "Pass", False: "Fail"})
    erc_pc_wide["Recovery Pass"] = erc_pc_wide["Recovery Pass"].map({True: "Pass", False: "Fail"})
    erc_pc_wide = erc_pc_wide[["Item", "Quantity %CV", "CV Pass", "% Recovery", "Recovery Pass"]]

    ntc_nec_rows = []
    for _, row in negative_control_summary.iterrows():
        ntc_nec_rows.append({
            "Item": f"{row['Sample']} ({row['Control Type']})",
            "Criteria": f"Undetermined, or Ct ≥ {loq_ct}",
            # str(), not style_table()'s own numeric formatting (which would
            # default to 2dp here) — row["Ct"] is already rounded upstream.
            "Mean Ct": str(row["Ct"]),
            "Status": "Pass" if row["Pass"] else "Fail",
        })

    # --- Triplicate resolution: single-outlier exclusion when a dilution's full
    # 3-well Quantity %CV fails SAMPLE_QTY_CV_MAX (silent) ---
    unspiked_samples = samples_df[~samples_df["sample_name"].str.endswith(" S")].copy()
    resolved_replicates = resolve_sample_replicates(unspiked_samples, SAMPLE_QTY_CV_MAX)
    unspiked_dilution_info = unspiked_samples.drop_duplicates(subset="sample_name")[[
        "base_sample", "sample_name", "ct_cv_percent", "dilution_factor", "protein_concentration",
    ]]

    # --- Sample %CV suitability (silent) — spiked (" S") rows aren't part of the
    # averaging pipeline, so their %CV is left as the instrument reported it;
    # unspiked rows use the outlier-resolved %CV from resolved_replicates above.
    spiked_cv = (
        samples_df[samples_df["sample_name"].str.endswith(" S")]
        .groupby("sample_name", as_index=False)
        .agg(**{"Quantity %CV": ("quantity_percent_cv", "first")})
    )
    unspiked_cv = resolved_replicates.rename(columns={"quantity_percent_cv": "Quantity %CV"})[
        ["sample_name", "Quantity %CV"]
    ]
    sample_cv = (
        pd.concat([spiked_cv, unspiked_cv], ignore_index=True)
        .sort_values("sample_name")
        .reset_index(drop=True)
    )
    sample_cv["Pass"] = (sample_cv["Quantity %CV"] <= SAMPLE_QTY_CV_MAX).astype(object)
    # Below-LOQ / non-amplifying replicates have no %CV to evaluate — N/A, not a fail
    sample_cv.loc[sample_cv["Quantity %CV"].isna(), "Pass"] = pd.NA

    # --- Sample STD Range suitability (silent) — compares each dilution's raw
    # (pre-dilution-adjustment) triplicate Quantity Mean, after single-outlier
    # assessment, against the standard curve's own calibrated range
    # [std6_backcalc_mean, std1_backcalc_mean]. Below std6_backcalc_mean is the
    # definition of "below LOQ"; above std1_backcalc_mean is above the curve's
    # highest calibrated point. compute_range_suitability() (Scripts/qpcr.py)
    # does the actual comparison, shared with the notebook so both stay in sync.
    range_df = compute_range_suitability(
        unspiked_samples, resolved_replicates, std6_backcalc_mean, std1_backcalc_mean
    )

    # --- Dilutional Linearity suitability (silent) — the reference dilution for
    # each sample is restricted to dilutions that already pass both Quantity %CV
    # and STD Range, so the comparison isn't anchored to an unreliable point.
    unspiked_dilutions = unspiked_dilution_info.merge(
        resolved_replicates[["sample_name", "quantity_percent_cv", "dilution_adjusted"]],
        on="sample_name",
    )
    _cv_pass_by_sample = sample_cv.set_index("sample_name")["Pass"]
    _range_pass_by_sample = range_df.set_index("sample_name")["Pass"]
    eligible_mask = (
        unspiked_dilutions["sample_name"].map(_cv_pass_by_sample).fillna(False).astype(bool)
        & unspiked_dilutions["sample_name"].map(_range_pass_by_sample).fillna(False).astype(bool)
    )
    linearity_df = compute_dilutional_linearity(unspiked_dilutions, SAMPLE_LINEARITY_BIAS_MAX, eligible_mask)
    linearity_df = linearity_df.rename(columns={"sample_name": "Sample"})

    # --- Spiked sample suitability (silent) — a follow-up confirmatory test
    # (sample_name ending " S"), typically run on samples flagged "LOQ - Spike
    # Test" below. Informational only: never gates the corresponding unspiked
    # dilution's own Suitability/Next Step/averaging. Most runs have none.
    spike_suitability = compute_spike_suitability(
        samples_df, SAMPLE_QTY_CV_MAX, SAMPLE_SPIKE_RECOVERY_MIN, SAMPLE_SPIKE_RECOVERY_MAX
    )

    # --- Final Sample Results by Dilution (silent build) ---
    final_results = (
        unspiked_dilution_info[["base_sample", "sample_name", "dilution_factor", "protein_concentration"]]
        .merge(resolved_replicates, on="sample_name")
        .rename(columns={
            "base_sample": "Base Sample", "sample_name": "Sample",
            "dilution_factor": "Dilution Factor", "quantity_percent_cv": "Quantity %CV",
            "quantity_mean": "Quantity Mean", "total_dna_per_ml": "Total DNA (ng/mL)",
            "protein_concentration": "Protein Concentration (mg/mL)",
            "total_dna_per_protein_concentration": "DNA per Protein (ng/mg)",
            "replicates_used": "Replicates Used",
        })
        .sort_values(["Base Sample", "Sample"])
        .reset_index(drop=True)
    )
    final_results["Quantity %CV Suitability"] = final_results["Quantity %CV"].apply(
        lambda cv: "N/A" if pd.isna(cv) else ("Pass" if cv <= SAMPLE_QTY_CV_MAX else "Fail")
    )
    final_results = final_results.merge(
        linearity_df[["Sample", "% Bias", "Pass"]].rename(columns={"% Bias": "Linearity %Bias"}),
        on="Sample", how="left",
    )
    final_results["Linearity Suitability"] = (
        final_results["Pass"].map({True: "Pass", False: "Fail"}).fillna("N/A")
    )
    final_results = final_results.drop(columns="Pass")

    # Bring in each dilution's STD Range verdict. Pass/Fail/N/A wording here for
    # consistency with its sibling suitability columns.
    range_suitability_col = f"STD Range Suitability ({std6_backcalc_mean}–{std1_backcalc_mean})"
    final_results = final_results.merge(
        range_df[["sample_name", "Range Status"]].rename(columns={"sample_name": "Sample"}),
        on="Sample",
        how="left",
    )
    final_results[range_suitability_col] = final_results["Range Status"].map(
        {"In Range": "Pass", "Out of Range": "Fail", "Undetermined": "N/A"}
    )
    final_results = final_results.drop(columns="Range Status")

    # A dilution is only reportable/averageable once it cleanly passes all three
    # checks — STD Range GATES averaging (an Out of Range dilution, including
    # anything below the LOQ, is excluded rather than merely flagged).
    final_results["Suitability"] = final_results.apply(
        lambda row: combined_suitability([
            row["Quantity %CV Suitability"], row[range_suitability_col], row["Linearity Suitability"],
        ]),
        axis=1,
    )
    # No quantity to assess (Undetermined) is still uninterpretable, not a soft
    # middle ground — the reported Suitability verdict is binary, Pass or Fail only.
    final_results["Suitability"] = final_results["Suitability"].replace("N/A", "Fail")

    # "Sample #" is kept here (not in the column list below) because
    # reportable_results still groups by it further down — it's dropped only from
    # the display/PDF copies right before rendering, since "Sample" (e.g. "S1 D1")
    # already carries the same information for a human reader.
    final_results = final_results.rename(columns={"Base Sample": "Sample #"})[[
        "Sample #", "Sample", "Dilution Factor", "Quantity Mean", range_suitability_col,
        "Quantity %CV", "Replicates Used", "Quantity %CV Suitability",
        "Linearity %Bias", "Linearity Suitability",
        "Total DNA (ng/mL)", "Protein Concentration (mg/mL)", "DNA per Protein (ng/mg)",
        "Suitability",
    ]]

    # -----------------------------------------------------------------------
    # Sample ID / Sample Name — one row of inputs per Base Sample actually
    # detected in this run (the notebook uses 8 fixed #@param slots since Colab
    # forms are static; here we can just generate one row per real sample)
    # -----------------------------------------------------------------------
    st.header("Sample ID / Sample Name")
    _base_sample_ids = sorted(samples_df["base_sample"].unique())
    sample_id_map = {}
    sample_display_names = {}
    for base in _base_sample_ids:
        id_col, name_col = st.columns(2)
        with id_col:
            sample_id_map[base] = st.text_input(f"{base} — Sample ID", key=f"sample_id_{base}")
        with name_col:
            sample_display_names[base] = st.text_input(f"{base} — Sample Name", key=f"sample_name_{base}")

    # --- Final Sample Results — Averaged per Sample (silent build) ---
    # aggregate_sample_results() (Scripts/qpcr.py) averages each sample's
    # suitability-passing dilutions into a single Total DNA / DNA per Protein
    # result. A sample with zero passing dilutions (e.g. every dilution was Out
    # of Range or Undetermined) is still reported — averaged from ALL its
    # dilutions instead, since a flagged number is more useful than no row at
    # all — but gets a red highlight (via Sample Passed below) making clear it
    # failed acceptance criteria and shouldn't be trusted the way a passing row
    # is. Shared with the notebook so both stay in sync.
    reportable_results, _status_col = aggregate_sample_results(
        final_results, sample_id_map, sample_display_names, SAMPLE_DNA_PER_PROTEIN_LIMIT
    )

    # Farthest-right "Next Step" column — what to do next with this sample,
    # derived from the same per-dilution Suitability breakdown as the
    # by-dilution table above (see compute_sample_status()'s docstring in
    # Scripts/qpcr.py for the per-dilution rules and how multi-dilution
    # samples are resolved). Assigned here (last) so it lands after every
    # other column, including the ng/mg status column just added above.
    reportable_results["Next Step"] = reportable_results["Sample #"].map(
        compute_sample_status(final_results, range_suitability_col, std6_backcalc_mean, std1_backcalc_mean)
    )

    # Rows whose Quantity Mean (averaged across the same dilutions as the rest of
    # the row) doesn't clear the standard curve's LOQ threshold — or had no
    # quantity at all (every replicate used was Undetermined) — get Total DNA /
    # DNA per Protein flagged low-confidence instead of a separate status
    # column: grayed out via dim_mask (real CSS, see style_table()'s docstring)
    # with a trailing " - LOQ" on the value. Computed after _status_col above
    # since the suffixed strings below couldn't survive a numeric comparison.
    _below_loq_mask = reportable_results["Quantity Mean"].apply(lambda q: pd.isna(q) or q < loq_quantity)
    loq_footnote_used = bool(_below_loq_mask.any())
    reportable_results = reportable_results.drop(columns="Quantity Mean")
    LOQ_FOOTNOTE_TEXT = (
        "Values marked \"- LOQ\" were calculated from a sample "
        f"concentration (Quantity) below the assay's limit of quantification "
        f"(LOQ = {loq_quantity} pg/uL), or from replicates with no detectable signal. "
        "Treat these results as low confidence."
    )
    _loq_footnote_cols = ["Total DNA (ng/mL)", "DNA per Protein (ng/mg)"]
    # Unlike the by-dilution table (where these are pass-through instrument
    # figures), here they're genuinely computed means across a sample's passing
    # dilutions — natural/instrument sigfig would surface raw float averaging
    # noise (e.g. 24471.731166666665), so this table gets an explicit precision.
    _AVERAGED_PRECISION = {"Total DNA (ng/mL)": 4, "DNA per Protein (ng/mg)": 4}

    # st.table() renders cell values as plain text (see style_table()'s dim_mask
    # docstring in Scripts/plotting.py), so the marker here is a literal trailing
    # " - LOQ" — dim_mask (real CSS) grays out the whole value (marker included)
    # instead of relying on separate text styling.
    reportable_results_display = reportable_results.drop(columns="Sample Passed").copy()
    for _col in _loq_footnote_cols:
        _precision = _AVERAGED_PRECISION.get(_col)
        reportable_results_display[_col] = [
            "—" if pd.isna(v) else f"{format_value(v, _precision)}{' - LOQ' if flagged else ''}"
            for v, flagged in zip(reportable_results[_col], _below_loq_mask)
        ]
    loq_dim_mask = pd.DataFrame(
        {col: _below_loq_mask for col in _loq_footnote_cols}, index=reportable_results.index
    )

    def _apply_pdf_loq_footnote(data):
        """PDF-only: unlike st.table(), reportlab's Paragraph genuinely parses its
        own markup, so the PDF gets a properly grayed "- LOQ" suffix via <font>
        rather than dim_mask + a trailing " - LOQ"."""
        data = data.copy()
        for col in _loq_footnote_cols:
            precision = _AVERAGED_PRECISION.get(col)
            data[col] = [
                "—" if pd.isna(v) else (
                    f'<font color="#999999">{format_value(v, precision)} - LOQ</font>'
                    if flagged else format_value(v, precision)
                )
                for v, flagged in zip(data[col], _below_loq_mask)
            ]
        return data

    # =========================================================================
    # DISPLAY — only the sections that appear in the PDF report
    # =========================================================================

    if changed_criteria:
        st.warning(
            "Non-default acceptance criteria are active this session — see the "
            "table below and the PDF report.\n\n"
            + "\n".join(
                f"- **{c['Criterion']}**: {c['Used']} (default: {c['Default']})"
                for c in changed_criteria
            )
        )

    st.header("System Suitability")
    if system_suitability_pass:
        st.success(f"System Suitability: {status}")
    else:
        st.error(f"System Suitability: {status}")

    st.table(style_table(curve_fit_wide, caption="STD Curve Fit", align="left"))
    st.table(style_table(
        std_points_wide, caption="STD Curve Points", align="left",
        highlight_rows=(std_points_wide["Ct %CV Pass"] == "Fail") | (std_points_wide["Back-Calc Pass"] == "Fail"),
        highlight_color="#F8D7DA",
    ))
    if len(erc_pc_wide):
        st.table(style_table(
            erc_pc_wide, caption="ERC / PC", align="left",
            highlight_rows=(erc_pc_wide["CV Pass"] == "Fail") | (erc_pc_wide["Recovery Pass"] == "Fail"),
            highlight_color="#F8D7DA",
        ))
    if ntc_nec_rows:
        ntc_nec_df = pd.DataFrame(ntc_nec_rows)
        st.table(style_table(
            ntc_nec_df, caption="NTC / NEC", align="left",
            highlight_rows=ntc_nec_df["Status"] == "Fail", highlight_color="#F8D7DA",
        ))

    st.header("Sample Suitability")
    st.table(style_table(
        final_results.drop(columns="Sample #"), caption="Final Sample Results by Dilution",
        align="left", precision=None, precision_overrides=FINAL_RESULTS_PRECISION,
        highlight_rows=final_results["Suitability"] == "Fail", highlight_color="#F8D7DA",
    ))

    st.header("Final Sample Results")
    st.table(style_table(
        reportable_results_display,
        caption=(
            "Final Sample Results — Averaged Across Passing Dilutions — green: below "
            f"{SAMPLE_DNA_PER_PROTEIN_LIMIT:.0f} ng/mg, red: failed acceptance criteria"
        ),
        align="left", precision=None, precision_overrides=FINAL_RESULTS_PRECISION,
        highlight_rows=[
            (reportable_results[_status_col] == "Below", "#D4EDDA"),
            (~reportable_results["Sample Passed"], "#F8D7DA"),
        ],
        dim_mask=loq_dim_mask,
    ))
    if loq_footnote_used:
        st.caption(LOQ_FOOTNOTE_TEXT)

    if len(spike_suitability):
        st.table(style_table(
            spike_suitability,
            caption=(
                f"Spike Recovery Suitability (Quantity %CV ≤ {SAMPLE_QTY_CV_MAX:g}%, Recovery "
                f"{SAMPLE_SPIKE_RECOVERY_MIN:g}–{SAMPLE_SPIKE_RECOVERY_MAX:g}%)"
            ),
            align="left", precision=None, precision_overrides={"Replicates Used": 0},
            highlight_rows=(
                (spike_suitability["CV Pass"] == "Pass") & (spike_suitability["Recovery Pass"] == "Pass")
            ),
            highlight_color="#D4EDDA",
        ))

    # =========================================================================
    # Standard Curve graphs — Ct vs log10(Quantity), same regression line as the
    # notebook's suitability tables above (linear, not 4PL — this pipeline fits
    # a single linear regression to the standard curve points). Fully interactive:
    # hover for well details, click a legend entry to show/hide that group.
    # =========================================================================
    st.header("Standard Curve")

    OKABE_ITO = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7", "#000000"]
    _equation_text = (
        f"Ct = {curve_slope:.4f} × log10(Qty)<br>+ {curve_intercept:.4f}<br>R² = {curve_r2:.4f}"
    )
    _std_log_qty = np.log10(ref_std_df["quantity"])
    _line_x = np.linspace(_std_log_qty.min(), _std_log_qty.max(), 100)
    _line_y = curve_slope * _line_x + curve_intercept

    def _prep_points(data):
        valid = data["quantity"].notna() & (data["quantity"] > 0) & data["ct"].notna()
        points = data.loc[valid, ["sample_name", "ct", "quantity"]].copy()
        points["log_qty"] = np.log10(points["quantity"])
        return points

    def build_curve_figure(title, overlay_groups, legend_title=None):
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=_line_x, y=_line_y, mode="lines", name="Regression Line",
            line=dict(color="#2C3E50", width=2), opacity=0.35, hoverinfo="skip",
        ))
        std_points = _prep_points(ref_std_df)
        fig.add_trace(go.Scatter(
            x=std_points["log_qty"], y=std_points["ct"], mode="markers", name="STD Points",
            marker=dict(color="#2C3E50", size=9, symbol="diamond"),
            customdata=std_points[["sample_name", "quantity"]],
            hovertemplate="<b>%{customdata[0]}</b><br>Ct=%{y:.2f}<br>Quantity=%{customdata[1]:.4g}"
                          "<br>log10(Qty)=%{x:.3f}<extra></extra>",
        ))
        for label, data, color in overlay_groups:
            points = _prep_points(data)
            fig.add_trace(go.Scatter(
                x=points["log_qty"], y=points["ct"], mode="markers", name=label,
                marker=dict(color=color, size=8),
                customdata=points[["sample_name", "quantity"]],
                hovertemplate="<b>%{customdata[0]}</b><br>Ct=%{y:.2f}<br>Quantity=%{customdata[1]:.4g}"
                              "<br>log10(Qty)=%{x:.3f}<extra></extra>",
                visible="legendonly",
            ))
        _eq_y, _eq_yanchor = (0.0, "bottom") if legend_title else (1.0, "top")
        fig.add_annotation(
            xref="paper", yref="paper", x=1.02, y=_eq_y, xanchor="left", yanchor=_eq_yanchor,
            text=_equation_text, showarrow=False, align="left",
            bordercolor="#2C3E50", borderwidth=1, borderpad=8, bgcolor="#FFFFFF",
        )
        legend = (
            dict(
                title=dict(text=f"<b>{legend_title}</b>", font=dict(size=13, color="#2C3E50")),
                bordercolor="#2C3E50", borderwidth=1, bgcolor="#FFFFFF",
                x=1.02, y=1.0, xanchor="left", yanchor="top",
            )
            if legend_title else dict(title=dict(text="Click to show/hide"))
        )
        fig.update_layout(
            title=title, xaxis_title="log10(Quantity)", yaxis_title="Ct",
            template="simple_white", legend=legend, margin=dict(r=220, t=80, b=60),
            width=1000, height=550,
        )
        return fig

    control_groups = [
        (control_type, controls_df[controls_df["control_type"] == control_type], OKABE_ITO[i])
        for i, control_type in enumerate(["NTC", "NEC", "ERC", "HPC", "MPC", "LPC"])
    ]
    fig_controls = build_curve_figure("Standard Curve — QC Controls", control_groups, legend_title="Controls")
    st.plotly_chart(fig_controls, use_container_width=False)

    _base_samples_for_plot = sorted(samples_df["base_sample"].unique())
    sample_groups = [
        (base, samples_df[samples_df["base_sample"] == base], OKABE_ITO[i % len(OKABE_ITO)])
        for i, base in enumerate(_base_samples_for_plot)
    ]
    fig_samples = build_curve_figure("Standard Curve — Sample Results", sample_groups, legend_title="Samples")
    st.plotly_chart(fig_samples, use_container_width=False)

    # =========================================================================
    # Amplification Curves — ΔRn vs Cycle, from the separate "Amplification Data"
    # sheet. Re-reads the uploaded file again (seeking back to the start first).
    # =========================================================================
    st.header("Amplification Curves")

    uploaded_file.seek(0)
    amp_raw = pd.read_excel(uploaded_file, sheet_name="Amplification Data", header=22, engine=engine)

    _amp_rename = {"Well": "well", "Cycle": "cycle", "ΔRn": "delta_rn"}
    _missing_amp_cols = [c for c in _amp_rename if c not in amp_raw.columns]
    if _missing_amp_cols:
        st.warning(f"Amplification Data sheet is missing required column(s): {_missing_amp_cols} — skipping this plot")
    else:
        amp_df = amp_raw[list(_amp_rename)].rename(columns=_amp_rename)

        _well_classification = parsed_df[["well", "sample_name", "sample_group", "control_type"]].drop_duplicates()
        amp_df = amp_df.merge(_well_classification, on="well", how="inner")

        def _amp_group(row):
            if row["sample_group"] == "Reference Standard":
                return "STD"
            if row["control_type"] == "NTC":
                return "NTC"
            if row["control_type"] == "NEC":
                return "NEC"
            if row["control_type"] in ("HPC", "MPC", "LPC"):
                return "PC"
            if row["sample_group"] == "Sample":
                return "Samples"
            return None  # ERC isn't part of this plot's groups

        amp_df["amp_group"] = amp_df.apply(_amp_group, axis=1)
        amp_df = amp_df[amp_df["amp_group"].notna()]
        amp_df["base_sample"] = amp_df["sample_name"].str.replace(r"\s+D\d+(?:\s+S)?$", "", regex=True)

        _AMP_STATIC_COLORS = {
            "STD": "#4D4D4D", "NTC": "#014421", "NEC": "#191970", "PC": "#F4C2C2",
        }
        _AMP_SAMPLE_PALETTE = [
            "#C8A2C8", "#FFDAB9", "#B5EAD7", "#AEC6CF",
            "#FDFD96", "#C1D8C3", "#C3B1E1", "#AFEEEE",
        ]

        fig_amp = go.Figure()

        def _add_well_traces(wells_by_well, label, color, opacity=1.0):
            for i, (well, well_data) in enumerate(wells_by_well):
                well_data = well_data.sort_values("cycle")
                fig_amp.add_trace(go.Scatter(
                    x=well_data["cycle"], y=well_data["delta_rn"], mode="lines",
                    name=label, legendgroup=label, showlegend=(i == 0),
                    line=dict(color=color, width=1.5), opacity=opacity,
                    customdata=well_data[["well", "sample_name"]],
                    hovertemplate="<b>%{customdata[0]} — %{customdata[1]}</b><br>Cycle=%{x}"
                                  "<br>ΔRn=%{y:.4f}<extra></extra>",
                    visible="legendonly",
                ))

        for group in ["STD", "NTC", "NEC", "PC"]:
            group_wells = amp_df[amp_df["amp_group"] == group]
            opacity = 0.5 if group == "STD" else 1.0
            _add_well_traces(group_wells.groupby("well"), group, _AMP_STATIC_COLORS[group], opacity)

        _base_samples_in_amp = sorted(amp_df.loc[amp_df["amp_group"] == "Samples", "base_sample"].unique())
        for i, base in enumerate(_base_samples_in_amp):
            sample_wells = amp_df[(amp_df["amp_group"] == "Samples") & (amp_df["base_sample"] == base)]
            color = _AMP_SAMPLE_PALETTE[i % len(_AMP_SAMPLE_PALETTE)]
            _add_well_traces(sample_wells.groupby("well"), base, color)

        fig_amp.update_layout(
            title="Amplification Curves — ΔRn vs Cycle",
            xaxis_title="Cycle", yaxis_title="ΔRn", template="simple_white",
            legend=dict(
                title=dict(text="<b>Groups</b>", font=dict(size=13, color="#2C3E50")),
                bordercolor="#2C3E50", borderwidth=1, bgcolor="#FFFFFF",
                x=1.02, y=1.0, xanchor="left", yanchor="top",
            ),
            margin=dict(r=200, t=80, b=60),
            width=1000, height=550,
        )
        st.plotly_chart(fig_amp, use_container_width=False)

    st.header("Signatures")
    sig_left, sig_right = st.columns(2)
    with sig_left:
        SUBMITTER_NAME = st.text_input("Submitter Name")
    with sig_right:
        REVIEWER_NAME = st.text_input("Reviewer Name")

    # =========================================================================
    # PDF Report — same layout as the notebook's PDF Report section, built into
    # an in-memory buffer here instead of a file on disk, so it can be offered
    # as a browser download
    # =========================================================================
    from io import BytesIO
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether,
    )

    REPORT_HEADER_COLOR = colors.HexColor("#2C3E50")
    REPORT_ALT_ROW_COLOR = colors.HexColor("#F7F9FA")
    REPORT_BORDER_COLOR = colors.HexColor("#DDDDDD")
    REPORT_FAIL_COLOR = colors.HexColor("#F8D7DA")
    REPORT_PASS_COLOR = colors.HexColor("#D4EDDA")
    _AVAILABLE_WIDTH = 10 * inch

    _pdf_styles = getSampleStyleSheet()
    _title_style = ParagraphStyle("ReportTitle", parent=_pdf_styles["Title"], textColor=REPORT_HEADER_COLOR)
    _section_style = ParagraphStyle(
        "SectionHeader", parent=_pdf_styles["Heading2"], textColor=REPORT_HEADER_COLOR,
        spaceBefore=14, spaceAfter=6,
    )
    _banner_style_pass = ParagraphStyle(
        "BannerPass", parent=_pdf_styles["Heading2"], textColor=colors.HexColor("#155724"),
        backColor=REPORT_PASS_COLOR, alignment=TA_CENTER, borderPadding=8,
    )
    _banner_style_fail = ParagraphStyle(
        "BannerFail", parent=_pdf_styles["Heading2"], textColor=colors.HexColor("#721C24"),
        backColor=REPORT_FAIL_COLOR, alignment=TA_CENTER, borderPadding=8,
    )
    _cell_style = ParagraphStyle("PdfCell", fontName="Helvetica", fontSize=7, leading=8.5, alignment=TA_CENTER)
    _header_cell_style = ParagraphStyle(
        "PdfHeaderCell", parent=_cell_style, fontName="Helvetica-Bold", textColor=colors.white,
    )
    _footnote_style = ParagraphStyle(
        "PdfFootnote", fontName="Helvetica-Oblique", fontSize=7, leading=9,
        textColor=colors.HexColor("#888888"), spaceBefore=4,
    )

    def _pdf_table(data, highlight_mask=None, highlight_color=REPORT_FAIL_COLOR, col_widths=None):
        n_cols = len(data.columns)
        if col_widths is None:
            col_widths = [_AVAILABLE_WIDTH / n_cols] * n_cols
        header_row = [Paragraph(str(c), _header_cell_style) for c in data.columns]
        body_rows = [[Paragraph(str(v), _cell_style) for v in row] for row in data.values.tolist()]
        table = Table([header_row] + body_rows, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), REPORT_HEADER_COLOR),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, REPORT_BORDER_COLOR),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        for row_idx in range(1, len(body_rows) + 1):
            if row_idx % 2 == 0:
                style.append(("BACKGROUND", (0, row_idx), (-1, row_idx), REPORT_ALT_ROW_COLOR))
        # highlight_mask is either a single boolean iterable (paired with
        # highlight_color) or a list of (mask, color) tuples for multi-condition
        # row highlighting — later entries win where masks overlap, mirroring
        # style_table()'s own highlight_rows in Scripts/plotting.py.
        if highlight_mask is not None:
            highlight_specs = (
                highlight_mask if isinstance(highlight_mask, list) else [(highlight_mask, highlight_color)]
            )
            for mask, color in highlight_specs:
                for i, flag in enumerate(mask, start=1):
                    if flag:
                        style.append(("BACKGROUND", (0, i), (-1, i), color))
        table.setStyle(TableStyle(style))
        return table

    _logo = Table([["[ COMPANY LOGO ]"]], colWidths=[2.5 * inch], rowHeights=[0.7 * inch])
    _logo.hAlign = "CENTER"
    _logo.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, REPORT_HEADER_COLOR),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TEXTCOLOR", (0, 0), (-1, -1), REPORT_HEADER_COLOR),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
    ]))

    pdf_story = [
        _logo,
        Spacer(1, 0.2 * inch),
        Paragraph("Residual CHO DNA Sample Analysis Report", _title_style),
        Spacer(1, 0.15 * inch),
    ]

    pdf_story.append(Paragraph("Assay Run Information", _section_style))
    run_info_df = pd.DataFrame([
        ["Assay Name", ASSAY_NAME or "—"],
        ["SA Run Number", RUN_NUMBER or "—"],
        ["Assay Date", ASSAY_DATE or "—"],
        ["Request Number", REQUEST_NUMBER or "—"],
        ["Test Method", TEST_METHOD or "—"],
        ["Notebook Number", NOTEBOOK_NUMBER or "—"],
        ["Laboratory", LAB_NAME or "—"],
        ["Laboratory Address", LAB_ADDRESS or "—"],
    ], columns=["Field", "Value"])
    pdf_story.append(_pdf_table(run_info_df, col_widths=[2 * inch, 5 * inch]))

    if changed_criteria:
        pdf_story.append(Paragraph("Modified Acceptance Criteria (this session only)", _section_style))
        pdf_story.append(_pdf_table(
            format_df_for_display(pd.DataFrame(changed_criteria)),
            col_widths=[4 * inch, 1.5 * inch, 1.5 * inch],
        ))

    pdf_story.append(Paragraph("System Suitability", _section_style))
    pdf_story.append(Paragraph(
        f"System Suitability: {status}",
        _banner_style_pass if system_suitability_pass else _banner_style_fail,
    ))
    pdf_story.append(Spacer(1, 0.1 * inch))
    pdf_story.append(_pdf_table(
        format_df_for_display(curve_fit_wide),
        highlight_mask=(curve_fit_wide["R² Pass"] == "Fail") | (curve_fit_wide["Efficiency Pass"] == "Fail"),
    ))
    pdf_story.append(Spacer(1, 0.1 * inch))
    pdf_story.append(_pdf_table(
        format_df_for_display(std_points_wide),
        highlight_mask=(std_points_wide["Ct %CV Pass"] == "Fail") | (std_points_wide["Back-Calc Pass"] == "Fail"),
    ))
    if len(erc_pc_wide):
        pdf_story.append(Spacer(1, 0.1 * inch))
        pdf_story.append(_pdf_table(
            format_df_for_display(erc_pc_wide),
            highlight_mask=(erc_pc_wide["CV Pass"] == "Fail") | (erc_pc_wide["Recovery Pass"] == "Fail"),
        ))
    if ntc_nec_rows:
        _ntc_nec_df = pd.DataFrame(ntc_nec_rows)
        pdf_story.append(Spacer(1, 0.1 * inch))
        pdf_story.append(_pdf_table(format_df_for_display(_ntc_nec_df), highlight_mask=_ntc_nec_df["Status"] == "Fail"))

    pdf_story.append(Paragraph("Sample Suitability", _section_style))
    pdf_story.append(_pdf_table(
        format_df_for_display(
            final_results.drop(columns="Sample #"),
            precision=None, precision_overrides=FINAL_RESULTS_PRECISION,
        ),
        highlight_mask=final_results["Suitability"] == "Fail",
    ))

    pdf_story.append(Paragraph("Final Sample Results", _section_style))
    pdf_story.append(_pdf_table(
        format_df_for_display(
            _apply_pdf_loq_footnote(reportable_results.drop(columns="Sample Passed")),
            precision=None, precision_overrides=FINAL_RESULTS_PRECISION,
        ),
        highlight_mask=[
            (reportable_results[_status_col] == "Below", REPORT_PASS_COLOR),
            (~reportable_results["Sample Passed"], REPORT_FAIL_COLOR),
        ],
    ))
    if loq_footnote_used:
        pdf_story.append(Paragraph(LOQ_FOOTNOTE_TEXT, _footnote_style))

    if len(spike_suitability):
        pdf_story.append(Paragraph("Spike Recovery Suitability (informational)", _section_style))
        pdf_story.append(_pdf_table(
            format_df_for_display(spike_suitability, precision=None, precision_overrides={"Replicates Used": 0}),
            highlight_mask=(
                (spike_suitability["CV Pass"] == "Pass") & (spike_suitability["Recovery Pass"] == "Pass")
            ),
            highlight_color=REPORT_PASS_COLOR,
        ))

    _sig_table = Table([
        ["Submitter", "Reviewer"],
        [f"Name: {SUBMITTER_NAME or '—'}", f"Name: {REVIEWER_NAME or '—'}"],
        ["Signature: " + "_" * 30, "Signature: " + "_" * 30],
        ["Date: " + "_" * 20, "Date: " + "_" * 20],
    ], colWidths=[4 * inch, 4 * inch])
    _sig_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), REPORT_HEADER_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    pdf_story.append(KeepTogether([
        Spacer(1, 0.4 * inch),
        Paragraph("Signatures", _section_style),
        _sig_table,
    ]))

    pdf_buffer = BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=landscape(letter),
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    doc.build(pdf_story)
    pdf_buffer.seek(0)

    _safe_run_no = RUN_NUMBER.strip().replace(" ", "_") if RUN_NUMBER.strip() else "run"
    _downloaded = st.download_button(
        label="Download PDF Report",
        data=pdf_buffer,
        file_name=f"Sample_Analysis_Report_{_safe_run_no}.pdf",
        mime="application/pdf",
    )
    # log_report_generated() (audit_log.py) is a no-op unless RESIDNA_AUDIT_LOG
    # is set — see that module's docstring. st.download_button() returns True
    # exactly once, on the rerun the click itself triggers, so this fires once
    # per actual download rather than needing manual dedup against Streamlit's
    # rerun-on-every-widget-change behavior.
    if _downloaded:
        log_report_generated(
            uploaded_filename=uploaded_file.name,
            file_bytes=uploaded_file.getvalue(),
            assay_name=ASSAY_NAME,
            run_number=RUN_NUMBER,
            submitter_name=SUBMITTER_NAME,
            reviewer_name=REVIEWER_NAME,
            system_suitability_status=status,
            sample_count=len(_base_sample_ids),
            changed_criteria=changed_criteria,
        )
