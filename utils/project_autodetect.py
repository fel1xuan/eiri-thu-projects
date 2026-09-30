from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

from utils.date_range_utils import parse_target_month
from utils.path_utils import normalize_path
from utils.standard_paths import derive_standard_paths


EXCEL_SUFFIXES = {".xls", ".xlsx"}


def autodetect_month_config(data_root: str, target_month: str) -> dict:
    """Detect month-specific inputs without changing config or creating files."""
    root = Path(normalize_path(data_root)) if str(data_root or "").strip() else None
    month_info = parse_target_month(target_month)
    result = {
        "report_file": "",
        "history_lowfreq_file": "",
        "lowfreq_current_path": "",
        "second_data_dir": "",
        "step0_output_dir": "",
        "step0_output_file": "",
        "step1_output_dir": "",
        "lowfreq_result_file": "",
        "step2_result_dir": "",
        "step2_abnormal_dir": "",
        "step3_result_dir": "",
        "process_start_date": "",
        "process_end_date": "",
        "warnings": [],
        "candidates": {},
        "statuses": {},
    }

    if not month_info.get("ok"):
        result["warnings"].append(month_info.get("message", "处理月份无效"))
        return result
    result["process_start_date"] = month_info["start_date"]
    result["process_end_date"] = month_info["end_date"]

    if root is None or not root.is_dir():
        result["warnings"].append(f"数据项目根目录不存在：{data_root or '未填写'}")
        return result

    lowfreq_root = _find_named_data_dir(root, "(3)低频数据", "低频数据")
    month_dir = _find_month_dir(lowfreq_root, month_info) if lowfreq_root else None
    if month_dir:
        result["lowfreq_current_path"] = str(month_dir)
        _set_status(result, "lowfreq_current_path", "detected", "已自动识别")
    else:
        message = f"未找到{month_info['target_month']}当月低频数据目录"
        result["warnings"].append(message)
        _set_status(result, "lowfreq_current_path", "missing", message)

    report_candidates = _find_report_candidates(month_dir, month_info)
    result["candidates"]["report_file"] = [str(item["path"]) for item in report_candidates]
    if len(report_candidates) == 1:
        result["report_file"] = str(report_candidates[0]["path"])
        _set_status(result, "report_file", "detected", "已自动识别")
    elif len(report_candidates) > 1:
        message = f"找到{len(report_candidates)}个生产综合日报候选，请确认"
        result["warnings"].append(message)
        _set_status(result, "report_file", "warning", message)
    else:
        message = "未找到生产综合日报"
        result["warnings"].append(message)
        _set_status(result, "report_file", "missing", message)

    history_candidates = _find_history_candidates(lowfreq_root, month_info["start_date"])
    result["candidates"]["history_lowfreq_file"] = history_candidates
    usable_history = [item for item in history_candidates if item.get("eligible")]
    if usable_history:
        chosen = usable_history[0]
        result["history_lowfreq_file"] = chosen["path"]
        _set_status(
            result,
            "history_lowfreq_file",
            "detected",
            f"已自动识别，数据截止{chosen['max_date']}",
        )
    else:
        message = "未找到日期早于处理开始日的可读历史低频主表"
        result["warnings"].append(message)
        _set_status(result, "history_lowfreq_file", "missing", message)

    second_data_dir = _find_named_data_dir(root, "(1)核心高频数据", "核心高频数据", "高频数据")
    if second_data_dir:
        month_specific = _find_month_dir(second_data_dir, month_info)
        selected_second_dir = month_specific or second_data_dir
        result["second_data_dir"] = str(selected_second_dir)
        matched_dates = _matching_date_entries(selected_second_dir, month_info)
        result["candidates"]["second_data_dates"] = matched_dates
        if matched_dates:
            _set_status(
                result,
                "second_data_dir",
                "detected",
                f"已自动识别，文件级检查发现{len(matched_dates)}个目标月日期",
            )
        else:
            message = "已识别高频目录，但文件级检查未发现目标月份数据"
            result["warnings"].append(message)
            _set_status(result, "second_data_dir", "warning", message)
    else:
        message = "未找到秒级/高频数据目录"
        result["warnings"].append(message)
        _set_status(result, "second_data_dir", "missing", message)

    standard_paths = derive_standard_paths(
        {"data_root": str(root), "target_month": month_info["target_month"], "process_end_date": month_info["end_date"]}
    )
    for key in (
        "step0_output_dir",
        "step0_output_file",
        "step1_output_dir",
        "lowfreq_result_file",
        "step2_result_dir",
        "step2_abnormal_dir",
        "step3_result_dir",
    ):
        result[key] = standard_paths[key]
        _set_status(result, key, "generated", "已根据数据项目根目录自动生成")
    return result


def _find_named_data_dir(root: Path, *preferred_names: str) -> Path | None:
    raw_root = root / "1.原始数据"
    search_roots = [raw_root, root] if raw_root.is_dir() else [root]
    for name in preferred_names:
        for base in search_roots:
            direct = base / name
            if direct.is_dir():
                return direct.resolve()
    for base in search_roots:
        try:
            for child in base.iterdir():
                if child.is_dir() and any(name in child.name for name in preferred_names):
                    return child.resolve()
        except OSError:
            continue
    return None


def _month_dir_names(month_info: dict) -> list[str]:
    year = month_info["year"]
    month = month_info["month"]
    return [
        f"{year:04d}{month:02d}",
        f"{year:04d}-{month:02d}",
        f"{year:04d}_{month:02d}",
        f"{year:04d}年{month:02d}月",
        f"{year:04d}年{month}月",
    ]


def _find_month_dir(parent: Path | None, month_info: dict) -> Path | None:
    if not parent or not parent.is_dir():
        return None
    for name in _month_dir_names(month_info):
        candidate = parent / name
        if candidate.is_dir():
            return candidate.resolve()
    return None


def _find_report_candidates(month_dir: Path | None, month_info: dict) -> list[dict]:
    if not month_dir or not month_dir.is_dir():
        return []
    target_markers = {
        f"{month_info['year']}年{month_info['month']}月",
        f"{month_info['year']}年{month_info['month']:02d}月",
        f"{month_info['year']}{month_info['month']:02d}",
    }
    candidates = []
    for path in sorted(month_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in EXCEL_SUFFIXES:
            continue
        if "提取结果" in path.name:
            continue
        if "生产综合日报" not in path.name and "日报" not in path.name:
            continue
        score = 100 if "生产综合日报" in path.name else 40
        if any(marker in path.name for marker in target_markers):
            score += 20
        candidates.append({"path": path.resolve(), "score": score})
    if not candidates:
        return []
    candidates.sort(key=lambda item: (-item["score"], item["path"].name))
    best_score = candidates[0]["score"]
    return [item for item in candidates if item["score"] == best_score]


def _find_history_candidates(lowfreq_root: Path | None, process_start_date: str) -> list[dict]:
    start = pd.Timestamp(process_start_date).normalize()
    paths = set()
    if lowfreq_root and lowfreq_root.is_dir():
        paths.update(_matching_lowfreq_files(lowfreq_root, recursive=False))
    items = []
    for path in paths:
        max_date, date_column, error = _read_excel_max_date(path)
        eligible = max_date is not None and max_date < start
        items.append(
            {
                "path": str(path.resolve()),
                "max_date": max_date.strftime("%Y-%m-%d") if max_date is not None else "",
                "date_column": date_column,
                "eligible": eligible,
                "error": error,
                "preferred_source": bool(lowfreq_root and path.parent.resolve() == lowfreq_root.resolve()),
                "filename_matches_content": bool(
                    max_date is not None and max_date.strftime("%Y-%m-%d") in path.name
                ),
            }
        )
    items.sort(
        key=lambda item: (
            0 if item["eligible"] else 1,
            -(pd.Timestamp(item["max_date"]).value if item["max_date"] else -1),
            0 if item["preferred_source"] else 1,
            0 if item["filename_matches_content"] else 1,
            item["path"],
        )
    )
    return items


def _matching_lowfreq_files(parent: Path, recursive: bool) -> set[Path]:
    iterator = parent.rglob("*") if recursive else parent.iterdir()
    matches = set()
    for path in iterator:
        if not path.is_file() or path.suffix.lower() not in EXCEL_SUFFIXES:
            continue
        name = path.name
        if "低频数据" in name and "~$" not in name:
            matches.add(path)
    return matches


def _read_excel_max_date(path: Path) -> tuple[pd.Timestamp | None, str, str]:
    try:
        columns = list(pd.read_excel(path, nrows=0).columns)
        if not columns:
            return None, "", "Excel没有列"
        date_column = _identify_date_column(columns)
        frame = pd.read_excel(path, usecols=[date_column])
        dates = pd.to_datetime(frame[date_column], errors="coerce").dropna()
        if dates.empty:
            return None, str(date_column), "日期列没有可解析日期"
        return dates.max().normalize(), str(date_column), ""
    except Exception as exc:
        return None, "", str(exc)


def _identify_date_column(columns) -> object:
    for column in columns:
        text = str(column).strip()
        if "日期" in text:
            return column
    for column in columns:
        text = str(column).strip().lower()
        if "时间" in text or text == "date" or "date" in text:
            return column
    return columns[0]


def _matching_date_entries(parent: Path, month_info: dict) -> list[str]:
    matches = set()
    if not parent.is_dir():
        return []
    patterns = [
        re.compile(rf"{month_info['year']:04d}-{month_info['month']:02d}-(\d{{2}})"),
        re.compile(rf"{month_info['year']:04d}{month_info['month']:02d}(\d{{2}})"),
    ]
    try:
        entries = list(parent.iterdir())
    except OSError:
        return []
    for entry in entries:
        for pattern in patterns:
            found = pattern.search(entry.name)
            if not found:
                continue
            day = int(found.group(1))
            try:
                matches.add(date(month_info["year"], month_info["month"], day).isoformat())
            except ValueError:
                pass
    return sorted(matches)


def _set_status(result: dict, key: str, status: str, message: str) -> None:
    result["statuses"][key] = {"status": status, "message": message, "source": "auto"}
