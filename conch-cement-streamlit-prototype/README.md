# Conch Cement Carbon Data Analysis — Streamlit Prototype

Early Web Prototype

This project is an early Streamlit-based web prototype developed to validate the workflow and user interaction of a carbon-emission data-processing tool for Conch Cement.

It demonstrates the software workflow before the later PySide6 desktop application:

- 0号 production-report extraction and result review
- 1号 low-frequency data aggregation
- 2号 second-level carbon-emission calculation and anomaly detection
- 3号 15-minute aggregation
- Project-path configuration and file selection
- Result download and 15-minute Plotly charts
- Workflow status and local run logs

This is a research prototype. It uses local files and Streamlit, has no authentication layer or database, and is not a hosted production service.

## Evolution

```text
Streamlit Web Prototype
        ↓
PySide6 Desktop Application
```

The maintained desktop version is available in [Conch Cement Carbon Emission Data Analysis App](../conch-cement-carbon-data-analysis-app/).

## Structure

```text
conch-cement-streamlit-prototype/
├── app.py
├── modules/
│   ├── extract_report.py
│   ├── lowfreq_update.py
│   ├── second_calc.py
│   ├── agg_15min.py
│   ├── plotting.py
│   └── utils.py
├── assets/
├── config/
│   └── cell_map.json
├── requirements.txt
└── README.md
```

The repository does not include user configuration, logs, original Excel files, second-level results, 15-minute results, or other production data.

## Run locally

Use Python 3.11:

```bash
python -m venv .venv
```

macOS / Linux:

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Windows:

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\streamlit.exe run app.py
```

Then open the local URL printed by Streamlit, normally `http://127.0.0.1:8501`.

At first launch, use the project-configuration page to select your own data project root and input files. The application may create `config/app_config.json`, `outputs/`, and `uploads/` locally; these paths are ignored by Git.

## Data requirements

The workflow expects the user's own production report, historical and current low-frequency files, high-frequency data, and three-channel data. Exact paths are selected in the interface. No private or real research dataset is bundled.

The extraction map in `config/cell_map.json` is retained because it is required by the 0号 extraction workflow. Update it locally only when the source report template changes.

## Migration notes

This copy was made from the read-only legacy Streamlit project. The business modules and formulas were copied without modification. Local launch scripts, user configuration, runtime logs, virtual environments, bytecode, duplicate/unused assets, and generated outputs were excluded.

No open-source license has been added.
