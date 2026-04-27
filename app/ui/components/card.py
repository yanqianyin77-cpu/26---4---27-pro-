from __future__ import annotations

# noinspection PyUnresolvedReferences
from PySide6.QtGui import QColor
# noinspection PyUnresolvedReferences
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QLabel, QVBoxLayout


class Card(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMouseTracking(True)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(0, 0, 0, 16))
        shadow.setOffset(0, 3)
        self._shadow = shadow
        self.setGraphicsEffect(shadow)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(18, 16, 18, 18)
        self.layout.setSpacing(10)
        if title:
            title_label = QLabel(title)
            title_label.setStyleSheet("font-size:16px;font-weight:700;")
            self.layout.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setWordWrap(True)
            subtitle_label.setStyleSheet("color:#6E7C84;")
            self.layout.addWidget(subtitle_label)

    def enterEvent(self, event):
        self._shadow.setBlurRadius(20)
        self._shadow.setOffset(0, 5)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._shadow.setBlurRadius(12)
        self._shadow.setOffset(0, 3)
        super().leaveEvent(event)
