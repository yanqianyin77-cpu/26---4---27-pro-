from __future__ import annotations

# noinspection PyUnresolvedReferences
from PySide6.QtCore import QRect, Qt, QTimer
# noinspection PyUnresolvedReferences
from PySide6.QtGui import QColor, QPainter, QPen
# noinspection PyUnresolvedReferences
from PySide6.QtWidgets import QWidget


class LoadingOverlay(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.angle = 0
        self.text = "正在处理…"
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.hide()

    def start(self, text: str = "正在处理…") -> None:
        self.text = text
        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        self.timer.start(32)

    def stop(self) -> None:
        self.timer.stop()
        self.hide()

    def _tick(self) -> None:
        self.angle = (self.angle + 8) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(250, 247, 241, 138))
        center = self.rect().center()
        radius = 18
        painter.setPen(QPen(QColor("#7E98A8"), 3))
        painter.drawArc(
            QRect(center.x() - radius, center.y() - radius, radius * 2, radius * 2),
            self.angle * 16,
            120 * 16,
        )
        painter.setPen(QColor("#33424B"))
        painter.drawText(QRect(0, center.y() + 28, self.width(), 36), Qt.AlignmentFlag.AlignCenter, self.text)
