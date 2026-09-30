# Research Projects at the Energy Internet Research Institute, Tsinghua University

EIRI, THU · Research & Engineering Projects

This repository contains personal research and engineering projects developed during work with the Energy Internet Research Institute, Tsinghua University (EIRI, THU), focusing on energy data analysis, carbon-emission accounting, industrial process analysis, and research software development.

## Projects

### 1. Conch Cement Operating Condition Analysis

Industrial operating-condition analysis for cement-production data. Two Python scripts combine 15-minute result files, generate overview plots, identify operating-condition changes, and export statistical summaries and condition maps.

[Source and usage](conch-cement-operating-condition-analysis/README.md)

### 2. Conch Cement Carbon Emission Data Analysis App

A PySide6 desktop application for carbon-emission data processing, validation, calculation, and visualization.

The workflow covers production-report extraction and manual review, low-frequency data aggregation, second-level carbon-emission calculation and anomaly detection, 15-minute aggregation, and result visualization.

Technology: Python, PySide6, pandas, NumPy, Matplotlib, openpyxl, xlrd, and optional PyInstaller packaging.

[Source and usage](conch-cement-carbon-data-analysis-app/README.md)

## Structure

```text
eiri-thu-projects/
├── README.md
├── docs/
│   └── MIGRATION.md
├── conch-cement-operating-condition-analysis/
└── conch-cement-carbon-data-analysis-app/
```

Each project has its own setup and usage instructions. Datasets, generated workbooks, user configurations, logs, environments, and packaged applications are intentionally excluded.

## Research focus

- Energy data analysis
- Carbon-emission accounting
- Industrial data processing
- Scientific software development
- Data visualization

## Organization and scope

Energy Internet Research Institute, Tsinghua University (EIRI, THU).

This is Felix / Yuxuan Zhan's personal project repository documenting research and engineering work conducted during a research/internship experience. It is not an official repository or software release of Tsinghua University or EIRI.

See [migration provenance](docs/MIGRATION.md) for source locations, history handling, and excluded artifacts. No open-source license has been added.
