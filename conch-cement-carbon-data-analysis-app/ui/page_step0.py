from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from core.step0_extract_report import run_step0_extract
from core.step0_review import review_step0_output
from ui.run_guards import confirm_step_run
from utils.config_utils import clear_step0_review_state, is_step0_review_approved, load_config, save_config
from utils.date_range_utils import resolve_process_date_range
from utils.log_utils import append_run_log, format_exception
from utils.path_utils import ensure_dir, is_existing_file, normalize_path, open_path
from utils.standard_paths import derive_standard_paths
from utils.step0_preview import load_step0_preview
from utils.table_models import PandasTableModel


class Step0Page(QWidget):
    navigate_to_config = Signal()

    def __init__(self):
        super().__init__()
        self.config = {}
        self.summary_labels = {}
        self.status_box = QPlainTextEdit()
        self.review_status_box = QPlainTextEdit()
        self.preview_model = PandasTableModel()
        self.preview_table = QTableView()
        self.preview_file_label = QLabel("结果文件：未生成")
        self.preview_meta_label = QLabel("数据范围：-    记录数：0    字段数：0")
        self.preview_message_label = QLabel("当前月份尚未生成0号结果。请先运行“0号日报提取”。")
        self.preview_review_label = QLabel("自动检查：未完成    人工审核：待审核")
        self.preview_data = None
        self.latest_auto_check = None
        self._build_ui()
        self.reload_config(show_message=False)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 34, 36, 34)
        layout.setSpacing(16)

        title = QLabel("0号 日报提取与审核")
        title.setObjectName("PageTitle")
        body = QLabel("按项目配置中的日期范围提取生产综合日报，并在同一页面审核0号结果。详细路径统一在“项目配置”中维护。")
        body.setObjectName("BodyText")
        body.setWordWrap(True)

        summary = QFrame()
        summary.setObjectName("InfoCard")
        grid = QGridLayout(summary)
        grid.setContentsMargins(18, 15, 18, 15)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(9)
        fields = [
            ("target_month", "处理月份"),
            ("date_range", "处理日期"),
            ("report_file", "生产日报"),
            ("step0_output", "0号结果位置"),
        ]
        for row, (key, label_text) in enumerate(fields):
            grid.addWidget(QLabel(label_text), row, 0)
            value = QLabel("-")
            value.setObjectName("CardText")
            value.setWordWrap(True)
            self.summary_labels[key] = value
            grid.addWidget(value, row, 1)
        config_button = QPushButton("前往项目配置")
        config_button.clicked.connect(self.navigate_to_config.emit)
        grid.addWidget(config_button, 0, 2, 2, 1)

        extract_card = QFrame()
        extract_card.setObjectName("InfoCard")
        extract_layout = QVBoxLayout(extract_card)
        extract_layout.setContentsMargins(18, 15, 18, 15)
        extract_title = QLabel("0号日报提取")
        extract_title.setObjectName("CardTitle")
        run_button = QPushButton("运行0号日报提取")
        run_button.clicked.connect(self.run_extract)
        row = QHBoxLayout()
        row.addWidget(run_button)
        row.addStretch(1)
        self.status_box.setReadOnly(True)
        self.status_box.setMinimumHeight(125)
        self.status_box.setPlainText("等待运行0号日报提取")
        extract_layout.addWidget(extract_title)
        extract_layout.addLayout(row)
        extract_layout.addWidget(self.status_box)

        preview_card = QFrame()
        preview_card.setObjectName("InfoCard")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(18, 15, 18, 15)
        preview_layout.setSpacing(10)
        preview_header = QHBoxLayout()
        preview_title = QLabel("0号结果预览")
        preview_title.setObjectName("CardTitle")
        refresh_preview_button = QPushButton("刷新预览")
        open_result_button = QPushButton("打开结果文件")
        refresh_preview_button.clicked.connect(self.refresh_preview)
        open_result_button.clicked.connect(self.open_result_file)
        preview_header.addWidget(preview_title)
        preview_header.addStretch(1)
        preview_header.addWidget(refresh_preview_button)
        preview_header.addWidget(open_result_button)

        self.preview_file_label.setObjectName("CardText")
        self.preview_file_label.setWordWrap(True)
        self.preview_file_label.setTextInteractionFlags(self.preview_file_label.textInteractionFlags())
        self.preview_meta_label.setObjectName("CardText")
        self.preview_review_label.setObjectName("CardText")
        self.preview_message_label.setObjectName("MutedText")
        self.preview_message_label.setWordWrap(True)

        self.preview_table.setModel(self.preview_model)
        self.preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.preview_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.verticalHeader().setDefaultSectionSize(28)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.preview_table.horizontalHeader().setMinimumSectionSize(90)
        self.preview_table.horizontalHeader().setDefaultSectionSize(150)
        self.preview_table.setMinimumHeight(310)

        preview_layout.addLayout(preview_header)
        preview_layout.addWidget(self.preview_file_label)
        preview_layout.addWidget(self.preview_meta_label)
        preview_layout.addWidget(self.preview_review_label)
        preview_layout.addWidget(self.preview_message_label)
        preview_layout.addWidget(self.preview_table)

        review_card = QFrame()
        review_card.setObjectName("InfoCard")
        review_layout = QVBoxLayout(review_card)
        review_layout.setContentsMargins(18, 15, 18, 15)
        review_title = QLabel("0号结果审核")
        review_title.setObjectName("CardTitle")
        self.output_file_label = QLabel("当前结果文件：未配置")
        self.output_file_label.setObjectName("CardText")
        self.output_file_label.setWordWrap(True)
        review_button = QPushButton("确认审核通过")
        review_button.clicked.connect(self.approve_review)
        review_row = QHBoxLayout()
        review_row.addWidget(review_button)
        review_row.addStretch(1)
        self.review_status_box.setReadOnly(True)
        self.review_status_box.setMinimumHeight(145)
        self.review_status_box.setPlainText("当前人工审核状态：待审核")
        review_layout.addWidget(review_title)
        review_layout.addWidget(self.output_file_label)
        review_layout.addLayout(review_row)
        review_layout.addWidget(self.review_status_box)

        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(summary)
        layout.addWidget(extract_card)
        layout.addWidget(preview_card)
        layout.addWidget(review_card)
        layout.addStretch(1)
        self.setStyleSheet(
            """
            QPushButton { border: 1px solid #c8c8c8; border-radius: 4px; padding: 7px 12px; background: #f4f4f4; }
            QPushButton:hover { background: #e8e8e8; }
            QPlainTextEdit, QTableView { border: 1px solid #d6d6d6; border-radius: 4px; padding: 8px; background: #fbfbfb; }
            QTableView { gridline-color: #eeeeee; padding: 0; alternate-background-color: #f7f7f7; }
            QHeaderView::section { border: none; border-bottom: 1px solid #d6d6d6; padding: 7px; background: #f3f3f3; font-weight: 600; }
            """
        )

    def reload_config(self, show_message=True):
        try:
            self.config = load_config()
            date_info = self._current_date_range(self.config)
            self.summary_labels["target_month"].setText(self.config.get("target_month") or "未配置")
            self.summary_labels["date_range"].setText(
                f"{date_info['start_date']} 至 {date_info['end_date']}" if date_info.get("ok") else "未配置或无效"
            )
            self._set_summary_path("report_file", self.config.get("report_file"), "已配置")
            self._set_summary_path("step0_output", derive_standard_paths(self.config).get("step0_output_dir"), "当月低频数据目录")
            output_file = self._step0_output_file(self.config)
            self.output_file_label.setText(f"当前结果文件：{Path(output_file).name if output_file else '未配置'}")
            self.output_file_label.setToolTip(output_file)
            self.refresh_preview(show_message=show_message)
        except Exception as exc:
            self._set_status(f"0号配置读取失败：{exc}")

    def refresh_from_config(self):
        self.reload_config(show_message=False)

    def run_extract(self):
        self.reload_config(show_message=False)
        config = self.config
        process_info = self._current_date_range(config)
        if not process_info.get("ok"):
            self._set_status(f"处理日期范围无效，已停止：{process_info.get('message', '')}")
            return
        target_month = str(config.get("target_month", "") or "").strip()
        report_file = str(config.get("report_file", "") or "").strip()
        paths = derive_standard_paths(config)
        output_dir = paths.get("step0_output_dir", "")
        output_file = paths.get("step0_output_file", "")
        if not confirm_step_run(
            self,
            "0号日报提取",
            output_dir=output_dir,
            target_month=target_month,
            notes=["将从项目配置中的生产综合日报生成0号结果文件。", f"处理日期：{process_info['start_date']} 至 {process_info['end_date']}"],
            process_start_date=process_info["start_date"],
            process_end_date=process_info["end_date"],
            existing_files=[output_file] if output_file and Path(output_file).is_file() else [],
            result_locations=[output_file],
        ):
            self._set_status("已取消运行。")
            return

        self._set_status("正在运行0号日报提取...")
        QApplication.processEvents()
        try:
            if not report_file:
                raise ValueError("生产综合日报文件未配置，请先前往项目配置")
            normalized_report = normalize_path(report_file)
            if not is_existing_file(normalized_report):
                raise FileNotFoundError(f"生产综合日报文件不存在：{normalized_report}")
            if not output_dir:
                raise ValueError("数据项目根目录未配置，无法推导0号结果位置")
            normalized_output = ensure_dir(output_dir)
            log_lines = []
            result = run_step0_extract(
                report_file=normalized_report,
                output_dir=normalized_output,
                target_month=target_month,
                logger=lambda message: log_lines.append(str(message)),
                process_start_date=process_info["start_date"],
                process_end_date=process_info["end_date"],
            )
            if result.get("success"):
                output_files = result.get("output_files", [])
                config = load_config()
                if output_files:
                    config["step0_output_file"] = normalize_path(output_files[0])
                self._clear_review(config)
                config["step0_needs_rerun"] = False
                save_config(config)
                text = "0号日报提取完成\n输出文件：\n" + "\n".join(output_files)
                if log_lines:
                    text += "\n\n运行日志：\n" + "\n".join(log_lines)
                text += "\n\n请先查看结果预览，再点击“确认审核通过”。"
                self._set_status(text)
                append_run_log("0号日报提取", "success", result.get("message", "0号日报提取完成"))
                self.reload_config(show_message=False)
            else:
                message = result.get("message", "0号日报提取失败")
                self._set_status(f"0号日报提取失败：\n{message}")
                append_run_log("0号日报提取", "failed", message)
        except Exception as exc:
            self._set_status(f"0号日报提取失败：\n{exc}\n\n详细信息：\n{format_exception(exc)}")
            append_run_log("0号日报提取", "failed", str(exc))

    def approve_review(self):
        self.reload_config(show_message=False)
        config = self.config
        process_info = self._current_date_range(config)
        if not process_info.get("ok"):
            self._set_review_status(f"处理日期范围无效，已停止：{process_info.get('message', '')}")
            return
        output_file = self._step0_output_file(config)
        try:
            result = review_step0_output(
                output_file=output_file,
                target_month=config.get("target_month", ""),
                process_start_date=process_info["start_date"],
                process_end_date=process_info["end_date"],
            )
            self._apply_auto_check_result(result)
            if not result.get("success") or result.get("status") == "failed":
                self._set_review_status(
                    self._format_review_result(result, self.preview_data, manual_approved=False)
                    + "\n\n自动检查未通过，不能确认人工审核通过。"
                )
                return
            if not self._confirm_manual_approval(config, process_info):
                self.review_status_box.appendPlainText("\n\n已取消人工审核确认。")
                return

            latest = load_config()
            latest["step0_output_file"] = normalize_path(output_file) if output_file else ""
            latest["step0_auto_check_status"] = str(result.get("status", "") or "")
            latest["step0_auto_check_message"] = str(result.get("message", "") or "")
            latest["step0_auto_checked_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            latest["step0_review_status"] = "approved"
            latest["step0_review_message"] = "人工确认审核通过"
            latest["step0_reviewed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            latest["step0_review_start_date"] = process_info["start_date"]
            latest["step0_review_end_date"] = process_info["end_date"]
            latest["step0_needs_rerun"] = False
            save_config(latest)
            self.config = load_config()
            self._apply_auto_check_result(result)
            append_run_log(
                "0号人工审核",
                "success",
                f"人工确认审核通过：{process_info['start_date']} 至 {process_info['end_date']}",
            )
        except Exception as exc:
            self._set_review_status(f"0号人工审核失败：\n{exc}\n\n详细信息：\n{format_exception(exc)}")
            append_run_log("0号人工审核", "failed", str(exc))

    def review_output(self):
        """Compatibility alias for the previous button callback."""
        self.approve_review()

    @staticmethod
    def _current_date_range(config):
        return resolve_process_date_range(
            config.get("target_month", ""), config.get("process_start_date", ""), config.get("process_end_date", "")
        )

    @staticmethod
    def _clear_review(config):
        clear_step0_review_state(config)

    @staticmethod
    def _step0_output_file(config):
        return derive_standard_paths(config).get("step0_output_file", "")

    def _set_summary_path(self, key, path, configured_text):
        path_text = str(path or "").strip()
        self.summary_labels[key].setText(f"{configured_text}：{Path(path_text).name}" if path_text else "未配置")
        self.summary_labels[key].setToolTip(path_text)

    def _set_status(self, message):
        self.status_box.setPlainText(str(message))

    def _set_review_status(self, message):
        self.review_status_box.setPlainText(str(message))

    def refresh_preview(self, show_message=True):
        output_file = self._step0_output_file(self.config)
        self.preview_model.set_dataframe(None)
        self.preview_data = None
        self.latest_auto_check = None
        self.preview_file_label.setText(f"结果文件：{Path(output_file).name if output_file else '未配置'}")
        self.preview_file_label.setToolTip(output_file)
        self.preview_meta_label.setText("数据范围：-    记录数：0    字段数：0")
        self.preview_review_label.setText("自动检查：未完成    人工审核：待审核")

        if not output_file or not Path(output_file).is_file():
            self.preview_message_label.setText("当前月份尚未生成0号结果。请先运行“0号日报提取”。")
            if self.config.get("step0_needs_rerun"):
                self._set_review_status("当前人工审核状态：待审核\n\n项目配置已变化，0号需要重新运行并重新人工审核。")
            elif show_message:
                self._set_review_status("当前人工审核状态：待审核")
            return

        try:
            preview = load_step0_preview(output_file)
            self.preview_data = preview
            self.preview_model.set_dataframe(preview["dataframe"])
            date_range = (
                f"{preview['start_date']} 至 {preview['end_date']}"
                if preview["start_date"] and preview["end_date"]
                else "未识别"
            )
            self.preview_meta_label.setText(
                f"数据范围：{date_range}    记录数：{preview['rows']}    字段数：{preview['columns']}"
            )
            info_columns = [column for column in preview["empty_columns"] if column == "本日库存"]
            self.preview_message_label.setText(
                f"提示字段：{', '.join(info_columns)}（当前流程未使用）" if info_columns else "结果已加载，可横向滚动查看全部字段。"
            )
            if preview["columns"]:
                self.preview_table.setColumnWidth(0, 125)
            process_info = self._current_date_range(self.config)
            if process_info.get("ok"):
                result = review_step0_output(
                    output_file=output_file,
                    target_month=self.config.get("target_month", ""),
                    process_start_date=process_info["start_date"],
                    process_end_date=process_info["end_date"],
                )
                self._apply_auto_check_result(result)
        except Exception as exc:
            self.preview_message_label.setText(f"0号结果预览失败：{exc}")
            self.preview_review_label.setText("自动检查：未通过    人工审核：待审核")
            self._set_review_status(f"0号结果读取失败：{exc}")

    def open_result_file(self):
        output_file = self._step0_output_file(self.config)
        if not output_file or not Path(output_file).is_file():
            self.preview_message_label.setText("当前月份尚未生成0号结果，无法打开文件。")
            return
        try:
            open_path(output_file)
            self.preview_message_label.setText(f"已使用系统默认方式打开：{output_file}")
        except Exception as exc:
            self.preview_message_label.setText(f"打开0号结果文件失败：{exc}")

    def _apply_auto_check_result(self, result):
        self.latest_auto_check = result
        auto_status = {"passed": "通过", "warning": "提醒", "failed": "未通过"}.get(result.get("status"), "未知")
        manual_approved = self._manual_approval_is_current()
        manual_status = "审核通过" if manual_approved else "待审核"
        self.preview_review_label.setText(f"自动检查：{auto_status}    人工审核：{manual_status}")
        self._set_review_status(self._format_review_result(result, self.preview_data, manual_approved))

    @staticmethod
    def _format_review_result(result, preview=None, manual_approved=False):
        auto_status = {"passed": "通过", "warning": "提醒", "failed": "未通过"}.get(result.get("status"), "未知")
        lines = [
            f"当前人工审核状态：{'审核通过' if manual_approved else '待审核'}",
            "",
            f"自动检查结果：{auto_status}",
        ]
        if preview:
            lines.extend(
                [
                    "",
                    f"数据范围：{preview.get('start_date') or '-'} 至 {preview.get('end_date') or '-'}",
                    f"有效记录：{preview.get('rows', 0)} 行",
                ]
            )
        lines.extend(["", "审核明细："])
        lines.extend(f"[{item.get('status')}] {item.get('message')}" for item in result.get("details", []))
        return "\n".join(lines).strip()

    def _manual_approval_is_current(self):
        process_info = self._current_date_range(self.config)
        return bool(
            process_info.get("ok")
            and is_step0_review_approved(
                self.config,
                process_info["start_date"],
                process_info["end_date"],
            )
        )

    def _confirm_manual_approval(self, config, process_info):
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Question)
        dialog.setWindowTitle("确认人工审核")
        dialog.setText("确认当前0号结果审核通过？")
        dialog.setInformativeText(
            f"处理月份：{config.get('target_month', '')}\n"
            f"处理日期：{process_info['start_date']} 至 {process_info['end_date']}\n\n"
            "确认后即可进入一键运行1→2→3。"
        )
        cancel_button = dialog.addButton("取消", QMessageBox.RejectRole)
        confirm_button = dialog.addButton("确认", QMessageBox.AcceptRole)
        dialog.setDefaultButton(cancel_button)
        dialog.exec()
        return dialog.clickedButton() is confirm_button
