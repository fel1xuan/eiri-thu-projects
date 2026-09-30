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

from core.step3_15min_aggregate import run_step3_15min_aggregate
from ui.run_guards import confirm_step_run
from utils.config_utils import load_config, save_config
from utils.log_utils import append_run_log, format_exception
from utils.path_utils import normalize_path
from utils.standard_paths import derive_standard_paths, expected_result_files


class Step3Page(QWidget):
    def __init__(self):
        super().__init__()
        self.target_month_input = QLineEdit()
        self.second_result_path_input = QLineEdit()
        self.abnormal_result_path_input = QLineEdit()
        self.output_dir_input = QLineEdit()
        self.status_box = QPlainTextEdit()
        self._build_ui()
        self.reload_config(show_message=False)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 34, 36, 34)
        layout.setSpacing(18)

        title = QLabel("3号 15min聚合")
        title.setObjectName("PageTitle")

        body = QLabel("用于读取2号秒级核算结果，按15min粒度进行聚合，生成后续查看和分析所需的15min结果文件。")
        body.setObjectName("BodyText")
        body.setWordWrap(True)

        form = QFrame()
        form.setObjectName("InfoCard")
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(18, 16, 18, 16)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(12)
        form_layout.setColumnStretch(1, 1)

        for line_edit in [self.second_result_path_input, self.abnormal_result_path_input, self.output_dir_input]:
            line_edit.setMinimumWidth(520)
        self.target_month_input.setPlaceholderText("YYYY-MM，例如 2026-05")
        self.second_result_path_input.setPlaceholderText("请选择2号秒级核算结果文件或文件夹")
        self.abnormal_result_path_input.setPlaceholderText("请选择2号异常检测结果文件或文件夹，可为空")
        self.output_dir_input.setReadOnly(True)
        self.output_dir_input.setPlaceholderText("由数据项目根目录自动推导")

        form_layout.addWidget(QLabel("目标月份"), 0, 0)
        form_layout.addWidget(self.target_month_input, 0, 1)
        form_layout.addWidget(QLabel(""), 0, 2)

        form_layout.addWidget(QLabel("2号秒级核算结果"), 1, 0)
        form_layout.addWidget(self.second_result_path_input, 1, 1)
        second_buttons = self._build_file_folder_buttons(
            self.second_result_path_input,
            "选择2号秒级核算结果文件",
            "选择2号秒级核算结果文件夹",
        )
        form_layout.addLayout(second_buttons, 1, 2)

        form_layout.addWidget(QLabel("2号异常检测结果"), 2, 0)
        form_layout.addWidget(self.abnormal_result_path_input, 2, 1)
        abnormal_buttons = self._build_file_folder_buttons(
            self.abnormal_result_path_input,
            "选择2号异常检测结果文件",
            "选择2号异常检测结果文件夹",
        )
        form_layout.addLayout(abnormal_buttons, 2, 2)

        form_layout.addWidget(QLabel("3号标准结果目录"), 3, 0)
        form_layout.addWidget(self.output_dir_input, 3, 1)
        form_layout.addWidget(QLabel("自动"), 3, 2)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        run_button = QPushButton("运行3号15min聚合")
        save_button = QPushButton("保存当前配置")
        reload_button = QPushButton("重新读取配置")
        run_button.clicked.connect(self.run_15min_aggregate)
        save_button.clicked.connect(self.save_current_config)
        reload_button.clicked.connect(self.reload_config)
        button_row.addWidget(run_button)
        button_row.addWidget(save_button)
        button_row.addWidget(reload_button)
        button_row.addStretch(1)

        status_title = QLabel("运行状态")
        status_title.setObjectName("CardTitle")

        self.status_box.setReadOnly(True)
        self.status_box.setMinimumHeight(210)
        self.status_box.setPlainText("等待运行3号15min聚合")

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

    def _build_file_folder_buttons(self, target_input, file_title, folder_title):
        button_row = QHBoxLayout()
        button_row.setSpacing(6)
        file_button = QPushButton("选择文件")
        folder_button = QPushButton("选择文件夹")
        file_button.clicked.connect(lambda: self.choose_file(target_input, file_title))
        folder_button.clicked.connect(lambda: self.choose_folder(target_input, folder_title))
        button_row.addWidget(file_button)
        button_row.addWidget(folder_button)
        return button_row

    def choose_file(self, target_input, title):
        selected, _ = QFileDialog.getOpenFileName(
            self,
            title,
            self._initial_dialog_dir(target_input.text()),
            "数据文件 (*.xls *.xlsx *.csv);;所有文件 (*)",
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
            self._save_step3_config()
            self._set_status("当前3号配置已保存")
        except Exception as exc:
            self._set_status(f"当前3号配置保存失败：{exc}")

    def reload_config(self, show_message=True):
        try:
            config = load_config()
            self.target_month_input.setText(str(config.get("target_month", "") or ""))
            self.output_dir_input.setText(derive_standard_paths(config).get("step3_result_dir", ""))
            self.second_result_path_input.setText(str(config.get("second_result_path", "") or self._default_second_result_path(config)))
            self.abnormal_result_path_input.setText(str(config.get("abnormal_result_path", "") or self._default_abnormal_result_path(config)))
            if show_message:
                self._set_status("已重新读取3号配置")
        except Exception as exc:
            self._set_status(f"3号配置读取失败：{exc}")

    def run_15min_aggregate(self):
        target_month = self.target_month_input.text().strip()
        second_result_path = self.second_result_path_input.text().strip()
        abnormal_result_path = self.abnormal_result_path_input.text().strip()
        probe = load_config()
        probe["target_month"] = target_month
        paths = derive_standard_paths(probe)

        if not confirm_step_run(
            self,
            "3号15min聚合",
            output_dir=paths["step3_result_dir"],
            target_month=target_month,
            notes=["该步骤会读取2号结果并生成15min聚合文件。"],
            existing_files=[path for path in expected_result_files(probe) if Path(path).is_file() and "15min" in path],
            result_locations=[paths["step3_result_dir"]],
        ):
            self._set_status("已取消运行。")
            return

        self._set_status("正在运行3号15min聚合...")
        QApplication.processEvents()

        try:
            if not second_result_path:
                raise ValueError("2号秒级核算结果不能为空")
            normalized_second_path = normalize_path(second_result_path)
            second_path = Path(normalized_second_path)
            if not second_path.exists():
                raise FileNotFoundError(f"2号秒级核算结果不存在：{normalized_second_path}")
            if not (second_path.is_file() or second_path.is_dir()):
                raise ValueError(f"2号秒级核算结果既不是文件也不是文件夹：{normalized_second_path}")

            normalized_abnormal_path = ""
            if abnormal_result_path:
                normalized_abnormal_path = normalize_path(abnormal_result_path)
                abnormal_path = Path(normalized_abnormal_path)
                if not abnormal_path.exists():
                    raise FileNotFoundError(f"2号异常检测结果不存在：{normalized_abnormal_path}")
                if not (abnormal_path.is_file() or abnormal_path.is_dir()):
                    raise ValueError(f"2号异常检测结果既不是文件也不是文件夹：{normalized_abnormal_path}")

            self.second_result_path_input.setText(normalized_second_path)
            self.abnormal_result_path_input.setText(normalized_abnormal_path)
            self._save_step3_config()

            log_lines = []

            def page_logger(message):
                log_lines.append(str(message))

            result = run_step3_15min_aggregate(
                second_result_path=normalized_second_path,
                result_dir=paths["step3_result_dir"],
                target_month=target_month,
                abnormal_result_path=normalized_abnormal_path,
                logger=page_logger,
            )

            if result.get("success"):
                output_files = result.get("output_files", [])
                displayed_files = output_files[:20]
                status_text = "3号15min聚合完成\n输出文件：\n" + "\n".join(displayed_files)
                if len(output_files) > len(displayed_files):
                    status_text += f"\n... 另有 {len(output_files) - len(displayed_files)} 个文件"
                if result.get("result_dir"):
                    status_text += f"\n\n15min结果目录：{result['result_dir']}"
                if log_lines:
                    status_text += "\n\n运行日志：\n" + "\n".join(log_lines[-60:])
                self._set_status(status_text)
                append_run_log("3号15min聚合", "success", result.get("message", "3号15min聚合完成"))
            else:
                message = result.get("message", "3号15min聚合失败")
                self._set_status(f"3号15min聚合失败：\n{message}")
                append_run_log("3号15min聚合", "failed", message)
        except Exception as exc:
            detail = format_exception(exc)
            self._set_status(f"3号15min聚合失败：\n{exc}\n\n详细信息：\n{detail}")
            append_run_log("3号15min聚合", "failed", str(exc))

    def _save_step3_config(self):
        config = load_config()
        config["target_month"] = self.target_month_input.text().strip()
        second_result_path = self.second_result_path_input.text().strip()
        abnormal_result_path = self.abnormal_result_path_input.text().strip()
        config["second_result_path"] = normalize_path(second_result_path) if second_result_path else ""
        config["abnormal_result_path"] = normalize_path(abnormal_result_path) if abnormal_result_path else ""
        save_config(config)

    def _default_second_result_path(self, config=None):
        current_config = config or load_config()
        return derive_standard_paths(current_config).get("step2_result_dir", "")

    def _default_abnormal_result_path(self, config=None):
        current_config = config or load_config()
        value = derive_standard_paths(current_config).get("step2_abnormal_dir", "")
        candidate = Path(value) if value else None
        return str(candidate) if candidate and candidate.exists() else ""

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
