# resiDNA_workflows
Residual DNA qPCR Analysis Python Notebooks

## Project Organization

`Scripts/` and `Figures/` are reserved for Phase V (see Road Map below). `Results/` holds generated PDF reports from the notebook's PDF Report section.

```text
resiDNA_workflows/
│
├── Notebooks/
│   └── 01_Phase I.ipynb          # Phase I notebook — import through PDF report generation
│
├── Data/
│   ├── experiment_001.xlsx       # primary dataset the notebook was built against
│   ├── sample_data_001.xls       # real-world dataset — validated
│   └── sample_data_002.xls       # real-world dataset — validated
│
├── Scripts/                      # reserved — Phase V
├── Figures/                      # reserved — Phase V
├── Results/                      # generated PDF reports
└── README.md
```

**Switching datasets**: the notebook's "Select Dataset" cell (`#@param` field, near the top) picks which `Data/` file to run against and auto-selects the right Excel engine (`openpyxl` for `.xlsx`, `xlrd` for `.xls`) — no code edits needed to point it at a different file.

## Application Architecture (In Progress)

Design of a local-first architecture with future hosted space.

```text
                     USER
                      |
               Web Browser
                      |
          --------------------------------
          |                              |
     Streamlit App              (Future React Frontend)
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

>Phase I - Colab Scientific Prototype (.ipynb)
>>Prove that the qPCR analysis logic works correctly.
>1. [x] Load QuantStudio file
>2. [x] QuantStudio Results Parser
>3. [x] Data Classification Engine
>4. [x] System Suitability Engine
>5. [x] Sample Result Processing
>6. [x] Create Prototype Graphs
>7. [x] Validate against `Data/sample_data_001.xls` and `Data/sample_data_002.xls`
>8. [x] PDF Report generation
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

## Acceptance Criteria

All thresholds live in one Colab-form-editable cell (`#@param`) right after Data Classification. Values marked "instrument-computed" are read forward from the QuantStudio export as-is (not recalculated) — an Output Verification cell checks they survive parsing unchanged. The one exception is Dilutional Linearity's `% Bias`, which is genuinely computed in-notebook.

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
- Both pass per well if Ct is `Undetermined` **or** `Ct ≥ LOQ_Ct`.
- LOQ formula — ICH Q2(R1) / USP \<1225\> signal-to-noise method, using the standard curve's residual standard error (`Std error`) as σ:
  ```
  ΔlogQ_LOQ = 10 × Std_error / |Slope|
  LOQ_Ct = Slope × ΔlogQ_LOQ + y-Intercept
         = y-Intercept − 10 × Std_error   (shortcut, valid when Slope < 0)
  ```

**Sample Suitability**
| Check | Formula | Pass |
|---|---|---|
| Quantity %CV (triplicate) | `(Qty_SD / Qty_Mean) × 100` | ≤ 25% |
| Dilutional linearity | `%Bias = (x₁ − x₂) / x₂ × 100`, where `x₂` is the `Dilution Adjusted` quantity of the sample's own dilution with the lowest combined Ct %CV + Quantity %CV, and `x₁` is each dilution's `Dilution Adjusted` quantity | `\|%Bias\|` ≤ 20% |

Dilutional linearity compares each dilution against its own sample's most precise dilution (no spiked-recovery series is collected anymore). Two result tables are produced: *Final Sample Results by Dilution* (every dilution, for traceability) and *Final Sample Results — Averaged per Sample* (averaged across only that sample's passing dilutions; samples with zero passing dilutions are excluded and listed separately).

## PDF Report

The notebook's final section (`## PDF Report`) generates a formatted PDF summarizing the run — Run Info, System Suitability, Sample Suitability, Final Sample Results, and a Signatures block — using the `#@param` fields in the Report Info cell (Assay/Lab info, Submitter/Reviewer names). Saved to `Results/Sample_Analysis_Report_<run_no>.pdf`. Requires `reportlab` (auto-installs if missing). The logo is currently a placeholder box pending a real logo file.

## Backlog — Recommended Cleanup

- [ ] Notebook outputs (styled tables, the `klib` plot) are committed inline, which makes diffs large. Consider `nbstripout` or committing a rendered HTML export alongside a stripped notebook.
- [ ] `style_table()` is defined in the notebook; once Phase V starts it belongs in `Scripts/plotting.py`, along with the suitability logic in `Scripts/qpcr.py`.

## Running the Notebook Locally

The notebook auto-detects Colab vs. local execution (`IN_COLAB` flag) — outside Colab it skips `git clone`/`pip install klib`/`google.colab` imports and resolves paths relative to the repo instead of `/content/`.

```powershell
python -m venv .venv
.venv\Scripts\pip install pandas numpy openpyxl xlrd klib ipykernel plotly reportlab
.venv\Scripts\python -m ipykernel install --user --name resiDNA-venv --display-name "resiDNA (.venv)"
```
Then select the **resiDNA (.venv)** kernel in VS Code / Jupyter and run all cells.
