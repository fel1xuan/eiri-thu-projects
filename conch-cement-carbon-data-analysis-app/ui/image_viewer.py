from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class ZoomableImageView(QGraphicsView):
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._pixmap = QPixmap(image_path)
        self._item = QGraphicsPixmapItem(self._pixmap)
        self._scene.addItem(self._item)
        self.setScene(self._scene)
        self.setSceneRect(self._item.boundingRect())
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(Qt.white)
        self._fit_on_resize = True

    @property
    def image_size(self):
        return self._pixmap.size()

    def fit_image(self):
        if not self._pixmap.isNull():
            self.fitInView(self._item, Qt.KeepAspectRatio)
            self._fit_on_resize = True

    def show_actual_size(self):
        self.resetTransform()
        self.centerOn(self._item)
        self._fit_on_resize = False

    def wheelEvent(self, event):
        if self._pixmap.isNull():
            return super().wheelEvent(event)
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        next_scale = self.transform().m11() * factor
        if 0.03 <= next_scale <= 12:
            self.scale(factor, factor)
            self._fit_on_resize = False
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.fit_image()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_on_resize:
            self.fit_image()


class ImageViewerDialog(QDialog):
    def __init__(self, image_path: str, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1280, 820)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        button_row = QHBoxLayout()
        fit_button = QPushButton("适应窗口")
        actual_button = QPushButton("100%原始比例")
        tip = QLabel("鼠标滚轮缩放，按住并拖动平移，双击恢复适应窗口")
        tip.setObjectName("MutedText")
        button_row.addWidget(fit_button)
        button_row.addWidget(actual_button)
        button_row.addWidget(tip)
        button_row.addStretch(1)

        self.image_view = ZoomableImageView(image_path, self)
        fit_button.clicked.connect(self.image_view.fit_image)
        actual_button.clicked.connect(self.image_view.show_actual_size)

        layout.addLayout(button_row)
        layout.addWidget(self.image_view, 1)

    def showEvent(self, event):
        super().showEvent(event)
        self.image_view.fit_image()
