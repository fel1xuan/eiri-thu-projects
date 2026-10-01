import json
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

STANDARD_DIR_CANDIDATES = {
    "raw_data_folder": {
        "label": "原始数据目录",
        "candidates": ["1.原始数据"],
    },
    "high_freq_base_path": {
        "label": "核心高频数据父目录",
        "candidates": [
            "1.原始数据/(1) 核心高频数据",
            "1.原始数据/(1)核心高频数据",
        ],
    },
    "low_freq_base_path": {
        "label": "低频数据根目录",
        "candidates": [
            "1.原始数据/(2) 原始低频数据",
            "1.原始数据/(2)原始低频数据",
            "1.原始数据/(3) 低频数据",
            "1.原始数据/(3)低频数据",
        ],
    },
    "three_channel_path": {
        "label": "三声道数据目录",
        "candidates": [
            "1.原始数据/(3) 声道三数据",
            "1.原始数据/(3)声道三数据",
            "1.原始数据/(3) 三声道数据",
            "1.原始数据/(3)三声道数据",
            "1.原始数据/(2) 清华三声道数据",
            "1.原始数据/(2)清华三声道数据",
        ],
    },
    "second_output_folder": {
        "label": "秒级核算结果目录",
        "candidates": [
            "2.秒级核算数据",
            "2.结果数据",
        ],
    },
    "abnormal_output_folder": {
        "label": "异常数据目录",
        "candidates": [
            "3.异常数据",
            "3.秒级异常数据统计",
        ],
    },
    "fifteen_output_folder": {
        "label": "15min结果目录",
        "candidates": [
            "4.15min核算数据",
            "2.结果数据/15min核算数据",
            "2.结果数据",
        ],
    },
    "source_code_folder": {
        "label": "源代码目录",
        "candidates": ["源代码"],
    },
}


def load_json(path, default=None):
    file_path = Path(path)
    if not file_path.exists():
        return default if default is not None else {}
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ensure_dir(path):
    normalized = normalize_path(path)
    Path(normalized).mkdir(parents=True, exist_ok=True)
    return str(Path(normalized))


def append_log(log_path, message, level="INFO"):
    if not log_path:
        return []
    level_text = str(level or "INFO").upper()
    if level_text not in {"INFO", "SUCCESS", "WARNING", "ERROR"}:
        level_text = "INFO"
    file_path = Path(log_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_lines = str(message).splitlines() or [""]
    formatted_lines = [f"[{timestamp}] [{level_text}] {line}" for line in message_lines]
    with file_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(formatted_lines) + "\n")
    return formatted_lines


def format_exception(exc):
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def normalize_path(path):
    if path is None:
        return ""
    path_text = str(path).strip().strip('"').strip("'")
    if not path_text:
        return ""
    replacements = {
        "文稿": "Documents",
        "桌面": "Desktop",
        "下载": "Downloads",
        "应用程序": "Applications",
    }
    for finder_name, real_name in replacements.items():
        path_text = path_text.replace(f"/{finder_name}/", f"/{real_name}/")
        if path_text.endswith(f"/{finder_name}"):
            path_text = path_text[: -len(finder_name)] + real_name
    return path_text


def normalize_date_str(date_value):
    if date_value is None or str(date_value).strip() == "":
        raise ValueError("日期不能为空")
    dt = pd.to_datetime(str(date_value).replace("/", "-"))
    if pd.isna(dt):
        raise ValueError(f"无法识别日期：{date_value}")
    return dt.strftime("%Y-%m-%d")


def get_expected_date_folders(start_date, end_date):
    start = pd.to_datetime(normalize_date_str(start_date))
    end = pd.to_datetime(normalize_date_str(end_date))
    if end < start:
        raise ValueError("数据处理结束日期不能早于数据处理开始日期")
    return [date.strftime("%Y-%m-%d") for date in pd.date_range(start, end)]


def generate_date_list(start_date, end_date):
    return get_expected_date_folders(start_date, end_date)


def month_folder_from_date(date_text):
    return datetime.strptime(normalize_date_str(date_text), "%Y-%m-%d").strftime("%Y%m")


def _resolve_standard_dir(root, candidates):
    fallback = root / candidates[0]
    for rel_path in candidates:
        folder = root / rel_path
        if folder.exists() and folder.is_dir():
            return folder, True
    return fallback, False


def find_standard_data_dirs(project_root):
    root = Path(normalize_path(project_root)).expanduser()
    result = {}
    for key, meta in STANDARD_DIR_CANDIDATES.items():
        path, exists = _resolve_standard_dir(root, meta["candidates"])
        result[key] = {
            "label": meta["label"],
            "path": str(path),
            "exists": exists,
            "candidates": [str(root / rel_path) for rel_path in meta["candidates"]],
        }
    return result


def get_standard_paths(project_root):
    root = Path(normalize_path(project_root)).expanduser()
    standard_dirs = find_standard_data_dirs(root)
    low_freq_base = Path(standard_dirs["low_freq_base_path"]["path"])
    return {
        "project_root": str(root),
        "high_freq_base_path": standard_dirs["high_freq_base_path"]["path"],
        "three_channel_path": standard_dirs["three_channel_path"]["path"],
        "low_freq_base_path": str(low_freq_base),
        "second_output_folder": standard_dirs["second_output_folder"]["path"],
        "abnormal_output_folder": standard_dirs["abnormal_output_folder"]["path"],
        "fifteen_output_folder": standard_dirs["fifteen_output_folder"]["path"],
        "source_code_folder": standard_dirs["source_code_folder"]["path"],
    }


def check_project_structure(project_root):
    missing = []
    existing = []
    standard_dirs = find_standard_data_dirs(project_root)
    for key, item in standard_dirs.items():
        if key in {"source_code_folder", "three_channel_path"}:
            continue
        if item["exists"]:
            existing.append(item["path"])
        else:
            missing.append(item["label"])
    return {"ok": len(missing) == 0, "missing": missing, "existing": existing}


def validate_date_folders(parent_dir, start_date, end_date):
    parent = Path(normalize_path(parent_dir)).expanduser()
    expected_dates = get_expected_date_folders(start_date, end_date)
    missing_dates = [date_text for date_text in expected_dates if not (parent / date_text).is_dir()]
    return {
        "ok": len(missing_dates) == 0,
        "status": "complete" if len(missing_dates) == 0 else "partial",
        "parent_dir": str(parent),
        "expected_count": len(expected_dates),
        "found_count": len(expected_dates) - len(missing_dates),
        "missing_dates": missing_dates,
    }


def validate_core_high_freq_dir(project_root, start_date, end_date):
    standard_dirs = find_standard_data_dirs(project_root)
    core_item = standard_dirs["high_freq_base_path"]
    if not core_item["exists"]:
        return {
            "ok": False,
            "status": "missing_core_dir",
            "core_dir": core_item["path"],
            "message": "未找到核心高频数据父目录",
            "expected_count": 0,
            "found_count": 0,
            "missing_dates": [],
        }

    result = validate_date_folders(core_item["path"], start_date, end_date)
    return {
        "ok": result["ok"],
        "status": result["status"],
        "core_dir": core_item["path"],
        "message": "日期范围检查完成",
        "expected_count": result["expected_count"],
        "found_count": result["found_count"],
        "missing_dates": result["missing_dates"],
    }


def find_latest_file(folder, pattern):
    folder_text = normalize_path(folder)
    if not folder_text:
        return ""
    folder_path = Path(folder_text)
    if not folder_path.exists():
        return ""
    files = sorted(folder_path.glob(pattern), key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    return str(files[0]) if files else ""


def list_files(folder, pattern):
    folder_text = normalize_path(folder)
    if not folder_text:
        return []
    folder_path = Path(folder_text)
    if not folder_path.exists():
        return []
    return sorted(folder_path.glob(pattern), key=lambda p: p.name)


def file_bytes(path):
    path_text = normalize_path(path)
    with Path(path_text).open("rb") as f:
        return f.read()
