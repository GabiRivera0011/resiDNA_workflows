"""Shared qPCR analysis logic used by both the Phase I notebook and the Streamlit app.

Pure functions only — no Streamlit, IPython, or notebook-specific display code.
Kept manually in sync with the acceptance criteria documented in README.md.
"""
import pandas as pd


def classify_sample(sample_name, task):
    """Classify a well into Reference Standard, Control (with subtype), or Sample.

    A blank sample_name normally means an empty/unused well, not a real Sample —
    except Reference Standard wells, which some exports leave unnamed and rely on
    Task="STANDARD" alone to identify. So blank name + non-STANDARD task is
    Unclassified rather than falling through to Sample, where it would otherwise
    corrupt every sample_name-keyed groupby downstream (e.g. base_sample).
    """
    if pd.isna(sample_name) and task != "STANDARD":
        return pd.Series(["Unclassified", None])

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


def resolve_sample_replicates(samples_df, cv_max):
    """Per-dilution triplicate handling with single-outlier exclusion.

    `samples_df` must have one row per well, with columns: sample_name,
    quantity (raw per-well value, not the mean), dilution_factor,
    protein_concentration, quantity_percent_cv, quantity_mean, dilution_adjusted,
    total_dna_per_ml, total_dna_per_protein_concentration (the last five
    are the instrument's own triplicate figures, identical across a
    dilution's 3 well-rows).

    When a dilution's full-triplicate Quantity %CV already passes cv_max,
    the instrument's own reported figures are passed through untouched —
    consistent with this pipeline's rule that instrument-computed values
    survive as-is, not recalculated. Only when the full-triplicate %CV
    fails does this check whether dropping the single well driving the CV
    up brings the remaining 2 wells' %CV under cv_max; if so, that pair's
    mean becomes the dilution's Quantity %CV / Quantity Mean / Dilution
    Adjusted / Total DNA (ng/mL) / DNA per Protein (2-of-3 replicates)
    instead of an outright fail. A dilution that still fails with its best
    2 wells is left as a 3-well fail, unchanged.

    Returns one row per sample_name: quantity_percent_cv, quantity_mean,
    dilution_adjusted, total_dna_per_ml, total_dna_per_protein_concentration,
    replicates_used.
    """
    def mean_sd_cv(values):
        s = pd.Series(values, dtype=float)
        mean = s.mean()
        sd = s.std()
        cv = (sd / mean * 100) if mean else float("nan")
        return mean, sd, cv

    rows = []
    for sample_name, group in samples_df.groupby("sample_name", sort=False):
        quantities = group["quantity"].dropna().tolist()
        dilution_factor = group["dilution_factor"].iloc[0]
        protein_concentration = group["protein_concentration"].iloc[0]

        # Default: trust the instrument's own reported triplicate figures as-is
        cv = group["quantity_percent_cv"].iloc[0]
        quantity_mean = group["quantity_mean"].iloc[0]
        dilution_adjusted = group["dilution_adjusted"].iloc[0]
        total_dna_per_ml = group["total_dna_per_ml"].iloc[0]
        total_dna_per_protein = group["total_dna_per_protein_concentration"].iloc[0]
        replicates_used = len(quantities)

        if len(quantities) == 3 and not (pd.notna(cv) and cv <= cv_max):
            pairs = [mean_sd_cv(quantities[:i] + quantities[i + 1:]) for i in range(3)]
            best_mean, _, best_cv = min(pairs, key=lambda t: t[2])
            if pd.notna(best_cv) and best_cv <= cv_max:
                quantity_mean = best_mean
                dilution_adjusted = best_mean * dilution_factor
                total_dna_per_ml = dilution_adjusted
                total_dna_per_protein = (
                    dilution_adjusted / protein_concentration if protein_concentration else float("nan")
                )
                cv, replicates_used = best_cv, 2

        rows.append({
            "sample_name": sample_name,
            "quantity_percent_cv": cv,
            "quantity_mean": quantity_mean,
            "dilution_adjusted": dilution_adjusted,
            "total_dna_per_ml": total_dna_per_ml,
            "total_dna_per_protein_concentration": total_dna_per_protein,
            "replicates_used": replicates_used,
        })

    return pd.DataFrame(rows)


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
