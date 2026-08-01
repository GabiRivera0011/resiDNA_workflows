# resiDNA_workflows
Residual DNA qPCR Analysis Python Notebooks


## Project Organization (In Progress)

This repository is organized to keep qPCR analysis workflows, datasets, scripts, and results easy to track and reproduce.

```text
qpcr-data-analysis/
│
├── notebooks/
│   ├── 01_data_import.ipynb
│   ├── 02_quality_control.ipynb
│   ├── 03_ddct_analysis.ipynb
│   ├── 04_visualization.ipynb
│   └── 05_statistical_analysis.ipynb
│
├── data/
│   ├── experiment_001/
│   ├── experiment_002/
│   ├── experiment_003/
│   └── sample_data/
│
├── scripts/
│   ├── qpcr.py          # ΔCt, ΔΔCt, fold change calculations
│   ├── plotting.py      # plotting functions
│   └── utils.py         # helper functions
│
├── figures/
├── results/
└── README.md
```

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
>1. [x] [Load QuantStudio file](Notebooks/01_Phase%20I.ipynb#L84)
>2. [x] [QuantStudio Results Parser](Notebooks/01_Phase%20I.ipynb#L1116)
>3. [x] [Data Classification Engine](Notebooks/01_Phase%20I.ipynb#L1763)
>4. [x] [System Suitability Engine](Notebooks/01_Phase%20I.ipynb#L2244)
>5. [x] [Sample Result Processing](Notebooks/01_Phase%20I.ipynb#L2659)
>6. [x] [Create Prototype Graphs](Notebooks/01_Phase%20I.ipynb#L2921)
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
| [Load QuantStudio 5 Dataset](Notebooks/01_Phase%20I.ipynb#L84) | 84 | Colab/local dual-path setup ([`IN_COLAB`](Notebooks/01_Phase%20I.ipynb#L47) detection), reads `Data/experiment_001.xlsx` |
| [Table Styling Helper](Notebooks/01_Phase%20I.ipynb#L278) | 278 | [`style_table()`](Notebooks/01_Phase%20I.ipynb#L295) and [`style_criteria_summary()`](Notebooks/01_Phase%20I.ipynb#L295) — shared formatting for every table in the notebook (2-decimal default, light-mode-forced colors, optional row highlighting) |
| [QuantStudio Results Parser](Notebooks/01_Phase%20I.ipynb#L1116) | 1116 | Renames/standardizes columns, converts dtypes, drops empty rows, handles `Undetermined` Ct |
| [Data Classification Engine](Notebooks/01_Phase%20I.ipynb#L1763) | 1763 | [`classify_sample()`](Notebooks/01_Phase%20I.ipynb#L2006) splits wells into Reference Standard / Control (NTC, NEC, ERC, HPC, MPC, LPC) / Sample |
| [Acceptance Criteria](Notebooks/01_Phase%20I.ipynb#L2226) | 2226 | Every System and Sample Suitability threshold, in one Colab-form-editable block (see [Acceptance Criteria](#acceptance-criteria) below) |
| [System Suitability Engine](Notebooks/01_Phase%20I.ipynb#L2244) | 2244 | Plate-level QC — STD curve fit, ERC/PC recovery, NTC/NEC vs. LOQ; ends with a PASS/FAIL banner and a full criteria summary table |
| [Sample Result Processing](Notebooks/01_Phase%20I.ipynb#L2659) | 2659 | Per-sample QC (quantity %CV, dilutional linearity), the [Sample Name Mapping](Notebooks/01_Phase%20I.ipynb#L2873) dict, and the [Final Sample Results](Notebooks/01_Phase%20I.ipynb#L2867) tables |
| [Create Prototype Graphs](Notebooks/01_Phase%20I.ipynb#L2921) | 2921 | Two interactive Plotly figures — standard curve with a toggleable QC-controls overlay, and standard curve with a toggleable per-sample overlay (see [Prototype Graphs](#prototype-graphs) below) |

## Acceptance Criteria

All thresholds — System Suitability and Sample Suitability alike — live in one consolidated cell right after Data Classification, before either engine runs, exposed as Colab form fields (`#@param`) so they're editable without touching code. This is also the natural seam for the Phase III criteria-settings page.

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

## Backlog — Recommended Cleanup

Reviewed but **not yet implemented**. Roughly highest-value first.

**Correctness**


**Clarity**

- [ ] Section headings mix `##`/`###`/`####` inconsistently (e.g. `#### Table Styling Helper` sits between `##` sections). Normalize the hierarchy.



**Cleanup**
- [ ] Commented-out `to_csv` / `processed_path` blocks are scattered through the parser cells — either wire up a real export step or delete them.
- [ ] The `Handle Warnings` cell is empty; either add the `warnings` filter it implies or drop the section.
- [ ] Notebook outputs (styled tables, the `klib` plot) are committed inline, which makes diffs large and line references drift. Consider `nbstripout` or committing a rendered HTML export alongside a stripped notebook.
- [ ] `style_table()` is defined in the notebook; once Phase V starts it belongs in `scripts/plotting.py`, along with the suitability logic in `scripts/qpcr.py`.
- [ ] The `Project Organization` tree at the top of this README still describes a planned layout (`notebooks/`, `scripts/`, `figures/`, `results/`) that does not match the current repo (`Notebooks/`, `Data/`). Reconcile the two.

## Running the Notebook Locally

The notebook auto-detects Colab vs. local execution (`IN_COLAB` flag) — outside Colab it skips `git clone`/`pip install klib`/`google.colab` imports and resolves paths relative to the repo instead of `/content/`.

```powershell
python -m venv .venv
.venv\Scripts\pip install pandas numpy openpyxl klib ipykernel plotly
.venv\Scripts\python -m ipykernel install --user --name resiDNA-venv --display-name "resiDNA (.venv)"
```
Then select the **resiDNA (.venv)** kernel in VS Code / Jupyter and run all cells.
