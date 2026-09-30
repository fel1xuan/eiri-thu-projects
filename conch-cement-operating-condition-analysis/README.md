# Conch Cement Operating Condition Analysis

Python scripts for processing 15-minute cement-production results, visualizing the selected operating indicators, and identifying operating-condition changes using deterministic statistical rules.

## Workflow

1. `01_拼接15min数据并绘图.py` scans daily 15-minute Excel results, matches the required columns, merges timestamps, completes the 15-minute timeline, and writes an overview workbook and plot.
2. `02_自动识别并划分工况.py` reads that summary, detects operating events and stable condition blocks, and writes analysis workbooks and condition plots.

The scripts include robust statistics, evidence tables, adaptive parameter selection, operating-event labelling, condition mapping, and Excel/plot formatting. They are research scripts, not a general-purpose production package.

## Environment

Use Python 3.11 and install:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.

## Data layout

No industrial source data or generated result workbook is included. Place your own files under this project:

```text
conch-cement-operating-condition-analysis/
├── data/
│   ├── 15min-results/          Input for the current workflow
│   ├── second-level-results/   Reserved for later physical-factor analysis
│   └── low-frequency/          Reserved for later physical-factor analysis
└── 输出结果/                    Generated workbooks and plots
```

The first script currently reads `data/15min-results/`. The second reads `输出结果/15min数据汇总.xlsx`. Adjust the path constants locally if a different data layout is required; do not commit real paths or data.

## Run

```bash
python 01_拼接15min数据并绘图.py
python 02_自动识别并划分工况.py
```

Run the first script before the second. The scripts can be compiled without data, but an analysis run requires compatible 15-minute Excel inputs.

## Repository notes

The original UCLA upload included generated Excel workbooks and plots. They were deliberately excluded from this source-only migration. Only two Python source files were migrated; their calculation, detection, mapping, and formatting logic is unchanged. Three personal absolute path constants were replaced with project-relative data directories.

See the parent repository's [migration provenance](../docs/MIGRATION.md). No open-source license has been added.
