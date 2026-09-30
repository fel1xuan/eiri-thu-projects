from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from utils.config_utils import is_step0_review_approved, load_config
from utils.date_range_utils import resolve_process_date_range
from utils.path_utils import is_existing_dir, is_existing_file
from utils.standard_paths import derive_standard_paths, expected_result_files


class WorkbenchPage(QWidget):
    def __init__(self):
        super().__init__()
        self.summary_labels = {}
        self._build_ui()
        self.refresh_from_config()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 34, 36, 34)
        layout.setSpacing(18)

        title = QLabel("工作台")
        title.setObjectName("PageTitle")
        intro = QLabel("清华数据分析软件用于海螺水泥碳排放数据处理。当前支持单月内指定日期范围处理。")
        intro.setObjectName("BodyText")
        intro.setWordWrap(True)

        summary = QFrame()
        summary.setObjectName("InfoCard")
        summary.setMaximumWidth(760)
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(18, 14, 18, 14)
        summary_layout.setSpacing(8)
        heading = QLabel("当前任务")
        heading.setObjectName("CardTitle")
        summary_layout.addWidget(heading)
        for key in ("project", "month", "date_range", "step0", "review", "step1", "step2", "step3"):
            label = QLabel("-")
            label.setObjectName("CardText")
            label.setWordWrap(True)
            self.summary_labels[key] = label
            summary_layout.addWidget(label)

        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(summary)
        layout.addWidget(
            self._info_card(
                "推荐使用顺序",
                "1. 在“项目配置”选择数据项目根目录和处理月份，由软件自动识别输入；\n"
                "2. 在“0号 日报提取与审核”运行并审核0号结果；\n"
                "3. 在“一键运行”依次执行1号、2号、3号；\n"
                "4. 在“结果查看”和“运行记录”检查输出。",
            )
        )
        layout.addWidget(
            self._info_card(
                "使用提醒",
                "当前只支持单月内日期范围，不允许跨月处理。详细路径只在“项目配置”页面维护。",
            )
        )
        layout.addStretch(1)

    def refresh_from_config(self):
        try:
            config = load_config()
            date_info = resolve_process_date_range(
                config.get("target_month", ""), config.get("process_start_date", ""), config.get("process_end_date", "")
            )
            complete = (
                date_info.get("ok")
                and is_existing_file(config.get("report_file", ""))
                and is_existing_file(config.get("history_lowfreq_file", ""))
                and is_existing_dir(config.get("lowfreq_current_path", ""))
                and is_existing_dir(config.get("second_data_dir", ""))
                and bool(str(config.get("data_root", "") or "").strip())
            )
            if config.get("step0_needs_rerun"):
                review = "已失效，需要重新运行并人工审核"
            elif date_info.get("ok") and is_step0_review_approved(
                config, date_info["start_date"], date_info["end_date"]
            ):
                review = "人工审核通过"
            else:
                review = "待人工审核"
            paths = derive_standard_paths(config)
            expected = expected_result_files(config)
            step2_files = [path for path in expected if "秒级CO2排放结果" in path]
            abnormal_files = [path for path in expected if "异常检测结果" in path]
            step3_files = [path for path in expected if "15minCO2排放结果" in path]
            self.summary_labels["project"].setText(
                f"当前数据项目：{Path(config.get('data_root', '')).name if config.get('data_root') else '未配置'}"
            )
            self.summary_labels["project"].setToolTip(str(config.get("data_root", "") or ""))
            self.summary_labels["month"].setText(f"处理月份：{config.get('target_month') or '未配置'}")
            self.summary_labels["date_range"].setText(
                f"当前日期：{date_info['start_date']} 至 {date_info['end_date']}" if date_info.get("ok") else "当前日期：未配置或无效"
            )
            self.summary_labels["step0"].setText(
                f"0号结果：{'已生成' if is_existing_file(paths.get('step0_output_file', '')) else '未生成'}"
            )
            self.summary_labels["review"].setText(f"0号人工审核：{review}")
            self.summary_labels["step1"].setText(
                f"1号结果：{'已生成' if is_existing_file(paths.get('lowfreq_result_file', '')) else '未生成'}"
            )
            self.summary_labels["step2"].setText(
                f"2号结果：秒级 {sum(Path(path).is_file() for path in step2_files)}/{len(step2_files)}；"
                f"异常 {sum(Path(path).is_file() for path in abnormal_files)}/{len(abnormal_files)}"
            )
            self.summary_labels["step3"].setText(
                f"3号结果：15min {sum(Path(path).is_file() for path in step3_files)}/{len(step3_files)}"
            )
            if not complete:
                self.summary_labels["project"].setText(self.summary_labels["project"].text() + "（配置不完整）")
        except Exception as exc:
            self.summary_labels["project"].setText(f"项目配置读取失败（{exc}）")

    @staticmethod
    def _info_card(title_text, body_text):
        card = QFrame()
        card.setObjectName("InfoCard")
        card.setMaximumWidth(760)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)
        title = QLabel(title_text)
        title.setObjectName("CardTitle")
        body = QLabel(body_text)
        body.setObjectName("CardText")
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(title)
        layout.addWidget(body)
        return card
