"""Shared qPCR analysis logic used by both the Phase I notebook and the Streamlit app.

Pure functions only — no Streamlit, IPython, or notebook-specific display code.
Kept manually in sync with the acceptance criteria documented in README.md.
"""
import pandas as pd


def classify_sample(sample_name, task):
    """Classify a well into Reference Standard, Control (with subtype), or Sample."""
    name = str(sample_name).strip().upper()

    if task == "STANDARD" or name.startswith("STD"):
        return pd.Series(["Reference Standard", "STD"])
    if name.startswith("NTC"):
        return pd.Series(["Control", "NTC"])
    if name.startswith("NEC"):
        return pd.Series(["Control", "NEC"])
    if name.startswith("ERC"):
        return pd.Series(["Control", "ERC"])
    if name.startswith("HPC"):
        return pd.Series(["Control", "HPC"])
    if name.startswith("MPC"):
        return pd.Series(["Control", "MPC"])
    if name.startswith("LPC"):
        return pd.Series(["Control", "LPC"])
    return pd.Series(["Sample", "Sample"])


def recovery_bounds(control_type, pc_min, pc_max, erc_min, erc_max):
    """%Recovery acceptance bounds — PC (HPC/MPC/LPC) and ERC use different ranges."""
    if control_type in ("HPC", "MPC", "LPC"):
        return pc_min, pc_max
    return erc_min, erc_max


def combined_suitability(statuses):
    """Combine several Pass/Fail/N/A verdicts into one overall verdict."""
    statuses = set(statuses)
    if "Fail" in statuses:
        return "Fail"
    if "N/A" in statuses:
        return "N/A"
    return "Pass"


def compute_sigma_ct(std_error, slope, intercept, sigma_multiplier):
    """ICH Q2(R1) / USP <1225> signal-to-noise Ct, converted from log-quantity space.

    Used for both LOD (sigma_multiplier=3.3) and LOQ (sigma_multiplier=10.0).
    """
    log_qty = sigma_multiplier * std_error / abs(slope)
    return slope * log_qty + intercept


def compute_dilutional_linearity(unspiked_dilutions, bias_max):
    """Reference-dilution Dilutional Linearity %Bias check.

    `unspiked_dilutions` must have columns: base_sample, sample_name, ct_cv_percent,
    quantity_percent_cv, dilution_adjusted.

    For each base_sample, the dilution with the lowest combined Ct %CV + Quantity %CV
    (its most precise triplicate) is taken as that sample's reference. Every dilution's
    Dilution Adjusted quantity is then compared to that reference to test linearity
    across the series.

    Returns `unspiked_dilutions` with "Reference Dilution Adjusted", "% Bias", and
    "Pass" columns added.
    """
    combined_cv = (
        unspiked_dilutions["ct_cv_percent"].fillna(float("inf"))
        + unspiked_dilutions["quantity_percent_cv"].fillna(float("inf"))
    )
    reference_dilution_adjusted = (
        unspiked_dilutions.assign(combined_cv=combined_cv)
        .sort_values("combined_cv")
        .drop_duplicates(subset="base_sample", keep="first")
        .set_index("base_sample")["dilution_adjusted"]
    )

    linearity_df = unspiked_dilutions.copy()
    linearity_df["Reference Dilution Adjusted"] = linearity_df["base_sample"].map(reference_dilution_adjusted)

    # % Bias = (x1 - x2) / x2 × 100, where x2 is the sample's reference dilution
    linearity_df["% Bias"] = (
        (linearity_df["dilution_adjusted"] - linearity_df["Reference Dilution Adjusted"])
        / linearity_df["Reference Dilution Adjusted"] * 100
    )
    linearity_df["Pass"] = (linearity_df["% Bias"].abs() <= bias_max).astype(object)
    linearity_df.loc[linearity_df["% Bias"].isna(), "Pass"] = pd.NA

    return linearity_df
