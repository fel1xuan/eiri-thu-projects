from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QDateEdit,
    QVBoxLayout,
    QWidget,
)

from utils.config_utils import (
    get_config_path,
    get_default_config,
    invalidate_step0_review_if_inputs_changed,
    load_config,
    save_config,
)
from utils.date_range_utils import month_bounds, resolve_process_date_range
from utils.path_utils import is_existing_dir, is_existing_file, normalize_path
from utils.project_autodetect import autodetect_month_config
from utils.runtime_paths import get_project_root
from utils.standard_paths import derive_standard_paths


class ProjectConfigPage(QWidget):
    FIELD_DEFINITIONS = [
        ("data_root", "数据项目根目录", "folder", "选择文件夹"),
        ("target_month", "处理月份", "text", ""),
        ("process_start_date", "处理开始日期", "date", ""),
        ("process_end_date", "处理结束日期", "date", ""),
        ("report_file", "生产综合日报文件", "file", "选择文件"),
        ("history_lowfreq_file", "历史低频主表文件", "file", "选择文件"),
        ("lowfreq_current_path", "当月低频数据目录", "folder", "选择文件夹"),
        ("second_data_dir", "秒级 / 高频数据目录", "folder", "选择文件夹"),
    ]
    PATH_FIELDS = {
        "data_root", "report_file", "history_lowfreq_file", "lowfreq_current_path", "second_data_dir"
    }
    AUTO_PATH_FIELDS = {
        "report_file", "history_lowfreq_file", "lowfreq_current_path", "second_data_dir"
    }

    def __init__(self):
        super().__init__()
        self.inputs = {}
        self.status_labels = {}
        self.manual_overrides = set()
        self._last_detection = {}
        self.result_path_labels = {}
        self._loading = False
        self._build_ui()
        self.reload_config(show_message=False)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 34, 36, 34)
        layout.setSpacing(16)

        title = QLabel("项目配置")
        title.setObjectName("PageTitle")
        body = QLabel("选择一次数据项目根目录和处理月份，软件会自动识别本月输入；必要时仍可手动覆盖。")
        body.setObjectName("BodyText")
        body.setWordWrap(True)
        self.boundary_label = QLabel()
        self.boundary_label.setObjectName("MutedText")
        self.boundary_label.setWordWrap(True)

        form = QFrame()
        form.setObjectName("InfoCard")
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(18, 16, 18, 16)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(12)
        form_layout.setColumnStretch(1, 1)

        for row, (key, label_text, kind, button_text) in enumerate(self.FIELD_DEFINITIONS):
            label = QLabel(label_text)
            label.setMinimumWidth(132)
            if kind == "date":
                widget = QDateEdit()
                widget.setCalendarPopup(True)
                widget.setDisplayFormat("yyyy-MM-dd")
                widget.setMinimumWidth(190)
            else:
                widget = QLineEdit()
                widget.setMinimumWidth(420)
                self._set_placeholder(widget, key, kind)
                if key in self.AUTO_PATH_FIELDS:
                    widget.textEdited.connect(lambda _text, field_key=key: self._mark_manual(field_key))
            self.inputs[key] = widget
            form_layout.addWidget(label, row, 0)
            form_layout.addWidget(widget, row, 1)

            if kind == "folder":
                button = QPushButton(button_text)
                button.clicked.connect(lambda checked=False, field_key=key: self.choose_folder(field_key))
                form_layout.addWidget(button, row, 2)
            elif kind == "file":
                button = QPushButton(button_text)
                button.clicked.connect(lambda checked=False, field_key=key: self.choose_file(field_key))
                form_layout.addWidget(button, row, 2)
            else:
                form_layout.addWidget(QLabel(""), row, 2)

            status = QLabel("-")
            status.setObjectName("MutedText")
            status.setMinimumWidth(130)
            status.setWordWrap(True)
            self.status_labels[key] = status
            form_layout.addWidget(status, row, 3)

        self.inputs["target_month"].editingFinished.connect(self._target_month_changed)

        result_frame = QFrame()
        result_frame.setObjectName("InfoCard")
        result_layout = QGridLayout(result_frame)
        result_layout.setContentsMargins(18, 16, 18, 16)
        result_layout.setHorizontalSpacing(12)
        result_layout.setVerticalSpacing(8)
        result_title = QLabel("自动识别结果目录")
        result_title.setObjectName("CardTitle")
        result_layout.addWidget(result_title, 0, 0, 1, 2)
        result_rows = [
            ("step0_output_dir", "0号结果"),
            ("step1_output_dir", "1号累计低频"),
            ("step2_result_dir", "2号秒级结果"),
            ("step2_abnormal_dir", "2号异常结果"),
            ("step3_result_dir", "3号15min结果"),
        ]
        for row, (key, label_text) in enumerate(result_rows, start=1):
            result_layout.addWidget(QLabel(label_text), row, 0)
            value = QLabel("-")
            value.setObjectName("CardText")
            value.setWordWrap(True)
            value.setTextInteractionFlags(value.textInteractionFlags() | Qt.TextSelectableByMouse)
            self.result_path_labels[key] = value
            result_layout.addWidget(value, row, 1)
        result_layout.setColumnStretch(1, 1)

        button_row = QHBoxLayout()
        save_button = QPushButton("保存配置")
        reload_button = QPushButton("重新读取配置")
        detect_button = QPushButton("重新自动识别")
        check_button = QPushButton("检查路径")
        save_button.clicked.connect(self.save_current_config)
        reload_button.clicked.connect(self.reload_config)
        detect_button.clicked.connect(self.redetect)
        check_button.clicked.connect(self.check_paths)
        for button in (save_button, reload_button, detect_button, check_button):
            button_row.addWidget(button)
        button_row.addStretch(1)

        self.status_box = QPlainTextEdit()
        self.status_box.setReadOnly(True)
        self.status_box.setMaximumHeight(210)
        self.status_box.setPlaceholderText("自动识别候选、警告和路径检查结果会显示在这里。")

        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(self.boundary_label)
        layout.addWidget(form)
        layout.addWidget(result_frame)
        layout.addLayout(button_row)
        layout.addWidget(self.status_box)
        layout.addStretch(1)
        self.setStyleSheet(
            """
            QLineEdit, QDateEdit { border: 1px solid #cfcfcf; border-radius: 4px; padding: 7px 9px; background: #ffffff; }
            QPushButton { border: 1px solid #c8c8c8; border-radius: 4px; padding: 7px 12px; background: #f4f4f4; }
            QPushButton:hover { background: #e8e8e8; }
            QPlainTextEdit { border: 1px solid #d6d6d6; border-radius: 4px; padding: 8px; background: #fbfbfb; }
            """
        )

    def choose_folder(self, field_key):
        selected = QFileDialog.getExistingDirectory(self, "选择文件夹", self._initial_dialog_dir(field_key))
        if not selected:
            return
        self.inputs[field_key].setText(normalize_path(selected))
        if field_key == "data_root":
            self.status_labels[field_key].setText("手动设置")
            self._run_autodetect(force=True, reason="数据项目根目录已更新")
        else:
            self._mark_manual(field_key)
            self._set_status(f"{self._field_label(field_key)}已手动设置。")

    def choose_file(self, field_key):
        selected, _ = QFileDialog.getOpenFileName(
            self, "选择文件", self._initial_dialog_dir(field_key), "Excel 文件 (*.xls *.xlsx);;所有文件 (*)"
        )
        if selected:
            self.inputs[field_key].setText(normalize_path(selected))
            self._mark_manual(field_key)
            self._set_status(f"{self._field_label(field_key)}已手动设置。")

    def save_current_config(self):
        try:
            previous = load_config()
            current = self._collect_config()
            current["manual_path_overrides"] = sorted(self.manual_overrides)
            current, changed = invalidate_step0_review_if_inputs_changed(previous, current)
            saved = save_config(current)
            self._apply_config(saved)
            message = "配置已保存"
            if changed:
                message += "\n0号输入条件已变化，旧人工审核已失效；请重新运行0号并再次人工确认。"
            self._set_status(message)
        except Exception as exc:
            self._set_status(f"配置保存失败：{exc}")

    def reload_config(self, show_message=True):
        try:
            self._apply_config(load_config())
            if show_message:
                self._set_status("配置已重新读取")
        except Exception as exc:
            self._apply_config(get_default_config())
            self._set_status(f"配置读取失败，已恢复默认配置：{exc}")

    def refresh_from_config(self):
        self.reload_config(show_message=False)

    def redetect(self):
        force = False
        if self.manual_overrides:
            answer = QMessageBox.question(
                self,
                "重新自动识别",
                "部分路径已标记为手动设置。\n\n选择“是”将覆盖这些手动路径；选择“否”将保留手动路径并只刷新其他字段。",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.No,
            )
            if answer == QMessageBox.Cancel:
                self._set_status("已取消重新自动识别。")
                return
            force = answer == QMessageBox.Yes
        self._run_autodetect(force=force, reason="已重新自动识别")

    def check_paths(self):
        config = self._collect_config()
        date_info = resolve_process_date_range(
            config.get("target_month", ""), config.get("process_start_date", ""), config.get("process_end_date", "")
        )
        messages = []
        if date_info.get("ok"):
            messages.append(f"处理日期范围：{date_info['start_date']} 至 {date_info['end_date']}，共{date_info['days']}天")
        else:
            messages.append(f"处理日期范围：失败（{date_info.get('message', '日期范围无效')}）")
        messages.append(f"数据项目根目录：{'存在' if is_existing_dir(config.get('data_root')) else '不存在'}")
        messages.append(self._optional_file_status("生产综合日报文件", config.get("report_file", "")))
        messages.append(self._optional_file_status("历史低频主表文件", config.get("history_lowfreq_file", "")))
        messages.append(self._optional_dir_status("当月低频数据目录", config.get("lowfreq_current_path", "")))
        messages.append(self._optional_dir_status("秒级数据目录", config.get("second_data_dir", "")))
        for key, label in (
            ("step0_output_dir", "0号结果目录"),
            ("step1_output_dir", "1号累计低频目录"),
            ("step2_result_dir", "2号秒级结果目录"),
            ("step2_abnormal_dir", "2号异常结果目录"),
            ("step3_result_dir", "3号15min结果目录"),
        ):
            path = derive_standard_paths(config).get(key, "")
            messages.append(f"{label}：{'存在' if is_existing_dir(path) else '尚未创建'} - {path or '未推导'}")
        self._set_status("\n".join(messages))

    def _run_autodetect(self, force=False, reason="自动识别完成"):
        result = autodetect_month_config(
            self.inputs["data_root"].text().strip(), self.inputs["target_month"].text().strip()
        )
        self._last_detection = result
        if not result.get("process_start_date"):
            self._set_status("\n".join(result.get("warnings", [])) or "自动识别失败")
            return result
        self._sync_date_widgets({"target_month": self.inputs["target_month"].text().strip()})
        self._set_date_widget(self.inputs["process_start_date"], result["process_start_date"])
        self._set_date_widget(self.inputs["process_end_date"], result["process_end_date"])
        if force:
            self.manual_overrides.difference_update(self.AUTO_PATH_FIELDS)
        for key in self.AUTO_PATH_FIELDS:
            if key in self.manual_overrides and not force:
                self.status_labels[key].setText("手动设置（已保留）")
                continue
            self.inputs[key].setText(str(result.get(key, "") or ""))
            status = result.get("statuses", {}).get(key, {})
            self.status_labels[key].setText(status.get("message", "未识别"))
        self._update_result_paths(
            {
                **result,
                "data_root": self.inputs["data_root"].text().strip(),
                "target_month": self.inputs["target_month"].text().strip(),
                "process_end_date": result.get("process_end_date", ""),
            }
        )
        self.status_labels["target_month"].setText("已更新")
        self.status_labels["process_start_date"].setText("按月份重置")
        self.status_labels["process_end_date"].setText("按月份重置")
        lines = [reason, f"处理日期：{result['process_start_date']} 至 {result['process_end_date']}"]
        lines.extend(result.get("warnings", []))
        report_candidates = result.get("candidates", {}).get("report_file", [])
        if len(report_candidates) > 1:
            lines.append("生产综合日报候选：")
            lines.extend(f"- {path}" for path in report_candidates)
        self._set_status("\n".join(lines))
        return result

    def _collect_config(self):
        config = load_config()
        for key, widget in self.inputs.items():
            value = widget.date().toString("yyyy-MM-dd") if isinstance(widget, QDateEdit) else widget.text().strip()
            if key in self.PATH_FIELDS and value:
                value = normalize_path(value)
            config[key] = value
        return config

    def _apply_config(self, config):
        self._loading = True
        try:
            merged = get_default_config()
            merged.update(config or {})
            self.manual_overrides = set(merged.get("manual_path_overrides", []) or [])
            self._sync_date_widgets(merged)
            for key, widget in self.inputs.items():
                value = str(merged.get(key, "") or "")
                if isinstance(widget, QDateEdit):
                    self._set_date_widget(widget, value)
                else:
                    widget.setText(value)
                if key in self.manual_overrides:
                    self.status_labels[key].setText("手动设置")
                elif value:
                    self.status_labels[key].setText("已配置")
                else:
                    self.status_labels[key].setText("未配置")
            self.status_labels["data_root"].setText("已配置" if merged.get("data_root") else "未配置")
            self._update_boundary_label(merged)
            self._update_result_paths(merged)
        finally:
            self._loading = False

    def _target_month_changed(self):
        if self._loading:
            return
        try:
            month_bounds(self.inputs["target_month"].text().strip())
            self._run_autodetect(force=True, reason="处理月份已更新，相关路径已按新月份重新识别")
        except Exception as exc:
            self._set_status(f"处理月份格式无效：{exc}")

    def _mark_manual(self, field_key):
        if self._loading or field_key not in self.AUTO_PATH_FIELDS:
            return
        self.manual_overrides.add(field_key)
        self.status_labels[field_key].setText("手动设置")

    def _sync_date_widgets(self, config):
        try:
            start_date, end_date = month_bounds(config.get("target_month", ""))
        except Exception:
            return
        minimum = QDate.fromString(start_date, "yyyy-MM-dd")
        maximum = QDate.fromString(end_date, "yyyy-MM-dd")
        for key in ("process_start_date", "process_end_date"):
            self.inputs[key].setMinimumDate(minimum)
            self.inputs[key].setMaximumDate(maximum)

    def _set_date_widget(self, widget, value):
        qdate = QDate.fromString(str(value or ""), "yyyy-MM-dd")
        if not qdate.isValid():
            try:
                start_date, _ = month_bounds(self.inputs["target_month"].text().strip())
                qdate = QDate.fromString(start_date, "yyyy-MM-dd")
            except Exception:
                qdate = QDate.currentDate()
        widget.setDate(qdate)

    def _initial_dialog_dir(self, field_key):
        widget = self.inputs[field_key]
        current = widget.text().strip() if hasattr(widget, "text") else ""
        if current:
            path = Path(normalize_path(current))
            if path.is_file():
                return str(path.parent)
            if path.is_dir():
                return str(path)
        root = self.inputs["data_root"].text().strip()
        return normalize_path(root) if root and is_existing_dir(root) else str(Path.home())

    def _update_boundary_label(self, config):
        self.boundary_label.setText(
            f"软件代码目录：{get_project_root()}\n"
            f"数据目录：{config.get('data_root') or '未选择'}\n"
            f"用户配置文件：{get_config_path()}\n"
            "详细路径只在本页面维护；软件代码目录与正式数据目录不要混用。"
        )

    def _set_status(self, message):
        self.status_box.setPlainText(str(message))

    def _update_result_paths(self, config):
        paths = derive_standard_paths(config)
        for key, label in self.result_path_labels.items():
            value = paths.get(key, "") or "未配置数据项目根目录"
            label.setText(value)
            label.setToolTip(value)

    def _set_placeholder(self, widget, key, kind):
        if key == "target_month":
            widget.setPlaceholderText("YYYY-MM，例如 2026-06")
        elif key == "data_root":
            widget.setPlaceholderText("选择数据项目根目录后自动识别本月输入")
        elif kind == "file":
            widget.setPlaceholderText("自动识别，也可手动选择 Excel 文件")
        else:
            widget.setPlaceholderText("自动识别，也可手动选择文件夹")

    def _field_label(self, field_key):
        return next((label for key, label, _, _ in self.FIELD_DEFINITIONS if key == field_key), field_key)

    @staticmethod
    def _optional_file_status(label, path):
        if not path:
            return f"{label}：未选择"
        return f"{label}：{'存在' if is_existing_file(path) else '不存在'}"

    @staticmethod
    def _optional_dir_status(label, path):
        if not path:
            return f"{label}：未选择"
        return f"{label}：{'存在' if is_existing_dir(path) else '不存在'}"
