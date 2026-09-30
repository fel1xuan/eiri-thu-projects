from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from utils.resource_utils import resource_path
from utils.version import APP_DISPLAY_VERSION
from ui.image_viewer import ImageViewerDialog


class ResponsiveImageLabel(QLabel):
    def __init__(self, image_path: str):
        super().__init__()
        self._source_pixmap = QPixmap(image_path)
        self.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(160)
        self._update_scaled_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if self._source_pixmap.isNull():
            self.setText("图片资源未找到")
            return
        available_width = max(320, self.width() - 4)
        scaled = self._source_pixmap.scaledToWidth(available_width, Qt.SmoothTransformation)
        self.setPixmap(scaled)
        self.setFixedHeight(scaled.height())


class HelpPage(QWidget):
    def __init__(self):
        super().__init__()
        self._image_viewers = []
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(36, 34, 36, 40)
        layout.setSpacing(18)

        title = QLabel("清华数据分析软件")
        title.setObjectName("PageTitle")
        version = QLabel(APP_DISPLAY_VERSION)
        version.setObjectName("BodyText")

        layout.addWidget(title)
        layout.addWidget(version)
        layout.addWidget(self._section_title("软件用途"))
        layout.addWidget(
            self._paragraph(
                "本软件用于海螺水泥碳排放数据处理，将生产日报、低频数据、高频数据、烟气数据和三声道数据进行统一处理，依次完成日报提取、低频汇总、秒级碳排放核算与异常检测以及15min聚合，并提供结果文件查看与15min图表展示功能。"
            )
        )
        layout.addWidget(self._section_title("推荐流程"))
        layout.addWidget(
            self._paragraph(
                "1. 项目配置\n"
                "2. 选择处理月份和日期范围\n"
                "3. 运行0号日报提取\n"
                "4. 查看自动检查结果并点击“确认审核通过”完成人工审核\n"
                "5. 一键运行1号 → 2号 → 3号\n"
                "6. 结果查看\n"
                "7. 15min图表分析\n"
                "8. 运行记录检查"
            )
        )

        layout.addWidget(self._section_title("海螺水泥碳排放核算：物理数据路径"))
        physical_path = resource_path("assets/mindmaps/physical_data_path.png")
        self.physical_image = ResponsiveImageLabel(physical_path)
        layout.addWidget(self.physical_image)
        layout.addLayout(self._viewer_button_row(physical_path, "海螺水泥碳排放核算：物理数据路径"))

        layout.addWidget(self._section_title("海螺水泥碳排放代码数据分析流程"))
        code_flow_path = resource_path("assets/mindmaps/code_data_analysis_flow.png")
        self.code_flow_image = ResponsiveImageLabel(code_flow_path)
        layout.addWidget(self.code_flow_image)
        layout.addLayout(self._viewer_button_row(code_flow_path, "海螺水泥碳排放代码数据分析流程"))

        layout.addWidget(self._section_title("输出说明"))
        layout.addWidget(
            self._paragraph(
                "正式输出数据不会写入软件代码目录。\n\n"
                "“清华数据分析软件”目录用于保存Python代码、UI、配置模板和打包资源；“清华能源实习数据分析”目录用于保存用户原始数据和正式结果。\n\n"
                "0号结果写入当月低频目录，1号累计低频表写入低频数据根目录，秒级、异常和15min结果分别写入2.秒级核算数据、3.秒级异常数据统计和4.15min核算数据。\n\n"
                "原始数据和计算结果不要与软件代码混在一起。"
            )
        )
        layout.addStretch(1)

        scroll.setWidget(content)
        root_layout.addWidget(scroll)

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("CardTitle")
        label.setWordWrap(True)
        label.setContentsMargins(0, 10, 0, 0)
        return label

    @staticmethod
    def _paragraph(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("BodyText")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    def _viewer_button_row(self, image_path: str, title: str) -> QHBoxLayout:
        row = QHBoxLayout()
        button = QPushButton("查看高清大图")
        button.clicked.connect(lambda checked=False, path=image_path, name=title: self._open_image_viewer(path, name))
        row.addWidget(button)
        row.addStretch(1)
        return row

    def _open_image_viewer(self, image_path: str, title: str):
        viewer = ImageViewerDialog(image_path, title, self)
        viewer.setAttribute(Qt.WA_DeleteOnClose)
        viewer.destroyed.connect(lambda _object=None: self._forget_viewer(viewer))
        self._image_viewers.append(viewer)
        viewer.show()

    def _forget_viewer(self, viewer):
        if viewer in self._image_viewers:
            self._image_viewers.remove(viewer)
