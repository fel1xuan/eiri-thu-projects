from __future__ import annotations

from datetime import datetime
from pathlib import Path

from utils.date_range_utils import resolve_process_date_range
from utils.config_utils import is_step0_review_approved
from utils.path_utils import normalize_path
from utils.runtime_paths import get_project_root, get_user_data_dir
from utils.standard_paths import derive_standard_paths, expected_result_files


PROJECT_ROOT = get_project_root()


def build_production_preflight_report(config: dict) -> dict:
    normalized = dict(config or {})
    items = []
    range_info = resolve_process_date_range(
        normalized.get("target_month", ""),
        normalized.get("process_start_date", ""),
        normalized.get("process_end_date", ""),
    )
    if range_info.get("ok"):
        _add(items, "处理日期范围", "通过", f"{range_info['start_date']} 至 {range_info['end_date']}，共{range_info['days']}天")
    else:
        _add(items, "处理日期范围", "失败", range_info.get("message", "日期范围无效"))

    _add_step0_review(items, normalized, range_info)
    _add_file(items, "历史低频主表", normalized.get("history_lowfreq_file", ""))
    _add_existing_path(items, "当月低频数据", normalized.get("lowfreq_current_path", ""), directory_only=False)
    _add_existing_path(items, "秒级 / 高频数据目录", normalized.get("second_data_dir", ""), directory_only=True)

    paths = derive_standard_paths(normalized)
    if not paths.get("data_root"):
        _add(items, "标准结果目录", "失败", "数据项目根目录未配置，无法推导标准结果目录")
    else:
        for key, label in (
            ("step1_output_dir", "1号累计低频目录"),
            ("step2_result_dir", "2号秒级结果目录"),
            ("step2_abnormal_dir", "2号异常结果目录"),
            ("step3_result_dir", "3号15min结果目录"),
        ):
            path = Path(paths[key])
            parent_ok = path.is_dir() or path.parent.is_dir()
            _add(
                items,
                label,
                "通过" if parent_ok else "失败",
                f"{'目录存在' if path.is_dir() else '运行时将在标准位置创建'}：{path}",
            )

    expected_outputs = _expected_output_items(normalized)
    existing_files = [path for path in expected_result_files(normalized) if Path(path).is_file()]
    if existing_files:
        names = ", ".join(Path(path).name for path in existing_files[:8])
        extra = f"，另有{len(existing_files) - 8}个" if len(existing_files) > 8 else ""
        _add(items, "覆盖风险检查", "警告", f"以下本次目标结果已存在：{names}{extra}")
    else:
        _add(items, "覆盖风险检查", "通过", "本次日期范围内未发现同名目标结果")

    status = _overall_status(items)
    message = {
        "passed": "正式运行前检查通过。",
        "warning": "当前配置存在覆盖警告，请确认后再运行。",
        "failed": "当前配置未通过正式运行检查，请先修复失败项。",
    }[status]
    report_text = _format_report(normalized, items, paths, expected_outputs, existing_files, status, message)
    return {
        "success": status != "failed",
        "status": status,
        "message": message,
        "report_text": report_text,
        "items": items,
        "existing_files": existing_files,
        "expected_outputs": expected_outputs,
    }


def save_preflight_report_text(report_text: str, output_dir: str = "") -> str:
    report_dir = get_user_data_dir() / "preflight_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"正式运行检查清单_{timestamp}.txt"
    path.write_text(str(report_text or ""), encoding="utf-8")
    return str(path)


def _add_step0_review(items, config, range_info):
    output_file = str(config.get("step0_output_file", "") or "").strip()
    if not output_file or not Path(normalize_path(output_file)).is_file():
        _add(items, "0号输出与审核", "失败", f"0号标准结果不存在：{output_file or '未配置'}")
        return
    review_status = str(config.get("step0_review_status", "") or "").strip().lower()
    if review_status != "approved":
        _add(
            items,
            "0号输出与人工审核",
            "失败",
            "当前0号结果尚未完成人工审核，请先在0号页面确认",
        )
    elif not range_info.get("ok") or not is_step0_review_approved(
        config, range_info.get("start_date", ""), range_info.get("end_date", "")
    ):
        _add(items, "0号输出与人工审核", "失败", "0号人工审核日期范围与当前处理范围不一致")
    else:
        _add(items, "0号输出与人工审核", "通过", f"人工审核通过：{normalize_path(output_file)}")


def _add_file(items, label, value):
    path = Path(normalize_path(value)) if str(value or "").strip() else None
    if path and path.is_file():
        _add(items, label, "通过", f"文件存在：{path}")
    else:
        _add(items, label, "失败", f"文件不存在或未选择：{path or '空'}")


def _add_existing_path(items, label, value, directory_only):
    path = Path(normalize_path(value)) if str(value or "").strip() else None
    valid = bool(path and path.exists() and (path.is_dir() if directory_only else True))
    _add(items, label, "通过" if valid else "失败", f"{'路径存在' if valid else '路径不存在或未选择'}：{path or '空'}")


def _expected_output_items(config):
    paths = derive_standard_paths(config)
    return [
        {"label": "1号输出", "path": paths.get("lowfreq_result_file", "")},
        {"label": "2号输出目录", "path": paths.get("step2_result_dir", "")},
        {"label": "2号异常目录", "path": paths.get("step2_abnormal_dir", "")},
        {"label": "3号输出目录", "path": paths.get("step3_result_dir", "")},
    ]


def _format_report(config, items, paths, expected, existing, status, message):
    status_text = {"passed": "通过", "warning": "存在警告", "failed": "未通过"}[status]
    lines = [
        "一键运行1号至3号前检查清单",
        f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        f"软件代码目录：{PROJECT_ROOT}",
        f"数据目录：{config.get('data_root', '') or '未填写'}",
        f"处理月份：{config.get('target_month', '') or '未填写'}",
        f"处理日期范围：{config.get('process_start_date', '') or '未填写'} 至 {config.get('process_end_date', '') or '未填写'}",
        "",
        "标准结果目录：",
        f"1号：{paths.get('step1_output_dir', '')}",
        f"2号：{paths.get('step2_result_dir', '')}",
        f"异常：{paths.get('step2_abnormal_dir', '')}",
        f"3号：{paths.get('step3_result_dir', '')}",
        "",
        f"总体结论：{status_text}",
        f"说明：{message}",
        "",
        "一、检查结果",
    ]
    lines.extend(f"[{item['status']}] {item['item']}：{item['message']}" for item in items)
    lines.extend(["", "二、覆盖风险"])
    lines.extend(existing or ["本次日期范围内未发现同名目标结果。"])
    lines.extend(["", "三、预计输出"])
    lines.extend(f"{item['label']}：{item['path']}" for item in expected)
    lines.extend(["", "本检查只读取配置和文件路径，不执行1/2/3业务计算。"])
    return "\n".join(lines)


def _add(items, item, status, message):
    items.append({"item": item, "status": status, "message": str(message)})


def _overall_status(items):
    statuses = {item["status"] for item in items}
    if "失败" in statuses:
        return "failed"
    if "警告" in statuses:
        return "warning"
    return "passed"
