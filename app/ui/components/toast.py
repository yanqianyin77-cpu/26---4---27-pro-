from __future__ import annotations

# noinspection PyUnresolvedReferences
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
# noinspection PyUnresolvedReferences
from PySide6.QtWidgets import QLabel, QWidget


class Toast(QLabel):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        self.hide()
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def show_message(self, text: str, timeout: int = 1800) -> None:
        self.setText(text)
        self.adjustSize()
        w = max(self.width() + 52, 260)
        h = 48
        self.resize(w, h)
        parent = self.parentWidget()
        if parent:
            self.move((parent.width() - w) // 2, parent.height() - h - 36)
        self.setWindowOpacity(0)
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(0)
        self._anim.setEndValue(1)
        self._anim.start()
        QTimer.singleShot(timeout, self._hide)

    def _hide(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(1)
        self._anim.setEndValue(0)
        self._anim.finished.connect(self.hide)
        self._anim.start()
