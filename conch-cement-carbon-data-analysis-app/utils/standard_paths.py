from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

from utils.path_utils import normalize_path


LOWFREQ_RELATIVE_PATH = Path("1.原始数据") / "(3)低频数据"


def derive_standard_paths(config_or_root, target_month: str = "", process_end_date: str = "") -> dict:
    """Derive every formal result path from the data project root."""
    if isinstance(config_or_root, dict):
        config = config_or_root
        data_root = str(config.get("data_root", "") or "").strip()
        target_month = str(config.get("target_month", target_month) or target_month).strip()
        process_end_date = str(config.get("process_end_date", process_end_date) or process_end_date).strip()
    else:
        data_root = str(config_or_root or "").strip()

    if not data_root:
        return _empty_paths()

    root = Path(normalize_path(data_root))
    lowfreq_root = root / LOWFREQ_RELATIVE_PATH
    month_token, month_end = _month_values(target_month)
    effective_end = _valid_date(process_end_date) or month_end
    step0_output_dir = lowfreq_root / month_token if month_token else lowfreq_root

    return {
        "data_root": str(root),
        "lowfreq_root": str(lowfreq_root),
        "step0_output_dir": str(step0_output_dir),
        "step0_output_file": str(step0_output_dir / "生产日报提取结果.xlsx"),
        "step1_output_dir": str(lowfreq_root),
        "lowfreq_result_file": str(
            lowfreq_root / f"海螺水泥低频数据_{effective_end or 'YYYY-MM-DD'}.xlsx"
        ),
        "step2_result_dir": str(root / "2.秒级核算数据"),
        "step2_abnormal_dir": str(root / "3.秒级异常数据统计"),
        "step3_result_dir": str(root / "4.15min核算数据"),
    }


def apply_standard_paths(config: dict) -> dict:
    normalized = dict(config or {})
    normalized.pop("output_dir", None)
    normalized.update(derive_standard_paths(normalized))
    normalized["second_result_path"] = normalized.get("step2_result_dir", "")
    normalized["abnormal_result_path"] = normalized.get("step2_abnormal_dir", "")
    return normalized


def expected_result_files(config: dict, include_step0: bool = False) -> list[str]:
    paths = derive_standard_paths(config)
    start_text = str((config or {}).get("process_start_date", "") or "").strip()
    end_text = str((config or {}).get("process_end_date", "") or "").strip()
    start = _parse_date(start_text)
    end = _parse_date(end_text)
    results = []
    if include_step0 and paths.get("step0_output_file"):
        results.append(paths["step0_output_file"])
    if paths.get("lowfreq_result_file"):
        results.append(paths["lowfreq_result_file"])
    if start and end and start <= end:
        current = start
        while current <= end:
            day = current.isoformat()
            results.extend(
                [
                    str(Path(paths["step2_result_dir"]) / f"{day}_秒级CO2排放结果.xlsx"),
                    str(Path(paths["step2_abnormal_dir"]) / f"{day}_秒级异常检测结果.xlsx"),
                    str(Path(paths["step3_result_dir"]) / f"{day}_15minCO2排放结果.xlsx"),
                ]
            )
            current += timedelta(days=1)
    return results


def result_directories(config: dict) -> list[tuple[str, str]]:
    paths = derive_standard_paths(config)
    return [
        ("低频主表", paths.get("step1_output_dir", "")),
        ("秒级核算", paths.get("step2_result_dir", "")),
        ("秒级异常", paths.get("step2_abnormal_dir", "")),
        ("15min结果", paths.get("step3_result_dir", "")),
    ]


def _month_values(target_month: str) -> tuple[str, str]:
    text = str(target_month or "").strip()
    try:
        year_text, month_text = text.split("-", 1)
        year, month = int(year_text), int(month_text)
        days = monthrange(year, month)[1]
    except Exception:
        return "", ""
    return f"{year:04d}{month:02d}", f"{year:04d}-{month:02d}-{days:02d}"


def _valid_date(value: str) -> str:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else ""


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


def _empty_paths() -> dict:
    return {
        "data_root": "",
        "lowfreq_root": "",
        "step0_output_dir": "",
        "step0_output_file": "",
        "step1_output_dir": "",
        "lowfreq_result_file": "",
        "step2_result_dir": "",
        "step2_abnormal_dir": "",
        "step3_result_dir": "",
    }
