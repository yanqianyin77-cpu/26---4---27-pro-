from __future__ import annotations

import json

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.ui.components.card import Card
from app.ui.components.loading import LoadingIndicator
from app.ui.components.ripple_button import RippleButton
from app.ui.workers.text_worker import TextAnalyzeWorker


class TextLabPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.analysis_thread = None
        self.worker = None
        self.build()
        self.load_cache()

    def build(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(14)

        editor_card = Card(parent=self)
        layout.addWidget(editor_card, 0, 0, 2, 3)
        title = QLabel("课文手札")
        title.setStyleSheet("font-weight: 600;")
        editor_card.layout.addWidget(title)

        tools = QHBoxLayout()
        self.save_button = RippleButton("保存并分析")
        self.save_button.setObjectName("accentButton")
        self.save_button.clicked.connect(self.run_analysis)
        tools.addWidget(self.save_button)
        load_btn = RippleButton("导入文本")
        load_btn.clicked.connect(self.import_file)
        tools.addWidget(load_btn)
        mark_btn = RippleButton("标记重点段")
        mark_btn.setObjectName("woodButton")
        mark_btn.clicked.connect(self.mark_selection)
        tools.addWidget(mark_btn)
        tools.addStretch(1)
        self.furigana_toggle = QCheckBox("振假名")
        self.furigana_toggle.toggled.connect(self.refresh_preview)
        tools.addWidget(self.furigana_toggle)
        self.loading = LoadingIndicator()
        tools.addWidget(self.loading)
        editor_card.layout.addLayout(tools)

        self.editor = QPlainTextEdit()
        self.editor.textChanged.connect(self.refresh_preview)
        editor_card.layout.addWidget(self.editor, 2)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(140)
        editor_card.layout.addWidget(QLabel("振假名预览"))
        editor_card.layout.addWidget(self.preview)

        right_card = Card(parent=self)
        layout.addWidget(right_card, 0, 3, 1, 2)
        filter_row = QHBoxLayout()
        self.pos_filter = QComboBox()
        self.pos_filter.addItems(["全部词性", "名词", "動詞", "形容詞", "副詞"])
        self.state_filter = QComboBox()
        self.state_filter.addItems(["全部状态", "未收录", "已收录"])
        apply_btn = RippleButton("应用筛选")
        apply_btn.clicked.connect(self.run_analysis)
        filter_row.addWidget(self.pos_filter)
        filter_row.addWidget(self.state_filter)
        filter_row.addWidget(apply_btn)
        right_card.layout.addWidget(QLabel("重点词"))
        right_card.layout.addLayout(filter_row)
        self.focus_table = self._make_table(["单词", "释义", "读音", "词性", "状态"])
        self.focus_table.itemDoubleClicked.connect(self.add_double_clicked_word)
        right_card.layout.addWidget(self.focus_table)
        add_btn = RippleButton("加入词汇本")
        add_btn.setObjectName("accentButton")
        add_btn.clicked.connect(self.add_selected_words)
        right_card.layout.addWidget(add_btn)

        freq_card = Card(parent=self)
        layout.addWidget(freq_card, 1, 3, 1, 2)
        freq_card.layout.addWidget(QLabel("词频统计"))
        self.freq_table = self._make_table(["单词", "出现次数"])
        freq_card.layout.addWidget(self.freq_table)

    def _make_table(self, headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(False)
        return table

    def load_cache(self):
        cache = self.main_window.store.get_text_cache()
        self.editor.setPlainText(cache["content"])
        self.furigana_toggle.setChecked(self.main_window.store.get_setting("furigana", "0") == "1")
        self.refresh_preview()

    def refresh_preview(self):
        text = self.editor.toPlainText()
        rendered = self.main_window.engine.annotate_with_furigana(text, self.furigana_toggle.isChecked())
        self.preview.setPlainText(rendered)
        self.main_window.store.set_setting("furigana", "1" if self.furigana_toggle.isChecked() else "0")

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入文本", "", "Text Files (*.txt);;All Files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as file:
                self.editor.setPlainText(file.read())
            self.main_window.show_toast("文本已导入。")
        except UnicodeDecodeError:
            self.main_window.show_toast("文本编码错误，请使用 UTF-8 文件。")

    def mark_selection(self):
        cursor = self.editor.textCursor()
        selected = cursor.selectedText().strip()
        if not selected:
            self.main_window.show_toast("请先选中句子或段落。")
            return
        cache = self.main_window.store.get_text_cache()
        segments = json.loads(cache["segments"])
        if selected not in segments:
            segments.append(selected)
        self.main_window.store.save_text_cache(cache["content"], json.loads(cache["highlights"]), segments)
        self.main_window.show_toast("已标记为重点段落。")

    def run_analysis(self):
        text = self.editor.toPlainText().strip()
        cache = self.main_window.store.get_text_cache()
        self.main_window.store.save_text_cache(text, json.loads(cache["highlights"]), json.loads(cache["segments"]))
        self.loading.start()
        self.save_button.setEnabled(False)
        self.analysis_thread = QThread(self)
        self.worker = TextAnalyzeWorker(
            engine=self.main_window.engine,
            text=text,
            system_dict=self.main_window.store.list_system_dict(),
            vocab_words={row["word"] for row in self.main_window.store.list_vocab()},
            pos_filter=self.pos_filter.currentText(),
            state_filter=self.state_filter.currentText(),
        )
        self.worker.moveToThread(self.analysis_thread)
        self.analysis_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_analysis_done)
        self.worker.finished.connect(self.analysis_thread.quit)
        self.analysis_thread.finished.connect(self.analysis_thread.deleteLater)
        self.analysis_thread.start()

    def on_analysis_done(self, result, error):
        self.loading.stop()
        self.save_button.setEnabled(True)
        if error:
            self.main_window.show_toast(error)
            return
        self._fill_table(self.focus_table, result.focus_rows)
        self._fill_table(self.freq_table, result.freq_rows)
        self.main_window.current_text_words = result.words
        self.main_window.show_toast(f"课文分析完成，提取到 {len(result.words)} 个有效词。")

    def _fill_table(self, table, rows):
        table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            for col_idx, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, row)
                table.setItem(row_idx, col_idx, item)

    def add_selected_words(self):
        selected_rows = {item.row() for item in self.focus_table.selectedItems()}
        if not selected_rows:
            self.main_window.show_toast("请先选择至少一个词。")
            return
        added = 0
        for row_idx in selected_rows:
            word = self.focus_table.item(row_idx, 0).text()
            meaning = self.focus_table.item(row_idx, 1).text()
            if meaning == "未收录":
                continue
            if not self.main_window.store.get_vocab(word):
                self.main_window.add_vocab_word(word, meaning)
                added += 1
        if added:
            self.main_window.show_toast(f"已加入 {added} 个单词。")
        else:
            self.main_window.show_toast("选中的词已经都在词汇本里了。")

    def add_double_clicked_word(self, item):
        row = item.row()
        word = self.focus_table.item(row, 0).text()
        meaning = self.focus_table.item(row, 1).text()
        if meaning != "未收录":
            self.main_window.add_vocab_word(word, meaning)
