from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.step1_lowfreq_update import run_step1_lowfreq_update
from ui.run_guards import confirm_step_run
from utils.config_utils import load_config, save_config
from utils.log_utils import append_run_log, format_exception
from utils.path_utils import ensure_dir, is_existing_file, normalize_path
from utils.standard_paths import derive_standard_paths


class Step1Page(QWidget):
    def __init__(self):
        super().__init__()
        self.target_month_input = QLineEdit()
        self.step0_output_file_input = QLineEdit()
        self.history_lowfreq_file_input = QLineEdit()
        self.lowfreq_current_path_input = QLineEdit()
        self.output_dir_input = QLineEdit()
        self.status_box = QPlainTextEdit()
        self._build_ui()
        self.reload_config(show_message=False)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 34, 36, 34)
        layout.setSpacing(18)

        title = QLabel("1号 低频汇总")
        title.setObjectName("PageTitle")

        body = QLabel("用于汇总0号日报提取结果、历史低频主表和当月低频数据，生成后续秒级核算所需的低频汇总文件。")
        body.setObjectName("BodyText")
        body.setWordWrap(True)

        form = QFrame()
        form.setObjectName("InfoCard")
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(18, 16, 18, 16)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(12)
        form_layout.setColumnStretch(1, 1)

        for line_edit in [
            self.step0_output_file_input,
            self.history_lowfreq_file_input,
            self.lowfreq_current_path_input,
            self.output_dir_input,
        ]:
            line_edit.setMinimumWidth(540)

        self.target_month_input.setPlaceholderText("YYYY-MM，例如 2026-05")
        self.step0_output_file_input.setPlaceholderText("请选择0号日报提取结果 Excel 文件")
        self.history_lowfreq_file_input.setPlaceholderText("请选择历史低频主表 Excel 文件")
        self.lowfreq_current_path_input.setPlaceholderText("请选择当月低频数据文件或文件夹")
        self.output_dir_input.setReadOnly(True)
        self.output_dir_input.setPlaceholderText("由数据项目根目录自动推导")

        form_layout.addWidget(QLabel("目标月份"), 0, 0)
        form_layout.addWidget(self.target_month_input, 0, 1)
        form_layout.addWidget(QLabel(""), 0, 2)

        form_layout.addWidget(QLabel("0号日报提取结果"), 1, 0)
        form_layout.addWidget(self.step0_output_file_input, 1, 1)
        step0_button = QPushButton("选择文件")
        step0_button.clicked.connect(lambda: self.choose_file(self.step0_output_file_input, "选择0号日报提取结果"))
        form_layout.addWidget(step0_button, 1, 2)

        form_layout.addWidget(QLabel("历史低频主表"), 2, 0)
        form_layout.addWidget(self.history_lowfreq_file_input, 2, 1)
        history_button = QPushButton("选择文件")
        history_button.clicked.connect(lambda: self.choose_file(self.history_lowfreq_file_input, "选择历史低频主表"))
        form_layout.addWidget(history_button, 2, 2)

        form_layout.addWidget(QLabel("当月低频数据"), 3, 0)
        form_layout.addWidget(self.lowfreq_current_path_input, 3, 1)
        current_buttons = QHBoxLayout()
        current_file_button = QPushButton("选择文件")
        current_folder_button = QPushButton("选择文件夹")
        current_file_button.clicked.connect(lambda: self.choose_file(self.lowfreq_current_path_input, "选择当月低频数据文件", allow_csv=True))
        current_folder_button.clicked.connect(lambda: self.choose_folder(self.lowfreq_current_path_input, "选择当月低频数据文件夹"))
        current_buttons.addWidget(current_file_button)
        current_buttons.addWidget(current_folder_button)
        form_layout.addLayout(current_buttons, 3, 2)

        form_layout.addWidget(QLabel("1号标准结果目录"), 4, 0)
        form_layout.addWidget(self.output_dir_input, 4, 1)
        form_layout.addWidget(QLabel("自动"), 4, 2)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        run_button = QPushButton("运行1号低频汇总")
        save_button = QPushButton("保存当前配置")
        reload_button = QPushButton("重新读取配置")
        run_button.clicked.connect(self.run_lowfreq)
        save_button.clicked.connect(self.save_current_config)
        reload_button.clicked.connect(self.reload_config)
        button_row.addWidget(run_button)
        button_row.addWidget(save_button)
        button_row.addWidget(reload_button)
        button_row.addStretch(1)

        status_title = QLabel("运行状态")
        status_title.setObjectName("CardTitle")

        self.status_box.setReadOnly(True)
        self.status_box.setMinimumHeight(190)
        self.status_box.setPlainText("等待运行1号低频汇总")

        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(form)
        layout.addLayout(button_row)
        layout.addWidget(status_title)
        layout.addWidget(self.status_box)
        layout.addStretch(1)

        self.setStyleSheet(
            """
            QLineEdit {
                border: 1px solid #cfcfcf;
                border-radius: 4px;
                padding: 7px 9px;
                color: #222222;
                background: #ffffff;
            }
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
            QPlainTextEdit {
                border: 1px solid #d6d6d6;
                border-radius: 4px;
                padding: 8px;
                color: #333333;
                background: #fbfbfb;
            }
            """
        )

    def choose_file(self, target_input, title, allow_csv=False):
        filter_text = "数据文件 (*.xls *.xlsx *.csv);;所有文件 (*)" if allow_csv else "Excel 文件 (*.xls *.xlsx);;所有文件 (*)"
        selected, _ = QFileDialog.getOpenFileName(
            self,
            title,
            self._initial_dialog_dir(target_input.text()),
            filter_text,
        )
        if selected:
            target_input.setText(normalize_path(selected))
            self._set_status(f"已选择文件：{normalize_path(selected)}")

    def choose_folder(self, target_input, title):
        selected = QFileDialog.getExistingDirectory(
            self,
            title,
            self._initial_dialog_dir(target_input.text()),
        )
        if selected:
            target_input.setText(normalize_path(selected))
            self._set_status(f"已选择文件夹：{normalize_path(selected)}")

    def save_current_config(self):
        try:
            self._save_step1_config()
            self._set_status("当前1号配置已保存")
        except Exception as exc:
            self._set_status(f"当前1号配置保存失败：{exc}")

    def reload_config(self, show_message=True):
        try:
            config = load_config()
            self.target_month_input.setText(str(config.get("target_month", "") or ""))
            self.step0_output_file_input.setText(str(config.get("step0_output_file", "") or self._default_step0_output_file(config)))
            self.history_lowfreq_file_input.setText(str(config.get("history_lowfreq_file", "") or ""))
            self.lowfreq_current_path_input.setText(str(config.get("lowfreq_current_path", "") or ""))
            self.output_dir_input.setText(derive_standard_paths(config).get("step1_output_dir", ""))
            if show_message:
                self._set_status("已重新读取1号配置")
        except Exception as exc:
            self._set_status(f"1号配置读取失败：{exc}")

    def run_lowfreq(self):
        target_month = self.target_month_input.text().strip()
        step0_output_file = self.step0_output_file_input.text().strip()
        history_lowfreq_file = self.history_lowfreq_file_input.text().strip()
        lowfreq_current_path = self.lowfreq_current_path_input.text().strip()
        output_dir = self.output_dir_input.text().strip()
        probe = load_config()
        probe["target_month"] = target_month
        paths = derive_standard_paths(probe)

        if not confirm_step_run(
            self,
            "1号低频汇总",
            output_dir=output_dir,
            target_month=target_month,
            notes=["将合并0号结果、历史低频主表和当月低频数据。"],
            existing_files=[paths["lowfreq_result_file"]] if Path(paths["lowfreq_result_file"]).is_file() else [],
            result_locations=[paths["lowfreq_result_file"]],
        ):
            self._set_status("已取消运行。")
            return

        self._set_status("正在运行1号低频汇总...")
        QApplication.processEvents()

        try:
            if not step0_output_file:
                raise ValueError("0号日报提取结果不能为空")
            normalized_step0 = normalize_path(step0_output_file)
            if not is_existing_file(normalized_step0):
                raise FileNotFoundError(f"0号日报提取结果不存在：{normalized_step0}")

            if not history_lowfreq_file:
                raise ValueError("历史低频主表文件不能为空")
            normalized_history = normalize_path(history_lowfreq_file)
            if not is_existing_file(normalized_history):
                raise FileNotFoundError(f"历史低频主表不存在：{normalized_history}")

            if not lowfreq_current_path:
                raise ValueError("当月低频数据路径不能为空")
            normalized_current = normalize_path(lowfreq_current_path)
            if not Path(normalized_current).exists():
                raise FileNotFoundError(f"当月低频数据路径不存在：{normalized_current}")

            if not output_dir:
                raise ValueError("输出目录不能为空")
            normalized_output_dir = ensure_dir(output_dir)

            self.step0_output_file_input.setText(normalized_step0)
            self.history_lowfreq_file_input.setText(normalized_history)
            self.lowfreq_current_path_input.setText(normalized_current)
            self.output_dir_input.setText(normalized_output_dir)
            self._save_step1_config()

            log_lines = []

            def page_logger(message):
                log_lines.append(str(message))

            result = run_step1_lowfreq_update(
                step0_output_file=normalized_step0,
                history_lowfreq_file=normalized_history,
                lowfreq_current_path=normalized_current,
                output_dir=normalized_output_dir,
                target_month=target_month,
                logger=page_logger,
            )

            if result.get("success"):
                output_files = result.get("output_files", [])
                status_text = "1号低频汇总完成\n输出文件：\n" + "\n".join(output_files)
                if log_lines:
                    status_text += "\n\n运行日志：\n" + "\n".join(log_lines)
                self._set_status(status_text)
                append_run_log("1号低频汇总", "success", result.get("message", "1号低频汇总完成"))
            else:
                message = result.get("message", "1号低频汇总失败")
                self._set_status(f"1号低频汇总失败：\n{message}")
                append_run_log("1号低频汇总", "failed", message)
        except Exception as exc:
            detail = format_exception(exc)
            self._set_status(f"1号低频汇总失败：\n{exc}\n\n详细信息：\n{detail}")
            append_run_log("1号低频汇总", "failed", str(exc))

    def _save_step1_config(self):
        config = load_config()
        config["target_month"] = self.target_month_input.text().strip()
        step0_output_file = self.step0_output_file_input.text().strip()
        history_lowfreq_file = self.history_lowfreq_file_input.text().strip()
        lowfreq_current_path = self.lowfreq_current_path_input.text().strip()
        config["step0_output_file"] = normalize_path(step0_output_file) if step0_output_file else ""
        config["history_lowfreq_file"] = normalize_path(history_lowfreq_file) if history_lowfreq_file else ""
        config["lowfreq_current_path"] = normalize_path(lowfreq_current_path) if lowfreq_current_path else ""
        save_config(config)

    def _default_step0_output_file(self, config=None):
        current_config = config or load_config()
        return derive_standard_paths(current_config).get("step0_output_file", "")

    def _initial_dialog_dir(self, value):
        current_value = value.strip()
        if current_value:
            current_path = Path(normalize_path(current_value))
            if current_path.is_file():
                return str(current_path.parent)
            if current_path.is_dir():
                return str(current_path)
        config = load_config()
        data_root = config.get("data_root") or ""
        return normalize_path(data_root) if data_root else str(Path.home())

    def _set_status(self, message):
        self.status_box.setPlainText(str(message))
