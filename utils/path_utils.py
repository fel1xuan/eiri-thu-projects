from datetime import datetime
import os
import platform
from pathlib import Path
import subprocess

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
    expanded = Path(os.path.expandvars(path_text)).expanduser()
    return str(expanded.resolve(strict=False))


def is_existing_dir(path):
    path_text = normalize_path(path)
    return bool(path_text) and Path(path_text).is_dir()


def is_existing_file(path):
    path_text = normalize_path(path)
    return bool(path_text) and Path(path_text).is_file()


def ensure_dir(path):
    normalized = normalize_path(path)
    if not normalized:
        raise ValueError("文件夹路径不能为空")
    Path(normalized).mkdir(parents=True, exist_ok=True)
    return str(Path(normalized))


def open_path(path):
    normalized = normalize_path(path)
    if not normalized:
        raise ValueError("路径不能为空")
    target = Path(normalized)
    if not target.exists():
        raise FileNotFoundError(f"路径不存在：{normalized}")

    system_name = platform.system()
    if system_name == "Darwin":
        subprocess.Popen(["open", normalized])
    elif system_name == "Windows":
        os.startfile(normalized)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", normalized])
    return True


def format_file_size(size_bytes):
    try:
        size = float(size_bytes)
    except (TypeError, ValueError):
        return ""
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"


def list_result_files(output_dir):
    result_extensions = {".xlsx", ".xls", ".csv", ".png", ".jpg", ".jpeg", ".pdf"}
    normalized_output_dir = normalize_path(output_dir)
    if not normalized_output_dir:
        raise ValueError("输出目录未填写")
    output_path = Path(normalized_output_dir)
    if not output_path.exists():
        raise FileNotFoundError(f"输出目录不存在：{output_path}")
    if not output_path.is_dir():
        raise NotADirectoryError(f"输出目录不是文件夹：{output_path}")

    files = []
    for file_path in output_path.iterdir():
        if not file_path.is_file():
            continue
        suffix = file_path.suffix.lower()
        if suffix not in result_extensions:
            continue
        stat = file_path.stat()
        files.append(
            {
                "name": file_path.name,
                "type": suffix.lstrip(".").upper(),
                "size": format_file_size(stat.st_size),
                "modified_time": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "path": str(file_path),
                "mtime": stat.st_mtime,
            }
        )
    return sorted(files, key=lambda item: item["mtime"], reverse=True)


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
        if key == "source_code_folder":
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
