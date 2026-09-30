import calendar
import os
import re
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from utils.date_range_utils import resolve_process_date_range


material_cols = [
    "入磨-A",
    "入磨-B",
    "入窑-A磨入分解炉转子秤累计",
    "入窑-A磨入窑头转子秤累计",
    "入磨煤低位发热量",
    "入窑煤低位发热量",
    "废纺低位发热量",
    "废纺平均消耗量",
    "熟料产量",
    "熟料中CaO含量%",
    "熟料中MgO含量%",
    "过程排放2023",
    "过程排放2024",
    "入磨煤CO2排放_2023",
    "入窑煤CO2排放_2023",
    "入磨煤CO2排放_2024",
    "入窑煤CO2排放_2024",
    "碳排放_2023_入磨",
    "碳排放_2023_入窑",
    "碳排放_2024_入磨",
    "碳排放_2024_入窑",
    "煤矸石CO2排放",
]
material_mul_cols = [
    "入磨-A",
    "入磨-B",
    "入窑-A磨入分解炉转子秤累计",
    "入窑-A磨入窑头转子秤累计",
    "废纺平均消耗量",
    "熟料产量",
    "过程排放2023",
    "过程排放2024",
    "入磨煤CO2排放_2023",
    "入窑煤CO2排放_2023",
    "入磨煤CO2排放_2024",
    "入窑煤CO2排放_2024",
    "碳排放_2023_入磨",
    "碳排放_2023_入窑",
    "碳排放_2024_入磨",
    "碳排放_2024_入窑",
    "煤矸石CO2排放",
]
material_mean_cols = ["入磨煤低位发热量", "入窑煤低位发热量", "废纺低位发热量", "熟料中CaO含量%", "熟料中MgO含量%"]

flue_gas_cols = [
    "湿度",
    "烟气温度",
    "烟气压力",
    "标干流量Path1",
    "标干流量Path2",
    "标干流量Path3",
    "标干流量Path1&3",
    "标干流量Path1&2",
    "标干流量Path1&2&3",
    "标干流量Path2&3",
    "CO2体积浓度",
    "CO2排放速率Path1",
    "CO2排放速率Path2",
    "CO2排放速率Path3",
    "CO2排放速率Path1&3",
    "CO2排放速率Path1&2",
    "CO2排放速率Path2&3",
    "CO2排放速率Path1&2&3",
]
fluegas_mul_cols = [
    "标干流量Path1",
    "标干流量Path2",
    "标干流量Path3",
    "标干流量Path1&3",
    "标干流量Path1&2",
    "标干流量Path1&2&3",
    "标干流量Path2&3",
    "CO2排放速率Path1",
    "CO2排放速率Path2",
    "CO2排放速率Path3",
    "CO2排放速率Path1&3",
    "CO2排放速率Path1&2",
    "CO2排放速率Path2&3",
    "CO2排放速率Path1&2&3",
]
fluegas_mean_cols = ["湿度", "烟气温度", "烟气压力", "CO2体积浓度"]

TIME_COL = "数据时间"
STATUS_COL = "状态"
all_need_cols = material_cols + flue_gas_cols
ADD_COLS = [
    "碳排放_2023_入磨_废纺平均",
    "碳排放_2023_入窑_废纺平均",
    "碳排放_2024_入磨_废纺平均",
    "碳排放_2024_入窑_废纺平均",
    "碳排放_2023_入磨_废纺熟料能耗",
    "碳排放_2023_入窑_废纺熟料能耗",
    "碳排放_2024_入磨_废纺熟料能耗",
    "碳排放_2024_入窑_废纺熟料能耗",
]
CO2_COEF = 0.0917


def _log(logger, message):
    if logger:
        logger(message)
    else:
        print(message)


def second_to_15min_agg(df, time_col, status_col, target_date, source_col_order):
    df = df.copy()
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col])
    df = df.set_index(time_col)

    df["material_valid_flag"] = df[status_col].apply(lambda x: 1 if x in [0, 2] else 0)
    df["fluegas_valid_flag"] = df[status_col].apply(lambda x: 1 if x in [0, 1] else 0)

    fifteen_min_grouper = pd.Grouper(freq="15min", closed="left", label="left")
    valid_threshold = 15 * 60 * 0.75

    agg_valid = df.groupby(fifteen_min_grouper).agg(
        {"material_valid_flag": "sum", "fluegas_valid_flag": "sum", status_col: "count"}
    ).rename(columns={status_col: "total_seconds"})
    agg_valid["material_group_valid"] = agg_valid["material_valid_flag"] >= valid_threshold
    agg_valid["fluegas_group_valid"] = agg_valid["fluegas_valid_flag"] >= valid_threshold

    material_agg_result = pd.DataFrame()
    if material_cols:
        material_valid_df = df[df["material_valid_flag"] == 1]
        material_mul_df = material_valid_df[material_mul_cols].groupby(fifteen_min_grouper).mean() * 900
        material_mean_df = material_valid_df[material_mean_cols].groupby(fifteen_min_grouper).mean()
        material_agg_result = pd.concat([material_mul_df, material_mean_df], axis=1)

    fluegas_agg_result = pd.DataFrame()
    if flue_gas_cols:
        fluegas_valid_df = df[df["fluegas_valid_flag"] == 1]
        fluegas_mul_df = fluegas_valid_df[fluegas_mul_cols].groupby(fifteen_min_grouper).mean() * 900
        fluegas_mean_df = fluegas_valid_df[fluegas_mean_cols].groupby(fifteen_min_grouper).mean()
        fluegas_agg_result = pd.concat([fluegas_mul_df, fluegas_mean_df], axis=1)

    full_time_index = pd.date_range(start=f"{target_date} 00:00:00", end=f"{target_date} 23:45:00", freq="15min")
    final_df = pd.concat([material_agg_result, fluegas_agg_result], axis=1)
    final_df = final_df.reindex(full_time_index)

    material_invalid_mask = ~agg_valid["material_group_valid"].reindex(full_time_index).fillna(False)
    final_df.loc[material_invalid_mask, material_cols] = None
    fluegas_invalid_mask = ~agg_valid["fluegas_group_valid"].reindex(full_time_index).fillna(False)
    final_df.loc[fluegas_invalid_mask, flue_gas_cols] = None

    final_df["碳排放_2023_入磨_废纺平均"] = final_df["碳排放_2023_入磨"] + (final_df["废纺平均消耗量"] * final_df["废纺低位发热量"] * CO2_COEF)
    final_df["碳排放_2023_入窑_废纺平均"] = final_df["碳排放_2023_入窑"] + (final_df["废纺平均消耗量"] * final_df["废纺低位发热量"] * CO2_COEF)
    final_df["碳排放_2024_入磨_废纺平均"] = final_df["碳排放_2024_入磨"] + (final_df["废纺平均消耗量"] * final_df["废纺低位发热量"] * CO2_COEF)
    final_df["碳排放_2024_入窑_废纺平均"] = final_df["碳排放_2024_入窑"] + (final_df["废纺平均消耗量"] * final_df["废纺低位发热量"] * CO2_COEF)

    df_material_day = df[df["material_valid_flag"] == 1]
    day_total_fang_spin = df_material_day["废纺平均消耗量"].sum()
    day_mean_fang_spin_heat = df_material_day["废纺低位发热量"].mean()
    day_total_ru_mo = (df_material_day["入磨-A"] + df_material_day["入磨-B"]).sum()
    day_mean_ru_mo_heat = df_material_day["入磨煤低位发热量"].mean()
    day_total_ru_yao = (df_material_day["入窑-A磨入分解炉转子秤累计"] + df_material_day["入窑-A磨入窑头转子秤累计"]).sum()
    day_mean_ru_yao_heat = df_material_day["入窑煤低位发热量"].mean()
    day_total_shuliao = df_material_day["熟料产量"].sum()

    day_avg_shuliao_energy = (
        (day_total_fang_spin * day_mean_fang_spin_heat + day_total_ru_mo * day_mean_ru_mo_heat) / day_total_shuliao
        if day_total_shuliao > 0
        else 0
    )
    final_df["能源缺口_入磨"] = (final_df["熟料产量"] * day_avg_shuliao_energy) - ((final_df["入磨-A"] + final_df["入磨-B"]) * final_df["入磨煤低位发热量"])
    final_df["有效能源缺口_入磨"] = final_df["能源缺口_入磨"].apply(lambda x: x if x > 0 else 0)
    total_valid_energy_gap_ru_mo = final_df["有效能源缺口_入磨"].sum()
    final_df["废纺消耗量_入磨_熟料能耗"] = np.where(
        total_valid_energy_gap_ru_mo > 0,
        day_total_fang_spin * final_df["有效能源缺口_入磨"] / total_valid_energy_gap_ru_mo,
        0,
    )
    final_df["碳排放_入磨_废纺熟料能耗"] = final_df["废纺消耗量_入磨_熟料能耗"] * final_df["废纺低位发热量"] * CO2_COEF
    final_df["碳排放_2023_入磨_废纺熟料能耗"] = final_df["碳排放_2023_入磨"] + final_df["碳排放_入磨_废纺熟料能耗"]
    final_df["碳排放_2024_入磨_废纺熟料能耗"] = final_df["碳排放_2024_入磨"] + final_df["碳排放_入磨_废纺熟料能耗"]

    day_avg_shuliao_energy = (
        (day_total_fang_spin * day_mean_fang_spin_heat + day_total_ru_yao * day_mean_ru_yao_heat) / day_total_shuliao
        if day_total_shuliao > 0
        else 0
    )
    final_df["能源缺口_入窑"] = (
        final_df["熟料产量"] * day_avg_shuliao_energy
    ) - ((final_df["入窑-A磨入分解炉转子秤累计"] + final_df["入窑-A磨入窑头转子秤累计"]) * final_df["入窑煤低位发热量"])
    final_df["有效能源缺口_入窑"] = final_df["能源缺口_入窑"].apply(lambda x: x if x > 0 else 0)
    total_valid_energy_gap_ru_yao = final_df["有效能源缺口_入窑"].sum()
    final_df["废纺消耗量_入窑_熟料能耗"] = np.where(
        total_valid_energy_gap_ru_yao > 0,
        day_total_fang_spin * final_df["有效能源缺口_入窑"] / total_valid_energy_gap_ru_yao,
        0,
    )
    final_df["碳排放_入窑_废纺熟料能耗"] = final_df["废纺消耗量_入窑_熟料能耗"] * final_df["废纺低位发热量"] * CO2_COEF
    final_df["碳排放_2023_入窑_废纺熟料能耗"] = final_df["碳排放_2023_入窑"] + final_df["碳排放_入窑_废纺熟料能耗"]
    final_df["碳排放_2024_入窑_废纺熟料能耗"] = final_df["碳排放_2024_入窑"] + final_df["碳排放_入窑_废纺熟料能耗"]

    final_df = final_df.reset_index().rename(columns={"index": time_col})
    final_df = final_df[[time_col] + source_col_order + ADD_COLS]
    return final_df


def run_15min_agg(input_folder, output_folder, start_date, end_date, logger=None):
    warnings.filterwarnings("ignore")
    input_path = Path(input_folder).expanduser()
    output_path = Path(output_folder).expanduser()
    if not input_path.exists():
        raise FileNotFoundError(f"秒级核算数据文件夹不存在：{input_path}")
    output_path.mkdir(parents=True, exist_ok=True)

    _log(logger, "[3号] 开始15min聚合...")
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    generated_files = []
    current_dt = start_dt
    while current_dt <= end_dt:
        date_str = current_dt.strftime("%Y-%m-%d")
        input_file_path = input_path / f"{date_str}_秒级CO2排放结果.xlsx"
        output_file_path = output_path / f"{date_str}_15minCO2排放结果.xlsx"

        if input_file_path.exists():
            _log(logger, f"[3号] 正在处理：{date_str}")
            df = pd.read_excel(input_file_path)
            source_col_order = [col for col in df.columns if col in all_need_cols]
            agg_df = second_to_15min_agg(df, TIME_COL, STATUS_COL, target_date=date_str, source_col_order=source_col_order)
            agg_df.to_excel(output_file_path, index=False)
            generated_files.append(str(output_file_path))
            _log(logger, f"[3号] 处理完成：{output_file_path}，共生成{len(agg_df)}行15分钟数据")
        else:
            _log(logger, f"[3号] {date_str} 无对应秒级数据文件，跳过该日期")

        current_dt += timedelta(days=1)

    if not generated_files:
        raise RuntimeError("15min聚合没有生成任何结果，请检查秒级结果文件是否存在。")

    _log(logger, "[3号] 全部日期批量处理完成")
    return {"output_files": generated_files}


def run_step3_15min_aggregate(
    second_result_path: str,
    output_dir: str = "",
    target_month: str = "",
    abnormal_result_path: str = "",
    logger=None,
    process_start_date: str = "",
    process_end_date: str = "",
    result_dir: str = "",
) -> dict:
    """
    运行3号15min数据聚合。

    参数：
        second_result_path: 2号秒级核算结果文件或结果目录
        output_dir: 输出目录
        target_month: 目标月份，格式 YYYY-MM，可为空
        abnormal_result_path: 2号异常检测结果文件或目录，可为空
        logger: 可选日志函数

    返回：
        {
            "success": True/False,
            "message": "...",
            "output_files": ["..."]
        }
    """
    try:
        if not str(second_result_path or "").strip():
            raise ValueError("2号秒级核算结果不能为空")
        if not str(result_dir or "").strip() and not str(output_dir or "").strip():
            raise ValueError("15min结果目录不能为空")

        second_path = Path(second_result_path).expanduser()
        abnormal_path = Path(abnormal_result_path).expanduser() if str(abnormal_result_path or "").strip() else None

        if not second_path.exists():
            raise FileNotFoundError(f"2号秒级核算结果不存在：{second_path}")
        if abnormal_path and not abnormal_path.exists():
            raise FileNotFoundError(f"2号异常检测结果不存在：{abnormal_path}")

        output_folder = (
            Path(result_dir).expanduser()
            if str(result_dir or "").strip()
            else Path(output_dir).expanduser() / "3号15min聚合结果"
        )
        if second_path.is_file():
            output_folder.mkdir(parents=True, exist_ok=True)
            output_files = [_aggregate_single_second_file(second_path, output_folder, target_month, logger=logger)]
        elif second_path.is_dir():
            second_dir = _resolve_second_result_dir(second_path)
            start_date, end_date = _resolve_step3_date_range(target_month, second_dir, process_start_date, process_end_date)
            _log(logger, f"[3号] 处理日期范围：{start_date} 至 {end_date}")
            result = run_15min_agg(
                input_folder=second_dir,
                output_folder=output_folder,
                start_date=start_date,
                end_date=end_date,
                logger=logger,
            )
            output_files = result.get("output_files", [])
        else:
            raise ValueError(f"2号秒级核算结果既不是文件也不是文件夹：{second_path}")

        return {
            "success": True,
            "status": "success",
            "message": f"3号15min聚合完成：{len(output_files)} 个输出文件",
            "output_files": output_files,
            "result_dir": str(output_folder),
        }
    except Exception as exc:
        return {
            "success": False,
            "status": "failed",
            "message": str(exc),
            "output_files": [],
            "error": str(exc),
        }


def _aggregate_single_second_file(second_file, output_folder, target_month="", logger=None):
    target_date = _infer_date_from_second_file(second_file)
    if str(target_month or "").strip():
        year, month = _parse_target_month(target_month)
        if target_date[:7] != f"{year:04d}-{month:02d}":
            raise ValueError(f"目标月份 {target_month} 与输入结果日期 {target_date} 不一致")

    _log(logger, f"[3号] 正在处理单个秒级结果文件：{second_file}")
    df = _read_second_result_file(second_file)
    _validate_second_result_columns(df)
    source_col_order = [col for col in df.columns if col in all_need_cols]
    agg_df = second_to_15min_agg(df, TIME_COL, STATUS_COL, target_date=target_date, source_col_order=source_col_order)
    output_file_path = Path(output_folder) / f"{target_date}_15minCO2排放结果.xlsx"
    agg_df.to_excel(output_file_path, index=False)
    _log(logger, f"[3号] 处理完成：{output_file_path}，共生成{len(agg_df)}行15分钟数据")
    return str(output_file_path)


def _read_second_result_file(file_path):
    suffix = Path(file_path).suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file_path)
    if suffix in {".xls", ".xlsx"}:
        return pd.read_excel(file_path)
    raise ValueError(f"不支持的2号结果文件类型：{file_path}")


def _validate_second_result_columns(df):
    missing = [col for col in [TIME_COL, STATUS_COL] if col not in df.columns]
    if missing:
        raise ValueError(f"2号秒级核算结果缺少必要列：{', '.join(missing)}")


def _resolve_second_result_dir(second_path):
    if list(Path(second_path).glob("*_秒级CO2排放结果.xlsx")):
        return Path(second_path)

    child_candidates = [
        Path(second_path) / "2号秒级核算结果",
        Path(second_path) / "2.秒级核算数据",
        Path(second_path) / "秒级核算结果",
    ]
    for candidate in child_candidates:
        if candidate.is_dir():
            return candidate
    return Path(second_path)


def _resolve_step3_date_range(target_month, second_dir, process_start_date="", process_end_date=""):
    if str(target_month or "").strip():
        range_info = resolve_process_date_range(target_month, process_start_date, process_end_date)
        if not range_info.get("ok"):
            raise ValueError(range_info.get("message", "处理日期范围无效"))
        return range_info["start_date"], range_info["end_date"]

    date_list = _find_second_result_dates(second_dir)
    if not date_list:
        raise ValueError("未填写目标月份，且无法从2号秒级核算结果目录中识别日期")
    return date_list[0], date_list[-1]


def _find_second_result_dates(second_dir):
    dates = []
    for file_path in Path(second_dir).glob("*_秒级CO2排放结果.xlsx"):
        date_text = _date_text_from_name(file_path.name)
        if date_text:
            dates.append(date_text)
    return sorted(set(dates))


def _infer_date_from_second_file(second_file):
    date_text = _date_text_from_name(Path(second_file).name)
    if date_text:
        return date_text

    df = _read_second_result_file(second_file)
    if TIME_COL not in df.columns:
        raise ValueError("无法从文件名识别日期，且2号秒级核算结果缺少数据时间列")
    dates = pd.to_datetime(df[TIME_COL], errors="coerce").dropna()
    if dates.empty:
        raise ValueError("无法从2号秒级核算结果中识别日期")
    return dates.min().strftime("%Y-%m-%d")


def _date_text_from_name(file_name):
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", str(file_name))
    return match.group(1) if match else ""


def _parse_target_month(target_month):
    text = str(target_month).strip()
    try:
        dt = datetime.strptime(f"{text}-01", "%Y-%m-%d")
    except Exception as exc:
        raise ValueError(f"目标月份格式应为 YYYY-MM，例如 2026-05。当前值：{target_month}") from exc
    return int(dt.year), int(dt.month)
