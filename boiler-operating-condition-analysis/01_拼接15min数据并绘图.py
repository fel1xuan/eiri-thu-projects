#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""递归拼接海螺水泥15分钟碳排放结果，并绘制跨日期总览图。"""

from __future__ import annotations

import re
import sys
import unicodedata
import warnings
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# ============================================================
# 路径参数（第二阶段再使用秒级和低频数据，本阶段绝不读取它们）
# ============================================================
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
SOURCE_15MIN_DIR = DATA_DIR / "15min-results"
FUTURE_SECOND_DATA_DIR = DATA_DIR / "second-level-results"
FUTURE_LOWFREQ_DATA_DIR = DATA_DIR / "low-frequency"
OUTPUT_DIR = PROJECT_DIR / "输出结果"
SUMMARY_XLSX = OUTPUT_DIR / "15min数据汇总.xlsx"
OVERVIEW_PNG = OUTPUT_DIR / "15min总览图.png"


# ============================================================
# 可调整参数
# ============================================================
TIME_FREQUENCY = "15min"  # 完整时间轴频率
FUZZY_MATCH_MIN_RATIO = 0.78  # 唯一近似字段的最低相似度
FUZZY_MATCH_MIN_GAP = 0.08  # 最佳与次佳候选的最小相似度差
PLOT_DPI = 300  # 图片分辨率
PLOT_MIN_WIDTH = 18.0  # 图片最小宽度（英寸）
PLOT_MAX_WIDTH = 38.0  # 图片最大宽度（英寸）
PLOT_HEIGHT = 8.5  # 图片高度（英寸）
EXCEL_FREEZE_PANES = "A2"


SCENE_FIELDS = {
    "场景1": "碳排放_2023_入磨",
    "场景2": "碳排放_2023_入窑",
    "场景3": "碳排放_2024_入磨",
    "场景4": "碳排放_2024_入窑",
    "场景A": "CO2排放速率Path1",
    "场景B": "CO2排放速率Path2",
    "场景C": "CO2排放速率Path3",
    "场景D": "CO2排放速率Path1&2",
    "场景E": "CO2排放速率Path1&3",
    "场景F": "CO2排放速率Path2&3",
    "场景G": "CO2排放速率Path1&2&3",
}
SCENE_COLUMNS = list(SCENE_FIELDS)
TIME_FIELD_CANDIDATES = [
    "数据时间",
    "时间",
    "日期时间",
    "采集时间",
    "统计时间",
    "datetime",
    "timestamp",
]
SCENE_LABELS = {
    "场景1": "场景1：2023年指南-燃煤（入磨监测）",
    "场景2": "场景2：2023年指南-燃煤（入窑监测）",
    "场景3": "场景3：2024年指南-燃煤（入磨监测）",
    "场景4": "场景4：2024年指南-燃煤（入窑监测）",
    "场景A": "场景A：1声道",
    "场景B": "场景B：2声道",
    "场景C": "场景C：3声道",
    "场景D": "场景D：1&2声道",
    "场景E": "场景E：1&3声道",
    "场景F": "场景F：2&3声道",
    "场景G": "场景G：1&2&3声道",
}


class AmbiguousColumnError(RuntimeError):
    """字段存在多个近似候选，禁止程序自行猜测。"""


def normalize_header(value: object) -> str:
    """统一全角半角、空白和中英文常见符号，供字段匹配使用。"""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    translation = str.maketrans(
        {
            "（": "(",
            "）": ")",
            "，": ",",
            "：": ":",
            "；": ";",
            "＆": "&",
            "－": "-",
            "＿": "_",
        }
    )
    text = text.translate(translation)
    return re.sub(r"\s+", "", text)


def match_column(target: str, columns: Iterable[object], *, allow_fuzzy: bool = True) -> str | None:
    """按精确、规范化、唯一近似的顺序匹配列名。"""
    column_names = [str(column) for column in columns]
    if target in column_names:
        return target

    normalized_target = normalize_header(target)
    normalized_matches = [
        column for column in column_names if normalize_header(column) == normalized_target
    ]
    if len(normalized_matches) == 1:
        return normalized_matches[0]
    if len(normalized_matches) > 1:
        raise AmbiguousColumnError(f"字段“{target}”存在多个规范化候选：{normalized_matches}")
    if not allow_fuzzy:
        return None

    scored = sorted(
        (
            SequenceMatcher(None, normalized_target, normalize_header(column)).ratio(),
            column,
        )
        for column in column_names
    )[::-1]
    if not scored or scored[0][0] < FUZZY_MATCH_MIN_RATIO:
        return None
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if scored[0][0] - second_score < FUZZY_MATCH_MIN_GAP:
        candidates = [column for score, column in scored[:5] if score >= FUZZY_MATCH_MIN_RATIO]
        raise AmbiguousColumnError(
            f"字段“{target}”存在多个近似候选，程序停止猜测：{candidates}"
        )
    return scored[0][1]


def extract_date_from_path(path: Path) -> pd.Timestamp | None:
    """从文件名或目录名提取日期，支持YYYY-MM-DD、YYYYMMDD和YYYYMM。"""
    for part in reversed(path.parts):
        match = re.search(r"(?<!\d)(20\d{2})[-_/年]?(\d{2})[-_/月]?(\d{2})(?!\d)", part)
        if match:
            return pd.Timestamp(
                year=int(match.group(1)), month=int(match.group(2)), day=int(match.group(3))
            )
    return None


def list_excel_files(root: Path) -> list[Path]:
    """递归列出候选Excel，并排除隐藏、临时和本项目输出。"""
    if not root.exists():
        raise FileNotFoundError(f"15min源目录不存在：{root}")
    candidates: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
            continue
        relative_parts = path.relative_to(root).parts
        if path.name.startswith("~$") or any(part.startswith(".") for part in relative_parts):
            continue
        if "输出结果" in relative_parts or path.resolve() in {
            SUMMARY_XLSX.resolve(),
            OVERVIEW_PNG.resolve(),
        }:
            continue
        candidates.append(path)
    return sorted(candidates)


def inspect_workbook(path: Path) -> tuple[str, list[str], str, dict[str, str]] | None:
    """定位包含时间列和11个目标字段的工作表。"""
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        matched_sheets = []
        for worksheet in workbook.worksheets:
            first_row = next(
                worksheet.iter_rows(min_row=1, max_row=1, values_only=True), tuple()
            )
            columns = [str(value).strip() for value in first_row if value is not None]
            if not columns:
                continue
            time_column = None
            for candidate in TIME_FIELD_CANDIDATES:
                time_column = match_column(candidate, columns, allow_fuzzy=False)
                if time_column:
                    break
            if not time_column:
                time_like = [
                    column
                    for column in columns
                    if any(key in normalize_header(column) for key in ("时间", "datetime", "timestamp"))
                ]
                if len(time_like) == 1:
                    time_column = time_like[0]
                elif len(time_like) > 1:
                    raise AmbiguousColumnError(
                        f"{path} 的工作表“{worksheet.title}”存在多个时间列候选：{time_like}"
                    )

            mapping: dict[str, str] = {}
            for scene, source_field in SCENE_FIELDS.items():
                matched = match_column(source_field, columns)
                if matched:
                    mapping[scene] = matched
            if time_column and len(mapping) == len(SCENE_FIELDS):
                matched_sheets.append((worksheet.title, columns, time_column, mapping))

        if len(matched_sheets) > 1:
            names = [item[0] for item in matched_sheets]
            raise AmbiguousColumnError(f"{path} 有多个符合条件的工作表：{names}")
        return matched_sheets[0] if matched_sheets else None
    finally:
        workbook.close()


def build_timestamps(series: pd.Series, path: Path) -> pd.Series:
    """优先解析完整时间；若只有时刻，则用文件名/目录名补日期。"""
    parsed = pd.to_datetime(series, errors="coerce")
    valid = parsed.dropna()
    if not valid.empty and valid.dt.normalize().nunique() > 1:
        return parsed.dt.floor(TIME_FREQUENCY)

    # Excel时刻可能被读取为datetime.time、字符串或1899/1900基准日期。
    date_hint = extract_date_from_path(path)
    if date_hint is None:
        if valid.empty:
            return parsed
        if valid.dt.year.max() >= 2000:
            return parsed.dt.floor(TIME_FREQUENCY)
        return pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    def combine(value: object) -> pd.Timestamp:
        if pd.isna(value):
            return pd.NaT
        timestamp = pd.to_datetime(value, errors="coerce")
        if pd.isna(timestamp):
            match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", str(value))
            if not match:
                return pd.NaT
            return date_hint + pd.Timedelta(
                hours=int(match.group(1)),
                minutes=int(match.group(2)),
                seconds=int(match.group(3) or 0),
            )
        if timestamp.year >= 2000:
            return timestamp
        return date_hint + pd.Timedelta(
            hours=timestamp.hour, minutes=timestamp.minute, seconds=timestamp.second
        )

    return series.map(combine).dt.floor(TIME_FREQUENCY)


def read_one_file(
    path: Path, sheet_name: str, time_column: str, field_mapping: dict[str, str]
) -> pd.DataFrame:
    """读取一个有效工作表，只保留时间、11个场景和来源文件。"""
    usecols = [time_column, *field_mapping.values()]
    frame = pd.read_excel(path, sheet_name=sheet_name, usecols=usecols, engine="openpyxl")
    output = pd.DataFrame({"时间": build_timestamps(frame[time_column], path)})
    for scene, source_column in field_mapping.items():
        output[scene] = pd.to_numeric(frame[source_column], errors="coerce")
    output["来源文件"] = str(path)
    return output.dropna(subset=["时间"])


def merge_duplicate_timestamps(data: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """重复时间优先保留有效值最多的行；并列时对数值列取中位数。"""
    duplicate_mask = data.duplicated("时间", keep=False)
    duplicate_count = int(duplicate_mask.sum())
    if duplicate_count == 0:
        result = data.sort_values("时间").drop_duplicates("时间").copy()
        result["_重复时间合并"] = False
        return result, 0

    rows: list[dict[str, object]] = []
    for timestamp, group in data.groupby("时间", sort=True):
        valid_counts = group[SCENE_COLUMNS].notna().sum(axis=1)
        best = group.loc[valid_counts == valid_counts.max()]
        row: dict[str, object] = {"时间": timestamp}
        if len(best) == 1:
            for scene in SCENE_COLUMNS:
                row[scene] = best.iloc[0][scene]
        else:
            for scene in SCENE_COLUMNS:
                row[scene] = best[scene].median(skipna=True)
        sources = sorted(set(best["来源文件"].dropna().astype(str)))
        row["来源文件"] = "；".join(sources)
        row["_重复时间合并"] = len(group) > 1
        rows.append(row)
    return pd.DataFrame(rows), duplicate_count


def complete_time_axis(data: pd.DataFrame) -> pd.DataFrame:
    """从最早到最晚补齐完整15分钟时间轴，长缺口保留NaN。"""
    if data.empty:
        raise ValueError("未读取到任何可用的15min数据。")
    start = data["时间"].min().floor(TIME_FREQUENCY)
    end = data["时间"].max().floor(TIME_FREQUENCY)
    full_index = pd.date_range(start, end, freq=TIME_FREQUENCY, name="时间")
    completed = data.set_index("时间").reindex(full_index).reset_index()
    completed["_重复时间合并"] = completed["_重复时间合并"].fillna(False).astype(bool)

    valid_count = completed[SCENE_COLUMNS].notna().sum(axis=1)
    completed["数据状态"] = np.select(
        [
            valid_count.eq(0),
            valid_count.between(1, len(SCENE_COLUMNS) - 1),
            completed["_重复时间合并"],
        ],
        ["全空", "部分缺失", "重复时间合并"],
        default="正常",
    )
    columns = ["时间", *SCENE_COLUMNS, "数据状态", "来源文件"]
    return completed[columns]


def select_chinese_font() -> str:
    """选择Mac可用中文字体，并避免反复触发findfont警告。"""
    preferred = ["PingFang SC", "Heiti SC", "Arial Unicode MS", "Songti SC"]
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in preferred:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["axes.unicode_minus"] = False
            return name
    plt.rcParams["axes.unicode_minus"] = False
    warnings.filterwarnings("ignore", message=r"Glyph .* missing from font")
    return "matplotlib默认字体"


def configure_date_axis(axis: plt.Axes, start: pd.Timestamp, end: pd.Timestamp) -> None:
    """按总时间跨度自动选取日、周或月刻度。"""
    days = max((end - start).total_seconds() / 86400, 1)
    if days <= 21:
        locator = mdates.DayLocator(interval=max(1, int(days // 10) or 1))
        formatter = mdates.DateFormatter("%m-%d")
    elif days <= 120:
        locator = mdates.WeekdayLocator(byweekday=mdates.MO, interval=1)
        formatter = mdates.DateFormatter("%m-%d")
    else:
        locator = mdates.MonthLocator(interval=1)
        formatter = mdates.DateFormatter("%Y-%m")
    axis.xaxis.set_major_locator(locator)
    axis.xaxis.set_major_formatter(formatter)


def plot_overview(data: pd.DataFrame, output_path: Path) -> None:
    """绘制左侧场景1—4、右侧场景A—G的连续时间总览。"""
    select_chinese_font()
    span_days = max((data["时间"].max() - data["时间"].min()).days + 1, 1)
    width = min(PLOT_MAX_WIDTH, max(PLOT_MIN_WIDTH, 16 + span_days / 18))
    figure, axes = plt.subplots(1, 2, figsize=(width, PLOT_HEIGHT), sharex=True)
    colors_left = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd"]
    colors_right = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#17becf"]
    groups = [
        (axes[0], SCENE_COLUMNS[:4], colors_left, "场景1—4碳排放总览"),
        (axes[1], SCENE_COLUMNS[4:], colors_right, "场景A—G碳排放总览"),
    ]
    for axis, columns, colors, title in groups:
        for scene, color in zip(columns, colors):
            axis.plot(
                data["时间"],
                data[scene],
                color=color,
                linewidth=0.55,
                alpha=0.82,
                label=SCENE_LABELS[scene],
            )
        axis.set_title(title, fontsize=14, pad=12)
        axis.set_xlabel("日期")
        axis.set_ylabel("碳排放相关结果")
        axis.grid(True, alpha=0.2, linewidth=0.5)
        axis.legend(loc="best", fontsize=8, framealpha=0.9)
        configure_date_axis(axis, data["时间"].min(), data["时间"].max())
        axis.tick_params(axis="x", rotation=35)
        axis.margins(x=0.005)
    figure.suptitle(
        f"海螺水泥15min碳排放连续总览（{data['时间'].min():%Y-%m-%d} 至 {data['时间'].max():%Y-%m-%d}）",
        fontsize=16,
        y=0.99,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.965))
    figure.savefig(output_path, dpi=PLOT_DPI, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def format_summary_excel(path: Path) -> None:
    """设置汇总Excel的冻结窗格、筛选、日期格式和适度列宽。"""
    workbook = load_workbook(path)
    worksheet = workbook["全部15min数据"]
    worksheet.freeze_panes = EXCEL_FREEZE_PANES
    worksheet.auto_filter.ref = worksheet.dimensions
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    worksheet.column_dimensions["A"].width = 20
    for column_index in range(2, 13):
        worksheet.column_dimensions[get_column_letter(column_index)].width = 15
    worksheet.column_dimensions["M"].width = 16
    worksheet.column_dimensions["N"].width = 64
    for cell in worksheet["A"][1:]:
        cell.number_format = "yyyy-mm-dd hh:mm"
    for row in worksheet.iter_rows(min_row=2, min_col=2, max_col=12):
        for cell in row:
            cell.number_format = "0.0000"
    workbook.save(path)


def main() -> None:
    """执行扫描、读取、拼接、补轴、Excel输出和绘图。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    excel_files = list_excel_files(SOURCE_15MIN_DIR)
    if not excel_files:
        raise FileNotFoundError(f"源目录中未找到Excel：{SOURCE_15MIN_DIR}")

    frames: list[pd.DataFrame] = []
    skipped = 0
    damaged = 0
    mappings_seen: dict[str, set[str]] = {scene: set() for scene in SCENE_COLUMNS}
    time_columns_seen: set[str] = set()

    for path in excel_files:
        try:
            inspected = inspect_workbook(path)
            if inspected is None:
                skipped += 1
                print(f"跳过无关Excel：{path}")
                continue
            sheet_name, _, time_column, mapping = inspected
            frame = read_one_file(path, sheet_name, time_column, mapping)
            if frame.empty:
                skipped += 1
                print(f"警告：文件没有可解析时间，已跳过：{path}")
                continue
            frames.append(frame)
            time_columns_seen.add(time_column)
            for scene, source_column in mapping.items():
                mappings_seen[scene].add(source_column)
        except AmbiguousColumnError:
            raise
        except Exception as exc:
            damaged += 1
            skipped += 1
            print(f"警告：文件读取失败，已跳过：{path}；原因：{exc}")

    success_count = len(frames)
    if success_count == 0:
        raise RuntimeError("没有成功读取任何15min核算结果。")
    if success_count < max(3, int(len(excel_files) * 0.5)):
        raise RuntimeError(
            f"大量文件缺少关键字段或损坏：扫描{len(excel_files)}个，仅成功{success_count}个。"
        )

    combined = pd.concat(frames, ignore_index=True)
    merged, duplicate_count = merge_duplicate_timestamps(combined)
    completed = complete_time_axis(merged)

    with pd.ExcelWriter(
        SUMMARY_XLSX,
        engine="openpyxl",
        datetime_format="yyyy-mm-dd hh:mm",
    ) as writer:
        completed.to_excel(writer, sheet_name="全部15min数据", index=False)
    format_summary_excel(SUMMARY_XLSX)
    plot_overview(completed, OVERVIEW_PNG)

    print("\n===== 01脚本运行摘要 =====")
    print(f"扫描到的Excel数量：{len(excel_files)}")
    print(f"成功读取数量：{success_count}")
    print(f"跳过数量：{skipped}（其中损坏或读取失败：{damaged}）")
    print(f"识别时间列：{'、'.join(sorted(time_columns_seen))}")
    print("11个真实字段映射：")
    for scene in SCENE_COLUMNS:
        print(f"  {scene} <- {'、'.join(sorted(mappings_seen[scene]))}")
    print(f"数据最早时间：{completed['时间'].min():%Y-%m-%d %H:%M}")
    print(f"数据最晚时间：{completed['时间'].max():%Y-%m-%d %H:%M}")
    print(f"汇总行数：{len(completed)}")
    print(f"重复时间数量：{duplicate_count}")
    print(f"全空时间点数量：{int((completed['数据状态'] == '全空').sum())}")
    print(f"部分缺失时间点数量：{int((completed['数据状态'] == '部分缺失').sum())}")
    print(f"汇总Excel：{SUMMARY_XLSX}")
    print(f"总览图：{OVERVIEW_PNG}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\n运行失败：{error}", file=sys.stderr)
        raise
