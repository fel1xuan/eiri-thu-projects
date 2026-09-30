import calendar
from pathlib import Path

import pandas as pd

from core.step0_extract_report import DEFAULT_CELL_MAP
from utils.date_range_utils import resolve_process_date_range


DATE_COLUMN_CANDIDATES = ("日期", "时间", "date")
REQUIRED_COLUMNS = [name for name, cell in DEFAULT_CELL_MAP.items() if cell]
INFO_ONLY_EMPTY_COLUMNS = {"本日库存"}


def review_step0_output(
    output_file: str,
    target_month: str = "",
    process_start_date: str = "",
    process_end_date: str = "",
) -> dict:
    """
    审核0号日报提取结果。

    参数：
        output_file: 0号输出 Excel 文件路径
        target_month: 目标月份，格式 YYYY-MM，可为空

    返回：
        {
            "success": True/False,
            "status": "passed" / "warning" / "failed",
            "message": "...",
            "details": [...]
        }
    """
    details = []
    try:
        range_info = None
        if str(target_month or "").strip():
            range_info = resolve_process_date_range(target_month, process_start_date, process_end_date)
            if not range_info.get("ok"):
                _add(details, "处理日期范围", "失败", range_info.get("message", "处理日期范围无效"))
                return _finish(details, "0号审核失败：处理日期范围无效")

        output_path = Path(str(output_file or "").strip()).expanduser()
        if not str(output_file or "").strip():
            _add(details, "输出文件存在", "失败", "0号输出文件路径不能为空")
            return _finish(details, "0号审核失败：0号输出文件路径不能为空")

        if not output_path.exists() or not output_path.is_file():
            _add(details, "输出文件存在", "失败", f"输出文件不存在：{output_path}")
            return _finish(details, "0号审核失败：输出文件不存在")
        _add(details, "输出文件存在", "通过", f"输出文件存在：{output_path}")

        try:
            df = pd.read_excel(output_path)
            _add(details, "Excel 可读取", "通过", f"Excel 可正常读取，共 {len(df)} 行，{len(df.columns)} 列")
        except Exception as exc:
            _add(details, "Excel 可读取", "失败", f"Excel 读取失败：{exc}")
            return _finish(details, "0号审核失败：Excel 读取失败")

        if df.empty:
            _add(details, "Excel 数据", "失败", "0号输出结果为空")
            return _finish(details, "0号审核失败：输出结果为空")

        date_col = _find_date_column(df)
        if not date_col:
            _add(details, "日期列识别", "失败", "未能识别日期列，请检查0号输出结果格式。")
            return _finish(details, "0号审核失败：未能识别日期列")
        _add(details, "日期列识别", "通过", f"已识别日期列：{date_col}")

        parsed_dates = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
        valid_dates = parsed_dates.dropna()
        invalid_count = len(parsed_dates) - len(valid_dates)
        if invalid_count:
            _add(details, "日期解析", "警告", f"存在 {invalid_count} 条日期为空或无法解析")
        else:
            _add(details, "日期解析", "通过", f"日期解析成功，有效日期 {len(valid_dates)} 条")

        if valid_dates.empty:
            _add(details, "日期解析", "失败", "没有可用于审核的有效日期")
            return _finish(details, "0号审核失败：没有有效日期")

        duplicate_dates = sorted(valid_dates[valid_dates.duplicated()].dt.strftime("%Y-%m-%d").unique().tolist())
        if duplicate_dates:
            _add(details, "重复日期", "警告", f"发现重复日期：{_sample_dates(duplicate_dates)}")
        else:
            _add(details, "重复日期", "通过", "未发现重复日期")

        missing_required = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_required:
            _add(details, "关键字段缺失", "失败", f"缺失关键字段：{', '.join(missing_required)}")
        else:
            _add(details, "关键字段缺失", "通过", "关键字段均存在")

        if range_info:
            _review_expected_range(details, df, valid_dates, range_info)
        else:
            _add(details, "处理日期范围覆盖", "警告", "未填写处理月份，已跳过日期范围覆盖检查。")

        empty_columns = _find_all_empty_columns(df)
        info_only_columns = [column for column in empty_columns if column in INFO_ONLY_EMPTY_COLUMNS]
        warning_columns = [column for column in empty_columns if column not in INFO_ONLY_EMPTY_COLUMNS]
        if warning_columns:
            _add(details, "全空列检查", "警告", f"发现全空列：{', '.join(warning_columns)}")
        elif empty_columns:
            _add(details, "全空列检查", "通过", "未发现影响后续计算的全空列")
        else:
            _add(details, "全空列检查", "通过", "未发现全空列")

        for column in info_only_columns:
            _add(
                details,
                "字段提示",
                "提示",
                f'“{column}”列为空，该字段当前不参与后续1号、2号、3号核心计算，不影响本次数据处理。',
            )

        return _finish(details)
    except Exception as exc:
        _add(details, "审核异常", "失败", f"审核过程出现异常：{exc}")
        return _finish(details, f"0号审核失败：{exc}")


def _review_expected_range(details, df, valid_dates, range_info):
    start = pd.Timestamp(range_info["start_date"])
    end = pd.Timestamp(range_info["end_date"])
    expected_days = int(range_info["days"])
    expected = pd.date_range(start, end, freq="D")
    unique_valid = pd.DatetimeIndex(valid_dates.drop_duplicates()).sort_values()

    actual_set = set(unique_valid)
    expected_set = set(expected)
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)

    if missing:
        missing_text = _sample_dates([date.strftime("%Y-%m-%d") for date in missing])
        _add(details, "处理日期范围覆盖", "失败", f"日期覆盖不完整，缺失日期：{missing_text}")
    elif extra:
        extra_text = _sample_dates([date.strftime("%Y-%m-%d") for date in extra])
        _add(details, "处理日期范围覆盖", "失败", f"日期包含处理范围外数据：{extra_text}")
    else:
        _add(details, "处理日期范围覆盖", "通过", f"日期覆盖完整：{start:%Y-%m-%d} 至 {end:%Y-%m-%d}，共{expected_days}天")

    if len(df) == expected_days:
        _add(details, "行数检查", "通过", f"行数符合处理日期天数：{len(df)} 行")
    else:
        _add(details, "行数检查", "警告", f"行数为 {len(df)}，处理日期范围应为 {expected_days} 天")

    min_date = unique_valid.min().strftime("%Y-%m-%d")
    max_date = unique_valid.max().strftime("%Y-%m-%d")
    if min_date == start.strftime("%Y-%m-%d") and max_date == end.strftime("%Y-%m-%d"):
        _add(details, "日期首尾", "通过", f"日期从 {min_date} 到 {max_date}")
    else:
        _add(details, "日期首尾", "失败", f"日期首尾为 {min_date} 到 {max_date}，目标应为 {start:%Y-%m-%d} 到 {end:%Y-%m-%d}")


def _find_date_column(df):
    columns = [str(col) for col in df.columns]
    for column in columns:
        if "日期" in column:
            return column
    for column in columns:
        if "时间" in column:
            return column
    for column in columns:
        if "date" in column.lower():
            return column
    first_col = df.columns[0] if len(df.columns) else None
    if first_col is None:
        return ""
    parsed = pd.to_datetime(df[first_col], errors="coerce")
    return str(first_col) if parsed.notna().any() else ""


def _find_all_empty_columns(df):
    empty_columns = []
    for column in df.columns:
        series = df[column]
        if series.isna().all():
            empty_columns.append(str(column))
            continue
        non_empty = series.dropna().astype(str).str.strip()
        if non_empty.empty or (non_empty == "").all():
            empty_columns.append(str(column))
    return empty_columns


def _parse_target_month(target_month):
    text = str(target_month).strip()
    try:
        dt = pd.to_datetime(f"{text}-01", format="%Y-%m-%d", errors="raise")
    except Exception as exc:
        raise ValueError(f"目标月份格式应为 YYYY-MM，例如 2026-05。当前值：{target_month}") from exc
    return int(dt.year), int(dt.month)


def _add(details, item, status, message):
    details.append({"item": item, "status": status, "message": message})


def _finish(details, message=None):
    has_failed = any(item["status"] == "失败" for item in details)
    has_warning = any(item["status"] == "警告" for item in details)
    if has_failed:
        status = "failed"
        success = False
        final_message = message or _first_message(details, "失败") or "0号审核失败"
    elif has_warning:
        status = "warning"
        success = True
        final_message = message or _first_message(details, "警告") or "0号审核存在警告"
    else:
        status = "passed"
        success = True
        final_message = message or "0号审核通过"
    review_info = [item["message"] for item in details if item["status"] == "提示"]
    return {
        "success": success,
        "status": status,
        "message": final_message,
        "details": details,
        "review_info": review_info,
    }


def _first_message(details, status):
    for item in details:
        if item["status"] == status:
            return item["message"]
    return ""


def _sample_dates(date_texts, limit=12):
    if len(date_texts) <= limit:
        return ", ".join(date_texts)
    return ", ".join(date_texts[:limit]) + f" 等{len(date_texts)}天"
