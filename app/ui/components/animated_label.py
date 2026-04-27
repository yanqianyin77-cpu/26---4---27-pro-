from __future__ import annotations

# noinspection PyUnresolvedReferences
from PySide6.QtCore import QEasingCurve, QVariantAnimation
# noinspection PyUnresolvedReferences
from PySide6.QtWidgets import QLabel


class AnimatedNumberLabel(QLabel):
    def __init__(self, value: int = 0, parent=None) -> None:
        super().__init__(str(value), parent)
        self._value = int(value)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_value)

    def _on_value(self, value) -> None:
        self._value = int(value)
        self.setText(str(self._value))

    def set_value(self, target: int) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._value)
        self._anim.setEndValue(int(target))
        self._anim.start()
