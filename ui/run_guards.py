from calendar import monthrange
from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from utils.path_utils import normalize_path
from utils.standard_paths import derive_standard_paths, expected_result_files


TEMP_OUTPUT_WARNING = "当前输出目录是临时目录，适合测试，不建议保存正式结果。"


def is_temp_output_dir(output_dir):
    normalized = normalize_path(output_dir)
    if not normalized:
        return False
    path_text = normalized.replace("\\", "/")
    return (
        path_text == "/tmp"
        or path_text.startswith("/tmp/")
        or "/private/tmp" in path_text
        or "/tmp/" in path_text
    )


def append_temp_output_warning(message, output_dir):
    text = str(message or "")
    if is_temp_output_dir(output_dir) and TEMP_OUTPUT_WARNING not in text:
        return f"{text}\n\n{TEMP_OUTPUT_WARNING}".strip()
    return text


def expected_lowfreq_filename(target_month):
    if not target_month:
        return ""
    try:
        year, month = [int(part) for part in str(target_month).split("-", 1)]
        last_day = monthrange(year, month)[1]
    except Exception:
        return ""
    return f"海螺水泥低频数据_{year:04d}-{month:02d}-{last_day:02d}.xlsx"


def find_existing_result_files(output_dir, target_month="", process_end_date="", include_step0=True):
    output_path = Path(normalize_path(output_dir))
    if not output_path.exists() or not output_path.is_dir():
        return []

    expected_lowfreq = f"海螺水泥低频数据_{process_end_date}.xlsx" if process_end_date else expected_lowfreq_filename(target_month)
    matches = []
    for file_path in output_path.rglob("*"):
        if not file_path.is_file():
            continue
        name = file_path.name
        lower_suffix = file_path.suffix.lower()
        is_match = False

        if include_step0 and name == "生产日报提取结果.xlsx":
            is_match = True
        elif expected_lowfreq and name == expected_lowfreq:
            is_match = True
        elif not expected_lowfreq and "海螺水泥低频数据" in name and lower_suffix == ".xlsx":
            is_match = True
        elif ("秒级CO2排放结果" in name or "秒级碳排放" in name) and lower_suffix in {".xls", ".xlsx"}:
            is_match = True
        elif ("秒级异常检测结果" in name or "异常检测" in name) and lower_suffix in {".xls", ".xlsx"}:
            is_match = True
        elif "15min" in name and lower_suffix in {".xls", ".xlsx"}:
            is_match = True

        if is_match:
            matches.append(file_path)
            if len(matches) >= 80:
                break

    return [str(path) for path in sorted(matches, key=lambda item: item.stat().st_mtime, reverse=True)]


def find_existing_standard_result_files(config, include_step0=False):
    return [path for path in expected_result_files(config, include_step0=include_step0) if Path(path).is_file()]


def _ask_yes_no(parent, title, message):
    reply = QMessageBox.question(
        parent,
        title,
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return reply == QMessageBox.StandardButton.Yes


def _overwrite_message(existing_files):
    shown_files = existing_files[:12]
    lines = [
        "标准结果目录中已经存在本次目标文件，继续运行可能覆盖旧结果。",
        "",
        "已发现：",
        *shown_files,
    ]
    if len(existing_files) > len(shown_files):
        lines.append(f"... 另有 {len(existing_files) - len(shown_files)} 个文件")
    if any("海螺水泥低频数据" in Path(path).name for path in existing_files):
        lines.extend(["", "当前日期范围对应的累计低频主表已存在；确认后才会重新生成并覆盖。"])
    lines.extend(["", "是否继续？"])
    return "\n".join(lines)


def confirm_step_run(
    parent,
    step_name,
    output_dir="",
    target_month="",
    notes=None,
    process_start_date="",
    process_end_date="",
    existing_files=None,
    result_locations=None,
):
    lines = [f"即将运行 {step_name}。"]
    if notes:
        lines.extend(str(note) for note in notes if note)
    lines.append("继续运行会在输出目录生成结果文件；如果同名结果已存在，可能覆盖旧结果。")
    if is_temp_output_dir(output_dir):
        lines.extend(["", TEMP_OUTPUT_WARNING])
    if process_start_date or process_end_date:
        lines.extend(["", "处理日期：", f"{process_start_date or '未填写'} 至 {process_end_date or '未填写'}"])
    if result_locations:
        lines.extend(["", "结果位置：", *[str(path) for path in result_locations if path]])
    else:
        lines.extend(["", "输出目录：", str(output_dir or "未填写")])
    lines.extend(["", "是否继续？"])

    if not _ask_yes_no(parent, "确认运行", "\n".join(lines)):
        return False

    if existing_files is None:
        existing_files = find_existing_result_files(output_dir, target_month, process_end_date, include_step0=True)
    if existing_files:
        return _ask_yes_no(parent, "覆盖风险提示", _overwrite_message(existing_files))
    return True


def confirm_pipeline_run(
    parent,
    target_month,
    output_dir="",
    process_start_date="",
    process_end_date="",
    config=None,
):
    paths = derive_standard_paths(config or {}) if config else {}
    lines = [
        "即将开始一键运行后续流程：",
        "",
        "1号低频汇总",
        "2号秒级核算",
        "3号15min聚合",
        "",
        "处理月份：",
        str(target_month or "未填写"),
        "",
        "处理日期：",
        f"{process_start_date or '未填写'} 至 {process_end_date or '未填写'}",
        "",
        "结果位置：",
        f"1号：{paths.get('step1_output_dir') or output_dir or '未填写'}",
        f"2号：{paths.get('step2_result_dir') or output_dir or '未填写'}",
        f"异常：{paths.get('step2_abnormal_dir') or output_dir or '未填写'}",
        f"3号：{paths.get('step3_result_dir') or output_dir or '未填写'}",
    ]
    if is_temp_output_dir(output_dir):
        lines.extend(["", TEMP_OUTPUT_WARNING])
    lines.extend(
        [
            "",
            "该流程可能耗时较长，并会在输出目录生成结果文件；如果同名结果已存在，可能覆盖旧结果。",
            "",
            "是否继续？",
        ]
    )

    if not _ask_yes_no(parent, "确认一键运行", "\n".join(lines)):
        return False

    existing_files = (
        find_existing_standard_result_files(config, include_step0=False)
        if config
        else find_existing_result_files(output_dir, target_month, process_end_date, include_step0=False)
    )
    if existing_files:
        return _ask_yes_no(parent, "覆盖风险提示", _overwrite_message(existing_files))
    return True
