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
    replicates_used. Correctly columned (just no rows) even when `samples_df`
    has zero rows — `pd.DataFrame([])` on an empty row list otherwise returns
    a DataFrame with no columns at all, which breaks any caller's column
    lookup (e.g. `.set_index("sample_name")`) rather than finding zero rows.
    """
    columns = [
        "sample_name", "quantity_percent_cv", "quantity_mean", "dilution_adjusted",
        "total_dna_per_ml", "total_dna_per_protein_concentration", "replicates_used",
    ]

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
                # Unlike the passthrough case above, these are genuinely computed
                # here (not instrument-reported) — round to the same precision the
                # instrument itself uses for these fields (4 decimals for
                # Quantity/Total DNA/DNA per Protein, 2 for %CV), so a rescued
                # dilution's display doesn't leak raw division noise (e.g.
                # dilution_adjusted / protein_concentration producing something
                # like 2.857142857142857) once display shows natural/instrument
                # sigfig instead of forcing its own rounding.
                quantity_mean = round(best_mean, 4)
                dilution_adjusted = round(best_mean * dilution_factor, 4)
                total_dna_per_ml = dilution_adjusted
                total_dna_per_protein = (
                    round(dilution_adjusted / protein_concentration, 4) if protein_concentration else float("nan")
                )
                cv, replicates_used = round(best_cv, 2), 2

        rows.append({
            "sample_name": sample_name,
            "quantity_percent_cv": cv,
            "quantity_mean": quantity_mean,
            "dilution_adjusted": dilution_adjusted,
            "total_dna_per_ml": total_dna_per_ml,
            "total_dna_per_protein_concentration": total_dna_per_protein,
            "replicates_used": replicates_used,
        })

    return pd.DataFrame(rows, columns=columns)


def identify_cv_outlier(well_labels, values, cv_max):
    """Diagnostic only — never alters a reported value. For a 3-well group,
    identifies which single well is the best explanation for an out-of-range
    %CV: the one whose exclusion minimizes the remaining pair's %CV, using
    the same selection method as resolve_sample_replicates(). Returns that
    well's label (e.g. "A1"), or None if the full-triplicate %CV already
    passes cv_max, or if there aren't exactly 3 wells.

    Flags regardless of whether excluding that well would actually bring the
    %CV under cv_max — this is for manual review (e.g. re-checking the well
    in the source instrument software), not an automatic correction. STD and
    Control suitability continue to use the full-triplicate instrument
    figures unchanged; this function only surfaces which well to look at.
    """
    if len(values) != 3 or len(well_labels) != 3:
        return None
    s = pd.Series(values, dtype=float)
    full_cv = (s.std() / s.mean() * 100) if s.mean() else float("nan")
    if pd.isna(full_cv) or full_cv <= cv_max:
        return None

    best_idx, best_cv = None, float("inf")
    for i in range(3):
        remaining = pd.Series([v for j, v in enumerate(values) if j != i], dtype=float)
        cv = (remaining.std() / remaining.mean() * 100) if remaining.mean() else float("inf")
        if cv < best_cv:
            best_cv, best_idx = cv, i
    return well_labels[best_idx]


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


SAMPLE_STATUS_PRIORITY = ["Reportable", "LOQ - Spike Test", "ULOQ - Adjust Dilution", "Retest"]


def _classify_dilution_status(row, range_suitability_col, std6_backcalc_mean, std1_backcalc_mean):
    """One dilution's reporting status.

    "Reportable" if the dilution fully passes (mirrors `Suitability`). Otherwise
    "LOQ - Spike Test" / "ULOQ - Adjust Dilution" apply only when STD Range is
    the SOLE failing check — Quantity %CV passes and Linearity is Pass or N/A
    (N/A isn't a hard fail: per compute_dilutional_linearity, a dilution whose
    own %CV+Range would otherwise pass never fails to get a reference, so N/A
    here reflects the rest of the SAMPLE lacking one, not this dilution being
    unreliable) — split by whether the failing Quantity Mean sits below STD6
    (LOQ) or above STD1 (ULOQ). Anything else (STD Range itself passes but
    another check fails, or multiple checks fail together) is "Retest".
    """
    if row["Suitability"] == "Pass":
        return "Reportable"

    only_range_fails = (
        row[range_suitability_col] == "Fail"
        and row["Quantity %CV Suitability"] == "Pass"
        and row["Linearity Suitability"] in ("Pass", "N/A")
    )
    quantity_mean = row["Quantity Mean"]
    if only_range_fails and pd.notna(quantity_mean):
        if quantity_mean < std6_backcalc_mean:
            return "LOQ - Spike Test"
        if quantity_mean > std1_backcalc_mean:
            return "ULOQ - Adjust Dilution"
    return "Retest"


def compute_sample_status(final_results, range_suitability_col, std6_backcalc_mean, std1_backcalc_mean):
    """Per-sample reporting Status for the averaged Final Sample Results table:
    "Reportable", "Retest", "ULOQ - Adjust Dilution", or "LOQ - Spike Test".

    A sample can have multiple dilutions with different outcomes (e.g. one
    dilution below LOQ, another failing Quantity %CV outright) — each dilution
    is classified via `_classify_dilution_status`, and the sample reports
    whichever status ranks best across its own dilutions (SAMPLE_STATUS_PRIORITY),
    the same "any dilution passing is enough" rule `aggregate_sample_results`
    already applies when deciding "Sample Passed".

    `final_results` must have one row per dilution, with columns: Sample #,
    Suitability, Quantity %CV Suitability, Linearity Suitability, Quantity Mean,
    and `range_suitability_col` (the STD Range Suitability column — its exact
    name embeds the STD6/STD1 bounds, so it's passed in rather than hardcoded).

    Returns a Series indexed by Sample #.
    """
    dilution_status = final_results.apply(
        lambda row: _classify_dilution_status(row, range_suitability_col, std6_backcalc_mean, std1_backcalc_mean),
        axis=1,
    )
    return (
        final_results.assign(_status=dilution_status)
        .groupby("Sample #")["_status"]
        .agg(lambda statuses: next(s for s in SAMPLE_STATUS_PRIORITY if s in set(statuses)))
    )


def compute_spike_suitability(samples_df, cv_max, recovery_min, recovery_max):
    """Precision + recovery suitability for spiked sample dilutions — a
    follow-up confirmatory test on a sample_name ending " S" (e.g. "S1 D1 S"),
    typically run on samples flagged "LOQ - Spike Test" by
    compute_sample_status() to check whether a low/below-LOQ result reflects
    genuine low DNA or matrix inhibition suppressing recovery.

    Deliberately informational only: results here do not feed into or gate
    the corresponding unspiked dilution's own Suitability, Next Step, or
    whether it's averaged into the final result — this function only reports
    on the " S" rows, never touches the unspiked ones.

    Quantity %CV precision reuses resolve_sample_replicates() (the same
    single-outlier-exclusion resolution used for unspiked dilutions) against
    `cv_max`. % Recovery is GENUINELY COMPUTED here — not read from the
    instrument's own `percent_recovery` column. Checking real export data
    (an unspiked counterpart with Undetermined/no-signal Quantity, paired
    with its spike reporting a confident, non-NaN % Recovery; and a
    high-endogenous-DNA sample where the instrument's own % Recovery was off
    by orders of magnitude from a baseline-corrected value) showed the
    instrument's own column does NOT subtract the unspiked baseline, despite
    that being the documented/assumed formula. So this function computes it
    directly instead:

        % Recovery = (Spiked Quantity Mean − Unspiked Quantity Mean) / Spike Input × 100

    Both means are the single-outlier-exclusion RESOLVED means (same
    resolve_sample_replicates() used throughout this pipeline), not raw
    instrument triplicate figures — so a rescued spiked or unspiked triplicate
    is reflected here too. If the unspiked counterpart has no resolvable
    Quantity (e.g. Undetermined — no amplification at all, often at a high
    dilution factor) or no counterpart row is found at all, its baseline is
    treated as zero rather than leaving % Recovery undefined: "Undetermined"
    reasonably reads as "nothing detectable," not "data missing for an
    unrelated reason," and this also matches the instrument's own apparent
    behavior in this exact scenario.

    `samples_df` must have the same columns resolve_sample_replicates()
    requires, plus spike_input (percent_recovery is no longer read).

    Returns one row per spiked dilution: Sample, Dilution Factor,
    Quantity %CV, Replicates Used, CV Pass, Total DNA (ng/mL),
    Spike Input, ng/mL, % Recovery, Recovery Pass. Empty (but correctly
    columned) if this run has no spiked dilutions — most runs don't; spiking
    is an occasional follow-up test, not part of every dilution series.
    """
    columns = [
        "Sample", "Dilution Factor", "Quantity %CV", "Replicates Used", "CV Pass",
        "Total DNA (ng/mL)", "Spike Input, ng/mL", "% Recovery", "Recovery Pass",
    ]
    spiked_samples = samples_df[samples_df["sample_name"].str.endswith(" S")].copy()
    if spiked_samples.empty:
        return pd.DataFrame(columns=columns)

    resolved = resolve_sample_replicates(spiked_samples, cv_max)
    spike_input = spiked_samples.groupby("sample_name", as_index=False).agg(**{
        "Spike Input, ng/mL": ("spike_input", "first"),
    })
    spike_suitability = resolved.merge(spike_input, on="sample_name")

    # Baseline (unspiked counterpart) resolved Quantity Mean — same
    # resolve_sample_replicates() call used elsewhere for unspiked dilutions,
    # so a rescued unspiked triplicate's mean is used here too, not a raw
    # recomputation that could silently disagree with the rest of the pipeline.
    unspiked_samples = samples_df[~samples_df["sample_name"].str.endswith(" S")]
    unspiked_quantity_means = (
        resolve_sample_replicates(unspiked_samples, cv_max)
        .set_index("sample_name")["quantity_mean"]
    )
    # A missing baseline (Undetermined — no amplification at all — or no
    # unspiked counterpart row found) is treated as zero quantity, not an
    # unknown value: "Undetermined" means nothing detectable, which is a
    # reasonable reading of "approximately zero" rather than "data missing
    # for an unrelated reason." This also matches the instrument's own
    # apparent behavior in this exact scenario (see this function's note
    # above on how % Recovery was found to actually be computed).
    unspiked_counterpart_mean = (
        spike_suitability["sample_name"].str.replace(r" S$", "", regex=True)
        .map(unspiked_quantity_means).fillna(0)
    )
    spike_suitability["% Recovery"] = (
        (spike_suitability["quantity_mean"] - unspiked_counterpart_mean)
        / spike_suitability["Spike Input, ng/mL"] * 100
    )

    # A spike well's own "Dilution Factor" in the raw export isn't meaningful
    # — the instrument reports 1.0 for every spike well regardless of which
    # dilution level it was actually spiked at. The dilution that matters is
    # its unspiked counterpart's (e.g. "S1 D2" for "S1 D2 S"), since the
    # spike is added to that already-diluted sample, not re-diluted itself.
    unspiked_dilution_factors = (
        unspiked_samples
        .drop_duplicates(subset="sample_name")
        .set_index("sample_name")["dilution_factor"]
    )
    spike_suitability["Dilution Factor"] = (
        spike_suitability["sample_name"]
        .str.replace(r" S$", "", regex=True)
        .map(unspiked_dilution_factors)
    )

    spike_suitability["CV Pass"] = spike_suitability["quantity_percent_cv"].apply(
        lambda cv: "N/A" if pd.isna(cv) else ("Pass" if cv <= cv_max else "Fail")
    )
    spike_suitability["Recovery Pass"] = spike_suitability["% Recovery"].apply(
        lambda r: "N/A" if pd.isna(r) else ("Pass" if recovery_min <= r <= recovery_max else "Fail")
    )
    spike_suitability = spike_suitability.rename(columns={
        "sample_name": "Sample",
        "quantity_percent_cv": "Quantity %CV", "replicates_used": "Replicates Used",
        "total_dna_per_ml": "Total DNA (ng/mL)",
    })
    return spike_suitability[columns].sort_values("Sample").reset_index(drop=True)


def compute_control_suitability(controls_df, cv_max, pc_min, pc_max, erc_min, erc_max):
    """Quantity %CV + % Recovery suitability for the ERC/PC controls (ERC,
    HPC, MPC, LPC) — the same single-outlier-exclusion rescue
    resolve_sample_replicates() already applies to Sample triplicates,
    applied here too. Deliberately NOT applied to STD or to NTC/NEC: STD's
    regression-fit dependency chain makes a rescue there high-risk (see
    project history), and NTC/NEC has no triplicate-mean/%CV concept at all
    (a per-well Ct pass/fail check instead).

    % Recovery is recomputed from the rescued Dilution-Adjusted quantity —
    `Dilution Adjusted / Spike Input × 100` — rather than read from the
    instrument's own `percent_recovery` column, so a rescued triplicate's
    changed Dilution-Adjusted value is reflected in its Recovery too (same
    principle as compute_spike_suitability()'s fix for spiked samples).

    `spike_input` here is the control's own nominal/reference concentration
    (e.g. 30 for "ERC - 30", 189.9937 for "HPC - 190") — NOT a dosed spike in
    the sample-recovery sense. Confirmed against real export data to be
    populated for every control row and to reproduce the instrument's own
    % Recovery exactly, including for control names that don't literally
    embed a number (e.g. a bare "ERC") — those have no reliable nominal
    anywhere else in the export, but do have a populated `spike_input`.

    `controls_df` must have the same columns resolve_sample_replicates()
    requires, plus control_type and spike_input.

    Returns one row per (control_type, sample_name): control_type,
    sample_name, Quantity %CV, Replicates Used, CV Pass, % Recovery,
    Recovery Pass. Empty (but correctly columned) if none of ERC/HPC/MPC/LPC
    are present.
    """
    columns = [
        "control_type", "sample_name", "Quantity %CV", "Replicates Used",
        "CV Pass", "% Recovery", "Recovery Pass",
    ]
    pc_controls = controls_df[controls_df["control_type"].isin(["ERC", "HPC", "MPC", "LPC"])].copy()
    if pc_controls.empty:
        return pd.DataFrame(columns=columns)

    resolved = resolve_sample_replicates(pc_controls, cv_max)
    control_types = pc_controls.drop_duplicates(subset="sample_name").set_index("sample_name")["control_type"]
    spike_input = pc_controls.groupby("sample_name", as_index=False).agg(**{
        "spike_input": ("spike_input", "first"),
    })
    suitability = resolved.merge(spike_input, on="sample_name")
    suitability["control_type"] = suitability["sample_name"].map(control_types)
    suitability["% Recovery"] = suitability["dilution_adjusted"] / suitability["spike_input"] * 100

    suitability["CV Pass"] = suitability["quantity_percent_cv"] <= cv_max
    suitability["Recovery Pass"] = suitability.apply(
        lambda row: recovery_bounds(row["control_type"], pc_min, pc_max, erc_min, erc_max)[0]
        <= row["% Recovery"]
        <= recovery_bounds(row["control_type"], pc_min, pc_max, erc_min, erc_max)[1],
        axis=1,
    )
    suitability = suitability.rename(columns={
        "quantity_percent_cv": "Quantity %CV", "replicates_used": "Replicates Used",
    })
    return suitability[columns].sort_values(["control_type", "sample_name"]).reset_index(drop=True)
