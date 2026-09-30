"""Single-month pipeline orchestration for the PySide6 desktop app."""

from pathlib import Path

from core.step0_extract_report import run_extract_report, run_step0_extract
from core.step0_review import review_step0_output
from core.step1_lowfreq_update import run_lowfreq_update, run_step1_lowfreq_update
from core.step2_second_calc import run_second_calc, run_step2_second_calc
from core.step3_15min_aggregate import run_15min_agg, run_step3_15min_aggregate
from utils.config_utils import is_step0_review_approved
from utils.date_range_utils import resolve_process_date_range
from utils.log_utils import append_run_log
from utils.standard_paths import derive_standard_paths


PIPELINE_STEP_NAMES = [
    "0号日报提取",
    "0号结果审核",
    "1号低频汇总",
    "2号秒级核算",
    "3号15min聚合",
]

PIPELINE_STEP_NAMES_1_TO_3 = [
    "1号低频汇总",
    "2号秒级核算",
    "3号15min聚合",
]


def run_steps_1_to_3(config: dict, logger=None) -> dict:
    """
    按顺序运行 1号、2号、3号。

    0号日报提取与0号审核由独立页面完成；这里仅复用已审核的0号输出文件。
    """
    working_config = dict(config or {})
    steps = []
    output_files = []
    config_updates = {}
    warning_steps = []
    run_label = _combine_run_label(
        str(working_config.get("pipeline_run_label", "") or "").strip(),
        _date_range_label(working_config),
    )

    def step_logger(message):
        if logger:
            logger(message)

    def run_step(step_name, func, *args, **kwargs):
        _log(step_logger, f"[进行中] {step_name}")
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            result = {"success": False, "message": str(exc), "output_files": [], "error": str(exc)}

        step_result = _step_from_result(step_name, result)
        steps.append(step_result)
        append_run_log(step_name, step_result["status"], _with_run_label(step_result["message"], run_label))
        _log(step_logger, f"[{_display_status(step_result['status'])}] {step_name}：{step_result['message']}")
        return result, step_result

    try:
        target_month = str(working_config.get("target_month", "") or "").strip()
        range_info = resolve_process_date_range(
            target_month,
            working_config.get("process_start_date", ""),
            working_config.get("process_end_date", ""),
        )
        if not range_info.get("ok"):
            raise ValueError(range_info.get("message", "处理日期范围无效"))

        process_start_date = range_info["start_date"]
        process_end_date = range_info["end_date"]
        if not is_step0_review_approved(working_config, process_start_date, process_end_date):
            raise ValueError(
                "当前0号结果尚未完成人工审核，请先前往“0号 日报提取与审核”页面确认。"
            )
        standard_paths = derive_standard_paths(working_config)
        if not standard_paths.get("data_root"):
            raise ValueError("数据项目根目录未配置，无法推导标准结果目录")
        step0_output_file = str(working_config.get("step0_output_file", "") or "").strip()

        _log(step_logger, "正在运行1号→2号→3号流程...")
        _log(step_logger, f"处理日期范围：{process_start_date} 至 {process_end_date}")

        step1_result, step1_step = run_step(
            "1号低频汇总",
            run_step1_lowfreq_update,
            step0_output_file=step0_output_file,
            history_lowfreq_file=working_config.get("history_lowfreq_file", ""),
            lowfreq_current_path=working_config.get("lowfreq_current_path", ""),
            output_dir=standard_paths["step1_output_dir"],
            target_month=target_month,
            logger=step_logger,
            process_start_date=process_start_date,
            process_end_date=process_end_date,
        )
        if not step1_step["success"]:
            return _stop_pipeline(
                steps,
                output_files,
                "1号低频汇总",
                config_updates,
                warning_steps,
                run_label,
                step_names=PIPELINE_STEP_NAMES_1_TO_3,
                pipeline_module="一键运行1-3",
            )
        output_files.extend(step1_step["output_files"])
        lowfreq_result_file = _select_output_file(
            step1_result,
            [_expected_lowfreq_name(target_month, process_end_date), "海螺水泥低频数据"],
        )
        if not lowfreq_result_file:
            return _path_identification_failed(
                steps,
                output_files,
                "1号低频汇总",
                "未能识别1号低频汇总结果文件：海螺水泥低频数据*.xlsx",
                config_updates,
                run_label,
                pipeline_module="一键运行1-3",
            )
        working_config["lowfreq_result_file"] = lowfreq_result_file
        config_updates["lowfreq_result_file"] = lowfreq_result_file

        step2_result, step2_step = run_step(
            "2号秒级核算",
            run_step2_second_calc,
            lowfreq_result_file=lowfreq_result_file,
            second_data_dir=working_config.get("second_data_dir", ""),
            result_dir=standard_paths["step2_result_dir"],
            abnormal_dir=standard_paths["step2_abnormal_dir"],
            target_month=target_month,
            logger=step_logger,
            process_start_date=process_start_date,
            process_end_date=process_end_date,
        )
        if not step2_step["success"]:
            return _stop_pipeline(
                steps,
                output_files,
                "2号秒级核算",
                config_updates,
                warning_steps,
                run_label,
                step_names=PIPELINE_STEP_NAMES_1_TO_3,
                pipeline_module="一键运行1-3",
            )
        output_files.extend(step2_step["output_files"])
        second_result_path = step2_result.get("result_dir") or _select_output_from_list(step2_step["output_files"], ["秒级CO2排放结果", "秒级碳排放"])
        abnormal_result_path = step2_result.get("abnormal_dir") or _select_output_from_list(step2_step["output_files"], ["异常检测"])
        if not second_result_path:
            return _path_identification_failed(
                steps,
                output_files,
                "2号秒级核算",
                "未能识别2号秒级核算结果文件或目录",
                config_updates,
                run_label,
                pipeline_module="一键运行1-3",
            )
        working_config["second_result_path"] = second_result_path
        working_config["abnormal_result_path"] = abnormal_result_path
        config_updates["second_result_path"] = second_result_path
        config_updates["abnormal_result_path"] = abnormal_result_path

        step3_result, step3_step = run_step(
            "3号15min聚合",
            run_step3_15min_aggregate,
            second_result_path=second_result_path,
            result_dir=standard_paths["step3_result_dir"],
            target_month=target_month,
            abnormal_result_path=abnormal_result_path,
            logger=step_logger,
            process_start_date=process_start_date,
            process_end_date=process_end_date,
        )
        if not step3_step["success"]:
            return _stop_pipeline(
                steps,
                output_files,
                "3号15min聚合",
                config_updates,
                warning_steps,
                run_label,
                step_names=PIPELINE_STEP_NAMES_1_TO_3,
                pipeline_module="一键运行1-3",
            )
        output_files.extend(step3_step["output_files"])

        message = f"1号→2号→3号流程运行完成；处理日期：{process_start_date} 至 {process_end_date}"
        append_run_log("一键运行1-3", "success", _with_run_label(message, run_label))
        _log(step_logger, message)
        return {
            "success": True,
            "message": message,
            "steps": steps,
            "output_files": output_files,
            "config_updates": config_updates,
        }
    except Exception as exc:
        message = f"1号→2号→3号流程失败：{exc}"
        append_run_log("一键运行1-3", "failed", _with_run_label(message, run_label))
        _log(step_logger, message)
        return {
            "success": False,
            "message": message,
            "steps": steps,
            "output_files": output_files,
            "config_updates": config_updates,
            "error": str(exc),
        }


def run_full_pipeline(config: dict, logger=None) -> dict:
    """
    按顺序运行完整单月流程：

    0号日报提取
    0号结果审核
    1号低频汇总
    2号秒级核算
    3号15min聚合

    参数：
        config: 从 config/app_config.json 读取的配置字典
        logger: 可选日志函数

    返回：
        {
            "success": True/False,
            "message": "...",
            "steps": [...],
            "output_files": [...]
        }
    """
    working_config = dict(config or {})
    steps = []
    output_files = []
    config_updates = {}
    warning_steps = []
    run_label = _combine_run_label(str(working_config.get("pipeline_run_label", "") or "").strip(), _date_range_label(working_config))

    def step_logger(message):
        if logger:
            logger(message)

    def run_step(step_name, func, *args, **kwargs):
        _log(step_logger, f"[进行中] {step_name}")
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            result = {"success": False, "message": str(exc), "output_files": [], "error": str(exc)}

        step_result = _step_from_result(step_name, result)
        steps.append(step_result)
        append_run_log(step_name, step_result["status"], _with_run_label(step_result["message"], run_label))
        _log(step_logger, f"[{_display_status(step_result['status'])}] {step_name}：{step_result['message']}")
        return result, step_result

    try:
        _log(step_logger, "正在运行完整流程...")
        standard_paths = derive_standard_paths(working_config)
        if not standard_paths.get("data_root"):
            raise ValueError("数据项目根目录未配置，无法推导标准结果目录")
        target_month = str(working_config.get("target_month", "") or "").strip()
        range_info = resolve_process_date_range(
            target_month,
            working_config.get("process_start_date", ""),
            working_config.get("process_end_date", ""),
        )
        process_start_date = range_info["start_date"] if range_info.get("ok") else ""
        process_end_date = range_info["end_date"] if range_info.get("ok") else ""

        step0_result, step0_step = run_step(
            "0号日报提取",
            run_step0_extract,
            report_file=working_config.get("report_file", ""),
            output_dir=standard_paths["step0_output_dir"],
            target_month=target_month,
            logger=step_logger,
            process_start_date=process_start_date,
            process_end_date=process_end_date,
        )
        if not step0_step["success"]:
            return _stop_pipeline(steps, output_files, "0号日报提取", config_updates, warning_steps, run_label)
        output_files.extend(step0_step["output_files"])
        step0_output_file = _select_output_file(step0_result, ["生产日报提取结果.xlsx", "生产日报提取结果"])
        if not step0_output_file:
            return _path_identification_failed(steps, output_files, "0号日报提取", "未能识别0号输出文件：生产日报提取结果.xlsx", config_updates, run_label)
        working_config["step0_output_file"] = step0_output_file
        config_updates["step0_output_file"] = step0_output_file

        review_result, review_step = run_step(
            "0号结果审核",
            review_step0_output,
            output_file=step0_output_file,
            target_month=target_month,
            process_start_date=process_start_date,
            process_end_date=process_end_date,
        )
        review_status = str(review_result.get("status", "") or "")
        if review_status == "warning":
            warning_steps.append("0号结果审核")
        if not review_step["success"]:
            return _stop_pipeline(steps, output_files, "0号结果审核", config_updates, warning_steps, run_label)

        step1_result, step1_step = run_step(
            "1号低频汇总",
            run_step1_lowfreq_update,
            step0_output_file=step0_output_file,
            history_lowfreq_file=working_config.get("history_lowfreq_file", ""),
            lowfreq_current_path=working_config.get("lowfreq_current_path", ""),
            output_dir=standard_paths["step1_output_dir"],
            target_month=target_month,
            logger=step_logger,
            process_start_date=process_start_date,
            process_end_date=process_end_date,
        )
        if not step1_step["success"]:
            return _stop_pipeline(steps, output_files, "1号低频汇总", config_updates, warning_steps, run_label)
        output_files.extend(step1_step["output_files"])
        lowfreq_result_file = _select_output_file(step1_result, [_expected_lowfreq_name(target_month, process_end_date), "海螺水泥低频数据"])
        if not lowfreq_result_file:
            return _path_identification_failed(steps, output_files, "1号低频汇总", "未能识别1号低频汇总结果文件：海螺水泥低频数据*.xlsx", config_updates, run_label)
        working_config["lowfreq_result_file"] = lowfreq_result_file
        config_updates["lowfreq_result_file"] = lowfreq_result_file

        step2_result, step2_step = run_step(
            "2号秒级核算",
            run_step2_second_calc,
            lowfreq_result_file=lowfreq_result_file,
            second_data_dir=working_config.get("second_data_dir", ""),
            result_dir=standard_paths["step2_result_dir"],
            abnormal_dir=standard_paths["step2_abnormal_dir"],
            target_month=target_month,
            logger=step_logger,
            process_start_date=process_start_date,
            process_end_date=process_end_date,
        )
        if not step2_step["success"]:
            return _stop_pipeline(steps, output_files, "2号秒级核算", config_updates, warning_steps, run_label)
        output_files.extend(step2_step["output_files"])
        second_result_path = step2_result.get("result_dir") or _select_output_from_list(step2_step["output_files"], ["秒级CO2排放结果", "秒级碳排放"])
        abnormal_result_path = step2_result.get("abnormal_dir") or _select_output_from_list(step2_step["output_files"], ["异常检测"])
        if not second_result_path:
            return _path_identification_failed(steps, output_files, "2号秒级核算", "未能识别2号秒级核算结果文件或目录", config_updates, run_label)
        working_config["second_result_path"] = second_result_path
        working_config["abnormal_result_path"] = abnormal_result_path
        config_updates["second_result_path"] = second_result_path
        config_updates["abnormal_result_path"] = abnormal_result_path

        step3_result, step3_step = run_step(
            "3号15min聚合",
            run_step3_15min_aggregate,
            second_result_path=second_result_path,
            result_dir=standard_paths["step3_result_dir"],
            target_month=target_month,
            abnormal_result_path=abnormal_result_path,
            logger=step_logger,
            process_start_date=process_start_date,
            process_end_date=process_end_date,
        )
        if not step3_step["success"]:
            return _stop_pipeline(steps, output_files, "3号15min聚合", config_updates, warning_steps, run_label)
        output_files.extend(step3_step["output_files"])
        fifteen_result_file = _select_output_file(step3_result, ["15min"])
        if not fifteen_result_file:
            return _path_identification_failed(steps, output_files, "3号15min聚合", "未能识别3号15min聚合结果文件", config_updates, run_label)

        if warning_steps:
            message = f"完整流程完成但存在警告：{', '.join(warning_steps)} warning"
            status = "warning"
            success = True
        else:
            message = "完整流程运行完成"
            status = "success"
            success = True

        append_run_log("一键运行", status, _with_run_label(message, run_label))
        _log(step_logger, message)
        return {
            "success": success,
            "message": message,
            "steps": steps,
            "output_files": output_files,
            "config_updates": config_updates,
        }
    except Exception as exc:
        message = f"完整流程失败：{exc}"
        append_run_log("一键运行", "failed", _with_run_label(message, run_label))
        _log(step_logger, message)
        return {
            "success": False,
            "message": message,
            "steps": steps,
            "output_files": output_files,
            "config_updates": config_updates,
            "error": str(exc),
        }


def run_step0(input_file, output_file, cell_map_path=None, cell_map=None, logger=None):
    return run_extract_report(
        input_file=input_file,
        output_file=output_file,
        cell_map_path=cell_map_path,
        cell_map=cell_map,
        logger=logger,
    )


def run_step1(
    main_file_path,
    source_folder_path,
    output_path,
    start_date,
    end_date,
    daily_extract_path=None,
    logger=None,
):
    return run_lowfreq_update(
        main_file_path=main_file_path,
        source_folder_path=source_folder_path,
        output_path=output_path,
        start_date=start_date,
        end_date=end_date,
        daily_extract_path=daily_extract_path,
        logger=logger,
    )


def run_step2(
    high_freq_base_path,
    low_freq_file_path,
    three_channel_path,
    output_result_path,
    output_abnormal_path,
    start_date,
    end_date,
    logger=None,
):
    return run_second_calc(
        high_freq_base_path=high_freq_base_path,
        low_freq_file_path=low_freq_file_path,
        three_channel_path=three_channel_path,
        output_result_path=output_result_path,
        output_abnormal_path=output_abnormal_path,
        start_date=start_date,
        end_date=end_date,
        logger=logger,
    )


def run_step3(input_folder, output_folder, start_date, end_date, logger=None):
    return run_15min_agg(
        input_folder=input_folder,
        output_folder=output_folder,
        start_date=start_date,
        end_date=end_date,
        logger=logger,
    )


def _stop_pipeline(
    steps,
    output_files,
    failed_step,
    config_updates=None,
    warning_steps=None,
    run_label="",
    step_names=None,
    pipeline_module="一键运行",
):
    _append_skipped_steps(steps, failed_step, step_names or PIPELINE_STEP_NAMES)
    message = f"完整流程失败：停止在 {failed_step}"
    append_run_log(pipeline_module, "failed", _with_run_label(message, run_label))
    return {
        "success": False,
        "message": message,
        "steps": steps,
        "output_files": output_files,
        "config_updates": config_updates or {},
        "warnings": warning_steps or [],
    }


def _append_skipped_steps(steps, failed_step, step_names=None):
    seen = {step["step"] for step in steps}
    failed_seen = False
    for step_name in step_names or PIPELINE_STEP_NAMES:
        if step_name == failed_step:
            failed_seen = True
            continue
        if failed_seen and step_name not in seen:
            steps.append(
                {
                    "step": step_name,
                    "success": False,
                    "status": "skipped",
                    "message": "前序步骤失败，已跳过",
                    "output_files": [],
                }
            )


def _step_from_result(step_name, result):
    raw_status = str(result.get("status", "") or "").strip().lower()
    success = bool(result.get("success"))
    if raw_status in {"warning"}:
        status = "warning"
    elif raw_status in {"passed"}:
        status = "success"
    elif success:
        status = "success"
    else:
        status = "failed"
    return {
        "step": step_name,
        "success": status in {"success", "warning"},
        "status": status,
        "message": str(result.get("message", "") or ""),
        "output_files": list(result.get("output_files", []) or []),
    }


def _first_output_file(result):
    output_files = result.get("output_files", []) or []
    return str(output_files[0]) if output_files else ""


def _select_output_file(result, patterns):
    return _select_output_from_list(result.get("output_files", []) or [], patterns)


def _select_output_from_list(output_files, patterns):
    normalized_patterns = [str(pattern).lower() for pattern in patterns if pattern]
    excel_outputs = [str(output_file) for output_file in output_files or [] if str(output_file).lower().endswith((".xlsx", ".xls"))]
    for output_file in excel_outputs:
        lower_name = Path(output_file).name.lower()
        if all(pattern in lower_name for pattern in normalized_patterns[:1]):
            return output_file
    for output_file in excel_outputs:
        lower_name = Path(output_file).name.lower()
        if any(pattern in lower_name for pattern in normalized_patterns):
            return output_file
    return excel_outputs[0] if excel_outputs else _first_matching_output(output_files, patterns[0] if patterns else "")


def _first_matching_output(output_files, text):
    for output_file in output_files or []:
        if text in str(output_file):
            return str(output_file)
    return str(output_files[0]) if output_files else ""


def _expected_lowfreq_name(target_month, end_date=""):
    if str(end_date or "").strip():
        return f"海螺水泥低频数据_{end_date}"
    if not str(target_month or "").strip():
        return ""
    try:
        import calendar

        year_text, month_text = str(target_month).split("-", 1)
        year = int(year_text)
        month = int(month_text)
        last_day = calendar.monthrange(year, month)[1]
        return f"海螺水泥低频数据_{year:04d}-{month:02d}-{last_day:02d}"
    except Exception:
        return ""


def _path_identification_failed(steps, output_files, step_name, message, config_updates=None, run_label="", pipeline_module="一键运行"):
    steps.append(
        {
            "step": f"{step_name}输出识别",
            "success": False,
            "status": "failed",
            "message": message,
            "output_files": [],
        }
    )
    append_run_log(step_name, "failed", _with_run_label(message, run_label))
    append_run_log(pipeline_module, "failed", _with_run_label(f"完整流程失败：停止在 {step_name}输出识别", run_label))
    return {
        "success": False,
        "message": f"完整流程失败：停止在 {step_name}输出识别",
        "steps": steps,
        "output_files": output_files,
        "config_updates": config_updates or {},
    }


def _with_run_label(message, run_label):
    return f"{message}（{run_label}）" if run_label else message


def _date_range_label(config):
    range_info = resolve_process_date_range(
        str((config or {}).get("target_month", "") or "").strip(),
        (config or {}).get("process_start_date", ""),
        (config or {}).get("process_end_date", ""),
    )
    if range_info.get("ok"):
        return f"处理日期：{range_info['start_date']} 至 {range_info['end_date']}"
    return ""


def _combine_run_label(*parts):
    clean_parts = [str(part).strip() for part in parts if str(part or "").strip()]
    return "；".join(clean_parts)


def _display_status(status):
    return {
        "success": "成功",
        "warning": "警告",
        "failed": "失败",
        "skipped": "跳过",
    }.get(status, status)


def _log(logger, message):
    if logger:
        logger(message)
