# Migration provenance

This repository consolidates three personal project areas from earlier local or GitHub workspaces.

## Boiler operating-condition analysis

Source: `fel1xuan/UCLA`, former directory `海螺水泥工况分析/`, snapshot `90edd587d919436946a785ee61acff89f8f97003`.

The two Python scripts were copied into `boiler-operating-condition-analysis/`. Generated Excel workbooks and plot images from `输出结果/` were excluded because they are analysis results, not source code. Personal absolute input paths were replaced by project-relative `data/` paths. Detection rules, calculations, mappings, thresholds, workbook structure, and plot logic were not changed.

The original upload commit remains in UCLA history. It was not rewritten or force-pushed.

## Conch Cement Streamlit prototype

Source: the read-only legacy local project formerly referenced as `海螺水泥App/carbon_app`; its current local location was resolved during migration without modifying it.

The Streamlit entry point, six business/plotting utility modules, required assets, extraction cell map, and requirements were copied into `conch-cement-streamlit-prototype/`. The following were excluded:

- Virtual environments, bytecode, and operating-system metadata
- User-specific `config/app_config.json`
- Runtime logs, `outputs/`, uploads, and generated results
- Local launch scripts and caches
- Duplicate or unused logo assets
- Any Excel or research-data files

No Streamlit business formula or module implementation was changed.

## Conch Cement PySide6 desktop application

Source: the standalone local repository `清华数据分析软件`, imported under `conch-cement-carbon-data-analysis-app/` through a subtree merge.

The app's existing source history was preserved:

- `5ccd3a5` — initial stable desktop application source
- `8ab2200` — repository documentation cleanup

Ignored local files, user configuration, logs, virtual environments, build products, packaged applications, Excel data, and generated results were never imported.

## Scope

This is Felix / Yuxuan Zhan's personal research-project repository. It is not an official Tsinghua University or EIRI repository.
