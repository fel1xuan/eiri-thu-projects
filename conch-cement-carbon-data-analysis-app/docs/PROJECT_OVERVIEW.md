# Project Overview

## Background

The original workflow consisted of several independent Python data-processing scripts. Although each script could run on its own, the complete monthly process involved multiple paths and Excel files, depended on the operator remembering the execution order, and required repeated path changes when switching months. A script could also finish without an obvious error while reading an unintended input file.

The goal of this project was therefore not simply to place scripts behind buttons. It was to make the workflow, paths, review state, result checks, and visualization explicit while preserving validated scientific calculation logic.

## Objectives

- Preserve validated scientific calculation logic
- Reduce manual path selection
- Make processing order explicit
- Add manual review before downstream processing
- Provide result inspection and visualization
- Support standalone desktop delivery

## Workflow

```text
0. Production report extraction
   ↓
Manual preview and review
   ↓
1. Low-frequency data aggregation
   ↓
2. Second-level carbon-emission calculation and anomaly detection
   ↓
3. 15-minute aggregation
   ↓
Result inspection and visualization
```

## Key Features

- Project configuration
- Automatic file and path detection
- Step 0 production-report extraction
- Result preview
- Automatic validation
- Explicit manual review
- One-click Step 1 → 2 → 3 pipeline
- Background worker and responsive UI
- Result file browser
- 15-minute charts
- Run history
- Built-in documentation
- macOS and Windows delivery support

## Design Constraints

The desktop layer coordinates existing business entry points instead of rewriting formulas. Automatic validation and manual review are separate states: a successful file check alone cannot unlock downstream processing. User configuration, logs, industrial data, and generated results are stored outside the source tree and are not included in this repository.
