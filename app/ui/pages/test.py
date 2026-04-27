from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from app.ui.components.card import Card
from app.ui.components.ripple_button import RippleButton


class TestPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.session = []
        self.index = 0
        self.correct = 0
        self.total = 0
        self.build()

    def build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        left = Card(parent=self)
        right = Card(parent=self)
        layout.addWidget(left, 2)
        layout.addWidget(right, 3)

        left.layout.addWidget(QLabel("测试设置"))
        row = QHBoxLayout()
        row.addWidget(QLabel("题量"))
        self.count = QSpinBox()
        self.count.setRange(1, 50)
        self.count.setValue(5)
        row.addWidget(self.count)
        start = RippleButton("开始自测")
        start.setObjectName("accentButton")
        start.clicked.connect(self.start_test)
        row.addWidget(start)
        row.addStretch(1)
        left.layout.addLayout(row)
        note = QLabel("测试采用四选一。答错的词会自动进入错题本。")
        note.setWordWrap(True)
        left.layout.addWidget(note)
        left.layout.addStretch(1)

        self.status = QLabel("点击左侧按钮开始。")
        self.question = QLabel("还没有开始测试。")
        self.question.setStyleSheet("font: 700 28px 'Yu Gothic UI';")
        self.hint = QLabel("")
        self.feedback = QLabel("")
        self.feedback.setWordWrap(True)
        self.option_box = QVBoxLayout()
        right.layout.addWidget(self.status)
        right.layout.addWidget(self.question)
        right.layout.addWidget(self.hint)
        right.layout.addLayout(self.option_box)
        right.layout.addWidget(self.feedback)
        right.layout.addStretch(1)

    def start_test(self):
        rows = self.main_window.store.list_vocab(order_by="RANDOM()")
        if not rows:
            self.main_window.show_toast("词汇本还是空的。")
            return
        count = min(self.count.value(), len(rows))
        self.session = rows[:count]
        self.index = 0
        self.correct = 0
        self.total = 0
        self.render_question()

    def render_question(self):
        while self.option_box.count():
            item = self.option_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if self.index >= len(self.session):
            self.status.setText(f"测试完成：{self.correct}/{self.total}")
            self.question.setText("这一轮测试结束")
            self.hint.setText("可以去学习报告查看趋势。")
            self.feedback.setText("")
            self.main_window.store.add_test_record("test", self.total, self.correct)
            return
        row = self.session[self.index]
        self.status.setText(f"第 {self.index + 1} / {len(self.session)} 题")
        self.question.setText(row["word"])
        self.hint.setText(f"读音：{row['reading']}    词性：{row['pos']}")
        options = self.main_window.engine.build_choices(row["meaning"], [item["meaning"] for item in self.main_window.store.list_vocab()])
        for option in options:
            button = RippleButton(option)
            button.clicked.connect(lambda _, value=option, data=row: self.answer(value, data))
            self.option_box.addWidget(button)

    def answer(self, answer_text, row):
        self.total += 1
        result = self.main_window.engine.answer_matches(answer_text, row["meaning"])
        if result in {"exact", "close"}:
            self.correct += 1
            self.main_window.store.resolve_mistake(row["word"])
            self.feedback.setText("回答正确。")
        else:
            self.main_window.store.add_mistake(row["word"], row["meaning"])
            self.feedback.setText(f"这题答错了，正确答案：{row['meaning']}")
        self.index += 1
        self.render_question()
