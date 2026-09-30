from pathlib import Path

from PySide6.QtWidgets import (
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from utils.log_utils import get_run_log_path, read_run_logs
from utils.path_utils import open_path


class LogsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.table = QTableWidget()
        self.status_label = QLabel("暂无运行记录")
        self._build_ui()
        self.refresh_logs()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 34, 36, 34)
        layout.setSpacing(18)

        title = QLabel("运行记录")
        title.setObjectName("PageTitle")

        body = QLabel(f"用于查看软件历史运行记录，记录来源为：{get_run_log_path()}。最新记录显示在最上方。")
        body.setObjectName("BodyText")
        body.setWordWrap(True)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        refresh_button = QPushButton("刷新运行记录")
        open_file_button = QPushButton("打开日志文件")
        open_folder_button = QPushButton("打开日志所在文件夹")
        refresh_button.clicked.connect(self.refresh_logs)
        open_file_button.clicked.connect(self.open_log_file)
        open_folder_button.clicked.connect(self.open_log_folder)
        button_row.addWidget(refresh_button)
        button_row.addWidget(open_file_button)
        button_row.addWidget(open_folder_button)
        button_row.addStretch(1)

        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["time", "module", "status", "message"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMinimumHeight(420)

        self.status_label.setObjectName("MutedText")
        self.status_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(body)
        layout.addLayout(button_row)
        layout.addWidget(self.table)
        layout.addWidget(self.status_label)

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
            QTableWidget {
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

    def refresh_logs(self):
        try:
            rows = read_run_logs()
            self.table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                values = [row.get("time", ""), row.get("module", ""), row.get("status", ""), row.get("message", "")]
                for col_index, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    self.table.setItem(row_index, col_index, item)

            if rows:
                self.status_label.setText(f"已读取运行记录：{len(rows)} 条")
            else:
                self.status_label.setText("暂无运行记录")
        except Exception as exc:
            self.table.setRowCount(0)
            self.status_label.setText(f"运行记录读取失败：{exc}")

    def refresh_from_config(self):
        self.refresh_logs()

    def open_log_file(self):
        log_path = Path(get_run_log_path())
        if not log_path.exists():
            self.status_label.setText("日志文件不存在")
            return
        try:
            open_path(log_path)
            self.status_label.setText(f"已打开日志文件：{log_path}")
        except Exception as exc:
            self.status_label.setText(f"打开日志文件失败：{exc}")

    def open_log_folder(self):
        folder = Path(get_run_log_path()).parent
        if not folder.exists():
            self.status_label.setText("日志所在文件夹不存在")
            return
        try:
            open_path(folder)
            self.status_label.setText(f"已打开日志所在文件夹：{folder}")
        except Exception as exc:
            self.status_label.setText(f"打开日志所在文件夹失败：{exc}")
