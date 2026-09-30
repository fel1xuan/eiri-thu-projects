# Migration provenance

This repository consolidates two personal project areas previously stored in [fel1xuan/UCLA](https://github.com/fel1xuan/UCLA) and the standalone local desktop-application repository.

## Operating-condition analysis

Source: `fel1xuan/UCLA`, directory `海螺水泥工况分析/`, snapshot `90edd587d919436946a785ee61acff89f8f97003`.

The two Python scripts were copied. Generated Excel workbooks and plot images from `输出结果/` were excluded because they are industrial analysis results, not source code. The scripts' personal absolute input paths were replaced by project-relative `data/` paths. Detection rules, statistical calculations, mappings, thresholds, workbook structure, and plot logic were not changed.

The original upload commit remains in UCLA history. It was not rewritten or force-pushed.

## Carbon-emission desktop application

Source: local repository `清华数据分析软件`, imported under `conch-cement-carbon-data-analysis-app/` through a subtree merge.

The app's two existing commits and source history were preserved:

- `5ccd3a5` — initial stable desktop application source
- `8ab2200` — repository documentation cleanup

Ignored local files, user configuration, logs, virtual environments, build products, packaged applications, Excel data, and generated results were never imported.

## Scope

This is Felix / Yuxuan Zhan's personal research-project repository. It is not an official Tsinghua University or EIRI repository.
