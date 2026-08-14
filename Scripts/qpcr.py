"""Shared qPCR analysis logic used by both the Phase I notebook and the Streamlit app.

Pure functions only — no Streamlit, IPython, or notebook-specific display code.
Kept manually in sync with the acceptance criteria documented in README.md.

Two non-obvious gotchas live in the notebook/app.py (not here, since they're
parsing/display concerns, not calculation) but are worth knowing before
touching anything downstream of these functions:
  1. Both callers clean the parsed DataFrame with
     `klib.data_cleaning(..., convert_dtypes=False)` — klib's default float32
     downcast reintroduces float noise (e.g. 0.003 -> 0.003000000026077032)
     once values are displayed at instrument sigfig instead of being rounded.
  2. In the *averaged* Final Sample Results table, Total DNA / DNA per Protein
     are genuinely computed means (via aggregate_sample_results below), not
     instrument pass-throughs — natural/instrument-sigfig display is correct
     for the by-dilution table but surfaces raw averaging noise here, so both
     callers give that table's Total DNA / DNA per Protein an explicit
     precision instead (see each file's `_AVERAGED_PRECISION`).
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


def compute_loq_and_range(std_suitability):
    """Derive the sample LOQ and calibrated STD Range from the standard curve's
    own back-calculated values at its highest (STD1) and lowest (STD6)
    calibrated points — replaces the old ICH sigma-in-Ct-space LOQ formula.

    `std_suitability` must have one row per standard level, with columns
    Quantity, Back-Calc Mean, Ct Mean. `.idxmax()`/`.idxmin()` are NaN-safe
    (unlike `sort_values("Quantity")` + `iloc[0]`/`iloc[-1]`: ascending sort
    puts NaN rows last, which would silently pick a NaN-quantity row as
    "highest" if any standard level had a missing Quantity).

    Returns a dict: std1_backcalc_mean / std6_backcalc_mean (the calibrated
    range bounds), loq_quantity (= std6_backcalc_mean, the sample LOQ), and
    loq_ct (STD6's own measured Ct Mean — used by NTC/NEC, which typically
    don't report a Quantity at all, so their check stays in Ct space).
    """
    std1_row = std_suitability.loc[std_suitability["Quantity"].idxmax()]
    std6_row = std_suitability.loc[std_suitability["Quantity"].idxmin()]
    std1_backcalc_mean = std1_row["Back-Calc Mean"]
    std6_backcalc_mean = std6_row["Back-Calc Mean"]
    return {
        "std1_backcalc_mean": std1_backcalc_mean,
        "std6_backcalc_mean": std6_backcalc_mean,
        "loq_quantity": std6_backcalc_mean,
        "loq_ct": std6_row["Ct Mean"],
    }


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


def compute_range_suitability(unspiked_samples, resolved_replicates, std6_backcalc_mean, std1_backcalc_mean):
    """Sample STD Range suitability: compares each dilution's raw
    (pre-dilution-adjustment) triplicate Quantity Mean — after single-outlier
    assessment, via `resolved_replicates` — against the standard curve's own
    calibrated range `[std6_backcalc_mean, std1_backcalc_mean]` (see
    `compute_loq_and_range`). Below `std6_backcalc_mean` is the definition of
    "below LOQ"; above `std1_backcalc_mean` is above the curve's highest
    calibrated point. Undetermined (no evaluable triplicate) gets its own
    status rather than a false Fail, consistent with the Quantity %CV check.

    `unspiked_samples` must have columns base_sample, sample_name.
    `resolved_replicates` (from `resolve_sample_replicates` above) must have
    columns sample_name, quantity_mean.

    Returns one row per sample_name: base_sample, sample_name, quantity_mean,
    "Range Status" (In Range / Out of Range / Undetermined), "Pass"
    (True / False / pd.NA).
    """
    range_df = (
        unspiked_samples
        .drop_duplicates(subset="sample_name")[["base_sample", "sample_name"]]
        .merge(resolved_replicates[["sample_name", "quantity_mean"]], on="sample_name")
    )
    range_df["Range Status"] = range_df["quantity_mean"].apply(
        lambda q: "Undetermined" if pd.isna(q)
        else ("Out of Range" if (q < std6_backcalc_mean or q > std1_backcalc_mean) else "In Range")
    )
    range_df["Pass"] = range_df["Range Status"].map({"In Range": True, "Out of Range": False}).astype(object)
    range_df.loc[range_df["Range Status"] == "Undetermined", "Pass"] = pd.NA
    return range_df


def compute_dilutional_linearity(unspiked_dilutions, bias_max, eligible_mask=None):
    """Reference-dilution Dilutional Linearity %Bias check.

    `unspiked_dilutions` must have columns: base_sample, sample_name, ct_cv_percent,
    quantity_percent_cv, dilution_adjusted.

    For each base_sample, the dilution with the lowest combined Ct %CV + Quantity %CV
    (its most precise triplicate) among ELIGIBLE dilutions is taken as that sample's
    reference. `eligible_mask`, if given, is a boolean Series aligned to
    `unspiked_dilutions` restricting which dilutions may be picked as the reference
    (e.g. dilutions that already pass Quantity %CV and are within the standard curve's
    calibrated range) — default None means every dilution is eligible, preserving the
    original behavior (used unchanged by app/app.py). Every dilution's Dilution
    Adjusted quantity is still compared to its base_sample's reference regardless of
    the dilution's OWN eligibility — only the reference pick is restricted. A
    base_sample with zero eligible dilutions ends up with no reference entry, so its
    rows all get NaN "% Bias" / pd.NA "Pass" via the .map() below (no error, no
    special-casing needed).

    Returns `unspiked_dilutions` with "Reference Dilution Adjusted", "% Bias", and
    "Pass" columns added.
    """
    combined_cv = (
        unspiked_dilutions["ct_cv_percent"].fillna(float("inf"))
        + unspiked_dilutions["quantity_percent_cv"].fillna(float("inf"))
    )
    candidates = unspiked_dilutions.assign(combined_cv=combined_cv)
    if eligible_mask is not None:
        candidates = candidates[eligible_mask]

    reference_dilution_adjusted = (
        candidates
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


def aggregate_sample_results(final_results, sample_id_map, sample_display_names, dna_per_protein_limit):
    """Average each sample's suitability-passing dilutions into a single Total
    DNA / DNA per Protein result. A sample with zero passing dilutions (e.g.
    every dilution was Out of Range or Undetermined) is still reported —
    averaged from ALL its dilutions instead, since a flagged number is more
    useful than no row at all; callers should red-highlight rows where
    "Sample Passed" is False, since that fallback average isn't a validated
    result the way a passing row's average is. Protein Concentration is
    constant per sample (same for every dilution), so it's carried through via
    "first" rather than averaged.

    `final_results` must have one row per dilution, with columns: Sample #,
    Sample, Suitability (Pass/Fail), Total DNA (ng/mL), Protein Concentration
    (mg/mL), DNA per Protein (ng/mg), Quantity Mean. `sample_id_map` /
    `sample_display_names` are dicts keyed by Sample #, used to insert the
    optional operator-entered Sample ID / Sample Name columns.

    Returns (reportable_results, status_col) — status_col is the name of the
    added "≤ {limit} ng/mg Status" column (Below/Above/N/A), returned
    alongside since callers need the exact column name for highlighting.
    Callers still own: the below-LOQ mask/footnote (LOQ is caller-specific
    context, not part of this aggregation) and all display formatting.
    """
    def _aggregate_sample(group):
        passing = group[group["Suitability"] == "Pass"]
        use = passing if len(passing) > 0 else group
        return pd.Series({
            "Total DNA (ng/mL)": use["Total DNA (ng/mL)"].mean(),
            "Protein Concentration (mg/mL)": use["Protein Concentration (mg/mL)"].iloc[0],
            "DNA per Protein (ng/mg)": use["DNA per Protein (ng/mg)"].mean(),
            "Quantity Mean": use["Quantity Mean"].mean(),
            "Dilutions Averaged": f"{', '.join(sorted(use['Sample']))} (n={len(use)})",
        })

    reportable_results = (
        final_results.groupby("Sample #").apply(_aggregate_sample, include_groups=False).reset_index()
    )
    sample_passed = final_results.groupby("Sample #")["Suitability"].apply(lambda s: (s == "Pass").any())
    reportable_results["Sample Passed"] = reportable_results["Sample #"].map(sample_passed)

    reportable_results.insert(1, "Sample ID", reportable_results["Sample #"].map(sample_id_map))
    reportable_results.insert(2, "Sample Name", reportable_results["Sample #"].map(sample_display_names))

    status_col = f"≤ {dna_per_protein_limit:.0f} ng/mg Status"
    reportable_results[status_col] = reportable_results["DNA per Protein (ng/mg)"].apply(
        lambda v: "N/A" if pd.isna(v) else ("Below" if v < dna_per_protein_limit else "Above")
    )
    return reportable_results, status_col
