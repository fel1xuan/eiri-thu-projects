#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基于11条碳排放曲线自动识别事件、变化点并划分连续工况。"""

from __future__ import annotations

import importlib.util
import math
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# ============================================================
# 路径参数（第二阶段物理因素分析预留路径，本脚本不读取这些目录）
# ============================================================
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
FUTURE_SECOND_DATA_DIR = DATA_DIR / "second-level-results"
FUTURE_LOWFREQ_DATA_DIR = DATA_DIR / "low-frequency"
OUTPUT_DIR = PROJECT_DIR / "输出结果"
INPUT_XLSX = OUTPUT_DIR / "15min数据汇总.xlsx"
RESULT_XLSX = OUTPUT_DIR / "工况分析结果.xlsx"
CONDITION_PNG = OUTPUT_DIR / "自动工况划分图.png"


# ============================================================
# 业务时间参数
# ============================================================
BEFORE_WINDOW_HOURS = 24
AFTER_WINDOW_HOURS = 24
MIN_CONDITION_HOURS = 48
CHANGE_MERGE_HOURS = 6
SHORT_EVENT_HOURS = 24
SUSPECTED_CONDITION_MAX_HOURS = 48
SHUTDOWN_MIN_HOURS = 1


# ============================================================
# 初始变化阈值；历史足够时由全历史网格搜索自适应选择
# ============================================================
MIN_RELATIVE_CHANGE = 0.05
STRONG_RELATIVE_CHANGE = 0.10
MIN_FLUCTUATION_MULTIPLE = 3.0
STRONG_FLUCTUATION_MULTIPLE = 5.0
USE_ADAPTIVE_PARAMETERS = True
MIN_HISTORY_DAYS_FOR_ADAPTIVE = 30
RANDOM_SEED = 42


# ============================================================
# 事件、检测和输出参数
# ============================================================
TIME_FREQUENCY_MINUTES = 15
POINTS_PER_HOUR = 4
SHORT_INTERPOLATION_HOURS = 1
NEAR_ZERO_ABSOLUTE_MIN = 1e-6
NEAR_ZERO_MEDIAN_RATIO = 0.001
SHUTDOWN_CHANNEL_RATIO = 0.20
SHUTDOWN_CALC_RATIO = 0.30
LOCAL_BASELINE_DAYS = 7
MIN_WINDOW_VALID_RATIO = 0.50
CANDIDATE_SAMPLE_MINUTES = 60
BOUNDARY_SUSTAIN_HOURS = 1
POST_STABLE_HOURS = 4
ABRUPT_MAX_TRANSITION_HOURS = 2
SHORT_ANOMALY_MIN_HOURS = 1
EVENT_MERGE_GAP_HOURS = 3  # 周期性部分缺失间隔不超过3小时归为同一间歇性事件
PLOT_DPI = 300
PLOT_MIN_WIDTH = 20.0
PLOT_MAX_WIDTH = 40.0
PLOT_HEIGHT = 9.2


SCENE_COLUMNS = [
    "场景1",
    "场景2",
    "场景3",
    "场景4",
    "场景A",
    "场景B",
    "场景C",
    "场景D",
    "场景E",
    "场景F",
    "场景G",
]
CALC_SCENES = SCENE_COLUMNS[:4]
BASE_CHANNEL_SCENES = SCENE_COLUMNS[4:7]
COMBO_CHANNEL_SCENES = SCENE_COLUMNS[7:]
GROUP_BY_SCENE = {
    **{scene: "核算场景组" for scene in CALC_SCENES},
    **{scene: "基础声道组" for scene in BASE_CHANNEL_SCENES},
    **{scene: "组合声道辅助组" for scene in COMBO_CHANNEL_SCENES},
}
SOURCE_FIELDS = {
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


@dataclass
class DetectionParameters:
    """一次候选变化检测实际使用的阈值。"""

    relative: float
    strong_relative: float
    multiple: float
    strong_multiple: float
    merge_hours: float
    adaptive: bool
    score: float = np.nan


@dataclass
class Candidate:
    """经规则C筛选后的候选变化点。"""

    peak_position: int
    boundary_position: int
    score: float
    rule_type: str
    calc_count: int
    base_count: int
    combo_count: int
    support_scenes: list[str]
    strong_scenes: list[str]
    transition_start: pd.Timestamp
    transition_end: pd.Timestamp
    change_form: str
    deviation_duration_hours: float | None = None


@dataclass
class Event:
    """连续事件区间。"""

    event_id: str
    event_type: str
    start_position: int
    end_position: int
    member_runs: list[tuple[str, int, int]] = field(default_factory=list)
    is_intermittent_missing: bool = False


@dataclass
class Condition:
    """一个连续正式工况。"""

    condition_id: str
    start_position: int
    end_position: int
    boundary_candidate: Candidate | None
    start_reason: str


def robust_mad(series: pd.Series) -> float:
    """返回经1.4826缩放的MAD。"""
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(float)
    if values.size == 0:
        return np.nan
    median = np.median(values)
    return float(1.4826 * np.median(np.abs(values - median)))


def robust_iqr(series: pd.Series) -> float:
    """返回IQR。"""
    values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(float)
    if values.size == 0:
        return np.nan
    return float(np.quantile(values, 0.75) - np.quantile(values, 0.25))


def contiguous_runs(mask: pd.Series | np.ndarray) -> list[tuple[int, int]]:
    """将布尔序列转换为闭区间位置列表。"""
    values = np.asarray(mask, dtype=bool)
    if values.size == 0:
        return []
    changes = np.diff(np.r_[False, values, False].astype(int))
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1) - 1
    return list(zip(starts.tolist(), ends.tolist()))


def rolling_future_median(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    """计算当前位置之后窗口的中位数，不包含当前位置。"""
    return series.iloc[::-1].shift(1).rolling(window, min_periods=min_periods).median().iloc[::-1]


def select_chinese_font() -> str:
    """选择可用中文字体，避免大量findfont警告。"""
    preferred = ["PingFang SC", "Heiti SC", "Arial Unicode MS", "Songti SC"]
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in preferred:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["font.family"] = "sans-serif"
            plt.rcParams["axes.unicode_minus"] = False
            return name
    warnings.filterwarnings("ignore", message=r"Glyph .* missing from font")
    plt.rcParams["axes.unicode_minus"] = False
    return "matplotlib默认字体"


def load_input() -> pd.DataFrame:
    """读取01脚本汇总结果并检查必要列。"""
    if not INPUT_XLSX.exists():
        raise FileNotFoundError(f"缺少输入文件，请先运行01脚本：{INPUT_XLSX}")
    data = pd.read_excel(INPUT_XLSX, sheet_name="全部15min数据", engine="openpyxl")
    required = ["时间", *SCENE_COLUMNS, "数据状态", "来源文件"]
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise ValueError(f"15min汇总文件缺少必要列：{missing}")
    data = data[required].copy()
    data["时间"] = pd.to_datetime(data["时间"], errors="coerce")
    if data["时间"].isna().any():
        raise ValueError(f"输入文件有{int(data['时间'].isna().sum())}行时间无法解析。")
    data = data.sort_values("时间").drop_duplicates("时间", keep="first").reset_index(drop=True)
    for scene in SCENE_COLUMNS:
        data[scene] = pd.to_numeric(data[scene], errors="coerce")
    expected = pd.date_range(data["时间"].min(), data["时间"].max(), freq="15min")
    if len(expected) != len(data) or not data["时间"].reset_index(drop=True).equals(
        pd.Series(expected, name="时间")
    ):
        raise ValueError("输入文件不是完整、连续的15分钟时间轴，请重新运行01脚本。")
    return data


def scene_reliability_weights(data: pd.DataFrame) -> tuple[dict[str, float], pd.DataFrame]:
    """按完整率、同组一致性和重复性约束学习可解释场景权重。"""
    rows = []
    raw_scores: dict[str, float] = {}
    groups = [CALC_SCENES, BASE_CHANNEL_SCENES, COMBO_CHANNEL_SCENES]
    group_totals = {
        "核算场景组": 0.45,
        "基础声道组": 0.40,
        "组合声道辅助组": 0.15,
    }
    for group in groups:
        correlation = data[group].corr(method="spearman", min_periods=96).abs()
        for scene in group:
            peers = correlation.loc[scene].drop(scene, errors="ignore").dropna()
            consistency = float(peers.median()) if not peers.empty else 0.5
            completeness = float(data[scene].notna().mean())
            # 极端一阶跳变比例近似表示孤立假变化频率，比例越高可靠性越低。
            positive_scale = max(robust_mad(data[scene]), abs(float(data[scene].median())) * 0.001, 1e-6)
            isolated_rate = float((data[scene].diff().abs() > 8 * positive_scale).mean())
            raw = max(0.05, completeness * (0.55 + 0.45 * consistency) * (1 - min(isolated_rate, 0.5)))
            raw_scores[scene] = raw
            rows.append(
                {
                    "场景": scene,
                    "所属变量组": GROUP_BY_SCENE[scene],
                    "数据完整率": completeness,
                    "同组一致性": consistency,
                    "孤立大跳变频率": isolated_rate,
                    "原始可靠性得分": raw,
                }
            )

    weights: dict[str, float] = {}
    for group in groups:
        group_name = GROUP_BY_SCENE[group[0]]
        denominator = sum(raw_scores[scene] for scene in group)
        for scene in group:
            weights[scene] = group_totals[group_name] * raw_scores[scene] / denominator
    table = pd.DataFrame(rows)
    table["可靠性权重"] = table["场景"].map(weights)
    table["权重依据"] = table.apply(
        lambda row: (
            f"完整率{row['数据完整率']:.1%}；同组一致性{row['同组一致性']:.3f}；"
            f"孤立大跳变频率{row['孤立大跳变频率']:.2%}；"
            f"{row['所属变量组']}总权重受结构约束"
        ),
        axis=1,
    )
    return weights, table


def initial_event_labels(data: pd.DataFrame) -> tuple[pd.Series, dict[str, float], dict[str, pd.Series]]:
    """识别全空、零值、疑似停窑和部分缺失事件。"""
    values = data[SCENE_COLUMNS]
    full_empty = values.isna().all(axis=1)
    any_missing = values.isna().any(axis=1)

    near_zero_thresholds: dict[str, float] = {}
    near_zero_flags = pd.DataFrame(index=data.index)
    for scene in SCENE_COLUMNS:
        positive = data.loc[data[scene] > 0, scene]
        reference = float(positive.median()) if not positive.empty else 0.0
        threshold = max(NEAR_ZERO_ABSOLUTE_MIN, abs(reference) * NEAR_ZERO_MEDIAN_RATIO)
        near_zero_thresholds[scene] = threshold
        near_zero_flags[scene] = data[scene].notna() & data[scene].abs().le(threshold)
    all_near_zero = values.notna().all(axis=1) & near_zero_flags.all(axis=1)

    local_window = LOCAL_BASELINE_DAYS * 24 * POINTS_PER_HOUR
    local_baselines: dict[str, pd.Series] = {}
    one_hour_medians: dict[str, pd.Series] = {}
    for scene in SCENE_COLUMNS:
        positive = data[scene].where(data[scene] > near_zero_thresholds[scene])
        fallback = float(positive.median()) if positive.notna().any() else np.nan
        baseline = (
            positive.shift(1)
            .rolling(local_window, min_periods=24 * POINTS_PER_HOUR)
            .median()
            .fillna(fallback)
        )
        local_baselines[scene] = baseline
        one_hour_medians[scene] = data[scene].rolling(POINTS_PER_HOUR, min_periods=2).median()

    base_low = pd.DataFrame(
        {
            scene: one_hour_medians[scene].lt(local_baselines[scene] * SHUTDOWN_CHANNEL_RATIO)
            & one_hour_medians[scene].notna()
            for scene in BASE_CHANNEL_SCENES
        }
    )
    calc_ratio = pd.DataFrame(
        {
            scene: one_hour_medians[scene] / local_baselines[scene].replace(0, np.nan)
            for scene in CALC_SCENES
        }
    )
    calc_overall_low = calc_ratio.median(axis=1, skipna=True).lt(SHUTDOWN_CALC_RATIO)
    shutdown_raw = base_low.sum(axis=1).ge(2) & calc_overall_low & ~full_empty & ~all_near_zero
    minimum_points = max(1, round(SHUTDOWN_MIN_HOURS * POINTS_PER_HOUR))
    shutdown = pd.Series(False, index=data.index)
    for start, end in contiguous_runs(shutdown_raw):
        if end - start + 1 >= minimum_points:
            shutdown.iloc[start : end + 1] = True

    labels = pd.Series("", index=data.index, dtype=object)
    labels.loc[full_empty] = "全空事件（原因需后续结合秒级或生产数据判断）"
    labels.loc[all_near_zero & labels.eq("")] = "零值事件"
    labels.loc[shutdown & labels.eq("")] = "疑似停窑"
    labels.loc[any_missing & labels.eq("")] = "部分缺失"
    masks = {
        "full_empty": full_empty,
        "all_near_zero": all_near_zero,
        "shutdown": shutdown,
        "partial_missing": any_missing & ~full_empty,
    }
    return labels, near_zero_thresholds, masks


def build_detection_copy(data: pd.DataFrame, excluded: pd.Series) -> pd.DataFrame:
    """仅在检测副本中插值不超过1小时的小缺口，原始数据保持不变。"""
    detection = data[SCENE_COLUMNS].copy()
    detection.loc[excluded, :] = np.nan
    limit = max(1, round(SHORT_INTERPOLATION_HOURS * POINTS_PER_HOUR))
    for scene in SCENE_COLUMNS:
        detection[scene] = detection[scene].interpolate(
            method="linear", limit=limit, limit_area="inside"
        )
    return detection


def prepare_evidence(
    detection: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], dict[str, float], pd.Series]:
    """预计算24小时前后中位数、稳健尺度、相对变化和变化倍数。"""
    before_points = BEFORE_WINDOW_HOURS * POINTS_PER_HOUR
    after_points = AFTER_WINDOW_HOURS * POINTS_PER_HOUR
    min_before = math.ceil(before_points * MIN_WINDOW_VALID_RATIO)
    min_after = math.ceil(after_points * MIN_WINDOW_VALID_RATIO)
    evidence: dict[str, pd.DataFrame] = {}
    scale_floors: dict[str, float] = {}
    standardized = pd.DataFrame(index=detection.index)

    for scene in SCENE_COLUMNS:
        series = detection[scene]
        global_mad = robust_mad(series)
        global_iqr = robust_iqr(series)
        median_abs = abs(float(series.median())) if series.notna().any() else 0.0
        floor = max(
            NEAR_ZERO_ABSOLUTE_MIN,
            median_abs * 0.001,
            (global_mad if np.isfinite(global_mad) else 0.0) * 0.10,
            (global_iqr if np.isfinite(global_iqr) else 0.0) * 0.03,
        )
        scale_floors[scene] = floor
        before = series.shift(1).rolling(before_points, min_periods=min_before)
        before_median = before.median()
        q25 = before.quantile(0.25)
        q75 = before.quantile(0.75)
        old_iqr = q75 - q25
        diff_noise = (
            series.diff()
            .abs()
            .shift(1)
            .rolling(before_points, min_periods=min_before)
            .median()
            * 1.4826
            / math.sqrt(2)
        )
        scale = pd.concat([old_iqr / 1.349, diff_noise], axis=1).max(axis=1).clip(lower=floor)
        after_median = rolling_future_median(series, after_points, min_after)
        absolute = after_median - before_median
        denominator = before_median.abs().clip(lower=max(median_abs * 0.02, floor))
        relative = absolute.abs() / denominator
        multiple = absolute.abs() / scale
        valid = before_median.notna() & after_median.notna() & scale.notna()
        evidence[scene] = pd.DataFrame(
            {
                "before": before_median,
                "after": after_median,
                "absolute": absolute,
                "relative": relative,
                "scale": scale,
                "old_iqr": old_iqr,
                "multiple": multiple,
                "valid": valid,
            }
        )
        center = float(series.median()) if series.notna().any() else 0.0
        standardized[scene] = (series - center) / max(global_mad, global_iqr / 1.349, floor)
    composite = standardized.median(axis=1, skipna=True).rolling(24, min_periods=8).median()
    return evidence, scale_floors, composite


def rule_arrays(
    evidence: dict[str, pd.DataFrame],
    params: DetectionParameters,
    weights: dict[str, float],
) -> pd.DataFrame:
    """应用普通/强变化阈值和规则C，返回逐点支持信息。"""
    normal = pd.DataFrame(index=next(iter(evidence.values())).index)
    strong = pd.DataFrame(index=normal.index)
    score = pd.Series(0.0, index=normal.index)
    for scene in SCENE_COLUMNS:
        item = evidence[scene]
        normal[scene] = (
            item["valid"]
            & item["relative"].ge(params.relative)
            & item["multiple"].ge(params.multiple)
        )
        strong[scene] = item["valid"] & (
            item["relative"].ge(params.strong_relative)
            | item["multiple"].ge(params.strong_multiple)
        )
        score += normal[scene].astype(float) * weights[scene]
        score += strong[scene].astype(float) * weights[scene] * 0.5

    calc_normal = normal[CALC_SCENES].sum(axis=1)
    base_normal = normal[BASE_CHANNEL_SCENES].sum(axis=1)
    combo_normal = normal[COMBO_CHANNEL_SCENES].sum(axis=1)
    calc_strong = strong[CALC_SCENES].sum(axis=1)
    base_strong = strong[BASE_CHANNEL_SCENES].sum(axis=1)
    type1 = calc_normal.ge(3) & base_normal.ge(2)
    type2 = calc_strong.ge(3)
    type3 = base_strong.ge(2) & combo_normal.ge(3)
    rule = type1 | type2 | type3
    rule_type = pd.Series("", index=normal.index, dtype=object)
    rule_type.loc[type1] = "类型1：两组共同变化"
    rule_type.loc[~type1 & type2] = "类型2：核算场景主导"
    rule_type.loc[~type1 & ~type2 & type3] = "类型3：多声道主导"
    return pd.DataFrame(
        {
            "rule": rule,
            "rule_type": rule_type,
            "score": score,
            "calc_count": calc_normal,
            "base_count": base_normal,
            "combo_count": combo_normal,
            **{f"普通_{scene}": normal[scene] for scene in SCENE_COLUMNS},
            **{f"强_{scene}": strong[scene] for scene in SCENE_COLUMNS},
        }
    )


def cluster_candidate_positions(rule_table: pd.DataFrame, merge_hours: float) -> list[int]:
    """将相近的多场景候选合并，并选择综合支持得分最高的位置。"""
    sample_step = max(1, round(CANDIDATE_SAMPLE_MINUTES / TIME_FREQUENCY_MINUTES))
    positions = np.flatnonzero(rule_table["rule"].to_numpy())[::sample_step]
    if positions.size == 0:
        return []
    max_gap = max(1, round(merge_hours * POINTS_PER_HOUR))
    clusters: list[list[int]] = [[int(positions[0])]]
    for position in positions[1:]:
        if int(position) - clusters[-1][-1] <= max_gap:
            clusters[-1].append(int(position))
        else:
            clusters.append([int(position)])
    peaks = []
    for cluster in clusters:
        scores = rule_table.iloc[cluster]["score"]
        peaks.append(int(scores.idxmax()))
    return peaks


def parameter_score(
    peaks: list[int],
    rule_table: pd.DataFrame,
    composite: pd.Series,
    history_days: float,
) -> float:
    """评价边界支持、段内稳定性、段间分离和碎片数量。"""
    if not peaks:
        overall_dispersion = robust_mad(composite)
        return -2.0 - (overall_dispersion if np.isfinite(overall_dispersion) else 0.0)
    positions = [0, *sorted(peaks), len(composite)]
    segment_medians = []
    segment_disps = []
    short_segments = 0
    for start, end in zip(positions[:-1], positions[1:]):
        segment = composite.iloc[start:end].dropna()
        if len(segment) < MIN_CONDITION_HOURS * POINTS_PER_HOUR:
            short_segments += 1
        if segment.empty:
            continue
        segment_medians.append(float(segment.median()))
        segment_disps.append(robust_mad(segment))
    separation = (
        float(np.median(np.abs(np.diff(segment_medians)))) if len(segment_medians) > 1 else 0.0
    )
    dispersion = float(np.nanmedian(segment_disps)) if segment_disps else 0.0
    support = float(rule_table.iloc[peaks]["score"].mean())
    excessive = max(0.0, len(peaks) - max(2.0, history_days / 7.0))
    return 3.0 * support + separation - dispersion - 2.5 * short_segments - 0.25 * excessive


def choose_parameters(
    evidence: dict[str, pd.DataFrame],
    weights: dict[str, float],
    composite: pd.Series,
    history_days: float,
) -> DetectionParameters:
    """当历史不少于30天时，用全历史、固定网格选择稳健参数。"""
    default = DetectionParameters(
        relative=MIN_RELATIVE_CHANGE,
        strong_relative=STRONG_RELATIVE_CHANGE,
        multiple=MIN_FLUCTUATION_MULTIPLE,
        strong_multiple=STRONG_FLUCTUATION_MULTIPLE,
        merge_hours=CHANGE_MERGE_HOURS,
        adaptive=False,
    )
    if not USE_ADAPTIVE_PARAMETERS or history_days < MIN_HISTORY_DAYS_FOR_ADAPTIVE:
        table = rule_arrays(evidence, default, weights)
        peaks = cluster_candidate_positions(table, default.merge_hours)
        default.score = parameter_score(peaks, table, composite, history_days)
        return default

    best: DetectionParameters | None = None
    for relative in [0.03, 0.05, 0.07, 0.10]:
        for multiple in [2.5, 3.0, 4.0, 5.0]:
            for merge_hours in [3.0, 6.0, 9.0]:
                params = DetectionParameters(
                    relative=relative,
                    strong_relative=max(0.10, relative * 2),
                    multiple=multiple,
                    strong_multiple=max(5.0, multiple + 2),
                    merge_hours=merge_hours,
                    adaptive=True,
                )
                table = rule_arrays(evidence, params, weights)
                peaks = cluster_candidate_positions(table, merge_hours)
                params.score = parameter_score(peaks, table, composite, history_days)
                if best is None or params.score > best.score:
                    best = params
    assert best is not None
    return best


def rule_from_scene_flags(flags: dict[str, bool], strong_flags: dict[str, bool]) -> bool:
    """对某一时刻的逐场景偏离应用规则C，不让D—G重复计票。"""
    calc = sum(flags.get(scene, False) for scene in CALC_SCENES)
    base = sum(flags.get(scene, False) for scene in BASE_CHANNEL_SCENES)
    combo = sum(flags.get(scene, False) for scene in COMBO_CHANNEL_SCENES)
    calc_strong = sum(strong_flags.get(scene, False) for scene in CALC_SCENES)
    base_strong = sum(strong_flags.get(scene, False) for scene in BASE_CHANNEL_SCENES)
    return (calc >= 3 and base >= 2) or calc_strong >= 3 or (base_strong >= 2 and combo >= 3)


def locate_candidate(
    peak: int,
    data: pd.DataFrame,
    detection: pd.DataFrame,
    evidence: dict[str, pd.DataFrame],
    rule_table: pd.DataFrame,
    params: DetectionParameters,
) -> Candidate:
    """定位最早持续偏离点，并区分突变与渐变。"""
    peak_row = rule_table.iloc[peak]
    support_scenes = [scene for scene in SCENE_COLUMNS if bool(peak_row[f"普通_{scene}"])]
    strong_scenes = [scene for scene in SCENE_COLUMNS if bool(peak_row[f"强_{scene}"])]
    search_start = max(0, peak - BEFORE_WINDOW_HOURS * POINTS_PER_HOUR)
    search_end = min(len(data) - 1, peak + round(params.merge_hours * POINTS_PER_HOUR))
    rolling_short = detection.rolling(
        max(1, BOUNDARY_SUSTAIN_HOURS * POINTS_PER_HOUR), min_periods=2
    ).median()
    point_rule = []
    for position in range(search_start, search_end + 1):
        flags: dict[str, bool] = {}
        strong_flags: dict[str, bool] = {}
        for scene in SCENE_COLUMNS:
            item = evidence[scene].iloc[peak]
            old = item["before"]
            scale = item["scale"]
            value = rolling_short.iloc[position][scene]
            if not np.isfinite(old) or not np.isfinite(scale) or not np.isfinite(value):
                flags[scene] = False
                strong_flags[scene] = False
                continue
            delta = abs(value - old)
            relative = delta / max(abs(old), scale)
            multiple = delta / scale
            flags[scene] = relative >= params.relative and multiple >= params.multiple
            strong_flags[scene] = (
                relative >= params.strong_relative or multiple >= params.strong_multiple
            )
        point_rule.append(rule_from_scene_flags(flags, strong_flags))
    sustain_points = max(1, BOUNDARY_SUSTAIN_HOURS * POINTS_PER_HOUR)
    sustained = pd.Series(point_rule).rolling(sustain_points).sum().ge(sustain_points)
    if sustained.any():
        first_end = int(np.flatnonzero(sustained.to_numpy())[0])
        boundary = search_start + max(0, first_end - sustain_points + 1)
    else:
        boundary = peak

    post_stable_points = max(1, POST_STABLE_HOURS * POINTS_PER_HOUR)
    closeness = pd.DataFrame(index=range(boundary, min(len(data), boundary + 96 + 1)))
    for scene in support_scenes:
        old = evidence[scene].iloc[peak]["before"]
        new = evidence[scene].iloc[peak]["after"]
        scale = evidence[scene].iloc[peak]["scale"]
        tolerance = max(abs(new - old) * 0.25, scale)
        closeness[scene] = (
            rolling_short.loc[closeness.index, scene].sub(new).abs().le(tolerance).to_numpy()
        )
    if closeness.empty or not support_scenes:
        transition_end_position = boundary
    else:
        group_close = closeness.sum(axis=1).ge(max(1, math.ceil(len(support_scenes) * 0.6)))
        stable = group_close.rolling(post_stable_points).sum().ge(post_stable_points)
        if stable.any():
            first_stable_end = int(np.flatnonzero(stable.to_numpy())[0])
            transition_end_position = int(
                closeness.index[max(0, first_stable_end - post_stable_points + 1)]
            )
        else:
            transition_end_position = min(len(data) - 1, boundary + 96)
    duration_hours = max(
        0.0,
        (data.at[transition_end_position, "时间"] - data.at[boundary, "时间"]).total_seconds()
        / 3600,
    )
    change_form = "突变" if duration_hours <= ABRUPT_MAX_TRANSITION_HOURS else "渐变"
    return Candidate(
        peak_position=peak,
        boundary_position=boundary,
        score=float(peak_row["score"]),
        rule_type=str(peak_row["rule_type"]),
        calc_count=int(peak_row["calc_count"]),
        base_count=int(peak_row["base_count"]),
        combo_count=int(peak_row["combo_count"]),
        support_scenes=support_scenes,
        strong_scenes=strong_scenes,
        transition_start=data.at[boundary, "时间"],
        transition_end=data.at[transition_end_position, "时间"],
        change_form=change_form,
    )


def estimate_deviation_duration(
    candidate: Candidate,
    detection: pd.DataFrame,
    evidence: dict[str, pd.DataFrame],
    params: DetectionParameters,
) -> float | None:
    """判断新水平是否在48小时内返回旧水平，用于短事件分类。"""
    start = candidate.boundary_position
    end = min(
        len(detection) - 1,
        start + round(SUSPECTED_CONDITION_MAX_HOURS * POINTS_PER_HOUR),
    )
    rolling = detection.rolling(POINTS_PER_HOUR, min_periods=2).median()
    deviated = []
    for position in range(start, end + 1):
        flags: dict[str, bool] = {}
        strong_flags: dict[str, bool] = {}
        for scene in SCENE_COLUMNS:
            old = evidence[scene].iloc[candidate.peak_position]["before"]
            scale = evidence[scene].iloc[candidate.peak_position]["scale"]
            value = rolling.iloc[position][scene]
            if not np.isfinite(old) or not np.isfinite(scale) or not np.isfinite(value):
                flags[scene] = False
                strong_flags[scene] = False
                continue
            delta = abs(value - old)
            relative = delta / max(abs(old), scale)
            multiple = delta / scale
            flags[scene] = relative >= params.relative and multiple >= params.multiple
            strong_flags[scene] = (
                relative >= params.strong_relative or multiple >= params.strong_multiple
            )
        deviated.append(rule_from_scene_flags(flags, strong_flags))
    recovery_points = 4 * POINTS_PER_HOUR
    recovered = (~pd.Series(deviated)).rolling(recovery_points).sum().ge(recovery_points)
    valid_recoveries = np.flatnonzero(recovered.to_numpy())
    if valid_recoveries.size == 0:
        return None
    recovery_end = int(valid_recoveries[0])
    recovery_start = max(0, recovery_end - recovery_points + 1)
    return recovery_start / POINTS_PER_HOUR


def apply_short_events(
    labels: pd.Series,
    candidates: list[Candidate],
    data: pd.DataFrame,
) -> pd.Series:
    """把24小时内返回的变化标为短时异常，24—48小时标为疑似短工况。"""
    updated = labels.copy()
    for candidate in candidates:
        duration = candidate.deviation_duration_hours
        if duration is None or duration < SHORT_ANOMALY_MIN_HOURS:
            continue
        if duration < SHORT_EVENT_HOURS:
            event_type = "短时异常"
        elif duration < SUSPECTED_CONDITION_MAX_HOURS:
            event_type = "疑似短工况"
        else:
            continue
        start = candidate.boundary_position
        end = min(len(data) - 1, start + max(0, round(duration * POINTS_PER_HOUR) - 1))
        replace = updated.iloc[start : end + 1].eq("")
        updated.iloc[start : end + 1] = np.where(
            replace, event_type, updated.iloc[start : end + 1]
        )
    return updated


def merge_intermittent_partial_missing(labels: pd.Series) -> pd.Series:
    """保留逐点标签；间歇性合并只在事件编号和事件汇总层执行。"""
    return labels.copy()


def add_recovery_status(labels: pd.Series) -> pd.Series:
    """在全空、零值或疑似停窑结束后标记前48小时恢复待确认。"""
    updated = labels.copy()
    recovery_points = MIN_CONDITION_HOURS * POINTS_PER_HOUR
    blocking_types = {
        "全空事件（原因需后续结合秒级或生产数据判断）",
        "零值事件",
        "疑似停窑",
    }
    confirmed_blocking_runs = blocking_runs(labels)
    for run_index, (_, end) in enumerate(confirmed_blocking_runs):
        start = end + 1
        stop = min(len(labels), start + recovery_points)
        if run_index + 1 < len(confirmed_blocking_runs):
            stop = min(stop, confirmed_blocking_runs[run_index + 1][0])
        if start >= len(labels):
            continue
        # 只填充原本没有事件的时间点，保留逐15分钟全空、部分缺失等原始事件标签。
        empty = updated.iloc[start:stop].eq("")
        updated.iloc[start:stop] = np.where(
            empty, "恢复后待确认", updated.iloc[start:stop]
        )
    return updated


def make_events(labels: pd.Series) -> tuple[list[Event], pd.Series]:
    """在汇总层合并短时全空/部分缺失交替，逐15分钟标签保持不变。"""
    full_empty_type = "全空事件（原因需后续结合秒级或生产数据判断）"
    missing_types = {full_empty_type, "部分缺失"}
    forbidden_between = {"零值事件", "疑似停窑", "短时异常", "疑似短工况"}
    blocking_points = max(1, round(SHUTDOWN_MIN_HOURS * POINTS_PER_HOUR))
    max_gap = max(1, round(EVENT_MERGE_GAP_HOURS * POINTS_PER_HOUR))
    event_ids = pd.Series("", index=labels.index, dtype=object)

    # 先提取所有逐类型连续子事件。
    atomic_runs: list[tuple[str, int, int]] = []
    for event_type in (value for value in pd.unique(labels) if value):
        atomic_runs.extend(
            (event_type, start, end)
            for start, end in contiguous_runs(labels.eq(event_type))
        )
    atomic_runs.sort(key=lambda item: (item[1], item[2]))

    # 连续全空达到1小时属于正式阻断，必须作为独立事件保留。
    standalone_runs: list[tuple[str, int, int]] = []
    mergeable_missing_runs: list[tuple[str, int, int]] = []
    for event_type, start, end in atomic_runs:
        is_long_full_empty = (
            event_type == full_empty_type and end - start + 1 >= blocking_points
        )
        if event_type in missing_types and not is_long_full_empty:
            mergeable_missing_runs.append((event_type, start, end))
        else:
            standalone_runs.append((event_type, start, end))

    raw_events: list[Event] = [
        Event("", event_type, start, end, [(event_type, start, end)], False)
        for event_type, start, end in standalone_runs
    ]

    # 短时全空与部分缺失可跨不超过3小时的清洁间隔合并。
    if mergeable_missing_runs:
        cluster = [mergeable_missing_runs[0]]
        clusters: list[list[tuple[str, int, int]]] = []
        for current in mergeable_missing_runs[1:]:
            previous = cluster[-1]
            gap_start = previous[2] + 1
            gap_end = current[1] - 1
            gap_length = max(0, gap_end - gap_start + 1)
            between = labels.iloc[gap_start : gap_end + 1] if gap_length else pd.Series(dtype=object)
            contains_forbidden = bool(between.isin(forbidden_between).any()) if gap_length else False
            contains_long_full_empty = any(
                event_type == full_empty_type
                and end - start + 1 >= blocking_points
                and not (end < gap_start or start > gap_end)
                for event_type, start, end in standalone_runs
            )
            if gap_length <= max_gap and not contains_forbidden and not contains_long_full_empty:
                cluster.append(current)
            else:
                clusters.append(cluster)
                cluster = [current]
        clusters.append(cluster)

        for members in clusters:
            start = members[0][1]
            end = members[-1][2]
            event_types = {item[0] for item in members}
            intermittent = len(members) > 1
            if intermittent:
                event_type = "间歇性数据缺失事件"
            else:
                event_type = next(iter(event_types))
            raw_events.append(
                Event("", event_type, start, end, members, intermittent)
            )

    events = sorted(raw_events, key=lambda item: (item.start_position, item.end_position))
    for counter, event in enumerate(events, start=1):
        event.event_id = f"事件{counter:03d}"
        for _, start, end in event.member_runs:
            event_ids.iloc[start : end + 1] = event.event_id
    return events, event_ids


def blocking_runs(labels: pd.Series) -> list[tuple[int, int]]:
    """返回足以切断连续工况的全空、零值和疑似停窑区间。"""
    blocking_types = {
        "全空事件（原因需后续结合秒级或生产数据判断）",
        "零值事件",
        "疑似停窑",
    }
    raw = labels.isin(blocking_types)
    minimum = max(1, round(SHUTDOWN_MIN_HOURS * POINTS_PER_HOUR))
    runs = []
    for start, end in contiguous_runs(raw):
        if end - start + 1 >= minimum:
            runs.append((start, end))
    return runs


def operational_blocks(length: int, blocked: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """由阻断事件切出可形成正式工况的连续运行区间。"""
    blocks = []
    cursor = 0
    for start, end in blocked:
        if cursor <= start - 1:
            blocks.append((cursor, start - 1))
        cursor = end + 1
    if cursor <= length - 1:
        blocks.append((cursor, length - 1))
    minimum_points = MIN_CONDITION_HOURS * POINTS_PER_HOUR
    return [(start, end) for start, end in blocks if end - start + 1 >= minimum_points]


def filter_formal_candidates(
    candidates: list[Candidate],
    blocks: list[tuple[int, int]],
    labels: pd.Series,
) -> list[Candidate]:
    """通过48小时持续性、段间距和事件隔离验证正式变化点。"""
    minimum = MIN_CONDITION_HOURS * POINTS_PER_HOUR
    accepted: list[Candidate] = []
    for block_start, block_end in blocks:
        in_block = [
            candidate
            for candidate in candidates
            if block_start + minimum <= candidate.boundary_position <= block_end - minimum
            and not labels.iloc[candidate.boundary_position]
        ]
        in_block.sort(key=lambda item: item.boundary_position)
        selected: list[Candidate] = []
        for candidate in in_block:
            if not selected:
                selected.append(candidate)
                continue
            if candidate.boundary_position - selected[-1].boundary_position >= minimum:
                selected.append(candidate)
            elif candidate.score > selected[-1].score:
                selected[-1] = candidate
        # 最后再次保证每个相邻段和尾段至少48小时。
        valid: list[Candidate] = []
        previous = block_start
        for candidate in selected:
            if candidate.boundary_position - previous >= minimum:
                valid.append(candidate)
                previous = candidate.boundary_position
        while valid and block_end - valid[-1].boundary_position + 1 < minimum:
            valid.pop()
        accepted.extend(valid)
    return sorted(accepted, key=lambda item: item.boundary_position)


def create_conditions(
    blocks: list[tuple[int, int]], candidates: list[Candidate]
) -> list[Condition]:
    """每个阻断事件后的连续区间重新编号，即使水平回到以前也不合并。"""
    conditions: list[Condition] = []
    counter = 1
    for block_index, (block_start, block_end) in enumerate(blocks):
        block_candidates = [
            candidate
            for candidate in candidates
            if block_start < candidate.boundary_position <= block_end
        ]
        starts = [block_start, *[candidate.boundary_position for candidate in block_candidates]]
        boundary_by_start = {candidate.boundary_position: candidate for candidate in block_candidates}
        for index, start in enumerate(starts):
            end = starts[index + 1] - 1 if index + 1 < len(starts) else block_end
            candidate = boundary_by_start.get(start)
            if start == block_start:
                reason = "数据起点建立首个连续工况" if block_index == 0 else "阻断事件后恢复并重新建立工况"
            else:
                reason = "规则C、持续性和工况内稳定性验证通过"
            conditions.append(
                Condition(
                    condition_id=f"工况{counter:02d}",
                    start_position=start,
                    end_position=end,
                    boundary_candidate=candidate,
                    start_reason=reason,
                )
            )
            counter += 1
    return conditions


def direction_text(old: float, new: float) -> str:
    """以2%或稳健极小尺度判断上升、下降或基本不变。"""
    if not np.isfinite(old) or not np.isfinite(new):
        return "数据不足"
    relative = (new - old) / max(abs(old), 1e-9)
    if relative > 0.02:
        return "上升"
    if relative < -0.02:
        return "下降"
    return "基本不变"


def group_direction(previous: pd.DataFrame, current: pd.DataFrame, scenes: list[str]) -> str:
    """比较两个工况的场景组中位数方向。"""
    directions = [
        direction_text(float(previous[scene].median()), float(current[scene].median()))
        for scene in scenes
    ]
    up = directions.count("上升")
    down = directions.count("下降")
    if up > down and up >= math.ceil(len(scenes) / 2):
        return "上升"
    if down > up and down >= math.ceil(len(scenes) / 2):
        return "下降"
    return "基本不变"


def boundary_stability(
    formal_candidates: list[Candidate],
    evidence: dict[str, pd.DataFrame],
    weights: dict[str, float],
    params: DetectionParameters,
) -> dict[int, tuple[int, str]]:
    """固定随机种子下轻微扰动阈值，记录20次重复检测匹配次数和时间范围。"""
    rng = np.random.default_rng(RANDOM_SEED)
    matches: dict[int, list[int]] = {candidate.boundary_position: [] for candidate in formal_candidates}
    for _ in range(20):
        relative = params.relative * float(rng.uniform(0.95, 1.05))
        multiple = params.multiple * float(rng.uniform(0.95, 1.05))
        perturbed = DetectionParameters(
            relative=relative,
            strong_relative=max(params.strong_relative, relative * 1.8),
            multiple=multiple,
            strong_multiple=max(params.strong_multiple, multiple + 1.5),
            merge_hours=params.merge_hours,
            adaptive=params.adaptive,
        )
        table = rule_arrays(evidence, perturbed, weights)
        peaks = cluster_candidate_positions(table, perturbed.merge_hours)
        for candidate in formal_candidates:
            nearby = [
                peak
                for peak in peaks
                if abs(peak - candidate.peak_position)
                <= round(params.merge_hours * POINTS_PER_HOUR)
            ]
            if nearby:
                closest = min(nearby, key=lambda peak: abs(peak - candidate.peak_position))
                matches[candidate.boundary_position].append(closest - candidate.peak_position)
    result = {}
    for boundary, offsets in matches.items():
        if offsets:
            minimum_minutes = min(offsets) * TIME_FREQUENCY_MINUTES
            maximum_minutes = max(offsets) * TIME_FREQUENCY_MINUTES
            range_text = f"{minimum_minutes:+d}至{maximum_minutes:+d}分钟"
        else:
            range_text = "无重复匹配"
        result[boundary] = (len(offsets), range_text)
    return result


def assign_condition_columns(
    data: pd.DataFrame,
    labels: pd.Series,
    event_ids: pd.Series,
    conditions: list[Condition],
) -> pd.DataFrame:
    """在完整时间轴上写入事件、工况和基准使用标识。"""
    output = data.copy()
    output["事件编号"] = event_ids
    output["事件类型"] = labels
    output["工况编号"] = ""
    for condition in conditions:
        output.loc[condition.start_position : condition.end_position, "工况编号"] = (
            condition.condition_id
        )
    output["工况状态"] = np.where(
        output["事件类型"].ne(""),
        output["事件类型"],
        np.where(output["工况编号"].ne(""), "正式工况", ""),
    )
    output["是否用于工况基准计算"] = (
        output["工况编号"].ne("")
        & output["事件类型"].eq("")
        & output[SCENE_COLUMNS].notna().all(axis=1)
    )
    columns = [
        "时间",
        *SCENE_COLUMNS,
        "数据状态",
        "事件编号",
        "事件类型",
        "工况编号",
        "工况状态",
        "是否用于工况基准计算",
        "来源文件",
    ]
    return output[columns]


def condition_summary(
    all_data: pd.DataFrame,
    conditions: list[Condition],
    events: list[Event],
) -> pd.DataFrame:
    """汇总每个正式工况的中位数、稳健波动、方向和分段依据。"""
    rows = []
    for index, condition in enumerate(conditions):
        segment = all_data.iloc[condition.start_position : condition.end_position + 1]
        baseline = segment.loc[segment["是否用于工况基准计算"]]
        if baseline.empty:
            baseline = segment
        previous_segment = (
            all_data.iloc[
                conditions[index - 1].start_position : conditions[index - 1].end_position + 1
            ]
            if index > 0
            else pd.DataFrame()
        )
        calc_direction = (
            group_direction(previous_segment, segment, CALC_SCENES)
            if index > 0
            else "首个工况"
        )
        channel_direction = (
            group_direction(previous_segment, segment, BASE_CHANNEL_SCENES)
            if index > 0
            else "首个工况"
        )
        if index == 0:
            overall_direction = "首个工况"
        elif calc_direction != channel_direction and {
            calc_direction,
            channel_direction,
        } == {"上升", "下降"}:
            overall_direction = (
                f"核算场景组{calc_direction}，声道监测场景组{channel_direction}（方向不一致）"
            )
        elif calc_direction == channel_direction:
            overall_direction = calc_direction
        else:
            overall_direction = f"核算场景组{calc_direction}，声道监测场景组{channel_direction}"

        candidate = condition.boundary_candidate
        if index == 0:
            boundary_source = "数据起点"
        elif candidate is not None:
            boundary_source = "自动变化点"
        else:
            boundary_source = "事件后重建"
        event_types = sorted(set(segment.loc[segment["事件类型"].ne(""), "事件类型"]))
        start_time = segment["时间"].iloc[0]
        end_time = segment["时间"].iloc[-1]
        duration_hours = (end_time - start_time).total_seconds() / 3600 + 0.25
        row: dict[str, object] = {
            "工况编号": condition.condition_id,
            "边界来源": boundary_source,
            "开始时间": start_time,
            "结束时间": end_time,
            "持续小时数": duration_hours,
            "持续天数": duration_hours / 24,
            "数据点数量": len(segment),
            "数据完整率": float(segment[SCENE_COLUMNS].notna().sum().sum() / (len(segment) * 11)),
            "变化形式": candidate.change_form if candidate else boundary_source,
            "过渡开始时间": candidate.transition_start if candidate else pd.NaT,
            "过渡结束时间": candidate.transition_end if candidate else pd.NaT,
            "过渡持续小时数": (
                (candidate.transition_end - candidate.transition_start).total_seconds() / 3600
                if candidate
                else np.nan
            ),
            "与上一工况相比的总体变化方向": overall_direction,
            "核算场景组变化方向": calc_direction,
            "声道场景组变化方向": channel_direction,
        }
        for scene in SCENE_COLUMNS:
            row[f"{scene}中位数"] = float(baseline[scene].median())
        for scene in SCENE_COLUMNS:
            row[f"{scene}稳健波动"] = robust_mad(baseline[scene])
        row.update(
            {
                "核算场景支持数": candidate.calc_count if candidate else np.nan,
                "基础声道支持数": candidate.base_count if candidate else np.nan,
                "组合声道支持数": candidate.combo_count if candidate else np.nan,
                "命中的规则类型": candidate.rule_type if candidate else "",
                "主要变化场景": (
                    "、".join(candidate.strong_scenes or candidate.support_scenes)
                    if candidate
                    else ""
                ),
                "自动分段说明": (
                    f"{candidate.rule_type}；支持场景{'、'.join(candidate.support_scenes)}；"
                    f"变化后持续不少于{MIN_CONDITION_HOURS}小时；"
                    f"最终边界定位为最早持续偏离点"
                    if candidate
                    else condition.start_reason
                ),
                "是否包含事件": "是" if event_types else "否",
                "事件类型": "；".join(event_types),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def evidence_rows(
    all_data: pd.DataFrame,
    conditions: list[Condition],
    evidence: dict[str, pd.DataFrame],
    params: DetectionParameters,
    stability: dict[int, tuple[int, str]],
) -> pd.DataFrame:
    """仅为算法自动检测到的正式边界输出逐场景变化依据。"""
    rows = []
    boundary_number = 1
    for index, condition in enumerate(conditions[1:], start=1):
        boundary = condition.start_position
        candidate = condition.boundary_candidate
        if candidate is None:
            continue
        previous_condition = conditions[index - 1]
        repeat_count, fluctuation_range = stability.get(boundary, (0, "无重复匹配"))
        for scene in SCENE_COLUMNS:
            item = evidence[scene].iloc[candidate.peak_position]
            before_value = float(item["before"]) if np.isfinite(item["before"]) else np.nan
            after_value = float(item["after"]) if np.isfinite(item["after"]) else np.nan
            old_iqr = float(item["old_iqr"]) if np.isfinite(item["old_iqr"]) else np.nan
            scale = float(item["scale"]) if np.isfinite(item["scale"]) else np.nan
            absolute = after_value - before_value
            relative = abs(absolute) / max(abs(before_value), scale, 1e-9)
            multiple = abs(absolute) / max(scale, 1e-9)
            normal = scene in candidate.support_scenes
            strong = scene in candidate.strong_scenes

            if not np.isfinite(before_value) or not np.isfinite(after_value):
                role = "数据不足"
            elif strong and scene in CALC_SCENES + BASE_CHANNEL_SCENES:
                role = "主要支持"
            elif normal and scene in COMBO_CHANNEL_SCENES:
                role = "辅助验证"
            elif normal:
                role = "普通支持"
            else:
                role = "不支持"
            rows.append(
                {
                    "分界编号": f"分界{boundary_number:02d}",
                    "前一工况": previous_condition.condition_id,
                    "后一工况": condition.condition_id,
                    "分界时间": all_data.at[boundary, "时间"],
                    "场景": scene,
                    "变化前中位数": before_value,
                    "变化后中位数": after_value,
                    "绝对变化": absolute,
                    "相对变化百分比": relative,
                    "旧状态MAD": scale,
                    "旧状态IQR": old_iqr,
                    "变化倍数": multiple,
                    "变化方向": direction_text(before_value, after_value),
                    "是否达到普通变化标准": "是" if normal else "否",
                    "是否达到强变化标准": "是" if strong else "否",
                    "是否支持分段": "是" if normal else "否",
                    "所属变量组": GROUP_BY_SCENE[scene],
                    "在该分界中的作用": role,
                    "变化后持续时间": (
                        f"{(condition.end_position - condition.start_position + 1) / POINTS_PER_HOUR:.2f}小时"
                    ),
                    "分界稳定重复次数": f"{repeat_count}/20",
                    "分界时间波动范围": fluctuation_range,
                }
            )
        boundary_number += 1
    columns = [
        "分界编号",
        "前一工况",
        "后一工况",
        "分界时间",
        "场景",
        "变化前中位数",
        "变化后中位数",
        "绝对变化",
        "相对变化百分比",
        "旧状态MAD",
        "旧状态IQR",
        "变化倍数",
        "变化方向",
        "是否达到普通变化标准",
        "是否达到强变化标准",
        "是否支持分段",
        "所属变量组",
        "在该分界中的作用",
        "变化后持续时间",
        "分界稳定重复次数",
        "分界时间波动范围",
    ]
    return pd.DataFrame(rows, columns=columns)


def event_summary(
    all_data: pd.DataFrame,
    events: list[Event],
    conditions: list[Condition],
    near_zero_thresholds: dict[str, float],
) -> pd.DataFrame:
    """汇总事件，并记录间歇性缺失的子事件组成和阻断影响。"""
    rows = []
    blocked = blocking_runs(all_data["事件类型"])
    rebuild_starts = {
        condition.start_position
        for condition in conditions[1:]
        if condition.boundary_candidate is None
        and "阻断事件后" in condition.start_reason
    }
    for event in events:
        interval = all_data.iloc[event.start_position : event.end_position + 1]
        segment = all_data.loc[all_data["事件编号"].eq(event.event_id)]
        start = interval["时间"].iloc[0]
        end = interval["时间"].iloc[-1]
        duration = (end - start).total_seconds() / 3600 + 0.25
        full_empty_runs = [
            (run_start, run_end)
            for event_type, run_start, run_end in event.member_runs
            if event_type.startswith("全空事件")
        ]
        partial_runs = [
            (run_start, run_end)
            for event_type, run_start, run_end in event.member_runs
            if event_type == "部分缺失"
        ]
        full_empty_points = sum(run_end - run_start + 1 for run_start, run_end in full_empty_runs)
        partial_points = sum(run_end - run_start + 1 for run_start, run_end in partial_runs)
        longest_full_empty_hours = (
            max(run_end - run_start + 1 for run_start, run_end in full_empty_runs)
            / POINTS_PER_HOUR
            if full_empty_runs
            else 0.0
        )
        affected_hours = len(segment) / POINTS_PER_HOUR
        overlapping_blocked = [
            (block_start, block_end)
            for block_start, block_end in blocked
            if any(
                not (run_end < block_start or run_start > block_end)
                for _, run_start, run_end in event.member_runs
            )
        ]
        cuts_condition = bool(overlapping_blocked)
        causes_rebuild = any(
            block_end + 1 in rebuild_starts for _, block_end in overlapping_blocked
        )
        all_empty = bool(segment[SCENE_COLUMNS].isna().all(axis=1).all())
        near_zero = pd.DataFrame(
            {
                scene: segment[scene].notna()
                & segment[scene].abs().le(near_zero_thresholds[scene])
                for scene in SCENE_COLUMNS
            }
        )
        all_zero = bool(
            (segment[SCENE_COLUMNS].notna().all(axis=1) & near_zero.all(axis=1)).all()
        )
        if event.event_type == "间歇性数据缺失事件":
            performance = (
                f"全空{full_empty_points}个15分钟点、部分缺失"
                f"{partial_points}个15分钟点，在{duration:.2f}小时区间内反复出现"
            )
            explanation = (
                "短时全空与部分缺失在合并窗口内交替出现，仅在事件编号和汇总层合并；"
                "逐15分钟原始标签保持不变"
            )
        elif event.event_type.startswith("全空事件"):
            performance = "11个场景连续全部为空"
            explanation = "全空事件（原因需后续结合秒级或生产数据判断）"
        elif event.event_type == "部分缺失":
            intermittent = len(segment) < len(interval)
            performance = (
                "区间内部分场景周期性或间歇性为空，其他场景仍有值"
                if intermittent
                else "部分场景连续为空，其他场景仍有值"
            )
            explanation = "部分场景缺失；该区间不用于正常工况基准学习"
        elif event.event_type == "疑似停窑":
            performance = "至少两个基础声道低于局部基准20%，且核算场景整体低于30%"
            explanation = "满足第一阶段疑似停窑低值规则，真实原因待后续物理数据验证"
        elif event.event_type == "零值事件":
            performance = "11个场景全部为0或低于各自自适应近零阈值"
            explanation = "连续近零事件；不直接断言真实物理原因"
        elif event.event_type == "恢复后待确认":
            performance = "阻断事件结束后数据恢复，尚处于48小时持续性验证窗口"
            explanation = "达到48小时持续性后，按新的连续工况编号回溯建立"
        else:
            performance = f"多场景形成持续{duration:.2f}小时的临时偏离"
            explanation = (
                "偏离后返回旧水平或接近旧水平，未作为正式工况"
                if event.event_type == "短时异常"
                else "新水平持续24—48小时，未达到正式工况48小时约束"
            )
        rows.append(
            {
                "事件编号": event.event_id,
                "开始时间": start,
                "结束时间": end,
                "持续小时数": duration,
                "自动事件类型": event.event_type,
                "子事件次数": len(event.member_runs),
                "全空时间点数量": full_empty_points,
                "部分缺失时间点数量": partial_points,
                "总受影响时间": affected_hours,
                "最长连续全空时长": longest_full_empty_hours,
                "是否属于间歇性数据缺失": "是" if event.is_intermittent_missing else "否",
                "是否切断正式工况": "是" if cuts_condition else "否",
                "是否导致事件后重新建立工况": "是" if causes_rebuild else "否",
                "数据表现": performance,
                "场景1—4有效数": int(segment[CALC_SCENES].notna().sum().sum()),
                "A—C有效数": int(segment[BASE_CHANNEL_SCENES].notna().sum().sum()),
                "D—G有效数": int(segment[COMBO_CHANNEL_SCENES].notna().sum().sum()),
                "是否全部为空": "是" if all_empty else "否",
                "是否全部近零": "是" if all_zero else "否",
                "是否满足疑似停窑低值规则": "是" if event.event_type == "疑似停窑" else "否",
                "自动说明": explanation,
            }
        )
    return pd.DataFrame(rows)


def model_parameter_table(
    data: pd.DataFrame,
    params: DetectionParameters,
    history_days: float,
    valid_points: int,
    conditions: list[Condition],
    events: list[Event],
    reliability: pd.DataFrame,
    baseline_mask: pd.Series,
) -> pd.DataFrame:
    """记录默认值、本次值、自适应依据、场景权重和稳健统计。"""
    adaptive_note = (
        "有效历史达到30天，基于全部历史进行固定网格搜索"
        if params.adaptive
        else "历史数据不足或自适应关闭，使用默认参数"
    )
    rows = [
        ["BEFORE_WINDOW_HOURS", BEFORE_WINDOW_HOURS, BEFORE_WINDOW_HOURS, "否", "业务定义", "固定", "变化前窗口"],
        ["AFTER_WINDOW_HOURS", AFTER_WINDOW_HOURS, AFTER_WINDOW_HOURS, "否", "业务定义", "固定", "变化后窗口"],
        ["MIN_CONDITION_HOURS", MIN_CONDITION_HOURS, MIN_CONDITION_HOURS, "否", "强领域约束", "固定48小时", "机器不得自由降低"],
        ["CHANGE_MERGE_HOURS", CHANGE_MERGE_HOURS, params.merge_hours, "是" if params.adaptive else "否", adaptive_note, "3—9小时", "相近场景变化合并"],
        ["SHORT_EVENT_HOURS", SHORT_EVENT_HOURS, SHORT_EVENT_HOURS, "否", "业务定义", "固定", "不足24小时作为短时事件"],
        ["SUSPECTED_CONDITION_MAX_HOURS", SUSPECTED_CONDITION_MAX_HOURS, SUSPECTED_CONDITION_MAX_HOURS, "否", "业务定义", "固定", "24—48小时疑似短工况"],
        ["SHUTDOWN_MIN_HOURS", SHUTDOWN_MIN_HOURS, SHUTDOWN_MIN_HOURS, "否", "业务定义", "固定", "疑似停窑最短持续"],
        ["EVENT_MERGE_GAP_HOURS", EVENT_MERGE_GAP_HOURS, EVENT_MERGE_GAP_HOURS, "否", "事件汇总展示规则", "固定3小时", "仅合并短时全空与部分缺失交替，不改变逐15分钟标签"],
        ["MIN_RELATIVE_CHANGE", MIN_RELATIVE_CHANGE, params.relative, "是" if params.adaptive else "否", adaptive_note, "3%—10%", "普通相对变化阈值"],
        ["STRONG_RELATIVE_CHANGE", STRONG_RELATIVE_CHANGE, params.strong_relative, "是" if params.adaptive else "否", "始终高于普通阈值", "不低于10%", "强变化相对阈值"],
        ["MIN_FLUCTUATION_MULTIPLE", MIN_FLUCTUATION_MULTIPLE, params.multiple, "是" if params.adaptive else "否", adaptive_note, "2.5—5倍", "普通变化倍数"],
        ["STRONG_FLUCTUATION_MULTIPLE", STRONG_FLUCTUATION_MULTIPLE, params.strong_multiple, "是" if params.adaptive else "否", "始终高于普通倍数", "不低于5倍", "强变化倍数"],
        ["RANDOM_SEED", RANDOM_SEED, RANDOM_SEED, "否", "确保重复运行一致", "固定", "稳定性扰动检测随机种子"],
        ["参与分析的日期范围", "", f"{data['时间'].min():%Y-%m-%d %H:%M} 至 {data['时间'].max():%Y-%m-%d %H:%M}", "否", "输入完整时间轴", "", ""],
        ["有效历史天数", "", history_days, "否", "至少一个场景有效且非事件的日期数", "", ""],
        ["参与分析的数据点数", "", valid_points, "否", "非事件有效数据点", "", ""],
        ["正式工况数量", "", len(conditions), "否", "本次自动划分结果", "", ""],
        ["事件数量", "", len(events), "否", "连续事件区间数", "", ""],
        ["自适应参数是否启用", USE_ADAPTIVE_PARAMETERS, params.adaptive, "否", adaptive_note, "", ""],
        ["参数搜索综合评分", "", params.score, "是" if params.adaptive else "否", "段内稳健离散度、段间分离、多场景支持及碎片惩罚", "", "不以切出更多工况为目标"],
        ["候选变化检测方法", "", "稳健滑动窗口多变量检测", "否", "ruptures不存在时的可解释后备方案", "", ""],
    ]
    for _, item in reliability.iterrows():
        scene = item["场景"]
        normal_values = data.loc[baseline_mask, scene]
        rows.extend(
            [
                [f"{scene}_可靠性权重", "", item["可靠性权重"], "是", item["权重依据"], "组合声道组总权重≤0.15", GROUP_BY_SCENE[scene]],
                [f"{scene}_正常MAD", "", robust_mad(normal_values), "是", "全部非事件基准数据稳健统计", "≥最小尺度", ""],
                [f"{scene}_正常IQR", "", robust_iqr(normal_values), "是", "全部非事件基准数据稳健统计", "≥0", ""],
                [f"{scene}_数据完整率", "", float(data[scene].notna().mean()), "是", "全部历史有效值比例", "0—1", ""],
                [f"{scene}_原始字段映射", "", SOURCE_FIELDS[scene], "否", "01脚本精确字段映射", "固定映射", ""],
            ]
        )
    return pd.DataFrame(
        rows,
        columns=["参数名称", "默认值", "本次使用值", "是否由历史数据学习", "学习依据", "上下限", "备注"],
    )


def configure_date_axis(axis: plt.Axes, start: pd.Timestamp, end: pd.Timestamp) -> None:
    """按跨度自动选择日期刻度。"""
    days = max((end - start).total_seconds() / 86400, 1)
    if days <= 21:
        locator = mdates.DayLocator(interval=max(1, int(days // 10) or 1))
        formatter = mdates.DateFormatter("%m-%d")
    elif days <= 120:
        locator = mdates.WeekdayLocator(byweekday=mdates.MO, interval=1)
        formatter = mdates.DateFormatter("%m-%d")
    else:
        locator = mdates.MonthLocator()
        formatter = mdates.DateFormatter("%Y-%m")
    axis.xaxis.set_major_locator(locator)
    axis.xaxis.set_major_formatter(formatter)


def plot_conditions(
    all_data: pd.DataFrame,
    conditions: list[Condition],
    events: list[Event],
    output_path: Path,
) -> None:
    """绘制同步子图，以贯穿全图竖线区分自动变化和事件后重建边界。"""
    select_chinese_font()
    span_days = max((all_data["时间"].max() - all_data["时间"].min()).days + 1, 1)
    width = min(PLOT_MAX_WIDTH, max(PLOT_MIN_WIDTH, 17 + span_days / 16))
    figure, axes = plt.subplots(1, 2, figsize=(width, PLOT_HEIGHT), sharex=True)
    colors_left = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd"]
    colors_right = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#17becf"]
    groups = [
        (axes[0], CALC_SCENES, colors_left, "场景1—4自动工况划分"),
        (axes[1], BASE_CHANNEL_SCENES + COMBO_CHANNEL_SCENES, colors_right, "场景A—G自动工况划分"),
    ]
    shade_colors = {
        "全空事件（原因需后续结合秒级或生产数据判断）": "#9e9e9e",
        "零值事件": "#4d4d4d",
        "疑似停窑": "#f39c12",
    }
    boundary_handles = [
        Line2D(
            [0],
            [0],
            color="#111111",
            linestyle="--",
            linewidth=1.6,
            alpha=0.95,
            label="自动变化边界",
        ),
        Line2D(
            [0],
            [0],
            color="#111111",
            linestyle=":",
            linewidth=1.4,
            alpha=0.90,
            label="事件后重建边界",
        ),
    ]
    event_handles = [
        Patch(
            facecolor=color,
            alpha=0.09,
            label=event_type.split("（")[0],
        )
        for event_type, color in shade_colors.items()
    ]

    for group_index, (axis, scenes, colors, title) in enumerate(groups):
        # 最低层：只有会影响连续运行判断的长事件才在半年主图中显示阴影。
        for event in events:
            if event.event_type not in shade_colors:
                continue
            event_points = event.end_position - event.start_position + 1
            if event_points < round(SHUTDOWN_MIN_HOURS * POINTS_PER_HOUR):
                continue
            start = all_data.at[event.start_position, "时间"]
            end = all_data.at[event.end_position, "时间"] + pd.Timedelta(minutes=15)
            axis.axvspan(
                start,
                end,
                color=shade_colors[event.event_type],
                alpha=0.09,
                linewidth=0,
                zorder=1,
            )

        # 原始值直接绘图，NaN保持NaN，从而让缺失区间自然断线。
        for scene, color in zip(scenes, colors):
            axis.plot(
                all_data["时间"],
                all_data[scene],
                linewidth=0.5,
                alpha=0.75,
                color=color,
                label=SCENE_LABELS[scene],
                zorder=3,
            )

        for condition_index, condition in enumerate(conditions):
            start = all_data.at[condition.start_position, "时间"]
            end = all_data.at[condition.end_position, "时间"]
            segment = all_data.iloc[condition.start_position : condition.end_position + 1]
            baseline = segment.loc[segment["是否用于工况基准计算"]]
            for scene, color in zip(scenes, colors):
                median = baseline[scene].median()
                if np.isfinite(median):
                    axis.hlines(
                        median,
                        start,
                        end,
                        colors=color,
                        linestyles=":",
                        linewidth=0.7,
                        alpha=0.60,
                        zorder=5,
                    )

            # 工况编号置于区间中点上部，不再显示拥挤的日期范围。
            midpoint = start + (end - start) / 2
            condition_days = max((end - start).total_seconds() / 86400, 0.0)
            label_y = (
                0.965
                if condition_days >= 7 or condition_index % 2 == 0
                else 0.905
            )
            axis.text(
                midpoint,
                label_y,
                condition.condition_id,
                transform=axis.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=9,
                color="#111111",
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.76, pad=1.8),
                clip_on=True,
                zorder=11,
            )

        # 最高层：除首个数据起点外，所有正式工况边界贯穿整个子图。
        for condition in conditions[1:]:
            boundary_time = all_data.at[condition.start_position, "时间"]
            is_automatic = condition.boundary_candidate is not None
            axis.axvline(
                boundary_time,
                color="#111111",
                linestyle="--" if is_automatic else ":",
                linewidth=1.6 if is_automatic else 1.4,
                alpha=0.95 if is_automatic else 0.90,
                zorder=10,
            )

        axis.set_title(title, fontsize=14, pad=10)
        axis.set_xlabel("日期")
        axis.set_ylabel("碳排放相关结果")
        axis.grid(True, alpha=0.18, linewidth=0.5)
        configure_date_axis(axis, all_data["时间"].min(), all_data["时间"].max())
        axis.tick_params(axis="x", rotation=35)
        axis.margins(x=0.004)

        scene_handles, scene_labels = axis.get_legend_handles_labels()
        scene_legend = axis.legend(
            handles=scene_handles,
            labels=scene_labels,
            loc="lower left" if group_index == 0 else "lower right",
            fontsize=7,
            framealpha=0.88,
            title="场景曲线",
            title_fontsize=7,
        )
        axis.add_artist(scene_legend)
        axis.legend(
            handles=boundary_handles + event_handles,
            loc="upper right",
            bbox_to_anchor=(0.995, 0.875),
            fontsize=7,
            framealpha=0.90,
            title="边界与事件",
            title_fontsize=7,
        )
    figure.suptitle(
        f"海螺水泥15min自动工况划分（{all_data['时间'].min():%Y-%m-%d} 至 {all_data['时间'].max():%Y-%m-%d}）",
        fontsize=16,
        y=0.99,
    )
    figure.tight_layout(rect=(0, 0, 1, 0.965))
    figure.savefig(output_path, dpi=PLOT_DPI, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def format_workbook(path: Path) -> None:
    """统一设置所有工作表的表头、冻结窗格、筛选和可读列宽。"""
    workbook = load_workbook(path)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    percent_headers = {"数据完整率", "相对变化百分比"}
    datetime_headers = {
        "时间",
        "开始时间",
        "结束时间",
        "分界时间",
        "过渡开始时间",
        "过渡结束时间",
    }
    integer_headers = {
        "数据点数量",
        "子事件次数",
        "全空时间点数量",
        "部分缺失时间点数量",
        "场景1—4有效数",
        "A—C有效数",
        "D—G有效数",
    }
    hour_headers = {
        "持续小时数",
        "过渡持续小时数",
        "总受影响时间",
        "最长连续全空时长",
    }
    for worksheet in workbook.worksheets:
        if worksheet.max_row < 1:
            continue
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        headers = {cell.column: str(cell.value) for cell in worksheet[1]}
        for column_index in range(1, worksheet.max_column + 1):
            header = headers[column_index]
            if "说明" in header or "依据" in header or header == "来源文件":
                width = 52
            elif header in datetime_headers:
                width = 20
            elif "场景" in header or "参数" in header:
                width = 18
            else:
                width = min(24, max(12, len(header) * 2 + 2))
            worksheet.column_dimensions[get_column_letter(column_index)].width = width
            for cell in worksheet.iter_cols(
                min_col=column_index,
                max_col=column_index,
                min_row=2,
                max_row=worksheet.max_row,
            ):
                for item in cell:
                    if header in datetime_headers and item.value is not None:
                        item.number_format = "yyyy-mm-dd hh:mm"
                    elif header in percent_headers and item.value is not None:
                        item.number_format = "0.00%"
                    elif header in integer_headers and item.value is not None:
                        item.number_format = "0"
                    elif header in hour_headers and item.value is not None:
                        item.number_format = "0.00"
                    elif isinstance(item.value, float):
                        item.number_format = "0.0000"
                    if "说明" in header or "依据" in header:
                        item.alignment = Alignment(vertical="top", wrap_text=True)
    workbook.save(path)


def write_outputs(
    all_data: pd.DataFrame,
    summaries: dict[str, pd.DataFrame],
    conditions: list[Condition],
) -> None:
    """写入必要工作表及每个正式工况独立工作表。"""
    with pd.ExcelWriter(
        RESULT_XLSX,
        engine="openpyxl",
        datetime_format="yyyy-mm-dd hh:mm",
    ) as writer:
        summaries["工况汇总"].to_excel(writer, sheet_name="工况汇总", index=False)
        all_data.to_excel(writer, sheet_name="全部15min数据", index=False)
        summaries["变化依据"].to_excel(writer, sheet_name="变化依据", index=False)
        summaries["事件汇总"].to_excel(writer, sheet_name="事件汇总", index=False)
        summaries["模型参数"].to_excel(writer, sheet_name="模型参数", index=False)
        condition_columns = [
            "时间",
            *SCENE_COLUMNS,
            "数据状态",
            "工况编号",
            "是否用于工况基准计算",
            "来源文件",
        ]
        for condition in conditions:
            segment = all_data.iloc[
                condition.start_position : condition.end_position + 1
            ][condition_columns]
            segment.to_excel(writer, sheet_name=condition.condition_id, index=False)
    format_workbook(RESULT_XLSX)


def main() -> None:
    """执行事件识别、自适应变化检测、工况划分、Excel与图形输出。"""
    np.random.seed(RANDOM_SEED)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = load_input()
    weights, reliability = scene_reliability_weights(data)
    labels, near_zero_thresholds, initial_masks = initial_event_labels(data)

    # 初始检测排除全空、零值、疑似停窑和部分缺失事件。
    initial_excluded = labels.ne("")
    detection = build_detection_copy(data, initial_excluded)
    evidence, _, composite = prepare_evidence(detection)
    initial_valid = detection.notna().any(axis=1)
    valid_dates = data.loc[initial_valid, "时间"].dt.normalize().nunique()
    history_days = float(valid_dates)
    params = choose_parameters(evidence, weights, composite, history_days)
    rule_table = rule_arrays(evidence, params, weights)
    peaks = cluster_candidate_positions(rule_table, params.merge_hours)
    candidates = [
        locate_candidate(peak, data, detection, evidence, rule_table, params)
        for peak in peaks
    ]
    for candidate in candidates:
        candidate.deviation_duration_hours = estimate_deviation_duration(
            candidate, detection, evidence, params
        )

    # 短事件加入事件层后，重新构建检测副本，避免短事件污染正式工况基准。
    labels = apply_short_events(labels, candidates, data)
    labels = merge_intermittent_partial_missing(labels)
    labels = add_recovery_status(labels)
    final_excluded = labels.ne("")
    detection = build_detection_copy(data, final_excluded)
    evidence, _, composite = prepare_evidence(detection)
    params = choose_parameters(evidence, weights, composite, history_days)
    rule_table = rule_arrays(evidence, params, weights)
    peaks = cluster_candidate_positions(rule_table, params.merge_hours)
    candidates = [
        locate_candidate(peak, data, detection, evidence, rule_table, params)
        for peak in peaks
    ]
    for candidate in candidates:
        candidate.deviation_duration_hours = estimate_deviation_duration(
            candidate, detection, evidence, params
        )

    blocks = operational_blocks(len(data), blocking_runs(labels))
    formal_candidates = filter_formal_candidates(candidates, blocks, labels)
    conditions = create_conditions(blocks, formal_candidates)
    events, event_ids = make_events(labels)
    all_data = assign_condition_columns(data, labels, event_ids, conditions)
    stability = boundary_stability(formal_candidates, evidence, weights, params)
    baseline_mask = all_data["是否用于工况基准计算"]
    valid_points = int(baseline_mask.sum())

    summaries = {
        "工况汇总": condition_summary(all_data, conditions, events),
        "变化依据": evidence_rows(all_data, conditions, evidence, params, stability),
        "事件汇总": event_summary(
            all_data, events, conditions, near_zero_thresholds
        ),
        "模型参数": model_parameter_table(
            data,
            params,
            history_days,
            valid_points,
            conditions,
            events,
            reliability,
            baseline_mask,
        ),
    }
    write_outputs(all_data, summaries, conditions)
    plot_conditions(all_data, conditions, events, CONDITION_PNG)

    print("\n===== 02脚本运行摘要 =====")
    print(
        f"参与分析的时间范围：{data['时间'].min():%Y-%m-%d %H:%M} 至 "
        f"{data['时间'].max():%Y-%m-%d %H:%M}"
    )
    print(f"有效历史天数：{history_days:.0f}")
    print(f"是否启用自适应参数：{'是' if params.adaptive else '否'}")
    print(f"候选变化检测：{'ruptures可用' if importlib.util.find_spec('ruptures') else '稳健滑动窗口后备方案（ruptures未安装）'}")
    print(f"正式工况数量：{len(conditions)}")
    print(f"事件数量：{len(events)}")
    for condition in conditions:
        print(
            f"  {condition.condition_id}："
            f"{data.at[condition.start_position, '时间']:%Y-%m-%d %H:%M} 至 "
            f"{data.at[condition.end_position, '时间']:%Y-%m-%d %H:%M}"
        )
    print(
        "本次主要参数："
        f"普通相对变化{params.relative:.1%}，强相对变化{params.strong_relative:.1%}，"
        f"普通变化倍数{params.multiple:.1f}，强变化倍数{params.strong_multiple:.1f}，"
        f"变化合并窗口{params.merge_hours:.0f}小时，最短正式工况{MIN_CONDITION_HOURS}小时"
    )
    print(f"参数搜索综合评分：{params.score:.4f}")
    print(f"结果Excel：{RESULT_XLSX}")
    print(f"划分图：{CONDITION_PNG}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\n运行失败：{error}", file=sys.stderr)
        raise
