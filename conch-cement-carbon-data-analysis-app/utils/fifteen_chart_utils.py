import re
from collections import OrderedDict
from pathlib import Path

import pandas as pd

from utils.date_range_utils import date_texts_between
from utils.path_utils import normalize_path


DATETIME_COL = "__datetime__"
RESULT_SUFFIXES = {".xlsx", ".xls", ".csv"}

PLOT_CATEGORY_Y_LABELS = OrderedDict(
    [
        ("CO₂浓度", "CO₂体积浓度"),
        ("标干流量", "标干流量"),
        ("CO₂排放速率", "CO₂排放速率"),
        ("入磨燃煤碳排放", "入磨燃煤碳排放"),
        ("入窑燃煤碳排放", "入窑燃煤碳排放"),
        ("过程排放", "过程排放"),
        ("入磨综合碳排放", "入磨综合碳排放"),
        ("入窑综合碳排放", "入窑综合碳排放"),
        ("废纺平均法 · 入磨", "废纺平均法入磨碳排放"),
        ("废纺平均法 · 入窑", "废纺平均法入窑碳排放"),
        ("废纺熟料能耗法 · 入磨", "废纺熟料能耗法入磨碳排放"),
        ("废纺熟料能耗法 · 入窑", "废纺熟料能耗法入窑碳排放"),
        ("其他碳排放", "碳排放"),
        ("低位发热量", "低位发热量"),
        ("入磨生产计量", "入磨生产计量"),
        ("入窑生产计量", "入窑生产计量"),
        ("废纺消耗量", "废纺消耗量"),
        ("熟料产量", "熟料产量"),
        ("熟料成分", "熟料成分含量"),
        ("湿度", "湿度"),
        ("烟气温度", "烟气温度"),
        ("烟气压力", "烟气压力"),
    ]
)

PATH_COLORS = {
    "Path1": "#1982C4",
    "Path2": "#FF595E",
    "Path3": "#8AC926",
    "Path1&3": "#FFCA3A",
    "Path1&2": "#EE4C97",
    "Path2&3": "#2EC4B6",
    "Path1&2&3": "#7E6148",
}

CATEGORY_BASE_COLORS = {
    "CO₂浓度": "#4C78A8",
    "入磨燃煤碳排放": "#00429D",
    "入窑燃煤碳排放": "#E41A1C",
    "过程排放": "#FF9F1C",
    "入磨综合碳排放": "#00429D",
    "入窑综合碳排放": "#E41A1C",
    "废纺平均法 · 入磨": "#00A087",
    "废纺平均法 · 入窑": "#00A087",
    "废纺熟料能耗法 · 入磨": "#7876B1",
    "废纺熟料能耗法 · 入窑": "#7876B1",
    "其他碳排放": "#6A4C93",
}

FALLBACK_COLORS = [
    "#4C78A8",
    "#F58518",
    "#54A24B",
    "#E45756",
    "#72B7B2",
    "#B279A2",
    "#FF9DA6",
    "#9D755D",
]


def scan_15min_files(source_path: str, start_date: str = "", end_date: str = "") -> list[Path]:
    source = Path(normalize_path(source_path))
    if not source.exists():
        raise FileNotFoundError(f"15min结果路径不存在：{source}")

    if source.is_file():
        candidates = [source]
    else:
        scan_root = source / "3号15min聚合结果" if (source / "3号15min聚合结果").is_dir() else source
        candidates = [path for path in scan_root.iterdir() if path.is_file()]

    files = []
    for path in candidates:
        if path.suffix.lower() not in RESULT_SUFFIXES:
            continue
        if path.is_file() and source.is_dir() and "15min" not in path.name:
            continue
        date_text = date_from_file_name(path.name)
        if start_date and end_date and source.is_dir():
            if not date_text or date_text < start_date or date_text > end_date:
                continue
        files.append(path)

    return sorted(files, key=lambda item: (date_from_file_name(item.name), item.name))


def load_15min_series(source_path: str, start_date: str = "", end_date: str = "") -> dict:
    files = scan_15min_files(source_path, start_date, end_date)
    frames = []
    failures = []
    for file_path in files:
        try:
            df = read_result_file(file_path)
            df = attach_datetime_column(df, file_path)
            frames.append(df)
        except Exception as exc:
            failures.append({"file": str(file_path), "error": str(exc)})

    if frames:
        merged = pd.concat(frames, axis=0, ignore_index=True)
        merged[DATETIME_COL] = pd.to_datetime(merged[DATETIME_COL], errors="coerce")
        merged = merged.dropna(subset=[DATETIME_COL])
        before = len(merged)
        merged = merged.drop_duplicates(subset=[DATETIME_COL], keep="first")
        duplicate_count = before - len(merged)
        merged = merged.sort_values(DATETIME_COL).reset_index(drop=True)
    else:
        merged = pd.DataFrame(columns=[DATETIME_COL])
        duplicate_count = 0

    missing_dates = []
    expected_start = start_date
    expected_end = end_date
    if not merged.empty:
        expected_start = expected_start or merged[DATETIME_COL].min().strftime("%Y-%m-%d")
        expected_end = expected_end or merged[DATETIME_COL].max().strftime("%Y-%m-%d")
    if expected_start and expected_end:
        expected = set(date_texts_between(expected_start, expected_end))
        present = set(merged[DATETIME_COL].dt.strftime("%Y-%m-%d").dropna().unique().tolist()) if not merged.empty else set()
        missing_dates = sorted(expected - present)

    numeric_columns = list_numeric_columns(merged)
    field_categories = group_plot_fields(numeric_columns)
    return {
        "data": merged,
        "files": [str(path) for path in files],
        "files_read": len(frames),
        "failures": failures,
        "duplicate_count": duplicate_count,
        "missing_dates": missing_dates,
        "numeric_columns": numeric_columns,
        "field_categories": field_categories,
        "time_start": merged[DATETIME_COL].min() if not merged.empty else None,
        "time_end": merged[DATETIME_COL].max() if not merged.empty else None,
        "rows": len(merged),
    }


def read_result_file(file_path: Path) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file_path)
    return pd.read_excel(file_path)


def attach_datetime_column(df: pd.DataFrame, file_path: Path) -> pd.DataFrame:
    result = df.copy()
    datetime_col = find_datetime_column(result)
    if datetime_col:
        result[DATETIME_COL] = pd.to_datetime(result[datetime_col], errors="coerce")
        return result

    date_col = find_column(result, ["日期", "date"])
    time_col = find_column(result, ["时间", "time"])
    if date_col and time_col:
        result[DATETIME_COL] = pd.to_datetime(result[date_col].astype(str) + " " + result[time_col].astype(str), errors="coerce")
        return result

    file_date = date_from_file_name(file_path.name)
    if file_date and time_col:
        result[DATETIME_COL] = pd.to_datetime(file_date + " " + result[time_col].astype(str), errors="coerce")
        return result

    if len(result.columns):
        first_col = result.columns[0]
        result[DATETIME_COL] = pd.to_datetime(result[first_col], errors="coerce")
        if result[DATETIME_COL].notna().any():
            return result

    raise ValueError("未能识别日期/时间列")


def find_datetime_column(df: pd.DataFrame):
    for col in df.columns:
        text = str(col).lower()
        if "数据时间" in str(col) or "datetime" in text or "日期时间" in str(col):
            return col
    for col in df.columns:
        parsed = pd.to_datetime(df[col], errors="coerce")
        if parsed.notna().sum() >= max(3, len(df) // 2):
            return col
    return None


def find_column(df: pd.DataFrame, keywords):
    for col in df.columns:
        text = str(col).lower()
        if any(keyword.lower() in text for keyword in keywords):
            return col
    return None


def list_numeric_columns(df: pd.DataFrame) -> list[str]:
    excluded = {DATETIME_COL}
    excluded_keywords = ["日期", "时间", "date", "time", "状态"]
    numeric_columns = []
    for col in df.columns:
        if col in excluded:
            continue
        col_text = str(col)
        if any(keyword.lower() in col_text.lower() for keyword in excluded_keywords):
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().any():
            numeric_columns.append(col_text)
    return numeric_columns


def classify_plot_field(field: str) -> str:
    text = str(field)
    lowered = text.lower()

    if "co2体积浓度" in lowered or "co₂体积浓度" in lowered or ("co2" in lowered and "浓度" in text):
        return "CO₂浓度"
    if "标干流量" in text:
        return "标干流量"
    if "co2排放速率" in lowered or "co₂排放速率" in lowered or "排放速率" in text:
        return "CO₂排放速率"
    if "入磨煤co2排放" in lowered:
        return "入磨燃煤碳排放"
    if "入窑煤co2排放" in lowered:
        return "入窑燃煤碳排放"
    if "过程排放" in text:
        return "过程排放"
    if "碳排放" in text and "废纺平均" in text and "入磨" in text:
        return "废纺平均法 · 入磨"
    if "碳排放" in text and "废纺平均" in text and "入窑" in text:
        return "废纺平均法 · 入窑"
    if "碳排放" in text and "废纺熟料能耗" in text and "入磨" in text:
        return "废纺熟料能耗法 · 入磨"
    if "碳排放" in text and "废纺熟料能耗" in text and "入窑" in text:
        return "废纺熟料能耗法 · 入窑"
    if "碳排放" in text and "入磨" in text:
        return "入磨综合碳排放"
    if "碳排放" in text and "入窑" in text:
        return "入窑综合碳排放"
    if "煤矸石" in text and ("co2" in lowered or "碳排放" in text):
        return "其他碳排放"
    if "低位发热量" in text:
        return "低位发热量"
    if text in {"入磨-A", "入磨-B"}:
        return "入磨生产计量"
    if "入窑-A磨" in text:
        return "入窑生产计量"
    if "废纺平均消耗量" in text:
        return "废纺消耗量"
    if "熟料产量" in text:
        return "熟料产量"
    if "熟料中CaO" in text or "熟料中MgO" in text:
        return "熟料成分"
    if text == "湿度":
        return "湿度"
    if text == "烟气温度":
        return "烟气温度"
    if text == "烟气压力":
        return "烟气压力"

    # 未知字段各自成类，避免无法确认量纲的字段被强制叠加。
    return f"其他字段 · {text}"


def group_plot_fields(fields: list[str]) -> dict[str, list[str]]:
    grouped = OrderedDict((category, []) for category in PLOT_CATEGORY_Y_LABELS)
    for field in fields:
        category = classify_plot_field(field)
        grouped.setdefault(category, []).append(str(field))
    return OrderedDict((category, values) for category, values in grouped.items() if values)


def category_y_label(category: str) -> str:
    if category in PLOT_CATEGORY_Y_LABELS:
        return PLOT_CATEGORY_Y_LABELS[category]
    if category.startswith("其他字段 · "):
        return category.removeprefix("其他字段 · ")
    return category


def line_style_for_field(field: str, category: str, index: int = 0) -> dict:
    text = str(field)
    path_key = _path_key(text)
    if path_key:
        color = PATH_COLORS[path_key]
    elif category in CATEGORY_BASE_COLORS:
        color = CATEGORY_BASE_COLORS[category]
    else:
        color = FALLBACK_COLORS[index % len(FALLBACK_COLORS)]

    if "2024" in text:
        linestyle = "--"
    elif "2023" in text:
        linestyle = "-"
    elif path_key:
        linestyle = ":"
    else:
        linestyle = "-"
    return {"color": color, "linestyle": linestyle, "linewidth": 1.35}


def _path_key(field: str) -> str:
    for key in ("Path1&2&3", "Path1&3", "Path1&2", "Path2&3", "Path1", "Path2", "Path3"):
        if key.lower() in field.lower():
            return key
    return ""


def date_from_file_name(file_name: str) -> str:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", str(file_name))
    return match.group(1) if match else ""
