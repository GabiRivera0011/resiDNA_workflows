# resiDNA_workflows
Residual DNA qPCR Analysis Python Notebooks


## Project Organization

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

```text
                         USER
                          |
                          |
                    FRONTEND (Web App)
                          |
        ---------------------------------------
        |                 |                   |
   Upload Page     Results Dashboard     Analytics
        |                 |                   |
        ---------------------------------------
                          |
                    API Communication
                          |
                          |
                    BACKEND SERVER
                          |
        ---------------------------------------
        |                 |                   |
 File Handler       Analysis Engine       Database
        |                 |                   |
        |                 |                   |
 QuantStudio       QC Rules Engine      Run History
 Parser            Suitability Check     Results Storage
        |
        |
 Data Classification
        |
 -----------------------------
 |            |              |
 STD       Controls       Samples
 |            |              |
 -----------------------------
        |
        |
 Report Generator

```
