from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from app.core.engine import QUOTES
from app.ui.components import AnimatedNumberLabel, Card


class DashboardPage(QWidget):
    def __init__(self, store, engine, streak: int, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.engine = engine
        self.streak = streak
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        title = QLabel("今日页")
        title.setObjectName("Title")
        subtitle = QLabel("像翻开一本安静的单词手帐，从这里开始今天的学习。")
        subtitle.setObjectName("Subtle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        quote = QUOTES[date.today().toordinal() % len(QUOTES)]
        hero = Card()
        hero.layout_root.addWidget(QLabel(f"<span style='font-size:28px;font-weight:700;'>{quote[0]}</span>"))
        hero.layout_root.addWidget(QLabel(f"<span style='color:#6E7C84;'>{quote[1]}</span>"))
        layout.addWidget(hero)

        stats = QGridLayout()
        rows = self.store.list_vocab()
        due = self.store.due_reviews(999)
        mistakes = self.store.mistakes()
        mastered = sum(1 for r in rows if r.get("mastered"))
        data = [("词汇本", len(rows)), ("待复习", len(due)), ("已掌握", mastered), ("错题本", len(mistakes))]
        for i, (name, value) in enumerate(data):
            card = Card()
            label = QLabel(name)
            label.setObjectName("Subtle")
            num = AnimatedNumberLabel()
            num.setObjectName("StatNumber")
            card.layout_root.addWidget(label)
            card.layout_root.addWidget(num)
            stats.addWidget(card, 0, i)
            num.set_value(value)
        layout.addLayout(stats)

        plan = Card()
        daily_review = self.store.setting("daily_review_limit", "15")
        daily_new = self.store.setting("daily_new_limit", "5")
        plan.layout_root.addWidget(QLabel("<b>今日建议</b>"))
        plan.layout_root.addWidget(QLabel(f"先复习 {min(len(due), int(daily_review))} 个词，再新学 {daily_new} 个以内。"))
        plan.layout_root.addWidget(QLabel(f"连续学习 {self.streak} 天。今天也保持轻一点、稳一点。"))
        layout.addWidget(plan)
        layout.addStretch(1)
