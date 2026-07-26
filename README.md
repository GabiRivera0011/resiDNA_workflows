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
>1. Load QuantStudio file
>2. QuantStudio Results Parser
>3. Data Classification Engine
>4. System Suitability Engine
>5. Sample Result Processing
>6. Create Prototype Graphs
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
