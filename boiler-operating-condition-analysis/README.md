# Boiler Operating Condition Analysis

锅炉工况分析

A data-analysis workflow for identifying and analyzing boiler operating conditions using historical operating data.

The project contains two Python scripts:

1. `01_拼接15min数据并绘图.py` scans daily 15-minute Excel results, matches required fields, merges timestamps, completes the 15-minute timeline, and creates a summary workbook and overview plot.
2. `02_自动识别并划分工况.py` reads the summary, detects data-quality and operating events, selects adaptive detection parameters, identifies change points, divides continuous operating-condition periods, and exports evidence, summaries, parameter tables, and condition maps.

The implementation includes robust statistics, rule-based candidate clustering, adaptive parameter selection, event classification, continuous-condition mapping, stability checks, and historical-window comparisons. It does not use an opaque machine-learning model.

## Environment

Use Python 3.11:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.

## Data layout

No historical operating data or generated result workbook is included. Place compatible files under:

```text
boiler-operating-condition-analysis/
├── data/
│   ├── 15min-results/          Current workflow input
│   ├── second-level-results/   Reserved for later analysis
│   └── low-frequency/          Reserved for later analysis
└── 输出结果/                    Generated workbooks and plots
```

The first script reads `data/15min-results/`. The second reads `输出结果/15min数据汇总.xlsx`.

## Run

```bash
python 01_拼接15min数据并绘图.py
python 02_自动识别并划分工况.py
```

Run the first script before the second. Syntax and imports can be checked without data, but a complete analysis requires compatible 15-minute Excel inputs.

## Repository notes

The original upload contained generated Excel workbooks and result plots. They are excluded from this source-only project. The two source scripts retain their calculation, event-detection, mapping, threshold, and formatting logic. Personal absolute input paths were replaced with project-relative `data/` paths during migration.

See the parent repository's [migration provenance](../docs/MIGRATION.md). No open-source license has been added.
