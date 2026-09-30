from pathlib import Path

from PySide6.QtCore import QDate, QDateTime, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from utils.runtime_paths import prepare_runtime_environment
from utils.matplotlib_utils import configure_matplotlib_fonts

prepare_runtime_environment()
configure_matplotlib_fonts()

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
    from matplotlib.figure import Figure

    MATPLOTLIB_AVAILABLE = True
    MATPLOTLIB_ERROR = ""
except Exception as exc:  # pragma: no cover - depends on local environment
    MATPLOTLIB_AVAILABLE = False
    MATPLOTLIB_ERROR = str(exc)

from utils.config_utils import load_config
from utils.date_range_utils import month_bounds
from utils.fifteen_chart_utils import DATETIME_COL, category_y_label, line_style_for_field, load_15min_series
from utils.path_utils import list_result_files, normalize_path, open_path
from utils.standard_paths import derive_standard_paths


class ResultsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.directory_summary_label = QLabel("")
        self.result_type_combo = QComboBox()
        self.result_dirs = {}
        self.table = QTableWidget()
        self.status_label = QLabel("")
        self.chart_path_input = QLineEdit()
        self.chart_start_date = QDateEdit()
        self.chart_end_date = QDateEdit()
        self.category_combo = QComboBox()
        self.field_list = QListWidget()
        self.chart_status_label = QLabel("")
        self.chart_data = None
        self.field_categories = {}
        self.category_selections = {}
        self.current_category = ""
        self.figure = None
        self.canvas = None
        self.toolbar = None
        self.tabs = QTabWidget()
        self._build_ui()
        self.reload_output_dir()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 34, 36, 34)
        layout.setSpacing(18)

        title = QLabel("结果查看")
        title.setObjectName("PageTitle")

        body = QLabel("用于查看标准数据目录中的低频、秒级、异常和15min结果，并拼接多日15min结果绘制图表。")
        body.setObjectName("BodyText")
        body.setWordWrap(True)

        self.tabs.addTab(self._build_files_tab(), "结果文件")
        self.tabs.addTab(self._build_chart_tab(), "15min图表查看")

        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(self.tabs, 1)

        self.setStyleSheet(
            """
            QLineEdit, QComboBox {
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
            QTableWidget, QListWidget {
                border: 1px solid #d6d6d6;
                border-radius: 4px;
                color: #222222;
                background: #ffffff;
                gridline-color: #eeeeee;
            }
            QHeaderView::section {
                border: none;
                border-bottom: 1px solid #d6d6d6;
                padding: 7px;
                background: #f3f3f3;
                color: #222222;
                font-weight: 600;
            }
            """
        )

    def _build_files_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        path_layout = QGridLayout()
        path_layout.setHorizontalSpacing(10)
        path_layout.setVerticalSpacing(10)
        output_label = QLabel("标准结果目录")
        output_label.setObjectName("CardTitle")
        path_layout.addWidget(output_label, 0, 0)
        self.directory_summary_label.setObjectName("CardText")
        self.directory_summary_label.setWordWrap(True)
        self.directory_summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_layout.addWidget(self.directory_summary_label, 0, 1)
        self.result_type_combo.addItems(["全部", "秒级核算", "秒级异常", "15min结果", "低频主表"])
        self.result_type_combo.currentTextChanged.connect(lambda _text: self.refresh_file_list())
        path_layout.addWidget(QLabel("结果类型"), 1, 0)
        path_layout.addWidget(self.result_type_combo, 1, 1)
        path_layout.setColumnStretch(1, 1)

        directory_button_row = QHBoxLayout()
        directory_button_row.setSpacing(10)
        file_button_row = QHBoxLayout()
        file_button_row.setSpacing(10)
        reload_button = QPushButton("重新读取标准目录")
        open_dir_button = QPushButton("打开当前类型目录")
        refresh_button = QPushButton("刷新文件列表")
        open_file_button = QPushButton("打开选中文件")
        open_file_folder_button = QPushButton("打开文件所在文件夹")
        chart_button = QPushButton("在15min图表中查看")
        reload_button.clicked.connect(self.reload_output_dir)
        open_dir_button.clicked.connect(self.open_output_dir)
        refresh_button.clicked.connect(self.refresh_file_list)
        open_file_button.clicked.connect(self.open_selected_file)
        open_file_folder_button.clicked.connect(self.open_selected_folder)
        chart_button.clicked.connect(self.view_selected_in_chart)
        for button in [reload_button, open_dir_button, refresh_button]:
            directory_button_row.addWidget(button)
        directory_button_row.addStretch(1)
        for button in [open_file_button, open_file_folder_button, chart_button]:
            file_button_row.addWidget(button)
        file_button_row.addStretch(1)

        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["文件名", "类型", "大小", "修改时间", "路径"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(390)

        self.status_label.setObjectName("MutedText")
        self.status_label.setWordWrap(True)

        layout.addLayout(path_layout)
        layout.addLayout(directory_button_row)
        layout.addLayout(file_button_row)
        layout.addWidget(self.table)
        layout.addWidget(self.status_label)
        return tab

    def _build_chart_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        controls = QGridLayout()
        controls.setHorizontalSpacing(10)
        controls.setVerticalSpacing(10)
        self.chart_path_input.setMinimumWidth(360)
        self.chart_path_input.setPlaceholderText("默认读取数据项目的4.15min核算数据，也可临时选择单个15min文件或文件夹")
        controls.addWidget(QLabel("15min结果路径"), 0, 0)
        controls.addWidget(self.chart_path_input, 0, 1)
        controls.setColumnStretch(1, 1)

        choose_file_button = QPushButton("选择文件")
        choose_folder_button = QPushButton("选择文件夹")
        use_output_button = QPushButton("使用标准15min目录")
        choose_file_button.clicked.connect(self.choose_chart_file)
        choose_folder_button.clicked.connect(self.choose_chart_folder)
        use_output_button.clicked.connect(self.use_output_dir_for_chart)
        chart_path_buttons = QHBoxLayout()
        chart_path_buttons.addWidget(choose_file_button)
        chart_path_buttons.addWidget(choose_folder_button)
        chart_path_buttons.addWidget(use_output_button)
        controls.addLayout(chart_path_buttons, 0, 2)

        for date_input in (self.chart_start_date, self.chart_end_date):
            date_input.setCalendarPopup(True)
            date_input.setDisplayFormat("yyyy-MM-dd")
            date_input.setMinimumWidth(160)
        controls.addWidget(QLabel("图表开始日期"), 1, 0)
        controls.addWidget(self.chart_start_date, 1, 1)
        controls.addWidget(QLabel("图表结束日期"), 2, 0)
        controls.addWidget(self.chart_end_date, 2, 1)

        self.category_combo.setMinimumWidth(260)
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        controls.addWidget(QLabel("图表类别"), 3, 0)
        controls.addWidget(self.category_combo, 3, 1)

        load_button = QPushButton("读取15min文件和字段")
        plot_button = QPushButton("绘制当前类别")
        clear_button = QPushButton("清空图表")
        select_all_button = QPushButton("全选当前类别")
        deselect_button = QPushButton("全不选当前类别")
        load_button.clicked.connect(self.load_chart_data)
        plot_button.clicked.connect(self.plot_chart)
        clear_button.clicked.connect(self.clear_chart)
        select_all_button.clicked.connect(self.select_all_current_category)
        deselect_button.clicked.connect(self.clear_field_selection)
        action_row = QHBoxLayout()
        action_row.addWidget(load_button)
        action_row.addWidget(plot_button)
        action_row.addWidget(clear_button)
        action_row.addWidget(select_all_button)
        action_row.addWidget(deselect_button)
        action_row.addStretch(1)

        self.field_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.field_list.setMinimumHeight(130)

        layout.addLayout(controls)
        layout.addLayout(action_row)
        layout.addWidget(QLabel("当前类别字段（不同物理维度不会共用同一Y轴）"))
        layout.addWidget(self.field_list)

        if MATPLOTLIB_AVAILABLE:
            self.figure = Figure(figsize=(8, 4), tight_layout=True)
            self.canvas = FigureCanvas(self.figure)
            self.canvas.setMinimumHeight(320)
            self.toolbar = NavigationToolbar(self.canvas, self)
            layout.addWidget(self.toolbar)
            layout.addWidget(self.canvas, 1)
        else:
            missing = QLabel(f"当前环境未安装或无法加载 Matplotlib：{MATPLOTLIB_ERROR}")
            missing.setWordWrap(True)
            layout.addWidget(missing)

        self.chart_status_label.setObjectName("MutedText")
        self.chart_status_label.setWordWrap(True)
        layout.addWidget(self.chart_status_label)
        return tab

    def reload_output_dir(self):
        config = load_config()
        paths = derive_standard_paths(config)
        self.result_dirs = {
            "低频主表": paths.get("step1_output_dir", ""),
            "秒级核算": paths.get("step2_result_dir", ""),
            "秒级异常": paths.get("step2_abnormal_dir", ""),
            "15min结果": paths.get("step3_result_dir", ""),
        }
        self.directory_summary_label.setText(
            "\n".join(f"{label}：{path or '未配置'}" for label, path in self.result_dirs.items())
        )
        self.chart_path_input.setText(paths.get("step3_result_dir", ""))
        self._apply_chart_dates(config)
        self._set_status("已重新读取标准结果目录")
        self.refresh_file_list()

    def refresh_from_config(self):
        self.reload_output_dir()

    def refresh_file_list(self):
        try:
            selected_type = self.result_type_combo.currentText() or "全部"
            categories = self.result_dirs.items() if selected_type == "全部" else [(selected_type, self.result_dirs.get(selected_type, ""))]
            files = []
            for category, directory in categories:
                if not directory or not Path(directory).is_dir():
                    continue
                for item in list_result_files(directory):
                    if category == "低频主表" and "海螺水泥低频数据" not in item["name"]:
                        continue
                    if category == "秒级核算" and "秒级CO2排放结果" not in item["name"] and "秒级碳排放" not in item["name"]:
                        continue
                    if category == "秒级异常" and "异常检测" not in item["name"]:
                        continue
                    if category == "15min结果" and "15min" not in item["name"]:
                        continue
                    item = dict(item)
                    item["type"] = category
                    item["mtime"] = Path(item["path"]).stat().st_mtime
                    files.append(item)
            files.sort(key=lambda item: item["mtime"], reverse=True)
            self.table.setRowCount(len(files))
            for row_index, item in enumerate(files):
                values = [item["name"], item["type"], item["size"], item["modified_time"], item["path"]]
                for col_index, value in enumerate(values):
                    table_item = QTableWidgetItem(str(value))
                    self.table.setItem(row_index, col_index, table_item)

            if files:
                file_types = sorted({item["type"] for item in files})
                self._set_status(f"已识别{len(files)}个结果文件；类型：{', '.join(file_types)}")
            else:
                self._set_status("当前结果类型下暂无可展示的文件")
        except Exception as exc:
            self.table.setRowCount(0)
            self._set_status(str(exc))

    def open_output_dir(self):
        selected_type = self.result_type_combo.currentText() or "全部"
        output_dir = self.result_dirs.get(selected_type, "")
        if not output_dir and selected_type == "全部":
            config = load_config()
            output_dir = str(config.get("data_root", "") or "")
        try:
            open_path(output_dir)
            self._set_status(f"已打开结果目录：{normalize_path(output_dir)}")
        except Exception as exc:
            self._set_status(f"打开输出目录失败：{exc}")

    def open_selected_file(self):
        selected_path = self._selected_file_path()
        if not selected_path:
            self._set_status("请先选择一个文件")
            return
        try:
            open_path(selected_path)
            self._set_status(f"已打开文件：{selected_path}")
        except Exception as exc:
            self._set_status(f"打开选中文件失败：{exc}")

    def open_selected_folder(self):
        selected_path = self._selected_file_path()
        selected_type = self.result_type_combo.currentText() or "全部"
        fallback = self.result_dirs.get(selected_type, "") or str(load_config().get("data_root", "") or "")
        folder = Path(selected_path).parent if selected_path else Path(normalize_path(fallback))
        try:
            open_path(folder)
            self._set_status(f"已打开文件夹：{folder}")
        except Exception as exc:
            self._set_status(f"打开文件夹失败：{exc}")

    def view_selected_in_chart(self):
        selected_path = self._selected_file_path()
        if not selected_path:
            self._set_status("请先选择一个15min结果文件")
            return
        if "15min" not in Path(selected_path).name.lower():
            self._set_status("当前文件不是15min结果文件。")
            return
        self.chart_path_input.setText(selected_path)
        self.tabs.setCurrentIndex(1)
        self.load_chart_data()

    def choose_chart_file(self):
        selected, _ = QFileDialog.getOpenFileName(self, "选择15min结果文件", self._chart_initial_dir(), "结果文件 (*.xlsx *.xls *.csv);;所有文件 (*)")
        if selected:
            self.chart_path_input.setText(normalize_path(selected))

    def choose_chart_folder(self):
        selected = QFileDialog.getExistingDirectory(self, "选择15min结果文件夹", self._chart_initial_dir())
        if selected:
            self.chart_path_input.setText(normalize_path(selected))

    def use_output_dir_for_chart(self):
        path = self.result_dirs.get("15min结果", "")
        self.chart_path_input.setText(path)
        self._set_chart_status(f"已使用标准15min结果目录：{path or '未配置'}")

    def load_chart_data(self):
        try:
            source_path = self.chart_path_input.text().strip() or self.result_dirs.get("15min结果", "")
            self._set_chart_status("正在读取15min文件...")
            source = Path(normalize_path(source_path))
            start_date, end_date = self._chart_date_range()
            result = load_15min_series(
                source_path,
                start_date=start_date if source.is_dir() else "",
                end_date=end_date if source.is_dir() else "",
            )
            if result.get("rows", 0) == 0:
                raise ValueError("未读取到有效的15min数据")
            self.chart_data = result
            self._apply_loaded_date_bounds(result)
            self._populate_categories(result.get("field_categories", {}))
            self._set_chart_status(self._format_chart_load_status(result))
        except Exception as exc:
            self.chart_data = None
            self.category_combo.clear()
            self.field_list.clear()
            self._set_chart_status(f"读取15min结果失败：{exc}")

    def plot_chart(self):
        if not MATPLOTLIB_AVAILABLE:
            self._set_chart_status(f"无法绘图：Matplotlib不可用。{MATPLOTLIB_ERROR}")
            return
        if not self.chart_data:
            self.load_chart_data()
        if not self.chart_data:
            return

        selected_fields = self._checked_fields()
        if not selected_fields:
            self._set_chart_status("请先在当前类别中选择至少一个字段")
            return
        if len(selected_fields) > 8:
            self._set_chart_status("当前选择字段较多，图表可能拥挤；建议减少字段后查看。")

        df = self.chart_data["data"]
        if df.empty:
            self._set_chart_status("没有可绘制的15min数据")
            return

        start_date, end_date = self._chart_date_range()
        range_start = QDateTime.fromString(f"{start_date} 00:00:00", "yyyy-MM-dd HH:mm:ss").toPython()
        range_end = QDateTime.fromString(f"{end_date} 23:59:59", "yyyy-MM-dd HH:mm:ss").toPython()
        plot_df = df[(df[DATETIME_COL] >= range_start) & (df[DATETIME_COL] <= range_end)]
        if plot_df.empty:
            self._set_chart_status("当前日期范围内没有可绘制的15min数据")
            return

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        category = self.current_category or str(self.category_combo.currentData() or "")
        chart_category = category.replace("₂", "2")
        for index, field in enumerate(selected_fields):
            values = plot_df[field] if field in plot_df.columns else None
            if values is None:
                continue
            ax.plot(
                plot_df[DATETIME_COL],
                values,
                label=field,
                **line_style_for_field(field, category, index),
            )
        ax.set_title(f"{start_date} 至 {end_date} · {chart_category}")
        ax.set_xlabel("时间")
        ax.set_ylabel(category_y_label(category).replace("₂", "2"))
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4)
        ax.legend(loc="best")
        self.figure.autofmt_xdate()
        self.canvas.draw()
        status = self._format_chart_load_status(self.chart_data)
        self._set_chart_status(
            f"{status}\n当前绘图区间：{start_date} 至 {end_date}\n"
            f"当前类别：{category}；当前字段：{len(selected_fields)}个；绘图数据：{len(plot_df)}行"
        )

    def clear_chart(self):
        if self.figure and self.canvas:
            self.figure.clear()
            self.canvas.draw()
        self._set_chart_status("图表已清空")

    def _selected_file_path(self):
        selected_items = self.table.selectedItems()
        if not selected_items:
            return ""
        row = selected_items[0].row()
        path_item = self.table.item(row, 4)
        return path_item.text() if path_item else ""

    def _populate_categories(self, categories):
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.field_categories = {str(category): list(fields) for category, fields in categories.items()}
        self.category_selections = {category: set() for category in self.field_categories}
        self.current_category = ""
        for category, fields in self.field_categories.items():
            self.category_combo.addItem(f"{category}（{len(fields)}）", category)
        self.category_combo.blockSignals(False)
        if self.category_combo.count():
            self.category_combo.setCurrentIndex(0)
            self._on_category_changed(self.category_combo.currentText())
        else:
            self.field_list.clear()

    def _on_category_changed(self, _display_text):
        self._remember_current_selection()
        self.current_category = str(self.category_combo.currentData() or "")
        self.field_list.clear()
        checked_fields = self.category_selections.get(self.current_category, set())
        for field in self.field_categories.get(self.current_category, []):
            item = QListWidgetItem(str(field))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if str(field) in checked_fields else Qt.Unchecked)
            self.field_list.addItem(item)
        if self.current_category:
            self._set_chart_status(
                f"当前类别：{self.current_category}；可选字段：{self.field_list.count()}个。"
                "请手动勾选，或使用当前类别全选。"
            )

    def _remember_current_selection(self):
        if self.current_category:
            self.category_selections[self.current_category] = set(self._checked_fields())

    def clear_field_selection(self):
        for index in range(self.field_list.count()):
            self.field_list.item(index).setCheckState(Qt.Unchecked)
        if self.current_category:
            self.category_selections[self.current_category] = set()
        self._set_chart_status(f"已取消选择当前类别字段：{self.current_category}")

    def select_all_current_category(self):
        for index in range(self.field_list.count()):
            self.field_list.item(index).setCheckState(Qt.Checked)
        selected = set(self._checked_fields())
        if self.current_category:
            self.category_selections[self.current_category] = selected
        self._set_chart_status(f"已选择当前类别全部字段：{self.current_category}，共{len(selected)}个")

    def _checked_fields(self):
        return [
            self.field_list.item(index).text()
            for index in range(self.field_list.count())
            if self.field_list.item(index).checkState() == Qt.Checked
        ]

    def _apply_loaded_date_bounds(self, result):
        time_start = result.get("time_start")
        time_end = result.get("time_end")
        if time_start is None or time_end is None:
            return
        min_date = QDate(time_start.year, time_start.month, time_start.day)
        max_date = QDate(time_end.year, time_end.month, time_end.day)
        previous_start = self.chart_start_date.date()
        previous_end = self.chart_end_date.date()
        for widget in (self.chart_start_date, self.chart_end_date):
            widget.setMinimumDate(min_date)
            widget.setMaximumDate(max_date)
        self.chart_start_date.setDate(previous_start if min_date <= previous_start <= max_date else min_date)
        self.chart_end_date.setDate(previous_end if min_date <= previous_end <= max_date else max_date)

    def _apply_chart_dates(self, config):
        target_month = str(config.get("target_month", "") or "").strip()
        try:
            month_start, month_end = month_bounds(target_month)
            min_qdate = QDate.fromString(month_start, "yyyy-MM-dd")
            max_qdate = QDate.fromString(month_end, "yyyy-MM-dd")
            for widget in (self.chart_start_date, self.chart_end_date):
                widget.setMinimumDate(min_qdate)
                widget.setMaximumDate(max_qdate)
            start = str(config.get("process_start_date", "") or month_start)
            end = str(config.get("process_end_date", "") or month_end)
            self.chart_start_date.setDate(QDate.fromString(start, "yyyy-MM-dd"))
            self.chart_end_date.setDate(QDate.fromString(end, "yyyy-MM-dd"))
        except Exception:
            today = QDate.currentDate()
            self.chart_start_date.setDate(today)
            self.chart_end_date.setDate(today)

    def _chart_date_range(self):
        start_date = self.chart_start_date.date()
        end_date = self.chart_end_date.date()
        if start_date > end_date:
            raise ValueError("图表开始日期不能晚于结束日期")
        return start_date.toString("yyyy-MM-dd"), end_date.toString("yyyy-MM-dd")

    def _chart_initial_dir(self):
        value = self.chart_path_input.text().strip() or self.result_dirs.get("15min结果", "")
        if value:
            path = Path(normalize_path(value))
            if path.is_file():
                return str(path.parent)
            if path.is_dir():
                return str(path)
        return str(Path.home())

    def _format_chart_load_status(self, result):
        time_start = result.get("time_start")
        time_end = result.get("time_end")
        time_range = "无有效时间"
        if time_start is not None and time_end is not None:
            time_range = f"{time_start:%Y-%m-%d %H:%M} 至 {time_end:%Y-%m-%d %H:%M}"
        missing = result.get("missing_dates", []) or []
        failures = result.get("failures", []) or []
        lines = [
            f"当前15min路径：{self.chart_path_input.text().strip()}",
            f"识别文件数量：{len(result.get('files', []) or [])}个",
            f"实际加载文件数量：{result.get('files_read', 0)}个",
            f"合并后共{result.get('rows', 0)}行",
            f"时间范围：{time_range}",
            f"可绘制字段：{len(result.get('numeric_columns', []) or [])}个",
            f"图表类别：{len(result.get('field_categories', {}) or {})}类",
            f"缺失日期：{', '.join(missing[:20]) if missing else '无'}",
            f"重复时间点数量：{result.get('duplicate_count', 0)}",
        ]
        if failures:
            lines.append("读取失败文件：")
            lines.extend(f"{item['file']}：{item['error']}" for item in failures[:8])
        return "\n".join(lines)

    def _set_status(self, message):
        self.status_label.setText(str(message))

    def _set_chart_status(self, message):
        self.chart_status_label.setText(str(message))
