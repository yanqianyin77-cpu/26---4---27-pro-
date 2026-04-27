from __future__ import annotations

# noinspection PyUnresolvedReferences
from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QVariantAnimation
# noinspection PyUnresolvedReferences
from PySide6.QtGui import QPainter
# noinspection PyUnresolvedReferences
from PySide6.QtWidgets import QPushButton


class RippleButton(QPushButton):
    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._ripple_radius = 0
        self._ripple_pos = QPoint(0, 0)
        self._ripple_anim = QVariantAnimation(self)
        self._ripple_anim.setDuration(420)
        self._ripple_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._ripple_anim.setStartValue(0)
        self._ripple_anim.setEndValue(260)
        self._ripple_anim.valueChanged.connect(self._set_ripple)
        self._ripple_anim.finished.connect(self._clear_ripple)
        self._press_anim = QPropertyAnimation(self, b"pos", self)
        self._press_anim.setDuration(120)
        self._press_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _set_ripple(self, value) -> None:
        self._ripple_radius = int(value)
        self.update()

    def _clear_ripple(self) -> None:
        self._ripple_radius = 0
        self.update()

    def mousePressEvent(self, event) -> None:
        self._ripple_pos = event.position().toPoint()
        self._ripple_anim.stop()
        self._ripple_anim.start()
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._ripple_radius <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = self.palette().buttonText().color()
        color.setAlpha(34)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(self._ripple_pos, self._ripple_radius, self._ripple_radius)
