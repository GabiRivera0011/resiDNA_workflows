# resiDNA_workflows
Residual DNA qPCR Analysis Python Notebooks


## Project Organization (In Progress)

This repository is organized to keep qPCR analysis workflows, datasets, scripts, and results easy to track and reproduce. Reflects the actual current layout, not an aspirational one — `Scripts/`, `Figures/`, and `Results/` are reserved (empty, `.gitkeep`-only) for the Phase V extraction/export work described in the Road Map below.

```text
resiDNA_workflows/
│
├── Notebooks/
│   └── 01_Phase I.ipynb          # Phase I notebook — import through prototype graphs
│
├── Data/
│   ├── experiment_001.xlsx       # primary dataset the notebook is built/verified against
│   ├── sample_data_001.xls       # additional real-world dataset, queued for validation
│   └── sample_data_002.xls       # additional real-world dataset, queued for validation
│
├── Scripts/                      # reserved — Phase V: style_table()/suitability logic moves here
├── Figures/                      # reserved — exported plots
├── Results/                      # reserved — exported results (e.g. CSV)
└── README.md
```

**Next up**: validate `01_Phase I.ipynb` end-to-end against `sample_data_001.xls` and `sample_data_002.xls` (currently only run against `experiment_001.xlsx`). Note both are the legacy `.xls` format rather than `.xlsx` — reading them will need the `xlrd` engine (`.venv\Scripts\pip install xlrd`), and the notebook's file-loading cell currently hardcodes `experiment_001.xlsx`, so that'll need pointing at whichever file is under test.

## Application Architect (In Progress)

Design of a local-first architecture with future hosted space. 

```text
                     USER
                      |
                      |
               Web Browser
                      |
                      |
          --------------------------------
          |                              |
     Streamlit App              (Future React Frontend)
          |
          |
      Python Backend Logic
          |
  --------------------------------
  |              |               |
Parser       QC Engine       Calculations
  |              |               |
  --------------------------------
                 |
        QuantStudio Results File
                 |
             SQLite Database

```


## Development Road Map

Order of Web Application Development Phases
>
>Phase I - Colab Scientific Prototype (.ipynb)
>>Prove that the qPCR analysis logic works correctly.
>1. [x] [Load QuantStudio file](Notebooks/01_Phase%20I.ipynb#L93)
>2. [x] [QuantStudio Results Parser](Notebooks/01_Phase%20I.ipynb#L1230)
>3. [x] [Data Classification Engine](Notebooks/01_Phase%20I.ipynb#L2131)
>4. [x] [System Suitability Engine](Notebooks/01_Phase%20I.ipynb#L2664)
>5. [x] [Sample Result Processing](Notebooks/01_Phase%20I.ipynb#L3795)
>6. [x] [Create Prototype Graphs](Notebooks/01_Phase%20I.ipynb#L4925)
>7. [ ] Validate against `Data/sample_data_001.xls` and `Data/sample_data_002.xls`
>
> Phase II - Convert Prototype into a Local Application (http://localhost:8501)
>>Create a simple website you run on your own computer using Local Streamlit App.
>1. Upload Page
>2. Backend Processing
>3. Results Dashboard
>
> Phase III - Add Criteria Management
>>Stop changing code every time acceptance criteria change.
>>Build a Criteria Settings Page using Streamlit + SQLite
>
>Phase IV - Improve Reporting and Visualization
>>Make it look like a professional analytical tool.
>>Add reports and interactive analytics using Streamlit
>
>Phase V - Organize as a Professional Software Project
>>Move from prototype to maintainable software.
>>Organize into professional software using VS Code Project
>
>Phase VI - (Maybe) Upgrade to Full Web Application
>>Replace Streamlit with React Frontend and FastAPI Backend

## Phase I Notebook Map

Line numbers point into the raw `.ipynb` JSON (open the file with a text editor, or follow the link and GitHub/VS Code will jump to that line). They reflect the notebook as of its last commit — because cell outputs (styled tables, plots) are stored inline, line numbers can drift by a few dozen lines after the notebook is next re-run and saved, even if no code changes. Cell IDs are stable if you need a re-run-proof anchor.

| Section | Line | What it does |
|---|---|---|
| [Load QuantStudio 5 Dataset](Notebooks/01_Phase%20I.ipynb#L93) | 93 | Colab/local dual-path setup ([`IN_COLAB`](Notebooks/01_Phase%20I.ipynb#L158) detection), reads `Data/experiment_001.xlsx` |
| [Table Styling Helper](Notebooks/01_Phase%20I.ipynb#L289) | 289 | [`style_table()`](Notebooks/01_Phase%20I.ipynb#L309) and [`style_criteria_summary()`](Notebooks/01_Phase%20I.ipynb#L380) — shared formatting for every table in the notebook (2-decimal default, light-mode-forced colors, optional row highlighting) |
| [QuantStudio Results Parser](Notebooks/01_Phase%20I.ipynb#L1230) | 1230 | Renames/standardizes columns, converts dtypes, drops empty rows, handles `Undetermined` Ct |
| [Output Verification](Notebooks/01_Phase%20I.ipynb#L1980) | 1980 | Re-reads the raw Results sheet fresh and checks, well by well, that instrument-computed QC values (`Ct CV%`, `Quantity %CV`, `% Recovery`, `Back Calculation % difference Mean`) survive renaming/klib cleaning unchanged — catches parser bugs, not instrument math |
| [Data Classification Engine](Notebooks/01_Phase%20I.ipynb#L2131) | 2131 | [`classify_sample()`](Notebooks/01_Phase%20I.ipynb#L2379) splits wells into Reference Standard / Control (NTC, NEC, ERC, HPC, MPC, LPC) / Sample |
| [Acceptance Criteria](Notebooks/01_Phase%20I.ipynb#L2617) | 2617 | Every System and Sample Suitability threshold, in one Colab-form-editable block (see [Acceptance Criteria](#acceptance-criteria) below) |
| [System Suitability Engine](Notebooks/01_Phase%20I.ipynb#L2664) | 2664 | Plate-level QC — STD curve fit, ERC/PC recovery, NTC/NEC vs. LOQ; ends with a PASS/FAIL banner and a full criteria summary table |
| [Sample Result Processing](Notebooks/01_Phase%20I.ipynb#L3795) | 3795 | Per-sample QC (quantity %CV, dilutional linearity), a [manual golden-reference check](Notebooks/01_Phase%20I.ipynb#L4132) for the one value actually computed here (`% Bias`), the [Sample Name Mapping](Notebooks/01_Phase%20I.ipynb#L4457) dict, and the [Final Sample Results](Notebooks/01_Phase%20I.ipynb#L4447) tables |
| [Create Prototype Graphs](Notebooks/01_Phase%20I.ipynb#L4925) | 4925 | Three interactive Plotly figures — standard curve with a toggleable QC-controls overlay, standard curve with a toggleable per-sample overlay, and an amplification curve (ΔRn vs Cycle) plot with toggleable STD/NTC/NEC/PC/Samples groups (see [Prototype Graphs](#prototype-graphs) below) |

## Acceptance Criteria

All thresholds — System Suitability and Sample Suitability alike — live in one consolidated cell right after Data Classification, before either engine runs, exposed as Colab form fields (`#@param`) so they're editable without touching code. This is also the natural seam for the Phase III criteria-settings page.

Nearly every value below marked "instrument-computed" is read forward from the QuantStudio export as-is rather than recalculated (`Ct CV%`, `Quantity %CV`, `% Recovery`, `Back Calculation % difference Mean` are already columns in the raw Results sheet) — the notebook just applies the pass/fail thresholds on top. An [Output Verification](Notebooks/01_Phase%20I.ipynb#L1980) cell re-reads the untouched sheet and checks these survive renaming/klib cleaning unchanged, to catch parsing bugs rather than instrument math. The one exception is Dilutional Linearity's `% Bias` (below), which is genuinely computed in-notebook.

**STD (Standard Curve)**
| Check | Formula | Pass |
|---|---|---|
| R² | instrument-computed | ≥ 0.99 |
| Ct %CV (triplicate) | `(Ct_SD / Ct_Mean) × 100` | ≤ 20% |
| Back-calculation bias | `\|(Back-Calc Qty − Nominal Qty) / Nominal Qty\| × 100` | ≤ 25% |
| Amplification efficiency | `(10^(−1/Slope) − 1) × 100` | 90%–110% |

**ERC & PC (Controls)**
| Check | Formula | Pass |
|---|---|---|
| Quantity %CV (triplicate) | `(Qty_SD / Qty_Mean) × 100` | ≤ 20% |
| PC %Recovery | `(Dilution-Adjusted Qty / Reference-Adjusted Qty) × 100` | 80%–125% |
| ERC %Recovery | same formula | 50%–150% |

**NTC / NEC**
- Both NTC and NEC pass per well if Ct is `Undetermined` **or** `Ct ≥ LOQ_Ct`.
- LOQ formula — ICH Q2(R1) / USP \<1225\> signal-to-noise method, using the standard curve's residual standard error (`Std error`, i.e. Sy.x) as σ:
  ```
  ΔlogQ_LOQ = 10 × Std_error / |Slope|
  LOQ_Ct = Slope × ΔlogQ_LOQ + y-Intercept
         = y-Intercept − 10 × Std_error   (shortcut, valid when Slope < 0)
  ```

The System Suitability section ends with a color-coded PASS/FAIL banner, then a **wide** summary table per group via `display_wide_table()` — one row per item, with each criterion as its own Value/Pass column pair, instead of one row per item×criterion. STD Curve splits into two tables (**STD Curve Fit**, one row for the plate's curve; **STD Curve Points**, one row per STD point with Ct %CV and Back-Calc %Bias side by side), and **ERC / PC** gets one row per control with Quantity %CV and % Recovery side by side. **NTC / NEC** only ever has a single criterion per item, so it stays in the simpler Item/Criteria/Value/Status form via `display_criteria_group()` — wide and long are the same shape there. A row is highlighted red if any of its criteria fail; a group with nothing to evaluate for a given run (e.g. no ERC/PC controls present) prints a note instead of an empty table.

**Sample Suitability**
| Check | Formula | Pass |
|---|---|---|
| Quantity %CV (triplicate) | `(Qty_SD / Qty_Mean) × 100` | ≤ 25% |
| Dilutional linearity | `%Bias = (x₁ − x₂) / x₂ × 100`, where `x₂` is the `Dilution Adjusted` quantity of the sample's own dilution with the lowest combined Ct %CV + Quantity %CV, and `x₁` is each dilution's `Dilution Adjusted` quantity | `\|%Bias\|` ≤ 20% |

Since spiked series are no longer collected, dilutional linearity no longer compares to a spiked 100% recovery target. Instead, for each sample, the dilution with the lowest combined Ct %CV + Quantity %CV (its most precise triplicate) is taken as an internal reference, and every dilution's `Dilution Adjusted` quantity is compared against it. `% Bias` is reported signed (can be positive or negative); the pass/fail gate uses its absolute value.

`% Bias` is the one suitability value actually computed in this notebook rather than pulled from the instrument, so the automated Output Verification check above doesn't cover it. A [manual golden-reference check](Notebooks/01_Phase%20I.ipynb#L4132) cell is provided instead — fill in a few hand/Excel-verified expected `% Bias` values and it flags any mismatch against the notebook's own calculation.

The Sample Suitability section similarly ends with one summary table per group (Quantity %CV, Dilutional Linearity) via `display_criteria_group()`; a separate PASS/FAIL banner was dropped as redundant since the tables already state each item's status.

**Final Sample Results**

The workflow now assumes **multiple samples**, each with its own unspiked dilution series (e.g. `S1 D1–D3`, `S2 D1–D3`) and no spiked series. Two tables are produced:

1. *Final Sample Results by Dilution* — every unspiked dilution, one row each, for traceability:

   | Column | Meaning |
   |---|---|
   | `Sample #` | Base Sample ID with the dilution suffix stripped (e.g. `S1 D2` → `S1`) |
   | `Sample Dilution` | The individual dilution's full identifier (e.g. `S1 D2`) |
   | `Quantity %CV`, `Quantity %CV Suitability` | Triplicate %CV for that dilution, and its own `Pass`/`Fail`/`N/A` verdict |
   | `Linearity %Bias`, `Linearity Suitability` | %Bias vs. the sample's reference dilution, and its own `Pass`/`Fail`/`N/A` verdict |
   | `Suitability` | Combined verdict — `Pass` only if **both** Quantity %CV and Linearity pass; `Fail` if either fails; `N/A` if neither fails but one is unevaluable |
   | `Total DNA (ng/mL)`, `Protein Concentration (mg/mL)`, `DNA per Protein (ng/mg)` | Reported for every row where available |

2. *Final Sample Results — Averaged per Sample* — for each `Sample #`, `Total DNA (ng/mL)` and `DNA per Protein (ng/mg)` are averaged across only that sample's suitability-**passing** dilutions; `Protein Concentration (mg/mL)` is constant per sample (same for every dilution) so it's carried through rather than averaged. `Sample ID` sits immediately next to `Sample #`, followed by `Sample Name` — both pulled from the Sample Name Mapping boxes below. Produces one row per sample. `Dilutions Averaged` records which dilutions (and how many) went into the average, for traceability. Samples with zero passing dilutions are excluded from this table and listed separately by the cell's `not_reported` print output. The `≤ 15 ng/mg Status` column (name reflects the live `SAMPLE_DNA_PER_PROTEIN_LIMIT`) reads `Below`/`Above`/`N/A`; rows reading `Below` are highlighted light green.

`Total DNA (ng/mL)`, `Protein Concentration (mg/mL)`, and `DNA per Protein (ng/mg)` render at **4-decimal precision** wherever they appear, via `style_table()`'s `precision_overrides` (`FINAL_RESULTS_PRECISION`); every other column — in these tables and everywhere else in the notebook — defaults to 2 decimals.

**Sample Name Mapping**

Editable as Colab form fields (`#@param {type:"string"}`), just like Acceptance Criteria. The cell first prints every `Base Sample` actually detected in the run's data (e.g. `['S1', 'S2', 'S3']`), then exposes 8 fixed slots (`Sample 1`–`Sample 8`) — enough headroom for the largest runs seen so far — each with a **Base Sample**, **Sample ID**, and **Sample Name** text box. Type a detected Base Sample into a slot's Base Sample box to activate it; leave a slot's Base Sample box blank to skip it, so runs with anywhere from 1 to 8 samples all work without editing code. A slot whose Base Sample doesn't match anything detected is skipped with a printed warning rather than silently applied (catches typos). The resulting `sample_id_map` and `sample_display_names` dicts are keyed by Base Sample; only the averaged table picks them up (as `Sample ID` and `Sample Name`) — the by-dilution table doesn't carry either, since it's a traceability table keyed on `Sample #` already.

## Prototype Graphs

Two interactive Plotly figures (`build_curve_figure()`), both plotting Ct vs `log10(Quantity)` — the same axes the standard curve regression was fit on. Each figure always shows the fitted **Regression Line** (rendered semi-transparent so the overlay colors stand out) and the **STD Points** it was built from. A boxed, titled legend sits top right; the equation and R² sit in their own box bottom right. Every other series is its own toggleable trace, starting hidden — click its legend entry to show it — using a fixed, colorblind-safe 8-color palette (Okabe & Ito, 2008) assigned in the same order every run.

- **Standard Curve — QC Controls**: one toggleable trace per `control_type` (NTC, NEC, ERC, HPC, MPC, LPC).
- **Standard Curve — Sample Results**: one toggleable trace per `Sample #`, labeled with its Sample Name if one was filled in above.

Overlay points are positioned at each well's **own back-calculated Quantity** — its Ct run back through the curve equation (the `quantity` column already computed for every well) — rather than a known/expected concentration. This shows where a well's observed Ct falls within the curve's dynamic range (interpolated vs. extrapolated beyond the standards): an NTC/NEC that picked up any signal shows up at whatever apparent concentration that Ct implies, and a sample shows whether its Ct is inside or outside the validated range. Recovery/bias against a known target is already covered numerically by the System/Sample Suitability tables above (`% Recovery`, `Back-Calc %Bias`) — this view complements rather than repeats those. Wells with an `Undetermined` Ct (or non-positive Quantity) simply have no point to plot, same as a clean negative control is expected to show nothing.

**Amplification Curves — ΔRn vs Cycle**

Reads the `Amplification Data` tab (header row 23, i.e. 0-indexed row 22): `Well`, `Cycle`, and `ΔRn` are read by column name, since not every export has the same columns (`Sample Name` in particular may be absent, or hand-filled from the Results tab). Rather than trust that tab's own `Sample Name`, well classification is joined in from `parsed_df` (already built from the Results tab) via `Well` — this works regardless of which columns a given Amplification Data export happens to have.

One toggleable trace per well, grouped into legend entries via Plotly `legendgroup` (all traces in a group show/hide together as one click): **STD** (dark gray, semi-transparent), **NTC** (dark forest green), **NEC** (midnight blue), **PC** (HPC/MPC/LPC bundled into one group, pale pink) — plus one entry **per Base Sample** (e.g. `S1`, `S2`), each its own pale pastel color (deliberately avoiding pink/rose tones so no sample is ever confused with PC), not bundled into one flat "Samples" color like the other groups. ERC isn't part of this plot. All groups start hidden, same click-to-show interaction model as the standard curve plots above (this plot uses its own palette rather than Okabe-Ito, since colors here were chosen for a specific look — and to keep every group and every sample visually distinct from one another — rather than categorical/colorblind-safety).

## Backlog — Recommended Cleanup

Reviewed but **not yet implemented**. Roughly highest-value first.

**Correctness**


**Clarity**





**Cleanup**
- [ ] Commented-out `to_csv` / `processed_path` blocks are scattered through the parser cells — either wire up a real export step or delete them.
- [ ] The `Handle Warnings` cell is empty; either add the `warnings` filter it implies or drop the section.
- [ ] Notebook outputs (styled tables, the `klib` plot) are committed inline, which makes diffs large and line references drift. Consider `nbstripout` or committing a rendered HTML export alongside a stripped notebook.
- [ ] `style_table()` is defined in the notebook; once Phase V starts it belongs in `Scripts/plotting.py`, along with the suitability logic in `Scripts/qpcr.py`.

## Running the Notebook Locally

The notebook auto-detects Colab vs. local execution (`IN_COLAB` flag) — outside Colab it skips `git clone`/`pip install klib`/`google.colab` imports and resolves paths relative to the repo instead of `/content/`.

```powershell
python -m venv .venv
.venv\Scripts\pip install pandas numpy openpyxl klib ipykernel plotly
.venv\Scripts\python -m ipykernel install --user --name resiDNA-venv --display-name "resiDNA (.venv)"
```
Then select the **resiDNA (.venv)** kernel in VS Code / Jupyter and run all cells.
