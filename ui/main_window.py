from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.page_logs import LogsPage
from ui.page_help import HelpPage
from ui.page_project_config import ProjectConfigPage
from ui.page_results import ResultsPage
from ui.page_run_pipeline import RunPipelinePage
from ui.page_step0 import Step0Page
from ui.page_workbench import WorkbenchPage
from utils.resource_utils import resource_path
from utils.version import APP_DISPLAY_VERSION


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("清华数据分析软件")
        logo_path = resource_path("assets/logo.png")
        if logo_path:
            self.setWindowIcon(QIcon(logo_path))
        self.resize(1200, 760)

        self.nav_buttons = []
        self.pages = [
            ("工作台", WorkbenchPage()),
            ("项目配置", ProjectConfigPage()),
            ("0号 日报提取与审核", Step0Page()),
            ("一键运行", RunPipelinePage()),
            ("结果查看", ResultsPage()),
            ("运行记录", LogsPage()),
            ("使用说明", HelpPage()),
        ]

        self.pages[2][1].navigate_to_config.connect(lambda: self._set_current_page(1))
        self.pages[3][1].navigate_to_config.connect(lambda: self._set_current_page(1))

        self._build_ui()
        self._set_current_page(0)

    def _build_ui(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = self._build_sidebar()
        self.stack = QStackedWidget()
        self.stack.setObjectName("ContentStack")

        for _, page in self.pages:
            if isinstance(page, HelpPage):
                self.stack.addWidget(page)
                continue
            scroll = QScrollArea()
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self.stack, 1)

        self.setCentralWidget(root)
        self.setStyleSheet(
            """
            QMainWindow {
                background: #ffffff;
            }
            QFrame#Sidebar {
                background: #f2f2f2;
                border-right: 1px solid #d8d8d8;
            }
            QLabel#AppTitle {
                color: #1f1f1f;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#AppSubtitle {
                color: #666666;
                font-size: 12px;
            }
            QPushButton#NavButton {
                border: none;
                border-radius: 6px;
                color: #222222;
                font-size: 14px;
                padding: 10px 14px;
                text-align: left;
                background: transparent;
            }
            QPushButton#NavButton:hover {
                background: #e8e8e8;
            }
            QPushButton#NavButton:checked {
                background: #d9d9d9;
                font-weight: 600;
            }
            QStackedWidget#ContentStack {
                background: #ffffff;
            }
            QLabel#PageTitle {
                color: #111111;
                font-size: 26px;
                font-weight: 700;
            }
            QLabel#BodyText {
                color: #333333;
                font-size: 15px;
                line-height: 1.5;
            }
            QLabel#MutedText {
                color: #666666;
                font-size: 13px;
            }
            QFrame#InfoCard {
                background: #f7f7f7;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }
            QLabel#CardTitle {
                color: #222222;
                font-size: 15px;
                font-weight: 600;
            }
            QLabel#CardText {
                color: #555555;
                font-size: 13px;
            }
            """
        )

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(240)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(8)

        title = QLabel("清华数据分析软件")
        title.setObjectName("AppTitle")
        title.setWordWrap(True)

        subtitle = QLabel(f"单月数据处理 · {APP_DISPLAY_VERSION}")
        subtitle.setObjectName("AppSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(18)

        for index, (label, _) in enumerate(self.pages):
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked=False, page_index=index: self._set_current_page(page_index))
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)
        return sidebar

    def _set_current_page(self, index):
        self.stack.setCurrentIndex(index)
        page = self.pages[index][1]
        refresh = getattr(page, "refresh_from_config", None)
        if callable(refresh):
            refresh()
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)
