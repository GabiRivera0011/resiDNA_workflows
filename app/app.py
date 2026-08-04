import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import klib

# Scripts/ lives at the repo root, one level up from this file's app/ folder
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Scripts"))

from qpcr import classify_sample, recovery_bounds, combined_suitability, compute_sigma_ct, compute_dilutional_linearity
from plotting import style_table, format_df_for_display

# Must be the very first Streamlit command — widens the page from the default
# centered ~730px column to the full browser width, so wide tables (like Sample
# Suitability, with 11 columns) fit without horizontal scrolling
st.set_page_config(page_title="Residual DNA QC Tool", layout="wide")

st.title("Residual DNA QC Tool")


FINAL_RESULTS_PRECISION = {
    "Total DNA (ng/mL)": 4,
    "Protein Concentration (mg/mL)": 4,
    "DNA per Protein (ng/mg)": 4,
}


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

    df = klib.data_cleaning(df, col_exclude=_columns_required_downstream)
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

    # --- Acceptance criteria (fixed defaults, matching the notebook) ---
    STD_R2_MIN = 0.99
    STD_CT_CV_MAX = 20.0
    STD_BACK_CALC_BIAS_MAX = 25.0
    STD_EFFICIENCY_MIN = 90.0
    STD_EFFICIENCY_MAX = 110.0
    CTRL_QTY_CV_MAX = 20.0
    PC_RECOVERY_MIN = 80.0
    PC_RECOVERY_MAX = 125.0
    ERC_RECOVERY_MIN = 50.0
    ERC_RECOVERY_MAX = 150.0
    LOD_SIGMA_MULTIPLIER = 3.3
    LOQ_SIGMA_MULTIPLIER = 10.0
    SAMPLE_QTY_CV_MAX = 25.0
    SAMPLE_LINEARITY_BIAS_MAX = 20
    SAMPLE_DNA_PER_PROTEIN_LIMIT = 15.0

    # --- Standard curve stats (silent) ---
    reg_stats = regression_table.set_index("Metric")["Value"].astype(float)
    curve_r2 = reg_stats["R2"]
    curve_slope = reg_stats["Slope"]
    curve_intercept = reg_stats["y-Intercept"]
    curve_efficiency = reg_stats["Efficiency"]
    curve_std_error = reg_stats["Std error"]
    loq_ct = compute_sigma_ct(curve_std_error, curve_slope, curve_intercept, LOQ_SIGMA_MULTIPLIER)

    # --- STD Curve Point suitability (silent) ---
    std_suitability = (
        ref_std_df.groupby("sample_name", as_index=False)
        .agg(**{
            "Quantity": ("quantity", "first"),
            "Ct %CV": ("ct_cv_percent", "first"),
            "Back-Calc %Bias": ("back_calculation_percent_difference_mean", "first"),
        })
        .sort_values("Quantity")
        .reset_index(drop=True)
    )
    std_suitability["Ct %CV Pass"] = std_suitability["Ct %CV"] <= STD_CT_CV_MAX
    std_suitability["Back-Calc Pass"] = std_suitability["Back-Calc %Bias"].abs() <= STD_BACK_CALC_BIAS_MAX

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
        .agg(**{"Wells Passing": ("well_pass", "sum"), "Total Wells": ("well_pass", "size")})
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
            "Criteria": "Undetermined, or Ct ≥ LOQ Ct",
            "Value": f"{row['Wells Passing']}/{row['Total Wells']}",
            "Status": "Pass" if row["Pass"] else "Fail",
        })

    # --- Sample %CV suitability (silent) ---
    sample_cv = (
        samples_df.groupby("sample_name", as_index=False)
        .agg(**{"Quantity %CV": ("quantity_percent_cv", "first")})
        .sort_values("sample_name")
        .reset_index(drop=True)
    )

    # --- Dilutional Linearity suitability (silent) ---
    unspiked_dilutions = (
        samples_df[~samples_df["sample_name"].str.endswith(" S")]
        .drop_duplicates(subset="sample_name")
        [["base_sample", "sample_name", "ct_cv_percent", "quantity_percent_cv", "dilution_adjusted"]]
        .copy()
    )
    linearity_df = compute_dilutional_linearity(unspiked_dilutions, SAMPLE_LINEARITY_BIAS_MAX)
    linearity_df = linearity_df.rename(columns={"sample_name": "Sample"})

    # --- Final Sample Results by Dilution (silent build) ---
    unspiked_samples = samples_df[~samples_df["sample_name"].str.endswith(" S")].copy()
    final_results = (
        unspiked_samples.drop_duplicates(subset="sample_name")
        [[
            "base_sample", "sample_name", "dilution_factor", "quantity_percent_cv",
            "total_dna_per_ml", "protein_concentration", "total_dna_per_protein_concentration",
        ]]
        .rename(columns={
            "base_sample": "Base Sample", "sample_name": "Sample",
            "dilution_factor": "Dilution Factor", "quantity_percent_cv": "Quantity %CV",
            "total_dna_per_ml": "Total DNA (ng/mL)",
            "protein_concentration": "Protein Concentration (mg/mL)",
            "total_dna_per_protein_concentration": "DNA per Protein (ng/mg)",
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

    final_results["Suitability"] = final_results.apply(
        lambda row: combined_suitability([row["Quantity %CV Suitability"], row["Linearity Suitability"]]),
        axis=1,
    )
    final_results = final_results.rename(columns={"Base Sample": "Sample #", "Sample": "Sample Dilution"})[[
        "Sample #", "Sample Dilution", "Dilution Factor",
        "Quantity %CV", "Quantity %CV Suitability",
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
    reportable_results = (
        final_results[final_results["Suitability"] == "Pass"]
        .groupby("Sample #")
        .agg(**{
            "Total DNA (ng/mL)": ("Total DNA (ng/mL)", "mean"),
            "Protein Concentration (mg/mL)": ("Protein Concentration (mg/mL)", "first"),
            "DNA per Protein (ng/mg)": ("DNA per Protein (ng/mg)", "mean"),
            "Dilutions Averaged": ("Sample Dilution", lambda s: f"{', '.join(sorted(s))} (n={len(s)})"),
        })
        .reset_index()
    )
    reportable_results.insert(1, "Sample ID", reportable_results["Sample #"].map(sample_id_map))
    reportable_results.insert(2, "Sample Name", reportable_results["Sample #"].map(sample_display_names))

    _status_col = f"≤ {SAMPLE_DNA_PER_PROTEIN_LIMIT:.0f} ng/mg Status"
    reportable_results[_status_col] = reportable_results["DNA per Protein (ng/mg)"].apply(
        lambda v: "N/A" if pd.isna(v) else ("Below" if v < SAMPLE_DNA_PER_PROTEIN_LIMIT else "Above")
    )

    # =========================================================================
    # DISPLAY — only the sections that appear in the PDF report
    # =========================================================================

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
    st.table(style_table(final_results, caption="Final Sample Results by Dilution",
                          align="left", precision_overrides=FINAL_RESULTS_PRECISION))

    st.header("Final Sample Results")
    st.table(style_table(
        reportable_results, caption="Averaged per Sample", align="left",
        precision_overrides=FINAL_RESULTS_PRECISION,
        highlight_rows=reportable_results[_status_col] == "Below", highlight_color="#D4EDDA",
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
        if highlight_mask is not None:
            for i, flag in enumerate(highlight_mask, start=1):
                if flag:
                    style.append(("BACKGROUND", (0, i), (-1, i), highlight_color))
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
    pdf_story.append(_pdf_table(format_df_for_display(final_results, precision_overrides=FINAL_RESULTS_PRECISION)))

    pdf_story.append(Paragraph("Final Sample Results", _section_style))
    pdf_story.append(_pdf_table(
        format_df_for_display(reportable_results, precision_overrides=FINAL_RESULTS_PRECISION),
        highlight_mask=reportable_results[_status_col] == "Below",
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
    st.download_button(
        label="Download PDF Report",
        data=pdf_buffer,
        file_name=f"Sample_Analysis_Report_{_safe_run_no}.pdf",
        mime="application/pdf",
    )
