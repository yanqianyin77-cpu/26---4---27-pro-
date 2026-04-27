from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QLabel,
)

from app.ui.components import Card, RippleButton


class WordDialog(QDialog):
    def __init__(self, parent=None, data=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("词条编辑")
        self.resize(520, 520)
        self.data = data or {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.word = QLineEdit(self.data.get("word", ""))
        self.meaning = QLineEdit(self.data.get("meaning", ""))
        self.tags = QLineEdit(self.data.get("tags", ""))
        self.example = QTextEdit(self.data.get("example", ""))
        self.notes = QTextEdit(self.data.get("notes", ""))
        self.priority = QSpinBox()
        self.priority.setRange(1, 3)
        self.priority.setValue(int(self.data.get("priority", 1) or 1))
        form.addRow("单词", self.word)
        form.addRow("释义", self.meaning)
        form.addRow("标签", self.tags)
        form.addRow("例句", self.example)
        form.addRow("备注", self.notes)
        form.addRow("优先级", self.priority)
        layout.addLayout(form)
        actions = QHBoxLayout()
        save = RippleButton("保存")
        save.setProperty("primary", True)
        cancel = RippleButton("取消")
        save.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        actions.addStretch(1)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

    def payload(self) -> dict:
        return {
            "word": self.word.text().strip(),
            "meaning": self.meaning.text().strip(),
            "tags": self.tags.text().strip(),
            "example": self.example.toPlainText().strip(),
            "notes": self.notes.toPlainText().strip(),
            "priority": self.priority.value(),
        }


class VocabPage(QWidget):
    changed = Signal()

    def __init__(self, store, engine, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.engine = engine
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("词汇本")
        title.setObjectName("Title")
        layout.addWidget(title)
        card = Card(hover=False)
        layout.addWidget(card)
        toolbar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索单词、释义或标签")
        self.search.textChanged.connect(self.refresh)
        add = RippleButton("新增")
        add.setProperty("primary", True)
        edit = RippleButton("编辑")
        delete = RippleButton("删除选中")
        delete.setProperty("danger", True)
        export = RippleButton("导出 CSV")
        export.setProperty("wood", True)
        add.clicked.connect(self.add_word)
        edit.clicked.connect(self.edit_word)
        delete.clicked.connect(self.delete_words)
        export.clicked.connect(self.export_csv)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(add)
        toolbar.addWidget(edit)
        toolbar.addWidget(delete)
        toolbar.addWidget(export)
        card.layout_root.addLayout(toolbar)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["单词", "释义", "读音", "词性", "标签", "阶段", "复习", "优先级"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        card.layout_root.addWidget(self.table)

    def refresh(self) -> None:
        rows = self.store.list_vocab(self.search.text().strip())
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            stage = "已掌握" if row.get("mastered") else ("新词" if not row.get("review_count") else f"阶段 {int(row.get('stage_index') or 0) + 1}")
            values = [row["word"], row["meaning"], row["reading"], row["pos"], row["tags"], stage, str(row.get("review_count") or 0), str(row["priority"])]
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(value))

    def add_word(self) -> None:
        dialog = WordDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        self._save_payload(dialog.payload())

    def edit_word(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        word = self.table.item(row, 0).text()
        data = self.store.get_vocab(word)
        dialog = WordDialog(self, data)
        if dialog.exec() != QDialog.Accepted:
            return
        self._save_payload(dialog.payload(), data)

    def _save_payload(self, payload: dict, old: dict | None = None) -> None:
        if not payload["word"] or not payload["meaning"]:
            QMessageBox.warning(self, "提示", "单词和释义不能为空。")
            return
        detail = self.engine.word_detail(payload["word"])
        forms = self.engine.infer_forms(payload["word"], detail["pos"])
        item = {
            **payload,
            "reading": detail["reading"],
            "base_form": detail["base_form"],
            "pos": detail["pos"],
            "polite_form": forms["polite"],
            "te_form": forms["te"],
            "ta_form": forms["ta"],
            "created_at": (old or {}).get("created_at", 0) or __import__("time").time(),
        }
        self.store.save_vocab(item)
        self.refresh()
        self.changed.emit()

    def delete_words(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not rows:
            return
        if QMessageBox.question(self, "确认", f"删除选中的 {len(rows)} 个单词？") != QMessageBox.Yes:
            return
        self.store.delete_words([self.table.item(r, 0).text() for r in rows])
        self.refresh()
        self.changed.emit()

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", "词汇本导出.csv", "CSV (*.csv)")
        if path:
            self.store.export_csv(path)
