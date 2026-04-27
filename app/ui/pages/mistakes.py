from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.ui.components.card import Card
from app.ui.components.ripple_button import RippleButton


class MistakesPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.session = []
        self.index = 0
        self.correct = 0
        self.total = 0
        self.build()
        self.refresh()

    def build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        top = Card(parent=self)
        layout.addWidget(top)
        tool = QHBoxLayout()
        start = RippleButton("开始专项练习")
        start.setObjectName("accentButton")
        start.clicked.connect(self.start_session)
        delete = RippleButton("删除选中")
        delete.clicked.connect(self.delete_selected)
        tool.addWidget(start)
        tool.addWidget(delete)
        tool.addStretch(1)
        top.layout.addLayout(tool)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["单词", "释义", "错误次数", "词性", "最近错误时间"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        top.layout.addWidget(self.table)

        bottom = Card(parent=self)
        layout.addWidget(bottom)
        self.status = QLabel("点击上方按钮开始。")
        self.question = QLabel("还没有开始。")
        self.question.setStyleSheet("font: 700 28px 'Yu Gothic UI';")
        self.hint = QLabel("")
        self.feedback = QLabel("")
        self.feedback.setWordWrap(True)
        self.option_box = QVBoxLayout()
        bottom.layout.addWidget(self.status)
        bottom.layout.addWidget(self.question)
        bottom.layout.addWidget(self.hint)
        bottom.layout.addLayout(self.option_box)
        bottom.layout.addWidget(self.feedback)

    def refresh(self):
        rows = self.main_window.store.list_mistakes()
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            values = [row["word"], row["meaning"], row["wrong_count"], row.get("pos", ""), self.main_window.format_ts(row["last_wrong_at"])]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                self.table.setItem(row_idx, col_idx, item)

    def delete_selected(self):
        rows = sorted({item.row() for item in self.table.selectedItems()})
        if not rows:
            self.main_window.show_toast("请先选择错题。")
            return
        words = [self.table.item(row, 0).text() for row in rows]
        self.main_window.store.delete_mistakes(words)
        self.refresh()

    def start_session(self):
        self.session = self.main_window.store.list_mistakes()
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
            self.status.setText(f"专项练习完成：{self.correct}/{self.total}")
            self.question.setText("这轮错题回看结束")
            self.hint.setText("系统已经根据结果更新错题本。")
            self.feedback.setText("")
            self.refresh()
            return
        row = self.session[self.index]
        vocab = self.main_window.store.get_vocab(row["word"])
        meaning = vocab["meaning"] if vocab else row["meaning"]
        self.status.setText(f"第 {self.index + 1} / {len(self.session)} 题")
        self.question.setText(row["word"])
        self.hint.setText(f"错误 {row['wrong_count']} 次")
        options = self.main_window.engine.build_choices(meaning, [item["meaning"] for item in self.main_window.store.list_vocab()])
        for option in options:
            button = RippleButton(option)
            button.clicked.connect(lambda _, value=option, data=row, target=meaning: self.answer(value, data, target))
            self.option_box.addWidget(button)

    def answer(self, answer_text, row, target):
        self.total += 1
        result = self.main_window.engine.answer_matches(answer_text, target)
        if result in {"exact", "close"}:
            self.correct += 1
            self.main_window.store.resolve_mistake(row["word"])
            self.feedback.setText("这一题稳住了。")
        else:
            self.main_window.store.add_mistake(row["word"], target)
            self.feedback.setText(f"再看一眼，正确答案：{target}")
        self.index += 1
        self.render_question()
