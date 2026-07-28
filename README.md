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
>1. [x] [Load QuantStudio file](Notebooks/01_Phase%20I.ipynb#L92)
>2. [x] [QuantStudio Results Parser](Notebooks/01_Phase%20I.ipynb#L1179)
>3. [x] [Data Classification Engine](Notebooks/01_Phase%20I.ipynb#L1857)
>4. [x] [System Suitability Engine](Notebooks/01_Phase%20I.ipynb#L2329)
>5. [x] [Sample Result Processing](Notebooks/01_Phase%20I.ipynb#L3053)
>6. [ ] [Create Prototype Graphs](Notebooks/01_Phase%20I.ipynb#L3609) — not started
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
| [Load QuantStudio 5 Dataset](Notebooks/01_Phase%20I.ipynb#L92) | 92 | Colab/local dual-path setup ([`IN_COLAB`](Notebooks/01_Phase%20I.ipynb#L55) detection), reads `Data/experiment_001.xlsx` |
| [Table Styling Helper](Notebooks/01_Phase%20I.ipynb#L286) | 286 | [`style_table()`](Notebooks/01_Phase%20I.ipynb#L306) — shared formatting for every table in the notebook (light-mode-forced colors, optional row highlighting) |
| [QuantStudio Results Parser](Notebooks/01_Phase%20I.ipynb#L1179) | 1179 | Renames/standardizes columns, converts dtypes, drops empty rows, handles `Undetermined` Ct |
| [Data Classification Engine](Notebooks/01_Phase%20I.ipynb#L1857) | 1857 | [`classify_sample()`](Notebooks/01_Phase%20I.ipynb#L2100) splits wells into Reference Standard / Control (NTC, NEC, ERC, HPC, MPC, LPC) / Sample |
| [System Suitability Engine](Notebooks/01_Phase%20I.ipynb#L2329) | 2329 | Plate-level QC — STD curve fit, ERC/PC recovery, NTC/NEC vs. LOQ (see [Acceptance Criteria](#acceptance-criteria) below) |
| [Sample Result Processing](Notebooks/01_Phase%20I.ipynb#L3053) | 3053 | Per-sample QC (quantity %CV, dilutional linearity) and the [Final Sample Results](Notebooks/01_Phase%20I.ipynb#L3411) table |
| [Create Prototype Graphs](Notebooks/01_Phase%20I.ipynb#L3609) | 3609 | Not started |

## Acceptance Criteria

Implemented in the System Suitability Engine and Sample Result Processing sections above.

**STD (Standard Curve)**
| Check | Formula | Pass |
|---|---|---|
| R² | instrument-computed | > 0.99 |
| Ct %CV (triplicate) | `(Ct_SD / Ct_Mean) × 100` | ≤ 20% |
| Back-calculation bias | `\|(Back-Calc Qty − Nominal Qty) / Nominal Qty\| × 100` | < 25% |
| Amplification efficiency | `(10^(−1/Slope) − 1) × 100` | 90%–110% |

**ERC & PC (Controls)**
| Check | Formula | Pass |
|---|---|---|
| Quantity %CV (triplicate) | `(Qty_SD / Qty_Mean) × 100` | < 20% |
| PC %Recovery | `(Dilution-Adjusted Qty / Reference-Adjusted Qty) × 100` | 80%–120% |
| ERC %Recovery | same formula | 50%–150% |

**NTC / NEC**
- NTC: Ct must be `Undetermined` on all replicates.
- NEC: Ct `Undetermined` **or** `Ct ≥ LOQ_Ct`.
- LOQ formula — ICH Q2(R1) / USP \<1225\> signal-to-noise method, using the standard curve's residual standard error (`Std error`, i.e. Sy.x) as σ:
  ```
  ΔlogQ_LOQ = 10 × Std_error / |Slope|
  LOQ_Ct = Slope × ΔlogQ_LOQ + y-Intercept
         = y-Intercept − 10 × Std_error   (shortcut, valid when Slope < 0)
  ```

**Sample Suitability**
| Check | Formula | Pass |
|---|---|---|
| Quantity %CV (triplicate) | `(Qty_SD / Qty_Mean) × 100` | < 20% |
| Dilutional linearity (D1–D4, spiked) | `\|100 − %Recovery\|` | < 20% |

**Final Sample Results**

The table lists the **entire unspiked dilution series (D1–D4)** for traceability — the spiked `" S"` series is excluded for now. Each row carries its own verdict, and only suitability-passing dilutions are tallied as reportable (`reportable_results`):

| Column | Meaning |
|---|---|
| `Quantity %CV` | Triplicate %CV for that dilution |
| `Suitability` | `Pass` (%CV ≤ 20), `Fail` (%CV > 20), or `N/A` (no evaluable triplicate — below LOQ / no amplification) |
| `Total DNA (ng/mL)` | Reported for every row |
| `Total DNA per Protein (ng/mg)` | Reported wherever a protein concentration is available |
| `Status` | `Below` / `Above` the 15 ng/mg limit for passing rows; `Not Reported` for `Fail` or `N/A` rows |

Rows with `Status = "Below"` (i.e. suitability-passing **and** under 15 ng/mg) are highlighted light green.

## Backlog — Recommended Cleanup

Reviewed but **not yet implemented**. Roughly highest-value first.

**Correctness**
- [ ] `classify_sample()` matches on sample-name prefixes, so a real sample named e.g. `NECTIN-1` would be misclassified as an `NEC` control. Match on a delimiter (`NEC - `, `NEC_`) or an explicit name map instead.
- [ ] `drop_duplicates(subset="sample_name")` in Final Sample Results silently keeps the first well and assumes all three replicates share identical mean/`total_dna_per_ml` values. Aggregate explicitly (e.g. `.groupby().first()` with a guard) so a divergent replicate cannot be dropped unnoticed.
- [ ] Dilutional linearity currently evaluates each spiked dilution against 100% recovery independently — it does not test linearity *across* the D1→D4 series. Consider adding a regression of observed vs. expected across dilutions, or bias vs. the series mean, if the SOP requires it.
- [ ] `%CV` and `%Recovery` are read straight from the instrument export rather than recomputed from replicates. Recomputing (and asserting agreement) would catch a malformed or hand-edited export.
- [ ] NEC pass rule uses `Ct >= loq_ct`; confirm this is the intended direction for a *No Extraction Control* (higher Ct = less DNA) and that borderline equality should pass.
- [ ] `klib.data_cleaning()` drops single-valued columns, which silently removed `slope`, `y_intercept`, and `r2` from `df`. The curve stats survive only because they are re-read into `regression_table` — worth an explicit comment or a guard so a future refactor doesn't break it.

**Clarity**
- [ ] Acceptance-criteria constants are split across two cells (System vs. Sample). Consolidate into one criteria block — this is also the natural seam for the Phase III criteria-settings page.
- [ ] `SAMPLE_DNA_PER_PROTEIN_LIMIT` is defined inside the Final Sample Results cell rather than with the other criteria constants.
- [ ] Section headings mix `##`/`###`/`####` inconsistently (e.g. `#### Table Styling Helper` sits between `##` sections). Normalize the hierarchy.
- [ ] Boolean `Pass` columns render as `True`/`False`; `Pass`/`Fail` strings would read better in a formal report and would match the new `Suitability` column.
- [ ] The trailing empty `##` markdown cell at the end of the notebook should be removed.
- [ ] Add units to the STD/control suitability tables the way the final results table does.

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
.venv\Scripts\pip install pandas numpy openpyxl klib ipykernel
.venv\Scripts\python -m ipykernel install --user --name resiDNA-venv --display-name "resiDNA (.venv)"
```
Then select the **resiDNA (.venv)** kernel in VS Code / Jupyter and run all cells.
