from pathlib import Path
from datetime import datetime

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.pipeline_worker import PipelineWorker, STEP_LABELS
from ui.run_guards import confirm_pipeline_run
from utils.config_utils import is_step0_review_approved, load_config, save_config
from utils.date_range_utils import resolve_process_date_range
from utils.path_utils import is_existing_dir, is_existing_file, normalize_path
from utils.preflight_utils import (
    build_production_preflight_report,
    save_preflight_report_text,
)
from utils.standard_paths import derive_standard_paths


class RunPipelinePage(QWidget):
    navigate_to_config = Signal()

    def __init__(self):
        super().__init__()
        self.config = {}
        self.summary_labels = {}
        self.status_box = QPlainTextEdit()
        self.run_button = QPushButton("开始一键运行")
        self.flow_text = QLabel()
        self.current_step_label = QLabel("未开始")
        self.current_date_label = QLabel("-")
        self.day_progress_label = QLabel("已完成 0 / 0 天")
        self.progress_bar = QProgressBar()
        self.step_states = {1: "pending", 2: "pending", 3: "pending"}
        self.worker_thread = None
        self.worker = None
        self.detail_log_path = ""
        self.preflight_report = None
        self.preflight_report_text = ""
        self._build_ui()
        self.reload_config(show_message=False)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 34, 36, 34)
        layout.setSpacing(18)

        title = QLabel("一键运行")
        title.setObjectName("PageTitle")

        body = QLabel(
            "当前支持单月内指定日期范围处理。一键运行只按顺序执行 1号低频汇总、"
            "2号秒级核算和3号15min聚合；0号日报提取与审核需要先在0号页面独立完成。"
            "结果会直接写入数据项目的标准目录；若同名文件已存在，软件会在运行前明确询问是否覆盖。"
        )
        body.setObjectName("BodyText")
        body.setWordWrap(True)

        summary = QFrame()
        summary.setObjectName("InfoCard")
        summary_layout = QGridLayout(summary)
        summary_layout.setContentsMargins(18, 16, 18, 16)
        summary_layout.setHorizontalSpacing(18)
        summary_layout.setVerticalSpacing(10)
        rows = [
            ("target_month", "处理月份"),
            ("date_range", "处理日期"),
            ("project_config", "项目配置"),
            ("step0_output", "0号日报提取"),
            ("step0_review", "0号结果审核"),
            ("result_locations", "结果位置"),
        ]
        for row_index, (key, label_text) in enumerate(rows):
            summary_layout.addWidget(QLabel(label_text), row_index, 0)
            value = QLabel("-")
            value.setObjectName("CardText")
            value.setWordWrap(True)
            self.summary_labels[key] = value
            summary_layout.addWidget(value, row_index, 1)
        config_button = QPushButton("前往项目配置")
        config_button.clicked.connect(self.navigate_to_config.emit)
        summary_layout.addWidget(config_button, 0, 2, 2, 1)

        flow_frame = QFrame()
        flow_frame.setObjectName("InfoCard")
        flow_layout = QVBoxLayout(flow_frame)
        flow_layout.setContentsMargins(18, 14, 18, 14)
        flow_title = QLabel("一键运行流程")
        flow_title.setObjectName("CardTitle")
        self.flow_text.setObjectName("CardText")
        flow_layout.addWidget(flow_title)
        flow_layout.addWidget(self.flow_text)
        self._render_flow_states()

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        check_button = QPushButton("检查运行前配置")
        check_button.clicked.connect(self.check_before_run)
        self.run_button.clicked.connect(self.run_pipeline)
        button_row.addWidget(check_button)
        button_row.addWidget(self.run_button)
        button_row.addStretch(1)

        preflight_frame = QFrame()
        preflight_frame.setObjectName("InfoCard")
        preflight_layout = QVBoxLayout(preflight_frame)
        preflight_layout.setContentsMargins(18, 14, 18, 14)
        preflight_layout.setSpacing(10)

        preflight_title = QLabel("正式运行前检查")
        preflight_title.setObjectName("CardTitle")
        preflight_body = QLabel(
            "一键运行前，建议先生成检查清单，确认日期范围、0号审核状态、输入文件、标准结果目录和覆盖风险。"
            "该检查只读取配置和路径，不执行 1/2/3 业务计算。"
        )
        preflight_body.setObjectName("MutedText")
        preflight_body.setWordWrap(True)

        preflight_button_row = QHBoxLayout()
        preflight_button_row.setSpacing(10)
        generate_preflight_button = QPushButton("生成正式运行检查清单")
        save_preflight_button = QPushButton("保存检查清单")
        generate_preflight_button.clicked.connect(self.generate_preflight_report)
        save_preflight_button.clicked.connect(self.save_preflight_report)
        preflight_button_row.addWidget(generate_preflight_button)
        preflight_button_row.addWidget(save_preflight_button)
        preflight_button_row.addStretch(1)

        preflight_layout.addWidget(preflight_title)
        preflight_layout.addWidget(preflight_body)
        preflight_layout.addLayout(preflight_button_row)

        progress_frame = QFrame()
        progress_frame.setObjectName("InfoCard")
        progress_layout = QGridLayout(progress_frame)
        progress_layout.setContentsMargins(18, 14, 18, 14)
        progress_layout.setHorizontalSpacing(18)
        progress_layout.setVerticalSpacing(10)

        progress_title = QLabel("当前进度")
        progress_title.setObjectName("CardTitle")
        progress_layout.addWidget(progress_title, 0, 0, 1, 2)
        progress_layout.addWidget(QLabel("当前步骤"), 1, 0)
        self.current_step_label.setObjectName("CardText")
        progress_layout.addWidget(self.current_step_label, 1, 1)
        progress_layout.addWidget(QLabel("当前处理"), 2, 0)
        self.current_date_label.setObjectName("CardText")
        progress_layout.addWidget(self.current_date_label, 2, 1)
        progress_layout.addWidget(QLabel("整体进度"), 3, 0)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar, 3, 1)
        self.day_progress_label.setObjectName("CardText")
        progress_layout.addWidget(self.day_progress_label, 4, 1)

        status_title = QLabel("运行信息")
        status_title.setObjectName("CardTitle")

        self.status_box.setReadOnly(True)
        self.status_box.setMinimumHeight(170)
        self.status_box.setPlainText("等待一键运行")

        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(summary)
        layout.addWidget(flow_frame)
        layout.addWidget(preflight_frame)
        layout.addLayout(button_row)
        layout.addWidget(progress_frame)
        layout.addWidget(status_title)
        layout.addWidget(self.status_box)
        layout.addStretch(1)

        self.setStyleSheet(
            """
            QPushButton {
                border: 1px solid #c8c8c8;
                border-radius: 4px;
                padding: 7px 12px;
                color: #222222;
                background: #f4f4f4;
            }
            QPushButton:hover {
                background: #e8e8e8;
            }
            QPushButton:disabled {
                color: #888888;
                background: #eeeeee;
            }
            QPlainTextEdit {
                border: 1px solid #d6d6d6;
                border-radius: 4px;
                padding: 8px;
                color: #333333;
                background: #fbfbfb;
            }
            """
        )

    def reload_config(self, show_message=True):
        try:
            self.config = load_config()
            range_info = resolve_process_date_range(
                self.config.get("target_month", ""),
                self.config.get("process_start_date", ""),
                self.config.get("process_end_date", ""),
            )
            self.summary_labels["target_month"].setText(self.config.get("target_month") or "未配置")
            self.summary_labels["date_range"].setText(
                f"{range_info['start_date']} 至 {range_info['end_date']}" if range_info.get("ok") else "未配置或无效"
            )
            config_complete = self._project_config_complete(self.config)
            self.summary_labels["project_config"].setText("已完成" if config_complete else "不完整，请前往项目配置")
            step0_file = str(self.config.get("step0_output_file", "") or "").strip()
            self.summary_labels["step0_output"].setText(
                f"已完成：{Path(step0_file).name}" if step0_file and is_existing_file(step0_file) else "未完成"
            )
            self.summary_labels["step0_output"].setToolTip(step0_file)
            if self.config.get("step0_needs_rerun"):
                review_text = "已失效，需要重新运行并人工审核"
            elif range_info.get("ok") and is_step0_review_approved(
                self.config, range_info["start_date"], range_info["end_date"]
            ):
                review_text = "人工审核通过"
            else:
                review_text = "待人工审核"
            self.summary_labels["step0_review"].setText(review_text)
            paths = derive_standard_paths(self.config)
            locations = (
                f"1号 → {paths.get('step1_output_dir', '')}\n"
                f"2号 → {paths.get('step2_result_dir', '')}\n"
                f"异常 → {paths.get('step2_abnormal_dir', '')}\n"
                f"3号 → {paths.get('step3_result_dir', '')}"
            )
            self.summary_labels["result_locations"].setText(locations)
            self.summary_labels["result_locations"].setToolTip(locations)
            if show_message:
                self._set_status("已重新读取一键运行配置")
        except Exception as exc:
            self._set_status(f"一键运行配置读取失败：{exc}")

    def refresh_from_config(self):
        self.reload_config(show_message=False)

    def check_before_run(self):
        self.reload_config(show_message=False)
        ok, lines = self._check_config(self.config)
        prefix = "运行前配置检查通过" if ok else "运行前配置检查未通过"
        self._set_status(prefix + "\n\n" + "\n".join(lines))
        return ok

    def generate_preflight_report(self):
        self.reload_config(show_message=False)
        self.preflight_report = build_production_preflight_report(self.config)
        self.preflight_report_text = self.preflight_report.get("report_text", "")
        self._set_status(self.preflight_report_text)
        return self.preflight_report

    def save_preflight_report(self):
        try:
            if not self.preflight_report_text:
                self.generate_preflight_report()
            saved_path = save_preflight_report_text(self.preflight_report_text)
            self._set_status(f"{self.preflight_report_text}\n\n检查清单已保存：{saved_path}")
        except Exception as exc:
            self._set_status(f"保存检查清单失败：{exc}")

    def run_pipeline(self):
        if self.worker_thread and self.worker_thread.isRunning():
            self._append_summary("一键运行正在进行，请勿重复启动")
            return
        self.reload_config(show_message=False)
        ok, lines = self._check_config(self.config)
        if not ok:
            self._set_status("运行前配置检查未通过，已停止。\n\n" + "\n".join(lines))
            return

        preflight = build_production_preflight_report(self.config)
        self.preflight_report = preflight
        self.preflight_report_text = preflight.get("report_text", "")
        if preflight.get("status") == "failed":
            self._set_status(
                f"{self.preflight_report_text}\n\n当前配置未通过正式运行检查，不建议开始一键运行。流程已停止。"
            )
            return
        if preflight.get("status") == "warning" and not self._confirm_preflight_warning(preflight):
            self._set_status(f"{self.preflight_report_text}\n\n已取消运行。")
            return

        range_info = resolve_process_date_range(
            self.config.get("target_month", ""),
            self.config.get("process_start_date", ""),
            self.config.get("process_end_date", ""),
        )
        target_month = str(self.config.get("target_month", "") or "").strip()
        if not confirm_pipeline_run(
            self,
            target_month=target_month,
            process_start_date=range_info.get("start_date", ""),
            process_end_date=range_info.get("end_date", ""),
            config=self.config,
        ):
            self._set_status("已取消运行。")
            return

        self._start_pipeline_worker(range_info)

    def _start_pipeline_worker(self, range_info):
        self.step_states = {1: "pending", 2: "pending", 3: "pending"}
        self._render_flow_states()
        self.current_step_label.setText("准备运行")
        self.current_date_label.setText("-")
        self.progress_bar.setValue(0)
        self.day_progress_label.setText(f"已完成 0 / {range_info.get('days', 0)} 天")
        self.status_box.clear()
        self._append_summary("开始一键运行1号→2号→3号")
        self.detail_log_path = ""
        self.run_button.setEnabled(False)
        self.run_button.setText("运行中…")

        self.worker_thread = QThread(self)
        self.worker = PipelineWorker(self.config)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.step_changed.connect(self._on_step_changed)
        self.worker.date_changed.connect(self._on_date_changed)
        self.worker.progress_changed.connect(self.progress_bar.setValue)
        self.worker.day_progress_changed.connect(self._on_day_progress_changed)
        self.worker.summary_log.connect(self._append_summary)
        self.worker.detail_log_ready.connect(self._on_detail_log_ready)
        self.worker.finished.connect(self._on_pipeline_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self._on_worker_thread_finished)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.start()

    def _on_step_changed(self, step, status):
        if step not in self.step_states:
            return
        if status == "running":
            for previous_step in range(1, step):
                if self.step_states[previous_step] != "failed":
                    self.step_states[previous_step] = "done"
        self.step_states[step] = status
        self.current_step_label.setText(STEP_LABELS.get(step, "-"))
        self._render_flow_states()

    def _on_date_changed(self, date_text):
        self.current_date_label.setText(date_text or "-")

    def _on_day_progress_changed(self, completed, total):
        self.day_progress_label.setText(f"已完成 {completed} / {total} 天")

    def _on_detail_log_ready(self, path):
        self.detail_log_path = str(path or "")

    def _on_pipeline_finished(self, result):
        try:
            self._save_pipeline_updates(result.get("config_updates", {}))
            self.reload_config(show_message=False)
        except Exception as exc:
            self._append_summary(f"配置更新失败：{exc}")

        if result.get("success"):
            self.step_states = {1: "done", 2: "done", 3: "done"}
            self._render_flow_states()
            self.current_step_label.setText("运行完成")
            self.progress_bar.setValue(100)
            self._append_summary(f"结果文件共 {len(result.get('output_files', []) or [])} 个")
        else:
            failed_step = int(result.get("failed_step", 0) or 0)
            if failed_step in self.step_states:
                self.step_states[failed_step] = "failed"
                self.current_step_label.setText(f"{STEP_LABELS[failed_step]}失败")
            self._render_flow_states()
            failed_date = str(result.get("failed_date", "") or "")
            if failed_date:
                self.current_date_label.setText(failed_date)
                self._append_summary(f"失败日期：{failed_date}")
            self._append_summary(f"错误摘要：{result.get('error') or result.get('message', '未知错误')}")
        detail_path = str(result.get("detail_log_path", "") or self.detail_log_path)
        if detail_path:
            self._append_summary(f"完整技术日志：{detail_path}")

    def _on_worker_thread_finished(self):
        self.run_button.setEnabled(True)
        self.run_button.setText("开始一键运行")
        self.worker = None
        self.worker_thread = None

    def _render_flow_states(self):
        symbol = {"pending": "○", "running": "●", "done": "✓", "failed": "✕"}
        self.flow_text.setText(
            "\n".join(
                f"{symbol.get(self.step_states[step], '○')} {STEP_LABELS[step]}"
                for step in (1, 2, 3)
            )
        )

    def _append_summary(self, message):
        timestamp = datetime.now().strftime("%H:%M")
        line = f"{timestamp}  {' '.join(str(message or '').split())}"
        current_lines = self.status_box.toPlainText().splitlines()
        if len(current_lines) >= 100:
            self.status_box.setPlainText("\n".join(current_lines[-79:]))
        self.status_box.appendPlainText(line)

    def _check_config(self, config):
        lines = []
        ok = True

        target_month = str(config.get("target_month", "") or "").strip()
        range_info = resolve_process_date_range(
            target_month,
            config.get("process_start_date", ""),
            config.get("process_end_date", ""),
        )
        if not target_month:
            ok = False
            lines.append("处理月份：未填写")
        elif range_info.get("ok"):
            lines.append(f"处理月份：{range_info['target_month']}")
            lines.append(f"处理日期范围：{range_info['start_date']} 至 {range_info['end_date']}，共{range_info['days']}天")
        else:
            ok = False
            lines.append(f"处理日期范围：无效 - {range_info.get('message', '')}")

        report_file = str(config.get("report_file", "") or "").strip()
        normalized_report = normalize_path(report_file) if report_file else ""
        if normalized_report and is_existing_file(normalized_report):
            lines.append("生产综合日报文件：存在")
        else:
            ok = False
            lines.append(f"生产综合日报文件：不存在或未配置 - {normalized_report or '空'}")

        step0_output_file = str(config.get("step0_output_file", "") or "").strip()
        normalized_step0 = normalize_path(step0_output_file) if step0_output_file else ""
        if normalized_step0 and is_existing_file(normalized_step0):
            lines.append(f"0号输出文件：存在 - {normalized_step0}")
        else:
            ok = False
            lines.append("0号输出文件：不存在或未配置，请先进入“0号 日报提取与审核”页面运行并审核0号结果")

        review_status = str(config.get("step0_review_status", "") or "").strip().lower()
        review_start = str(config.get("step0_review_start_date", "") or "").strip()
        review_end = str(config.get("step0_review_end_date", "") or "").strip()
        if config.get("step0_needs_rerun"):
            ok = False
            lines.append("0号人工审核：项目配置已变化，需要重新运行0号并确认人工审核")
        elif review_status != "approved":
            ok = False
            lines.append(
                "当前0号结果尚未完成人工审核，请先前往“0号 日报提取与审核”页面确认。"
            )
        elif not range_info.get("ok") or not is_step0_review_approved(
            config, range_info.get("start_date", ""), range_info.get("end_date", "")
        ):
            ok = False
            lines.append(
                "0号人工审核范围不一致，"
                f"当前{range_info.get('start_date', '未记录')}至{range_info.get('end_date', '未记录')}，"
                f"上次人工审核{review_start or '未记录'}至{review_end or '未记录'}"
            )
        else:
            lines.append("0号人工审核：审核通过")

        required_files = [
            ("history_lowfreq_file", "历史低频主表"),
        ]
        for key, label in required_files:
            value = str(config.get(key, "") or "").strip()
            normalized = normalize_path(value) if value else ""
            if normalized and is_existing_file(normalized):
                lines.append(f"{label}：存在")
            else:
                ok = False
                lines.append(f"{label}：不存在或未选择 - {normalized or '空'}")

        current_path = str(config.get("lowfreq_current_path", "") or "").strip()
        normalized_current = normalize_path(current_path) if current_path else ""
        if normalized_current and Path(normalized_current).exists():
            lines.append("当月低频数据：存在")
        else:
            ok = False
            lines.append(f"当月低频数据：不存在或未选择 - {normalized_current or '空'}")

        second_data_dir = str(config.get("second_data_dir", "") or "").strip()
        normalized_second_dir = normalize_path(second_data_dir) if second_data_dir else ""
        if normalized_second_dir and is_existing_dir(normalized_second_dir):
            lines.append("秒级 / 高频数据目录：存在")
        else:
            ok = False
            lines.append(f"秒级 / 高频数据目录：不存在或不是文件夹 - {normalized_second_dir or '空'}")

        paths = derive_standard_paths(config)
        if not paths.get("data_root"):
            ok = False
            lines.append("标准结果目录：数据项目根目录未配置")
        else:
            lines.extend(
                [
                    f"1号结果目录：{paths['step1_output_dir']}",
                    f"2号结果目录：{paths['step2_result_dir']}",
                    f"异常结果目录：{paths['step2_abnormal_dir']}",
                    f"3号结果目录：{paths['step3_result_dir']}",
                ]
            )

        return ok, lines

    @staticmethod
    def _project_config_complete(config):
        file_ok = is_existing_file(config.get("report_file", "")) and is_existing_file(
            config.get("history_lowfreq_file", "")
        )
        dir_ok = is_existing_dir(config.get("lowfreq_current_path", "")) and is_existing_dir(
            config.get("second_data_dir", "")
        )
        range_info = resolve_process_date_range(
            config.get("target_month", ""), config.get("process_start_date", ""), config.get("process_end_date", "")
        )
        return bool(file_ok and dir_ok and range_info.get("ok") and str(config.get("data_root", "") or "").strip())

    def _save_pipeline_updates(self, updates):
        if not updates:
            return
        config = load_config()
        config.update({key: value for key, value in updates.items() if value})
        save_config(config)

    def _format_pipeline_result(self, result):
        lines = []
        for step in result.get("steps", []):
            status_text = self._display_status(step.get("status", ""))
            lines.append(f"[{status_text}] {step.get('step', '')}：{step.get('message', '')}")

        output_files = result.get("output_files", []) or []
        if output_files:
            lines.append("")
            lines.append("输出文件：")
            lines.extend(str(path) for path in output_files[:40])
            if len(output_files) > 40:
                lines.append(f"... 另有 {len(output_files) - 40} 个文件")

        lines.append("")
        lines.append(result.get("message", "一键运行结束"))
        if not result.get("success"):
            lines.append("流程已停止。")
        return "\n".join(lines)

    def _display_status(self, status):
        return {
            "success": "成功",
            "warning": "警告",
            "failed": "失败",
            "skipped": "跳过",
        }.get(status, str(status))

    def _confirm_preflight_warning(self, preflight):
        message = (
            "当前配置存在警告，请确认后再运行。\n\n"
            "建议先生成并保存正式运行检查清单，确认输入路径和覆盖风险后再运行。\n\n"
            f"{preflight.get('message', '')}\n\n是否继续？"
        )
        reply = QMessageBox.question(
            self,
            "正式运行检查存在警告",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _set_status(self, message):
        self.status_box.setPlainText(str(message))
