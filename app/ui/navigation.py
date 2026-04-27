from __future__ import annotations

# noinspection PyUnresolvedReferences
from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Signal
# noinspection PyUnresolvedReferences
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.ui.components import RippleButton


class NavigationBar(QWidget):
    changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SideBar")
        self.expanded_width = 280
        self.collapsed_width = 92
        self.collapsed = False
        self.setFixedWidth(self.expanded_width)
        self.buttons: dict[str, RippleButton] = {}
        self.button_texts: dict[str, str] = {}
        self.current_key = ""

        self.indicator = QWidget(self)
        self.indicator.setFixedSize(4, 42)
        self.indicator.setStyleSheet("background:#7E98A8;border-radius:2px;")
        self.anim = QPropertyAnimation(self.indicator, b"pos", self)
        self.anim.setDuration(250)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 28, 18, 22)
        layout.setSpacing(8)

        self.title = QLabel("Kotoba Note")
        self.title.setStyleSheet("font-size:22px;font-weight:800;")
        self.subtitle = QLabel("言葉の手帳")
        self.subtitle.setStyleSheet("color:#6E7C84;letter-spacing:2px;")
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addSpacing(20)

        items = [
            ("dashboard", "今日页"),
            ("text_lab", "课文手札"),
            ("vocab", "词汇本"),
            ("review", "复习计划"),
            ("test", "随机自测"),
            ("mistakes", "错题本"),
            ("report", "学习报告"),
        ]
        for key, text in items:
            btn = RippleButton(text)
            btn.setMinimumHeight(42)
            btn.clicked.connect(lambda checked=False, k=key: self.select(k))
            btn.setToolTip(text)
            layout.addWidget(btn)
            self.buttons[key] = btn
            self.button_texts[key] = text
        layout.addStretch()

        self.rhythm = QLabel("")
        self.rhythm.setWordWrap(True)
        self.rhythm.setObjectName("MiniCard")
        self.rhythm.setStyleSheet("padding:14px;color:#6E7C84;")
        layout.addWidget(self.rhythm)

    def set_rhythm(self, text: str) -> None:
        self.rhythm.setText(text)

    def set_collapsed(self, collapsed: bool) -> None:
        self.collapsed = collapsed
        self.setFixedWidth(self.collapsed_width if collapsed else self.expanded_width)
        self.subtitle.setVisible(not collapsed)
        self.rhythm.setVisible(not collapsed)
        self.title.setText("言" if collapsed else "Kotoba Note")
        self.title.setStyleSheet(
            "font-size:24px;font-weight:900;text-align:center;" if collapsed else "font-size:22px;font-weight:800;"
        )
        for key, button in self.buttons.items():
            text = self.button_texts[key]
            button.setText(text[:2] if collapsed else text)
            button.setToolTip(text)
        self.update_indicator()

    def toggle_collapsed(self) -> bool:
        self.set_collapsed(not self.collapsed)
        return self.collapsed

    def select(self, key: str) -> None:
        self.current_key = key
        for item_key, button in self.buttons.items():
            button.setProperty("primary", item_key == key)
            button.style().unpolish(button)
            button.style().polish(button)
        self.update_indicator()
        self.changed.emit(key)

    def update_indicator(self):
        if self.current_key not in self.buttons:
            return
        btn = self.buttons[self.current_key]
        y = btn.y() + (btn.height() - self.indicator.height()) // 2
        self.anim.stop()
        self.anim.setEndValue(QPoint(0, y))
        self.anim.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_key in self.buttons:
            btn = self.buttons[self.current_key]
            self.indicator.move(0, btn.y() + (btn.height() - self.indicator.height()) // 2)
