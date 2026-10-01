# Research Projects at the Energy Internet Research Institute, Tsinghua University

EIRI, THU · Research & Engineering Projects

This repository documents selected research and engineering projects developed during my work at the Energy Internet Research Institute, Tsinghua University (EIRI, THU).

This is a personal project repository and is not an official repository of Tsinghua University or EIRI.

## Projects

### 1. Boiler Operating Condition Analysis

Analysis and identification of boiler operating conditions using historical operational data. The workflow combines 15-minute records, checks data quality, selects adaptive detection parameters, identifies operating events and change points, and maps continuous operating-condition periods.

[Project source and usage](boiler-operating-condition-analysis/README.md)

### 2. Conch Cement Carbon Data Analysis — Streamlit Prototype

An early Streamlit-based web prototype for validating the carbon-emission data-processing workflow, path configuration, result inspection, charting, and user interaction.

[Prototype source and usage](conch-cement-streamlit-prototype/README.md)

### 3. Conch Cement Carbon Emission Data Analysis App

A PySide6 desktop application developed from the earlier Streamlit prototype, integrating carbon-emission data processing, manual validation, calculation, anomaly detection, 15-minute aggregation, result inspection, and visualization.

[Desktop application source and usage](conch-cement-carbon-data-analysis-app/README.md)

## Software evolution

```text
Conch Cement data-processing scripts
                ↓
      Streamlit Web Prototype
                ↓
   PySide6 Desktop Application
                ↓
       macOS / Windows delivery
```

The delivery stage refers to tested desktop packaging workflows. Packaged applications and user data are not stored in this source repository.

## Structure

```text
eiri-thu-projects/
├── README.md
├── docs/
│   └── MIGRATION.md
├── boiler-operating-condition-analysis/
├── conch-cement-streamlit-prototype/
└── conch-cement-carbon-data-analysis-app/
```

Each project includes its own scope, environment, and usage notes. Datasets, generated workbooks, user configurations, logs, environments, and packaged applications are intentionally excluded.

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
