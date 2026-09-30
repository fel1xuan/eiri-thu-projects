import re
from datetime import datetime

from PySide6.QtCore import QObject, Signal, Slot

from core.pipeline import run_steps_1_to_3
from utils.date_range_utils import resolve_process_date_range
from utils.log_utils import append_text_log, create_pipeline_detail_log, format_exception


STEP_LABELS = {
    1: "1号 低频汇总",
    2: "2号 秒级核算与异常检测",
    3: "3号 15min聚合",
}


class PipelineProgressTracker:
    """Turn existing core log messages into a small set of user-facing events."""

    def __init__(self, total_days):
        self.total_days = max(int(total_days or 0), 1)
        self.current_step = 0
        self.current_date = ""
        self.completed_dates = {2: set(), 3: set()}

    def consume(self, message):
        text = str(message or "").strip()
        events = []

        step = self._step_from_pipeline_message(text)
        if step:
            status = self._status_from_pipeline_message(text)
            if status:
                self.current_step = step
                events.append({"type": "step", "step": step, "status": status})
                if status == "running":
                    events.extend(self._step_started_events(step))
                elif status in {"done", "failed"}:
                    events.extend(self._step_finished_events(step, status, text))
                return events

        date_text = self._extract_date(text)
        if text.startswith("[2号] 正在处理日期：") and date_text:
            self.current_step = 2
            self.current_date = date_text
            return [{"type": "date", "date": date_text}]
        if text.startswith("[2号] 秒级结果保存：") and date_text:
            return self._complete_day(2, date_text, skipped=False)
        if text.startswith("[2号] 日期 ") and "跳过处理" in text and date_text:
            return self._complete_day(2, date_text, skipped=True)

        if text.startswith("[3号] 正在处理：") and date_text:
            self.current_step = 3
            self.current_date = date_text
            return [{"type": "date", "date": date_text}]
        if text.startswith("[3号] 处理完成：") and date_text:
            return self._complete_day(3, date_text, skipped=False)
        if text.startswith("[3号] ") and "跳过该日期" in text and date_text:
            return self._complete_day(3, date_text, skipped=True)

        if any(token in text for token in ("警告", "失败", "错误")):
            events.append({"type": "summary", "message": self._shorten(text)})
        return events

    def mark_result_failure(self, result):
        steps = result.get("steps", []) if isinstance(result, dict) else []
        failed_step = 0
        message = str(result.get("message", "一键运行失败") if isinstance(result, dict) else result)
        for item in reversed(steps):
            if item.get("status") == "failed" or not item.get("success", True):
                failed_step = self._step_from_name(item.get("step", ""))
                message = str(item.get("message", message))
                break
        failed_step = failed_step or self.current_step or 1
        return failed_step, self.current_date, self._shorten(message)

    def _step_started_events(self, step):
        self.completed_dates.setdefault(step, set()).clear()
        events = [
            {"type": "summary", "message": f"开始{STEP_LABELS[step]}"},
            {"type": "day_progress", "completed": 0, "total": self.total_days},
        ]
        if step == 1:
            events.append({"type": "progress", "value": 0})
        elif step == 2:
            events.append({"type": "progress", "value": 10})
        else:
            events.append({"type": "progress", "value": 80})
        return events

    def _step_finished_events(self, step, status, text):
        if status == "done":
            progress = {1: 10, 2: 80, 3: 100}[step]
            return [
                {"type": "progress", "value": progress},
                {"type": "summary", "message": f"{STEP_LABELS[step]}完成"},
            ]
        return [{"type": "summary", "message": self._shorten(text)}]

    def _complete_day(self, step, date_text, skipped):
        dates = self.completed_dates.setdefault(step, set())
        if date_text in dates:
            return []
        dates.add(date_text)
        self.current_date = date_text
        completed = len(dates)
        if step == 2:
            progress = 10 + round(70 * completed / self.total_days)
        else:
            progress = 80 + round(20 * completed / self.total_days)
        progress = min(progress, 80 if step == 2 else 100)
        suffix = "跳过" if skipped else "完成"
        return [
            {"type": "date", "date": date_text},
            {"type": "day_progress", "completed": completed, "total": self.total_days},
            {"type": "progress", "value": progress},
            {"type": "summary", "message": f"{date_text} {suffix}"},
        ]

    @staticmethod
    def _extract_date(text):
        match = re.search(r"\d{4}-\d{2}-\d{2}", text)
        return match.group(0) if match else ""

    @staticmethod
    def _shorten(text, limit=220):
        compact = " ".join(str(text or "").split())
        return compact if len(compact) <= limit else compact[: limit - 3] + "..."

    @classmethod
    def _step_from_pipeline_message(cls, text):
        if not text.startswith(("[进行中]", "[成功]", "[警告]", "[失败]")):
            return 0
        return cls._step_from_name(text)

    @staticmethod
    def _step_from_name(text):
        value = str(text or "")
        if "1号低频汇总" in value:
            return 1
        if "2号秒级核算" in value:
            return 2
        if "3号15min聚合" in value:
            return 3
        return 0

    @staticmethod
    def _status_from_pipeline_message(text):
        if text.startswith("[进行中]"):
            return "running"
        if text.startswith(("[成功]", "[警告]")):
            return "done"
        if text.startswith("[失败]"):
            return "failed"
        return ""


class PipelineWorker(QObject):
    step_changed = Signal(int, str)
    date_changed = Signal(str)
    progress_changed = Signal(int)
    day_progress_changed = Signal(int, int)
    summary_log = Signal(str)
    detail_log_ready = Signal(str)
    finished = Signal(object)

    def __init__(self, config, runner=None):
        super().__init__()
        self.config = dict(config or {})
        self.runner = runner or run_steps_1_to_3
        range_info = resolve_process_date_range(
            self.config.get("target_month", ""),
            self.config.get("process_start_date", ""),
            self.config.get("process_end_date", ""),
        )
        self.tracker = PipelineProgressTracker(range_info.get("days", 0))
        self.detail_log_path = ""

    @Slot()
    def run(self):
        self.detail_log_path = create_pipeline_detail_log()
        self.detail_log_ready.emit(self.detail_log_path)
        append_text_log(self.detail_log_path, "开始一键运行1号→2号→3号完整技术日志")
        try:
            result = self.runner(self.config, logger=self._handle_core_log)
            if not isinstance(result, dict):
                raise TypeError("一键运行返回结果格式无效")
        except Exception as exc:
            append_text_log(self.detail_log_path, format_exception(exc), level="ERROR")
            result = {
                "success": False,
                "message": f"一键运行失败：{exc}",
                "steps": [],
                "output_files": [],
                "config_updates": {},
                "error": str(exc),
            }

        result = dict(result)
        result["detail_log_path"] = self.detail_log_path
        if result.get("success"):
            self.progress_changed.emit(100)
            self.summary_log.emit("全部运行完成")
            append_text_log(self.detail_log_path, "全部运行完成", level="SUCCESS")
        else:
            step, date_text, message = self.tracker.mark_result_failure(result)
            self.step_changed.emit(step, "failed")
            if date_text:
                self.date_changed.emit(date_text)
            self.summary_log.emit(f"运行失败：{message}")
            append_text_log(self.detail_log_path, message, level="ERROR")
            result["failed_step"] = step
            result["failed_date"] = date_text
        self.finished.emit(result)

    def _handle_core_log(self, message):
        append_text_log(self.detail_log_path, message)
        for event in self.tracker.consume(message):
            event_type = event["type"]
            if event_type == "step":
                self.step_changed.emit(event["step"], event["status"])
            elif event_type == "date":
                self.date_changed.emit(event["date"])
            elif event_type == "progress":
                self.progress_changed.emit(event["value"])
            elif event_type == "day_progress":
                self.day_progress_changed.emit(event["completed"], event["total"])
            elif event_type == "summary":
                self.summary_log.emit(event["message"])
