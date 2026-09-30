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

from core.step2_second_calc import run_step2_second_calc
from ui.run_guards import confirm_step_run
from utils.config_utils import load_config, save_config
from utils.log_utils import append_run_log, format_exception
from utils.path_utils import is_existing_dir, is_existing_file, normalize_path
from utils.standard_paths import derive_standard_paths, expected_result_files


class Step2Page(QWidget):
    def __init__(self):
        super().__init__()
        self.target_month_input = QLineEdit()
        self.lowfreq_result_file_input = QLineEdit()
        self.second_data_dir_input = QLineEdit()
        self.output_dir_input = QLineEdit()
        self.status_box = QPlainTextEdit()
        self._build_ui()
        self.reload_config(show_message=False)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 34, 36, 34)
        layout.setSpacing(18)

        title = QLabel("2号 秒级核算")
        title.setObjectName("PageTitle")

        body = QLabel("用于读取1号低频汇总结果和秒级 / 高频数据，执行秒级碳排放核算与异常检测，生成后续15min聚合所需的结果文件。")
        body.setObjectName("BodyText")
        body.setWordWrap(True)

        form = QFrame()
        form.setObjectName("InfoCard")
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(18, 16, 18, 16)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(12)
        form_layout.setColumnStretch(1, 1)

        for line_edit in [self.lowfreq_result_file_input, self.second_data_dir_input, self.output_dir_input]:
            line_edit.setMinimumWidth(540)
        self.target_month_input.setPlaceholderText("YYYY-MM，例如 2026-05")
        self.lowfreq_result_file_input.setPlaceholderText("请选择1号低频汇总结果 Excel 文件")
        self.second_data_dir_input.setPlaceholderText("请选择秒级 / 高频数据目录")
        self.output_dir_input.setReadOnly(True)
        self.output_dir_input.setPlaceholderText("由数据项目根目录自动推导")

        form_layout.addWidget(QLabel("目标月份"), 0, 0)
        form_layout.addWidget(self.target_month_input, 0, 1)
        form_layout.addWidget(QLabel(""), 0, 2)

        form_layout.addWidget(QLabel("1号低频汇总结果"), 1, 0)
        form_layout.addWidget(self.lowfreq_result_file_input, 1, 1)
        lowfreq_button = QPushButton("选择文件")
        lowfreq_button.clicked.connect(self.choose_lowfreq_file)
        form_layout.addWidget(lowfreq_button, 1, 2)

        form_layout.addWidget(QLabel("秒级 / 高频数据目录"), 2, 0)
        form_layout.addWidget(self.second_data_dir_input, 2, 1)
        second_dir_button = QPushButton("选择文件夹")
        second_dir_button.clicked.connect(lambda: self.choose_folder(self.second_data_dir_input, "选择秒级 / 高频数据目录"))
        form_layout.addWidget(second_dir_button, 2, 2)

        form_layout.addWidget(QLabel("2号标准结果目录"), 3, 0)
        form_layout.addWidget(self.output_dir_input, 3, 1)
        form_layout.addWidget(QLabel("自动"), 3, 2)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        run_button = QPushButton("运行2号秒级核算")
        save_button = QPushButton("保存当前配置")
        reload_button = QPushButton("重新读取配置")
        run_button.clicked.connect(self.run_second_calc)
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
        self.status_box.setPlainText("等待运行2号秒级核算")

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

    def choose_lowfreq_file(self):
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择1号低频汇总结果",
            self._initial_dialog_dir(self.lowfreq_result_file_input.text()),
            "Excel 文件 (*.xls *.xlsx);;所有文件 (*)",
        )
        if selected:
            self.lowfreq_result_file_input.setText(normalize_path(selected))
            self._set_status(f"已选择1号低频汇总结果：{normalize_path(selected)}")

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
            self._save_step2_config()
            self._set_status("当前2号配置已保存")
        except Exception as exc:
            self._set_status(f"当前2号配置保存失败：{exc}")

    def reload_config(self, show_message=True):
        try:
            config = load_config()
            self.target_month_input.setText(str(config.get("target_month", "") or ""))
            self.output_dir_input.setText(derive_standard_paths(config).get("step2_result_dir", ""))
            self.lowfreq_result_file_input.setText(str(config.get("lowfreq_result_file", "") or self._default_lowfreq_result_file(config)))
            self.second_data_dir_input.setText(str(config.get("second_data_dir", "") or self._default_second_data_dir(config)))
            if show_message:
                self._set_status("已重新读取2号配置")
        except Exception as exc:
            self._set_status(f"2号配置读取失败：{exc}")

    def run_second_calc(self):
        target_month = self.target_month_input.text().strip()
        lowfreq_result_file = self.lowfreq_result_file_input.text().strip()
        second_data_dir = self.second_data_dir_input.text().strip()
        probe = load_config()
        probe["target_month"] = target_month
        paths = derive_standard_paths(probe)

        if not confirm_step_run(
            self,
            "2号秒级核算",
            output_dir=paths["step2_result_dir"],
            target_month=target_month,
            notes=["该步骤可能耗时较长。"],
            existing_files=[path for path in expected_result_files(probe) if Path(path).is_file() and "15min" not in path and "海螺水泥低频数据" not in path],
            result_locations=[paths["step2_result_dir"], paths["step2_abnormal_dir"]],
        ):
            self._set_status("已取消运行。")
            return

        self._set_status("正在运行2号秒级核算...")
        QApplication.processEvents()

        try:
            if not lowfreq_result_file:
                raise ValueError("1号低频汇总结果不能为空")
            normalized_lowfreq = normalize_path(lowfreq_result_file)
            if not is_existing_file(normalized_lowfreq):
                raise FileNotFoundError(f"1号低频汇总结果不存在：{normalized_lowfreq}")

            if not second_data_dir:
                raise ValueError("秒级 / 高频数据目录不能为空")
            normalized_second_dir = normalize_path(second_data_dir)
            if not is_existing_dir(normalized_second_dir):
                raise FileNotFoundError(f"秒级 / 高频数据目录不存在或不是文件夹：{normalized_second_dir}")

            self.lowfreq_result_file_input.setText(normalized_lowfreq)
            self.second_data_dir_input.setText(normalized_second_dir)
            self._save_step2_config()

            log_lines = []

            def page_logger(message):
                log_lines.append(str(message))

            result = run_step2_second_calc(
                lowfreq_result_file=normalized_lowfreq,
                second_data_dir=normalized_second_dir,
                result_dir=paths["step2_result_dir"],
                abnormal_dir=paths["step2_abnormal_dir"],
                target_month=target_month,
                logger=page_logger,
            )

            if result.get("success"):
                output_files = result.get("output_files", [])
                displayed_files = output_files[:20]
                status_text = "2号秒级核算完成\n输出文件：\n" + "\n".join(displayed_files)
                if len(output_files) > len(displayed_files):
                    status_text += f"\n... 另有 {len(output_files) - len(displayed_files)} 个文件"
                if result.get("result_dir"):
                    status_text += f"\n\n秒级结果目录：{result['result_dir']}"
                if result.get("abnormal_dir"):
                    status_text += f"\n异常检测目录：{result['abnormal_dir']}"
                if log_lines:
                    status_text += "\n\n运行日志：\n" + "\n".join(log_lines[-60:])
                self._set_status(status_text)
                append_run_log("2号秒级核算", "success", result.get("message", "2号秒级核算完成"))
            else:
                message = result.get("message", "2号秒级核算失败")
                self._set_status(f"2号秒级核算失败：\n{message}")
                append_run_log("2号秒级核算", "failed", message)
        except Exception as exc:
            detail = format_exception(exc)
            self._set_status(f"2号秒级核算失败：\n{exc}\n\n详细信息：\n{detail}")
            append_run_log("2号秒级核算", "failed", str(exc))

    def _save_step2_config(self):
        config = load_config()
        config["target_month"] = self.target_month_input.text().strip()
        lowfreq_result_file = self.lowfreq_result_file_input.text().strip()
        second_data_dir = self.second_data_dir_input.text().strip()
        config["lowfreq_result_file"] = normalize_path(lowfreq_result_file) if lowfreq_result_file else ""
        config["second_data_dir"] = normalize_path(second_data_dir) if second_data_dir else ""
        save_config(config)

    def _default_lowfreq_result_file(self, config=None):
        current_config = config or load_config()
        return derive_standard_paths(current_config).get("lowfreq_result_file", "")

    def _default_second_data_dir(self, config=None):
        current_config = config or load_config()
        data_root = current_config.get("data_root", "")
        if not data_root:
            return ""
        return str(Path(normalize_path(data_root)) / "1.原始数据" / "(1)核心高频数据")

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
