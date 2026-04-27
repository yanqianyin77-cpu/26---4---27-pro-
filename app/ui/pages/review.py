from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.ui.components.card import Card
from app.ui.components.ripple_button import RippleButton


class ReviewPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.session = []
        self.index = 0
        self.correct = 0
        self.total = 0
        self.build()
        self.refresh_list()

    def build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        left = Card(parent=self)
        right = Card(parent=self)
        layout.addWidget(left, 3)
        layout.addWidget(right, 2)

        left.layout.addWidget(QLabel("今日待复习"))
        start_btn = RippleButton("开始今日复习")
        start_btn.setObjectName("accentButton")
        start_btn.clicked.connect(self.start_session)
        left.layout.addWidget(start_btn)
        self.list_table = QTableWidget(0, 4)
        self.list_table.setHorizontalHeaderLabels(["单词", "阶段", "优先级", "应复习时间"])
        self.list_table.horizontalHeader().setStretchLastSection(True)
        self.list_table.verticalHeader().setVisible(False)
        self.list_table.setEditTriggers(QTableWidget.NoEditTriggers)
        left.layout.addWidget(self.list_table)

        self.status = QLabel("准备好后点击“开始今日复习”。")
        self.question = QLabel("今日还没有开始。")
        self.question.setStyleSheet("font: 700 28px 'Yu Gothic UI';")
        self.hint = QLabel("")
        self.feedback = QLabel("")
        self.feedback.setWordWrap(True)
        self.answer_buttons = []
        right.layout.addWidget(self.status)
        right.layout.addWidget(self.question)
        right.layout.addWidget(self.hint)
        button_box = QVBoxLayout()
        self.button_box = button_box
        right.layout.addLayout(button_box)
        right.layout.addWidget(self.feedback)
        right.layout.addStretch(1)

    def refresh_list(self):
        items = self.main_window.store.get_today_review(self.main_window.review_stages(), int(self.main_window.store.get_setting("daily_review_limit", "15")))
        self.list_table.setRowCount(len(items))
        for row_idx, row in enumerate(items):
            stage = "新词" if row["review_count"] == 0 else f"阶段 {row['stage_index'] + 1}"
            values = [row["word"], stage, row["priority"], self.main_window.format_ts(row["due_at"])]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, row)
                self.list_table.setItem(row_idx, col_idx, item)

    def start_session(self):
        self.session = self.main_window.store.get_today_review(self.main_window.review_stages(), int(self.main_window.store.get_setting("daily_review_limit", "15")))
        self.index = 0
        self.correct = 0
        self.total = 0
        self.render_question()

    def render_question(self):
        for button in self.answer_buttons:
            button.deleteLater()
        self.answer_buttons.clear()
        if self.index >= len(self.session):
            self.status.setText(f"复习完成：{self.correct}/{self.total}")
            self.question.setText("今天的复习告一段落")
            self.hint.setText("系统已经根据你的表现自动调整下一次出现时间。")
            self.feedback.setText("可以去错题本查看最近的波动词汇。")
            self.main_window.store.add_test_record("review", self.total, self.correct)
            self.refresh_list()
            return
        row = self.session[self.index]
        self.status.setText(f"第 {self.index + 1} / {len(self.session)} 题")
        self.question.setText(row["word"])
        self.hint.setText(f"读音：{row['reading']}    词性：{row['pos']}    优先级：{row['priority']}")
        all_meanings = [item["meaning"] for item in self.main_window.store.list_vocab()]
        options = self.main_window.engine.build_choices(row["meaning"], all_meanings)
        for option in options:
            button = RippleButton(option)
            button.clicked.connect(lambda _, value=option, data=row: self.answer(value, data))
            self.button_box.addWidget(button)
            self.answer_buttons.append(button)

    def answer(self, answer_text, row):
        self.total += 1
        result = self.main_window.engine.answer_matches(answer_text, row["meaning"])
        if result in {"exact", "close"}:
            self.correct += 1
            self.main_window.store.apply_review_result(row["word"], True, self.main_window.review_stages())
            self.main_window.store.resolve_mistake(row["word"])
            self.feedback.setText("答对了，记忆正在稳定下来。")
        else:
            self.main_window.store.apply_review_result(row["word"], False, self.main_window.review_stages())
            self.main_window.store.add_mistake(row["word"], row["meaning"])
            self.feedback.setText(f"这题容易混，正确答案：{row['meaning']}")
        self.index += 1
        self.render_question()
