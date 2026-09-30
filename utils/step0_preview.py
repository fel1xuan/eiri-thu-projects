from pathlib import Path

import pandas as pd


def load_step0_preview(output_file: str) -> dict:
    """Read a step-0 workbook without modifying it and return display metadata."""
    path = Path(str(output_file or "").strip()).expanduser()
    if not str(output_file or "").strip():
        raise ValueError("0号结果文件路径为空")
    if not path.is_file():
        raise FileNotFoundError(f"0号结果文件不存在：{path}")

    dataframe = pd.read_excel(path)
    date_column = _find_date_column(dataframe)
    parsed_dates = pd.to_datetime(dataframe[date_column], errors="coerce") if date_column else pd.Series(dtype="datetime64[ns]")
    valid_dates = parsed_dates.dropna()
    all_empty_columns = [str(column) for column in dataframe.columns if _is_all_empty(dataframe[column])]
    return {
        "path": str(path.resolve()),
        "dataframe": dataframe,
        "rows": int(dataframe.shape[0]),
        "columns": int(dataframe.shape[1]),
        "date_column": str(date_column or ""),
        "start_date": valid_dates.min().strftime("%Y-%m-%d") if not valid_dates.empty else "",
        "end_date": valid_dates.max().strftime("%Y-%m-%d") if not valid_dates.empty else "",
        "empty_columns": all_empty_columns,
    }


def _find_date_column(dataframe):
    for column in dataframe.columns:
        text = str(column)
        if "日期" in text or "时间" in text or "date" in text.lower():
            return column
    if len(dataframe.columns):
        first = dataframe.columns[0]
        if pd.to_datetime(dataframe[first], errors="coerce").notna().any():
            return first
    return None


def _is_all_empty(series):
    if series.isna().all():
        return True
    non_empty = series.dropna().astype(str).str.strip()
    return non_empty.empty or (non_empty == "").all()
