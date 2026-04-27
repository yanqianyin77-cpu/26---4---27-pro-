from __future__ import annotations

import csv
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# noinspection PyUnresolvedReferences
from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QThread, Qt, QTimer
# noinspection PyUnresolvedReferences
from PySide6.QtGui import QAction, QColor, QPainter, QPen
# noinspection PyUnresolvedReferences
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.engine import StudyEngine
from app.core.store import DBStore
from app.ui.components import AnimatedNumberLabel, Card, LoadingOverlay, RippleButton, Toast
from app.ui.navigation import NavigationBar
from app.ui.workers import TextWorker


class SmartTableItem(QTableWidgetItem):
    def __init__(self, value):
        super().__init__(str(value))
        self.sort_value = value

    def __lt__(self, other):
        if isinstance(other, SmartTableItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)


class DropTextEdit(QPlainTextEdit):
    def __init__(self, on_file_drop, parent=None):
        super().__init__(parent)
        self.on_file_drop = on_file_drop
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            self.on_file_drop(urls[0].toLocalFile())
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class TrendChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.values: list[float] = []
        self.labels: list[str] = []
        self.setMinimumHeight(170)

    def set_points(self, labels: list[str], values: list[float]):
        self.labels = labels
        self.values = values
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(16, 12, -12, -24)
        painter.setPen(QPen(QColor("#CCD7DE"), 1))
        for i in range(5):
            y = rect.bottom() - i * rect.height() / 4
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))
        if not self.values:
            painter.setPen(QColor("#6E7C84"))
            painter.drawText(self.rect(), Qt.AlignCenter, "做几轮复习或自测后，这里会开始长出你的学习曲线。")
            return
        lo = min(self.values)
        hi = max(self.values)
        span = max(hi - lo, 1.0)
        step = rect.width() / max(len(self.values) - 1, 1)
        points = []
        for idx, value in enumerate(self.values):
            x = rect.left() + idx * step
            y = rect.bottom() - ((value - lo) / span) * rect.height()
            points.append(QPoint(int(x), int(y)))
        painter.setPen(QPen(QColor("#7E98A8"), 3))
        for a, b in zip(points, points[1:]):
            painter.drawLine(a, b)
        painter.setBrush(QColor("#9B785D"))
        painter.setPen(Qt.NoPen)
        for point in points:
            painter.drawEllipse(point, 4, 4)
        painter.setPen(QColor("#6E7C84"))
        for idx, label in enumerate(self.labels[-6:]):
            x = rect.left() + (len(self.values) - len(self.labels[-6:]) + idx) * step
            painter.drawText(int(x) - 16, rect.bottom() + 18, label)


class DistributionChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: list[tuple[str, int]] = []
        self.setMinimumHeight(170)

    def set_data(self, data: list[tuple[str, int]]):
        self.data = data[:6]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(18, 14, -18, -14)
        if not self.data:
            painter.setPen(QColor("#6E7C84"))
            painter.drawText(self.rect(), Qt.AlignCenter, "错题和词性分布会在这里帮你看见薄弱点。")
            return
        max_value = max(v for _, v in self.data) or 1
        row_h = rect.height() / len(self.data)
        for idx, (label, value) in enumerate(self.data):
            y = rect.top() + idx * row_h
            painter.setPen(QColor("#33424B"))
            painter.drawText(rect.left(), int(y + row_h * 0.6), label)
            bar_x = rect.left() + 90
            bar_w = (rect.width() - 110) * (value / max_value)
            painter.setBrush(QColor("#7E98A8"))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(bar_x, int(y + row_h * 0.25), int(bar_w), int(row_h * 0.45), 7, 7)
            painter.setPen(QColor("#6E7C84"))
            painter.drawText(rect.right() - 24, int(y + row_h * 0.6), str(value))


class WordDialog(QDialog):
    def __init__(self, engine: StudyEngine, data: dict | None = None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.data = data or {}
        self.setWindowTitle("词条编辑")
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        title = QLabel("整理一条词汇")
        title.setStyleSheet("font-size:20px;font-weight:800;")
        layout.addWidget(title)

        form = QFormLayout()
        self.word = QLineEdit(self.data.get("word", ""))
        self.meaning = QLineEdit(self.data.get("meaning", ""))
        self.tags = QLineEdit(self.data.get("tags", ""))
        self.example = QTextEdit(self.data.get("example", ""))
        self.example.setMaximumHeight(90)
        self.notes = QTextEdit(self.data.get("notes", ""))
        self.notes.setMaximumHeight(70)
        self.priority = QSpinBox()
        self.priority.setRange(1, 5)
        self.priority.setValue(int(self.data.get("priority") or 1))
        self.mastered = QCheckBox("标记为已掌握")
        self.mastered.setChecked(bool(self.data.get("mastered")))
        self.reading_preview = QLabel()
        self.reading_preview.setWordWrap(True)

        self.word.setPlaceholderText("例如：覚える")
        self.meaning.setPlaceholderText("例如：记住，掌握")
        self.tags.setPlaceholderText("例如：N4, 动词, 考试重点")
        self.example.setPlaceholderText("例句会让记忆更稳。")
        self.notes.setPlaceholderText("写下容易混淆的点，会比死记更有用。")

        form.addRow("单词", self.word)
        form.addRow("释义", self.meaning)
        form.addRow("标签", self.tags)
        form.addRow("例句", self.example)
        form.addRow("备注", self.notes)
        form.addRow("复习优先级", self.priority)
        form.addRow("自动识别", self.reading_preview)
        form.addRow("", self.mastered)
        layout.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch()
        copy_word = RippleButton("复制单词")
        copy_reading = RippleButton("复制读音")
        cancel = RippleButton("取消")
        save = RippleButton("保存")
        save.setProperty("primary", True)
        copy_word.clicked.connect(lambda: QApplication.clipboard().setText(self.word.text().strip()))
        copy_reading.clicked.connect(lambda: QApplication.clipboard().setText(self.engine.get_word_detail(self.word.text().strip())["reading"]))
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        for btn in (copy_word, copy_reading, cancel, save):
            actions.addWidget(btn)
        layout.addLayout(actions)
        self.word.textChanged.connect(self.refresh_preview)
        self.refresh_preview()

    def refresh_preview(self):
        word = self.word.text().strip()
        if not word:
            self.reading_preview.setText("输入单词后，这里会自动显示读音、原形和词性。")
            return
        detail = self.engine.get_word_detail(word)
        self.reading_preview.setText(
            f"读音：{detail['reading'] or '-'}    原形：{detail['base_form'] or word}    词性：{detail['pos'] or '-'}"
        )

    def accept(self):
        if not self.word.text().strip():
            QMessageBox.information(self, "还差一点", "请先输入单词。")
            return
        if not self.meaning.text().strip():
            QMessageBox.information(self, "还差一点", "请补上一句中文释义，后面复习会更顺手。")
            return
        super().accept()

    def payload(self) -> dict:
        word = self.word.text().strip()
        meaning = self.meaning.text().strip()
        detail = self.engine.get_word_detail(word)
        forms = self.engine.infer_verb_forms(word, detail["pos"])
        created_at = self.data.get("created_at")
        return {
            "word": word,
            "meaning": meaning,
            "reading": detail["reading"],
            "base_form": detail["base_form"],
            "pos": detail["pos"],
            "tags": self.tags.text().strip(),
            "example": self.example.toPlainText().strip(),
            "notes": self.notes.toPlainText().strip(),
            "priority": self.priority.value(),
            "polite_form": forms["polite"],
            "te_form": forms["te"],
            "ta_form": forms["ta"],
            "created_at": created_at,
            "mastered": self.mastered.isChecked(),
        }


class TagBatchDialog(QDialog):
    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量整理标签")
        self.setModal(True)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"准备给 {count} 个单词整理标签。"))
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("例如：N3, 考试重点, 易混词")
        self.replace = QCheckBox("替换原有标签，而不是追加")
        layout.addWidget(self.tags)
        layout.addWidget(self.replace)
        row = QHBoxLayout()
        row.addStretch()
        cancel = RippleButton("取消")
        ok = RippleButton("保存")
        ok.setProperty("primary", True)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        layout.addLayout(row)


class TrashRestoreDialog(QDialog):
    def __init__(self, rows: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("回收站")
        self.setModal(True)
        self.setMinimumSize(760, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("选中想恢复的词。没有选中时，默认恢复全部。"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["单词", "释义", "标签", "删除时间"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setRowCount(len(rows))
        self.rows = rows
        for r, item in enumerate(rows):
            deleted_at = datetime.fromtimestamp(item["deleted_at"]).strftime("%Y-%m-%d %H:%M") if item.get("deleted_at") else ""
            values = [item.get("word", ""), item.get("meaning", ""), item.get("tags", ""), deleted_at]
            for c, value in enumerate(values):
                self.table.setItem(r, c, SmartTableItem(value))
        layout.addWidget(self.table)
        row = QHBoxLayout()
        row.addStretch()
        cancel = RippleButton("取消")
        all_btn = RippleButton("全部恢复")
        selected = RippleButton("恢复选中")
        selected.setProperty("primary", True)
        cancel.clicked.connect(self.reject)
        all_btn.clicked.connect(self.accept)
        selected.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(all_btn)
        row.addWidget(selected)
        layout.addLayout(row)

    def selected_words(self) -> list[str]:
        rows = sorted({i.row() for i in self.table.selectedItems()})
        if not rows:
            return [item.get("word", "") for item in self.rows if item.get("word")]
        return [self.table.item(r, 0).text() for r in rows if self.table.item(r, 0)]


class MainWindow(QMainWindow):
    def __init__(self, store: DBStore, engine: StudyEngine, base_dir: Path):
        super().__init__()
        self.store = store
        self.engine = engine
        self.base_dir = base_dir
        self.theme = self.store.setting("theme", "light")
        self.streak = self.store.do_checkin()
        self.current_words: list[str] = []
        self.analysis_busy = False
        self.review_queue: list[dict] = []
        self.test_queue: list[dict] = []
        self.practice_queue: list[dict] = []
        self.review_i = self.review_ok = self.test_i = self.test_ok = self.practice_i = self.practice_ok = 0
        self.review_misses: list[str] = []
        self.test_misses: list[str] = []
        self.practice_misses: list[str] = []
        self.last_deleted_words: list[str] = []
        self.page_scroll: dict[str, int] = {}
        self.current_page_key = "dashboard"
        self.drag_pos = QPoint()

        self.setWindowTitle("Kotoba Note | Kotoba Notebook")
        self.setMinimumSize(980, 680)
        self.restore_window_geometry()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self.build_ui()
        self.apply_theme(self.theme)
        self.build_pages()
        self.toast = Toast(self)
        self.loading = LoadingOverlay(self)
        self.nav.select(self.store.setting("last_page", "dashboard"))
        self.setup_shortcuts()
        self.restore_focus_mode()
        self.auto_backup_if_needed()
        self.install_drag_handlers()

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setSingleShot(True)
        self.autosave_timer.timeout.connect(self.autosave_text)
        self.text_editor.textChanged.connect(self.queue_text_autosave)

    def build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(14, 14, 14, 14)
        main.setSpacing(12)

        self.topbar = QFrame()
        self.topbar.setObjectName("TopBar")
        self.topbar.setFixedHeight(58)
        top = QHBoxLayout(self.topbar)
        top.setContentsMargins(18, 0, 14, 0)

        logo = QLabel("言")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(38, 38)
        logo.setStyleSheet("background:#9B785D;color:white;border-radius:19px;font-size:20px;font-weight:900;")
        title = QLabel("Kotoba Note")
        title.setStyleSheet("font-size:18px;font-weight:800;")
        sub = QLabel("言葉の手帳 · 顶部栏可拖动窗口")
        sub.setStyleSheet("color:#6E7C84;letter-spacing:1px;font-size:12px;")
        self.sidebar_btn = RippleButton("收起侧栏")
        self.sidebar_btn.clicked.connect(self.toggle_sidebar)
        self.theme_btn = RippleButton("浅色 / 深色")
        self.theme_btn.clicked.connect(self.toggle_theme)
        min_btn = RippleButton("—")
        max_btn = RippleButton("□")
        close_btn = RippleButton("×")
        for btn in (self.sidebar_btn, self.theme_btn, min_btn, max_btn, close_btn):
            btn.setMinimumSize(48, 38)
        close_btn.setProperty("danger", True)
        min_btn.clicked.connect(self.showMinimized)
        max_btn.clicked.connect(lambda: self.showNormal() if self.isMaximized() else self.showMaximized())
        close_btn.clicked.connect(self.close)

        top.addWidget(logo)
        top.addWidget(title)
        top.addWidget(sub)
        top.addStretch()
        top.addWidget(self.sidebar_btn)
        top.addWidget(self.theme_btn)
        top.addWidget(min_btn)
        top.addWidget(max_btn)
        top.addWidget(close_btn)
        main.addWidget(self.topbar)

        shell = QHBoxLayout()
        shell.setSpacing(14)
        self.nav = NavigationBar()
        self.nav.changed.connect(self.switch_page)
        self.nav.set_collapsed(self.store.setting("sidebar_collapsed", "0") == "1")
        self.stack = QStackedWidget()
        self.stack.setObjectName("PageHost")
        shell.addWidget(self.nav)
        shell.addWidget(self.stack, 1)
        main.addLayout(shell, 1)
        self.update_sidebar_button()

    def install_drag_handlers(self):
        self.topbar.installEventFilter(self)
        for child in self.topbar.findChildren(QWidget):
            if isinstance(child, RippleButton):
                continue
            child.installEventFilter(self)

    def setup_shortcuts(self):
        add = QAction(self)
        add.setShortcut("Ctrl+N")
        add.triggered.connect(self.add_word)
        self.addAction(add)

        export = QAction(self)
        export.setShortcut("Ctrl+E")
        export.triggered.connect(self.export_csv)
        self.addAction(export)

    def restore_window_geometry(self):
        raw = self.store.setting("window_geometry", "")
        if raw:
            try:
                x, y, w, h = [int(part) for part in raw.split(",")]
                self.setGeometry(x, y, max(980, w), max(680, h))
                return
            except Exception:
                logging.exception("Failed to restore window geometry")
        screen = QApplication.primaryScreen().availableGeometry()
        width = min(1360, max(980, int(screen.width() * 0.86)))
        height = min(880, max(680, int(screen.height() * 0.86)))
        self.resize(width, height)
        self.move(screen.center() - self.rect().center())

    def save_window_geometry(self):
        geo = self.geometry()
        self.store.set_setting("window_geometry", f"{geo.x()},{geo.y()},{geo.width()},{geo.height()}")

    def apply_theme(self, theme: str):
        qss_path = self.base_dir / "app" / "ui" / "styles" / f"{theme}.qss"
        if not qss_path.exists():
            qss_path = self.base_dir / "app" / "ui" / "styles" / "light.qss"
        QApplication.instance().setStyleSheet(qss_path.read_text(encoding="utf-8"))
        self.store.set_setting("theme", theme)
        self.theme = theme

    def toggle_theme(self):
        self.apply_theme("dark" if self.theme == "light" else "light")
        self.toast.show_message(f"已切换到{'深色' if self.theme == 'dark' else '浅色'}主题")
        self.update()

    def build_pages(self):
        self.pages = {
            "dashboard": self.page_dashboard(),
            "text_lab": self.page_text_lab(),
            "vocab": self.page_vocab(),
            "review": self.page_review(),
            "test": self.page_test(),
            "mistakes": self.page_mistakes(),
            "report": self.page_report(),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

    def switch_page(self, key: str):
        if self.current_page_key in self.pages:
            current = self.pages[self.current_page_key]
            if isinstance(current, QScrollArea):
                self.page_scroll[self.current_page_key] = current.verticalScrollBar().value()
        widget = self.pages[key]
        fade = QPropertyAnimation(widget, b"windowOpacity", widget)
        fade.setDuration(220)
        fade.setStartValue(0.88)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.stack.setCurrentWidget(widget)
        fade.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self.current_page_key = key
        self.store.set_setting("last_page", key)
        if isinstance(widget, QScrollArea):
            QTimer.singleShot(0, lambda: widget.verticalScrollBar().setValue(self.page_scroll.get(key, 0)))
        self.refresh_light_state()

    def refresh_light_state(self):
        task = self.today_task()
        self.nav.set_rhythm(f"今日节奏\n复习 {task['review']}  新学 {task['new']}  错题 {task['mistake']}")

    def today_task(self):
        return {
            "review": min(len(self.store.due_reviews()), int(self.store.setting("daily_review_limit", "15"))),
            "new": min(sum(1 for row in self.store.vocab() if not row.get("review_count")), int(self.store.setting("daily_new_limit", "5"))),
            "mistake": min(len(self.store.mistakes()), 5),
        }

    def start_quick_study(self):
        rows = self.store.due_reviews(5)
        if not rows:
            warmup = [row for row in self.store.vocab(order="priority DESC, updated_at DESC", limit=8) if not row.get("mastered")]
            if warmup:
                rows = warmup[:5]
                self.store.schedule_now([row["word"] for row in rows])
                rows = self.store.due_reviews(5)
        if not rows:
            self.toast.show_message("现在还没有适合快速学习的词，先去课文手札收一点新词吧。")
            return
        self.review_queue = rows
        self.review_i = 0
        self.review_ok = 0
        self.review_misses = []
        self.nav.select("review")
        self.render_review()
        self.toast.show_message("已经帮你准备好 5 个词，适合快速进入状态。")

    def vocab_matches_scope(self, row: dict, scope: str) -> bool:
        if scope == "全部范围":
            return True
        today = datetime.now().date()
        now_ts = datetime.now().timestamp()
        created_at = float(row.get("created_at") or 0)
        last_review_at = float(row.get("last_review_at") or 0)
        wrong_count = int(row.get("wrong_count") or 0)
        priority = int(row.get("priority") or 0)
        if scope == "今天新增":
            return bool(created_at) and datetime.fromtimestamp(created_at).date() == today
        if scope == "今天复习":
            return bool(last_review_at) and datetime.fromtimestamp(last_review_at).date() == today
        if scope == "高频错词":
            return wrong_count >= 2
        if scope == "高优先级":
            return priority >= 4
        if scope == "久未复习":
            return (not last_review_at) or (now_ts - last_review_at >= 7 * 24 * 3600)
        if scope == "例句待补":
            return not str(row.get("example") or "").strip()
        return True

    def should_promote_to_mistakes(self, row: dict, extra_wrong: int = 1) -> bool:
        return int(row.get("wrong_count") or 0) + extra_wrong >= 2

    def scroll_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(26, 26, 26, 26)
        layout.setSpacing(16)
        scroll.setWidget(body)
        return scroll, layout

    def page_dashboard(self):
        page, layout = self.scroll_page()
        jp, cn = self.engine.daily_quote()

        hero = Card("今日手帐", "把一段日语课文贴进去，系统就会帮你提词、收词、安排复习。")
        grid = QGridLayout()
        quote = QLabel(jp)
        quote.setStyleSheet("font-size:28px;font-weight:800;")
        trans = QLabel(cn)
        trans.setStyleSheet("color:#6E7C84;")
        start = RippleButton("开始复习")
        start.setProperty("primary", True)
        start.clicked.connect(lambda: self.nav.select("review"))
        quick = RippleButton("快速学 5 词")
        quick.clicked.connect(self.start_quick_study)
        open_text = RippleButton("去课文手札")
        open_text.clicked.connect(lambda: self.nav.select("text_lab"))
        sample = RippleButton("加载示例")
        sample.clicked.connect(self.load_sample_text)
        backup = RippleButton("立即备份")
        backup.setProperty("wood", True)
        backup.clicked.connect(self.backup_database)
        restore = RippleButton("恢复备份")
        restore.setProperty("wood", True)
        restore.clicked.connect(self.restore_database)
        self.focus_mode_btn = RippleButton("开启专注学习")
        self.focus_mode_btn.setProperty("wood", True)
        self.focus_mode_btn.clicked.connect(self.toggle_focus_mode)
        grid.addWidget(quote, 0, 0)
        grid.addWidget(trans, 1, 0)
        grid.addWidget(start, 0, 1)
        grid.addWidget(open_text, 1, 1)
        grid.addWidget(quick, 0, 2)
        grid.addWidget(sample, 1, 2)
        grid.addWidget(backup, 0, 3)
        grid.addWidget(restore, 1, 3)
        grid.addWidget(self.focus_mode_btn, 0, 4, 2, 1)
        hero.layout.addLayout(grid)
        layout.addWidget(hero)

        if self.store.setting("first_run_done", "0") != "1":
            guide = Card("第一次使用，可以这样开始", "不用研究菜单，照着这 3 步走就够了。")
            guide.layout.addWidget(QLabel("1. 在“课文手札”粘贴一段日语课文，然后点“分析课文”。"))
            guide.layout.addWidget(QLabel("2. 在重点词里把想记的词加入词汇本，系统会自动补读音。"))
            guide.layout.addWidget(QLabel("3. 去“复习计划”做今天的复习，错题会自动进入错题本。"))
            dismiss = RippleButton("我知道了")
            dismiss.setProperty("primary", True)
            dismiss.clicked.connect(self.dismiss_first_run_guide)
            guide.layout.addWidget(dismiss)
            layout.addWidget(guide)

        stats = QGridLayout()
        self.stat_vocab = self.stat_card("词汇本", len(self.store.vocab()))
        self.stat_due = self.stat_card("待复习", len(self.store.due_reviews()))
        self.stat_mistake = self.stat_card("错题", len(self.store.mistakes()))
        self.stat_streak = self.stat_card("连续学习", self.streak)
        for i, card in enumerate([self.stat_vocab, self.stat_due, self.stat_mistake, self.stat_streak]):
            stats.addWidget(card, 0, i)
        layout.addLayout(stats)

        plan = Card("本周计划", "先消化旧词，再慢慢加新词，会更轻松也更容易坚持。")
        task = self.today_task()
        plan.layout.addWidget(QLabel(f"今天建议：复习 {task['review']} 个，新学 {task['new']} 个，错题回看 {task['mistake']} 个。"))
        plan.layout.addWidget(QLabel("如果今天只想完成一件事，就先把复习做完。稳定比一口气冲很多更重要。"))
        layout.addWidget(plan)

        settings_card = Card("学习偏好", "先把节奏调成适合自己的样子，软件才会真正顺手。")
        settings_form = QFormLayout()
        self.daily_review_spin = QSpinBox()
        self.daily_review_spin.setRange(5, 100)
        self.daily_review_spin.setValue(int(self.store.setting("daily_review_limit", "15")))
        self.daily_new_spin = QSpinBox()
        self.daily_new_spin.setRange(1, 30)
        self.daily_new_spin.setValue(int(self.store.setting("daily_new_limit", "5")))
        save_settings = RippleButton("保存学习节奏")
        save_settings.setProperty("primary", True)
        save_settings.clicked.connect(self.save_learning_settings)
        settings_form.addRow("每日复习上限", self.daily_review_spin)
        settings_form.addRow("每日新词建议", self.daily_new_spin)
        settings_card.layout.addLayout(settings_form)
        settings_card.layout.addWidget(save_settings)
        layout.addWidget(settings_card)
        layout.addStretch()
        return page

    def dismiss_first_run_guide(self):
        self.store.set_setting("first_run_done", "1")
        new_page = self.page_dashboard()
        old_page = self.pages["dashboard"]
        self.pages["dashboard"] = new_page
        self.stack.removeWidget(old_page)
        old_page.deleteLater()
        self.stack.insertWidget(0, new_page)
        self.nav.select("dashboard")

    def stat_card(self, title: str, value: int) -> Card:
        card = Card(title)
        num = AnimatedNumberLabel(value)
        num.setStyleSheet("font-size:34px;font-weight:900;color:#7E98A8;")
        card.layout.addWidget(num)
        return card

    def page_text_lab(self):
        page, layout = self.scroll_page()

        info = Card("课文手札", "粘贴或拖入一段日语课文，系统会自动分析、标注读音并提取重点词。")
        layout.addWidget(info)

        top = QHBoxLayout()
        self.analyze_btn = RippleButton("分析课文")
        self.analyze_btn.setProperty("primary", True)
        self.analyze_btn.clicked.connect(self.analyze_text_async)
        self.load_text_btn = RippleButton("导入文本")
        self.load_text_btn.clicked.connect(self.load_text_file)
        self.clear_text_btn = RippleButton("清空")
        self.clear_text_btn.setProperty("wood", True)
        self.clear_text_btn.clicked.connect(self.clear_text)
        self.sample_text_btn = RippleButton("加载示例")
        self.sample_text_btn.clicked.connect(self.load_sample_text)
        self.furigana_mode = QComboBox()
        self.furigana_mode.addItems(["关闭读音提示", "只标生词读音", "全文标注读音"])
        saved_mode = self.store.setting("furigana_mode", "new_only")
        self.furigana_mode.setCurrentIndex({"off": 0, "new_only": 1, "all": 2}.get(saved_mode, 1))
        self.furigana_mode.currentIndexChanged.connect(self.refresh_furigana)
        top.addWidget(self.analyze_btn)
        top.addWidget(self.load_text_btn)
        top.addWidget(self.clear_text_btn)
        top.addWidget(self.sample_text_btn)
        top.addStretch()
        top.addWidget(QLabel("读音提示"))
        top.addWidget(self.furigana_mode)
        layout.addLayout(top)

        editor_card = Card("课文原文", "草稿会自动保存。长课文会在后台分析，界面不会假死。")
        self.text_editor = DropTextEdit(self.load_dropped_text_file)
        self.text_editor.setPlaceholderText("请粘贴一段日语课文，或直接把 txt 文件拖进来。")
        self.text_editor.setPlainText(self.store.text())
        self.text_editor.setMinimumHeight(150)
        self.text_editor.setMaximumHeight(200)
        editor_card.layout.addWidget(self.text_editor)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(260)
        editor_card.layout.addWidget(QLabel("阅读预览：只有需要时才标注读音，不会一直把画面挤得很花。"))
        editor_card.layout.addWidget(self.preview)
        copy_plain = RippleButton("复制纯文本")
        copy_plain.clicked.connect(lambda: QApplication.clipboard().setText(self.text_editor.toPlainText()))
        editor_card.layout.addWidget(copy_plain)
        self.text_status = QLabel("准备就绪。")
        self.text_status.setStyleSheet("color:#6E7C84;")
        editor_card.layout.addWidget(self.text_status)
        layout.addWidget(editor_card)

        focus_card = Card("重点词", "双击一行也能直接加入词汇本。状态为“待补充”表示需要补充释义，不是系统坏了。")
        focus_filters = QHBoxLayout()
        self.focus_pos_filter = QComboBox()
        self.focus_pos_filter.addItems(["全部词性", "名词", "动词", "形容词"])
        self.focus_pos_filter.currentIndexChanged.connect(self.render_text_tables)
        self.focus_status_filter = QComboBox()
        self.focus_status_filter.addItems(["全部状态", "可加入", "已收录", "待补充"])
        self.focus_status_filter.currentIndexChanged.connect(self.render_text_tables)
        self.focus_sort = QComboBox()
        self.focus_sort.addItems(["课文顺序", "高频优先", "未收录优先", "读音顺序"])
        self.focus_sort.currentIndexChanged.connect(self.render_text_tables)
        add_all = RippleButton("加入全部可加入")
        add_all.clicked.connect(self.add_all_focus_words)
        focus_filters.addWidget(QLabel("词性"))
        focus_filters.addWidget(self.focus_pos_filter)
        focus_filters.addWidget(QLabel("状态"))
        focus_filters.addWidget(self.focus_status_filter)
        focus_filters.addWidget(QLabel("排序"))
        focus_filters.addWidget(self.focus_sort)
        focus_filters.addStretch()
        focus_filters.addWidget(add_all)
        focus_card.layout.addLayout(focus_filters)
        self.focus_table = self.make_table(["单词", "释义", "读音", "词性", "状态"])
        self.focus_table.cellDoubleClicked.connect(lambda *_: self.add_selected_focus())
        focus_card.layout.addWidget(self.focus_table)
        self.add_focus_btn = RippleButton("加入选中单词")
        self.add_focus_btn.setProperty("primary", True)
        self.add_focus_btn.clicked.connect(self.add_selected_focus)
        focus_card.layout.addWidget(self.add_focus_btn)
        layout.addWidget(focus_card)

        freq_card = Card("词频统计", "这里统计的是原形，不会把 見る / 見た / 見ます 当成不同的词。")
        self.freq_table = self.make_table(["单词", "次数"])
        freq_card.layout.addWidget(self.freq_table)
        layout.addWidget(freq_card)

        self.refresh_furigana()
        if self.text_editor.toPlainText().strip():
            try:
                self.current_words = self.engine.split_words(self.text_editor.toPlainText())
                self.render_text_tables()
            except Exception:
                logging.exception("Initial text analysis failed")
        return page

    def queue_text_autosave(self):
        if not self.analysis_busy:
            self.autosave_timer.start(800)
            self.refresh_furigana()

    def autosave_text(self):
        self.store.save_text(self.text_editor.toPlainText())
        self.text_status.setText("草稿已自动保存。")

    def set_text_busy(self, busy: bool, text: str = "正在处理…"):
        self.analysis_busy = busy
        for widget in (self.analyze_btn, self.load_text_btn, self.clear_text_btn, self.add_focus_btn, self.furigana_mode):
            widget.setEnabled(not busy)
        self.text_editor.setReadOnly(busy)
        if busy:
            self.loading.start(text)
            self.text_status.setText(text)
        else:
            self.loading.stop()

    def analyze_text_async(self):
        if self.analysis_busy:
            return
        text = self.text_editor.toPlainText().strip()
        if not text:
            self.toast.show_message("先放一段日语课文进来，我们再帮你分析。")
            return
        if not self.engine.looks_like_japanese(text):
            self.toast.show_message("这段内容看起来不像日语，先换一段日语课文试试。", 2400)
            return
        self.store.save_text(text)
        self.set_text_busy(True, "正在分析课文，请稍等…")
        self.thread = QThread(self)
        self.worker = TextWorker(self.engine, text)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_text_analyzed)
        self.worker.failed.connect(self.on_worker_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.start()

    def on_text_analyzed(self, words: list[str]):
        self.set_text_busy(False)
        self.current_words = words
        self.render_text_tables()
        self.refresh_furigana()
        self.text_status.setText(f"分析完成，提取到 {len(words)} 个可学习词。")
        self.toast.show_message(f"课文分析完成，提取到 {len(words)} 个可学习词。")

    def on_worker_failed(self, msg: str):
        self.set_text_busy(False)
        self.text_status.setText("这次分析没有成功。你可以换一段更短的课文再试。")
        self.toast.show_message(f"分析没有成功：{msg}", 3000)

    def clear_text(self):
        if not self.text_editor.toPlainText().strip():
            return
        if QMessageBox.question(self, "确认清空", "清空后当前课文草稿会被移除，确定继续吗？") != QMessageBox.StandardButton.Yes:
            return
        self.text_editor.clear()
        self.preview.clear()
        self.current_words = []
        self.store.save_text("")
        self.fill_table(self.focus_table, [])
        self.fill_table(self.freq_table, [])
        self.text_status.setText("课文已清空。")
        self.toast.show_message("课文已清空。")

    def refresh_furigana(self):
        mode = {0: "off", 1: "new_only", 2: "all"}[self.furigana_mode.currentIndex()]
        self.store.set_setting("furigana_mode", mode)
        vocab_words = {row["word"] for row in self.store.vocab()}
        self.preview.setPlainText(self.engine.annotate_text(self.text_editor.toPlainText(), mode, vocab_words))

    def render_text_tables(self):
        vocab_words = {row["word"] for row in self.store.vocab()}
        counts = Counter(self.current_words)
        rows = []
        seen = set()
        pos_filter = getattr(self, "focus_pos_filter", None).currentText() if hasattr(self, "focus_pos_filter") else "全部词性"
        status_filter = getattr(self, "focus_status_filter", None).currentText() if hasattr(self, "focus_status_filter") else "全部状态"
        for word in self.current_words:
            if word in seen:
                continue
            seen.add(word)
            detail = self.engine.get_word_detail(word)
            meaning = self.store.resolve_meaning(word, detail["base_form"], detail["reading"], detail["pos"]) or "待补充"
            status = "已收录" if word in vocab_words else ("待补充" if meaning == "待补充" else "可加入")
            if not self.pos_matches(pos_filter, detail["pos"]):
                continue
            if status_filter != "全部状态" and status_filter != status:
                continue
            rows.append({
                "word": word,
                "meaning": meaning,
                "reading": detail["reading"],
                "pos": detail["pos"],
                "status": status,
                "count": counts[word],
            })
        sort_mode = self.focus_sort.currentText() if hasattr(self, "focus_sort") else "课文顺序"
        if sort_mode == "高频优先":
            rows.sort(key=lambda x: (-x["count"], x["word"]))
        elif sort_mode == "未收录优先":
            order = {"待补充": 0, "可加入": 1, "已收录": 2}
            rows.sort(key=lambda x: (order.get(x["status"], 9), -x["count"], x["word"]))
        elif sort_mode == "读音顺序":
            rows.sort(key=lambda x: (x["reading"] or x["word"], x["word"]))
        display_rows = [[row["word"], row["meaning"], row["reading"], row["pos"], row["status"]] for row in rows]
        self.fill_table(self.focus_table, display_rows)
        self.fill_table(self.freq_table, [[w, c] for w, c in counts.most_common(30)])

    def add_all_focus_words(self):
        if not self.current_words:
            self.toast.show_message("先分析一段课文，我们再帮你批量收词。")
            return
        added = 0
        for word in self.current_words:
            detail = self.engine.get_word_detail(word)
            meaning = self.store.resolve_meaning(word, detail["base_form"], detail["reading"], detail["pos"]) or "待补充"
            if meaning == "待补充" or self.store.get_word(word):
                continue
            forms = self.engine.infer_verb_forms(word, detail["pos"])
            self.store.save_word({"word": word, "meaning": meaning, **detail, **forms, "priority": 2})
            added += 1
        self.refresh_vocab()
        self.refresh_text_if_needed()
        self.toast.show_message(f"已加入 {added} 个可直接识别释义的重点词。")

    def load_text_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择文本文件", str(self.base_dir), "Text Files (*.txt);;All Files (*)")
        if path:
            self.load_dropped_text_file(path)

    def load_sample_text(self):
        sample = (
            "春の朝、公園を散歩すると、桜の花びらが静かに風に乗って流れていく。\n"
            "私はベンチに座り、昨日覚えた単語を小さく復習した。\n"
            "難しい言葉もあるけれど、毎日少しずつ続ければ、きっと自然に身についていく。"
        )
        self.text_editor.setPlainText(sample)
        self.refresh_furigana()
        self.autosave_text()
        self.text_status.setText("示例课文已加载，可以直接开始分析。")
        self.toast.show_message("已加载示例课文，可以直接开始分析。")

    @staticmethod
    def pos_matches(filter_text: str, pos_text: str) -> bool:
        if filter_text == "全部词性":
            return True
        mapping = {
            "名词": ("名詞", "名词"),
            "动词": ("動詞", "动词"),
            "形容词": ("形容詞", "形容词", "形容動詞"),
        }
        return any(token in (pos_text or "") for token in mapping.get(filter_text, (filter_text,)))

    def load_dropped_text_file(self, path: str):
        try:
            raw = Path(path).read_bytes()
            text = None
            for encoding in ("utf-8", "utf-8-sig", "cp932", "shift_jis", "gb18030"):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                raise UnicodeDecodeError("unknown", raw, 0, 1, "无法识别文本编码")
            if self.looks_garbled(text):
                self.text_status.setText("这份文本看起来像乱码，已取消导入。")
                self.toast.show_message("这份文本像是乱码或编码不对。你可以换成 UTF-8 / Shift-JIS 后再试。", 3200)
                QMessageBox.warning(self, "导入没有成功", "这份文本像是乱码或编码不对。建议另存为 UTF-8、Shift-JIS 或 CP932 后再试。")
                return
            self.text_editor.setPlainText(text)
            self.refresh_furigana()
            self.text_status.setText("文本已导入。")
            self.toast.show_message("文本已导入。")
        except Exception:
            self.text_status.setText("导入没有成功。")
            self.toast.show_message("导入没有成功。建议把文本另存为 UTF-8、Shift-JIS 或 CP932 后再试。", 3200)
            QMessageBox.warning(self, "导入没有成功", "建议把文本另存为 UTF-8、Shift-JIS 或 CP932 后再试。")

    @staticmethod
    def looks_garbled(text: str) -> bool:
        if not text.strip():
            return False
        markers = ("ã", "�", "銇", "銈", "銉", "鈥", "锛", "銆")
        marker_hits = sum(text.count(token) for token in markers)
        halfwidth = sum(1 for ch in text if "\uff61" <= ch <= "\uff9f")
        full_japanese = sum(1 for ch in text if ("\u3040" <= ch <= "\u30ff") or ("\u4e00" <= ch <= "\u9fff"))
        question_marks = text.count("?")
        replacement = text.count("\ufffd")
        total = max(len(text), 1)
        return (
            replacement > 0
            or marker_hits / total > 0.04
            or halfwidth / total > 0.12
            or (halfwidth / total > 0.06 and full_japanese / total < 0.12)
            or (question_marks / total > 0.2 and full_japanese / total < 0.1)
        )

    def add_selected_focus(self):
        row = self.focus_table.currentRow()
        if row < 0:
            self.toast.show_message("先选中一行重点词，再加入词汇本。")
            return
        word = self.focus_table.item(row, 0).text()
        meaning = self.focus_table.item(row, 1).text()
        if self.store.get_word(word):
            self.toast.show_message(f"{word} 已经在词汇本里了。")
            self.render_text_tables()
            return
        detail = self.engine.get_word_detail(word)
        forms = self.engine.infer_verb_forms(word, detail["pos"])
        auto_meaning = self.store.resolve_meaning(word, detail["base_form"], detail["reading"], detail["pos"])
        if meaning == "待补充":
            dialog = WordDialog(
                self.engine,
                {
                    "word": word,
                    "meaning": auto_meaning or "",
                    "reading": detail["reading"],
                    "base_form": detail["base_form"],
                    "pos": detail["pos"],
                    "priority": 2,
                },
                self,
            )
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.toast.show_message("这条词先留在重点词里，等你想收的时候再加也可以。")
                return
            payload = dialog.payload()
        else:
            payload = {"word": word, "meaning": meaning, **detail, **forms, "priority": 2}
        self.store.save_word(payload)
        self.toast.show_message(f"{word} 已加入词汇本。")
        self.refresh_vocab()
        self.refresh_text_if_needed()

    def page_vocab(self):
        page, layout = self.scroll_page()
        toolbar = QHBoxLayout()
        add = RippleButton("新增")
        add.setProperty("primary", True)
        add.clicked.connect(self.add_word)
        edit = RippleButton("编辑")
        edit.clicked.connect(self.edit_word)
        delete = RippleButton("删除选中")
        delete.setProperty("danger", True)
        delete.clicked.connect(self.delete_words)
        restore = RippleButton("恢复回收站")
        restore.setProperty("wood", True)
        restore.clicked.connect(self.restore_deleted_words)
        review_now = RippleButton("立即复习")
        review_now.clicked.connect(self.review_selected_words_now)
        p5 = RippleButton("设为重点")
        p5.clicked.connect(lambda: self.set_selected_priority(5))
        mastered = RippleButton("标记掌握")
        mastered.clicked.connect(lambda: self.set_selected_mastered(True))
        unmastered = RippleButton("恢复学习")
        unmastered.clicked.connect(lambda: self.set_selected_mastered(False))
        tags_btn = RippleButton("批量标签")
        tags_btn.clicked.connect(self.edit_selected_tags)
        undo_delete = RippleButton("撤销删除")
        undo_delete.setProperty("wood", True)
        undo_delete.clicked.connect(self.undo_delete_words)
        export = RippleButton("导出 CSV")
        export.clicked.connect(self.export_csv)
        backup = RippleButton("备份数据")
        backup.setProperty("wood", True)
        backup.clicked.connect(self.backup_database)
        self.tag_filter = QLineEdit()
        self.tag_filter.setPlaceholderText("模糊搜索：单词 / 释义 / 读音 / 标签")
        self.tag_filter.textChanged.connect(self.refresh_vocab)
        self.vocab_pos_filter = QComboBox()
        self.vocab_pos_filter.addItems(["全部词性", "名词", "动词", "形容词"])
        self.vocab_pos_filter.currentIndexChanged.connect(self.refresh_vocab)
        self.vocab_stage_filter = QComboBox()
        self.vocab_stage_filter.addItems(["全部阶段", "新词", "复习中", "已掌握", "重点词"])
        self.vocab_stage_filter.currentIndexChanged.connect(self.refresh_vocab)
        self.vocab_scope_filter = QComboBox()
        self.vocab_scope_filter.addItems(["全部范围", "今天新增", "今天复习", "高频错词", "高优先级", "久未复习", "例句待补"])
        self.vocab_scope_filter.currentIndexChanged.connect(self.refresh_vocab)
        for btn in (add, edit, delete, undo_delete, restore, review_now, p5, mastered, unmastered, tags_btn, export, backup):
            toolbar.addWidget(btn)
        toolbar.addStretch()
        toolbar.addWidget(self.vocab_pos_filter)
        toolbar.addWidget(self.vocab_stage_filter)
        toolbar.addWidget(self.vocab_scope_filter)
        toolbar.addWidget(self.tag_filter)
        layout.addLayout(toolbar)

        tip = QLabel("双击一行可以编辑。支持 Ctrl 多选。想快点找到词，可以直接输部分读音或释义。")
        tip.setStyleSheet("color:#6E7C84;")
        layout.addWidget(tip)

        card = Card("词汇本", "词汇会保存标签、例句、优先级和复习阶段，方便你按自己的方式整理。")
        self.vocab_table = self.make_table(["单词", "释义", "读音", "词性", "标签", "阶段", "复习", "优先级"])
        self.vocab_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.vocab_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.vocab_table.cellDoubleClicked.connect(lambda *_: self.edit_word())
        self.vocab_table.itemSelectionChanged.connect(self.show_vocab_detail)
        card.layout.addWidget(self.vocab_table)
        layout.addWidget(card)

        self.detail_card = Card("词汇详情", "选中一条词，就能看例句、变形、记忆提示和容易混淆的点。")
        self.detail_text = QLabel("先在上面选中一条词汇。")
        self.detail_text.setWordWrap(True)
        detail_actions = QHBoxLayout()
        copy_example = RippleButton("复制例句")
        copy_example.clicked.connect(self.copy_selected_example)
        copy_reading = RippleButton("复制读音")
        copy_reading.clicked.connect(self.copy_selected_reading)
        detail_actions.addWidget(copy_example)
        detail_actions.addWidget(copy_reading)
        detail_actions.addStretch()
        self.detail_card.layout.addWidget(self.detail_text)
        self.detail_card.layout.addLayout(detail_actions)
        layout.addWidget(self.detail_card)

        self.refresh_vocab()
        return page

    def refresh_vocab(self):
        rows = []
        filters = {}
        if self.tag_filter.text().strip():
            filters["keyword"] = self.tag_filter.text().strip()
        filters = filters or None
        pos_filter = self.vocab_pos_filter.currentText() if hasattr(self, "vocab_pos_filter") else "全部词性"
        for r in self.store.vocab(filters=filters):
            if not (r.get("reading") and r.get("pos")):
                detail = self.engine.get_word_detail(r["word"])
                r["reading"] = detail["reading"]
                r["pos"] = detail["pos"]
                r["base_form"] = detail["base_form"]
                self.store.save_word(r)
            if not self.pos_matches(pos_filter, r.get("pos") or ""):
                continue
            stage = "已掌握" if r.get("mastered") else ("新词" if not r.get("review_count") else f"阶段 {int(r.get('stage_index') or 0) + 1}")
            stage_filter = self.vocab_stage_filter.currentText() if hasattr(self, "vocab_stage_filter") else "全部阶段"
            if stage_filter == "新词" and r.get("review_count"):
                continue
            if stage_filter == "复习中" and (not r.get("review_count") or r.get("mastered")):
                continue
            if stage_filter == "已掌握" and not r.get("mastered"):
                continue
            if stage_filter == "重点词" and int(r.get("priority") or 0) < 4:
                continue
            scope_filter = self.vocab_scope_filter.currentText() if hasattr(self, "vocab_scope_filter") else "全部范围"
            if not self.vocab_matches_scope(r, scope_filter):
                continue
            rows.append([r["word"], r["meaning"], r["reading"], r["pos"], r["tags"], stage, int(r.get("review_count") or 0), int(r["priority"])])
        self.fill_table(self.vocab_table, rows)
        self.refresh_dashboard_numbers()
        self.show_vocab_detail()

    def selected_vocab_words(self) -> list[str]:
        rows = sorted({i.row() for i in self.vocab_table.selectedItems()})
        return [self.vocab_table.item(r, 0).text() for r in rows if self.vocab_table.item(r, 0)]

    def add_word(self):
        dialog = WordDialog(self.engine, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                payload = dialog.payload()
                self.store.save_word(payload)
                self.refresh_vocab()
                self.refresh_text_if_needed()
                self.toast.show_message("词条已保存。")
            except Exception as exc:
                self.toast.show_message(f"保存没有成功：{exc}", 2800)

    def edit_word(self):
        words = self.selected_vocab_words()
        if not words:
            self.toast.show_message("先选中一条词，再编辑。")
            return
        data = self.store.get_word(words[0])
        dialog = WordDialog(self.engine, data, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.store.save_word(dialog.payload())
            self.refresh_vocab()
            self.refresh_text_if_needed()
            self.toast.show_message("词条已更新。")

    def delete_words(self):
        words = self.selected_vocab_words()
        if not words:
            self.toast.show_message("先选中要删除的词。")
            return
        if QMessageBox.question(self, "确认删除", f"把选中的 {len(words)} 个单词移到回收站？之后还能恢复。") != QMessageBox.StandardButton.Yes:
            return
        self.last_deleted_words = words[:]
        self.store.delete_words(words)
        self.refresh_vocab()
        self.refresh_text_if_needed()
        self.toast.show_message("已移到回收站。想反悔的话，可以点“撤销删除”。")

    def restore_deleted_words(self):
        trash = self.store.trash_items()
        if not trash:
            self.toast.show_message("回收站现在是空的。")
            return
        dialog = TrashRestoreDialog(trash, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        words = dialog.selected_words()
        restored = self.store.restore_words(words)
        self.refresh_vocab()
        self.refresh_text_if_needed()
        self.toast.show_message(f"已恢复 {restored} 个单词。")

    def undo_delete_words(self):
        if not self.last_deleted_words:
            self.toast.show_message("现在没有可撤销的删除。")
            return
        restored = self.store.restore_words(self.last_deleted_words)
        self.last_deleted_words = []
        self.refresh_vocab()
        self.refresh_text_if_needed()
        self.toast.show_message(f"已撤销删除，恢复了 {restored} 个单词。")

    def set_selected_priority(self, priority: int):
        words = self.selected_vocab_words()
        if not words:
            self.toast.show_message("先选中一些单词，再设置优先级。")
            return
        self.store.set_priority(words, priority)
        self.refresh_vocab()
        self.toast.show_message(f"已把 {len(words)} 个单词设为优先级 {priority}。")

    def set_selected_mastered(self, mastered: bool):
        words = self.selected_vocab_words()
        if not words:
            self.toast.show_message("先选中一些单词，再调整掌握状态。")
            return
        self.store.set_mastered(words, mastered)
        self.refresh_vocab()
        self.refresh_due()
        self.toast.show_message(f"已把 {len(words)} 个单词设为{'已掌握' if mastered else '继续学习'}。")

    def edit_selected_tags(self):
        words = self.selected_vocab_words()
        if not words:
            self.toast.show_message("先选中一些单词，再一起整理标签。")
            return
        dialog = TagBatchDialog(len(words), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        tags = dialog.tags.text().strip()
        if not tags:
            self.toast.show_message("这次没有填写标签，所以先不修改。")
            return
        updated = self.store.merge_tags(words, tags, replace=dialog.replace.isChecked())
        self.refresh_vocab()
        self.toast.show_message(f"已更新 {updated} 个单词的标签。")

    def review_selected_words_now(self):
        words = self.selected_vocab_words()
        if not words:
            self.toast.show_message("先选中一些单词，再安排立即复习。")
            return
        self.store.schedule_now(words)
        self.refresh_due()
        self.toast.show_message(f"已把 {len(words)} 个单词加入待复习。")

    def show_vocab_detail(self):
        if not hasattr(self, "detail_text"):
            return
        words = self.selected_vocab_words()
        if not words:
            self.detail_text.setText("先在上面选中一条词汇。")
            return
        data = self.store.get_word(words[0]) or {}
        if data and not (data.get("reading") and data.get("pos")):
            detail = self.engine.get_word_detail(data["word"])
            data["reading"] = detail["reading"]
            data["pos"] = detail["pos"]
            data["base_form"] = detail["base_form"]
            self.store.save_word(data)
        forms = []
        if data.get("polite_form"):
            forms.append(f"ます形：{data['polite_form']}")
        if data.get("te_form"):
            forms.append(f"て形：{data['te_form']}")
        if data.get("ta_form"):
            forms.append(f"た形：{data['ta_form']}")
        rule = self.explain_verb_rule(data.get("word", ""), data.get("pos", ""))
        memory_tip = self.memory_hint(data)
        text = (
            f"单词：{data.get('word', '')}\n"
            f"读音：{data.get('reading', '-')}\n"
            f"释义：{data.get('meaning', '')}\n"
            f"标签：{data.get('tags', '') or '未设置'}\n"
            f"例句：{data.get('example', '') or '还没有例句'}\n"
            f"备注：{data.get('notes', '') or '还没有备注'}\n"
            f"变形：{'  '.join(forms) if forms else '当前不是动词，或还没有变形信息'}\n"
            f"规则说明：{rule}\n"
            f"记忆提示：{memory_tip}"
        )
        self.detail_text.setText(text)

    def explain_verb_rule(self, word: str, pos: str) -> str:
        if "動詞" not in pos and "动词" not in pos:
            return "这条词目前不是按动词来处理。"
        if word.endswith("する"):
            return "这是 する 类动词，变化最特殊，建议整组记。"
        if word in {"来る", "くる"}:
            return "这是 来る 类不规则动词，读音和写法都需要单独记。"
        if word.endswith("る"):
            return "这类常见于一段动词，ます形通常去る加ます。"
        return "这是五段动词思路，词尾会按行变化，建议把 ます形 / て形 / た形一起记。"

    def memory_hint(self, data: dict) -> str:
        tags = data.get("tags", "")
        word = data.get("word", "")
        meaning = data.get("meaning", "")
        if "动词" in tags or "動詞" in (data.get("pos") or ""):
            return f"把 {word} 和它的 ます形、て形 放在一起记，会比单背释义更稳。"
        if "N" in tags:
            return f"这是考试标签词，建议把“{word} = {meaning}”放进今天的主动回忆里。"
        return f"试着先遮住释义，只看 {word} 回想“{meaning}”，记忆会更牢。"

    def confusion_hint(self, row: dict) -> str:
        word = row.get("word", "")
        meaning = row.get("meaning", "")
        candidates = [r for r in self.store.vocab() if r["word"] != word]
        close = []
        for item in candidates:
            score = len(set(item["word"]) & set(word)) + len(set(item["meaning"]) & set(meaning))
            if score > 0:
                close.append((score, item))
        close.sort(key=lambda x: x[0], reverse=True)
        if close:
            peer = close[0][1]
            return f"这题容易和 {peer['word']}（{peer['meaning']}）混在一起，复习时可以把这两个放在一起辨别。"
        return "这题更像是记忆还不稳，不是你学不会。隔一会儿再见一次，通常就会顺很多。"

    def copy_selected_example(self):
        words = self.selected_vocab_words()
        if not words:
            self.toast.show_message("先选中一条词汇。")
            return
        example = (self.store.get_word(words[0]) or {}).get("example", "")
        if not example:
            self.toast.show_message("这条词还没有例句。")
            return
        QApplication.clipboard().setText(example)
        self.toast.show_message("例句已复制。")

    def copy_selected_reading(self):
        words = self.selected_vocab_words()
        if not words:
            self.toast.show_message("先选中一条词汇。")
            return
        reading = (self.store.get_word(words[0]) or {}).get("reading", "")
        QApplication.clipboard().setText(reading)
        self.toast.show_message("读音已复制。")

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", str(self.base_dir / "词汇本导出.csv"), "CSV Files (*.csv)")
        if path:
            self.store.export_csv(Path(path))
            self.toast.show_message("导出完成。")

    def backup_database(self):
        try:
            target = self.store.backup()
            self.toast.show_message("数据库备份完成。")
            QMessageBox.information(self, "备份完成", f"备份文件已保存到：\n{target}")
        except Exception as exc:
            self.toast.show_message(f"备份没有成功：{exc}", 2800)

    def restore_database(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择备份文件", str(self.base_dir), "SQLite Backup (*.db *.sqlite *.bak)")
        if not path:
            return
        if QMessageBox.question(self, "确认恢复", "恢复备份会覆盖当前数据。建议先做一次备份，确定继续吗？") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.restore(Path(path))
            self.toast.show_message("备份已恢复，界面内容已刷新。")
            self.refresh_vocab()
            self.refresh_text_if_needed()
            self.refresh_due()
            self.refresh_mistakes()
            self.refresh_report()
            self.refresh_dashboard_numbers()
        except Exception as exc:
            QMessageBox.warning(self, "恢复没有成功", f"这次恢复没有成功：\n{exc}")
            self.toast.show_message(f"恢复没有成功：{exc}", 2800)

    def save_learning_settings(self):
        self.store.set_setting("daily_review_limit", str(self.daily_review_spin.value()))
        self.store.set_setting("daily_new_limit", str(self.daily_new_spin.value()))
        self.refresh_light_state()
        self.toast.show_message("学习节奏已保存。")

    def page_review(self):
        page, layout = self.scroll_page()
        top = QHBoxLayout()
        self.review_mode = QComboBox()
        self.review_mode.addItem("看日语想中文", "jp_to_cn")
        self.review_mode.addItem("看中文想日语", "cn_to_jp")
        self.review_mode.addItem("看读音想中文", "reading_to_cn")
        self.review_mode.setCurrentIndex({"jp_to_cn": 0, "cn_to_jp": 1, "reading_to_cn": 2}.get(self.store.setting("review_mode", "jp_to_cn"), 0))
        self.review_mode.currentIndexChanged.connect(lambda: self.store.set_setting("review_mode", self.review_mode.currentData()))
        start = RippleButton("开始今日复习")
        start.setProperty("primary", True)
        start.clicked.connect(self.start_review)
        top.addWidget(QLabel("模式"))
        top.addWidget(self.review_mode)
        top.addWidget(start)
        top.addStretch()
        layout.addLayout(top)

        self.review_card = Card("复习卡片", "可以按自己的习惯切换练习方向。系统是来配合你，不是来管你。")
        self.review_word = QLabel("点击开始")
        self.review_word.setStyleSheet("font-size:36px;font-weight:900;")
        self.review_hint = QLabel("")
        self.review_status = QLabel("")
        self.review_status.setStyleSheet("font-size:18px;font-weight:800;")
        self.review_result = QLabel("")
        self.review_result.setWordWrap(True)
        self.review_result.setMinimumHeight(84)
        self.review_result.setStyleSheet("font-size:17px;line-height:1.7;padding:10px 2px;")
        self.review_options = QGridLayout()
        self.review_card.layout.addWidget(self.review_word)
        self.review_card.layout.addWidget(self.review_hint)
        self.review_card.layout.addWidget(self.review_status)
        self.review_card.layout.addWidget(self.review_result)
        self.review_card.layout.addLayout(self.review_options)
        layout.addWidget(self.review_card)

        due = Card("今日待复习")
        self.due_table = self.make_table(["单词", "读音", "阶段", "优先级"])
        due.layout.addWidget(self.due_table)
        layout.addWidget(due)
        self.refresh_due()
        return page

    def refresh_due(self):
        if hasattr(self, "due_table"):
            rows = [[r["word"], r["reading"], f"阶段 {int(r.get('stage_index') or 0) + 1}", int(r["priority"])] for r in self.store.due_reviews()]
            self.fill_table(self.due_table, rows)
        self.refresh_dashboard_numbers()

    def start_review(self):
        self.review_queue = self.store.due_reviews(int(self.store.setting("daily_review_limit", "15")))
        self.review_i = 0
        self.review_ok = 0
        self.review_misses = []
        if not self.review_queue:
            warmup = [row for row in self.store.vocab(order="priority DESC, updated_at DESC", limit=5) if not row.get("mastered")]
            if warmup:
                self.store.schedule_now([row["word"] for row in warmup])
                self.review_queue = self.store.due_reviews(5)
                self.toast.show_message("今天没有到点复习，我先帮你准备了 5 个重点词热身。")
            else:
                self.review_word.setText("今天没有待复习内容")
                self.review_hint.setText("你可以去课文手札收新词，或者做一轮随机自测。")
                self.review_result.setText("")
                self.clear_layout(self.review_options)
                return
        self.render_review()

    def render_review(self):
        if self.review_i >= len(self.review_queue):
            self.store.save_test(len(self.review_queue), self.review_ok, "review")
            summary = "；".join(self.review_misses[:5]) if self.review_misses else "这一轮没有错题，状态很稳。"
            self.review_word.setText("复习完成")
            self.review_hint.setText(f"正确 {self.review_ok}/{len(self.review_queue)}")
            self.review_result.setText(f"复盘：{summary}")
            self.clear_layout(self.review_options)
            self.refresh_due()
            self.refresh_report()
            return
        row = self.review_queue[self.review_i]
        mode = self.review_mode.currentData()
        if mode == "cn_to_jp":
            self.review_word.setText(row["meaning"])
            self.review_hint.setText("先自己回想日语单词，再判断自己的熟悉程度。")
            reveal_text = f"单词：{row['word']}  读音：{row['reading']}  词性：{row['pos']}"
            reveal_label = "显示答案"
        elif mode == "reading_to_cn":
            self.review_word.setText(row["reading"] or row["word"])
            self.review_hint.setText("只看读音回想中文意思，会更贴近听到词时的反应。")
            reveal_text = f"释义：{row['meaning']}  单词：{row['word']}  词性：{row['pos']}"
            reveal_label = "显示单词"
        else:
            self.review_word.setText(row["word"])
            self.review_hint.setText("先自己回想释义，再判断自己的熟悉程度。")
            reveal_text = f"读音：{row['reading']}  词性：{row['pos']}"
            reveal_label = "显示读音"
        self.review_result.setText("")
        self.review_status.setText("")
        self.clear_layout(self.review_options)
        know = RippleButton("会")
        know.setProperty("primary", True)
        blur = RippleButton("模糊")
        blur.setProperty("wood", True)
        hard = RippleButton("不会")
        hard.setProperty("danger", True)
        skip = RippleButton("先跳过")
        show = RippleButton(reveal_label)
        for btn in (know, blur, hard, skip, show):
            btn.setMinimumHeight(54)
        know.clicked.connect(lambda: self.answer_review_level("know", row))
        blur.clicked.connect(lambda: self.answer_review_level("blur", row))
        hard.clicked.connect(lambda: self.answer_review_level("hard", row))
        skip.clicked.connect(self.skip_review)
        show.clicked.connect(lambda: self.review_result.setText(reveal_text))
        self.review_options.addWidget(know, 0, 0)
        self.review_options.addWidget(blur, 0, 1)
        self.review_options.addWidget(hard, 1, 0)
        self.review_options.addWidget(skip, 1, 1)
        self.review_options.addWidget(show, 2, 0, 1, 2)

    def answer_review_level(self, level: str, row: dict):
        mode = self.review_mode.currentData()
        if mode == "cn_to_jp":
            correct_text = f"单词：{row['word']}  读音：{row['reading']}  词性：{row['pos']}"
        elif mode == "reading_to_cn":
            correct_text = f"正确意思：{row['meaning']}  单词：{row['word']}  词性：{row['pos']}"
        else:
            correct_text = f"读音：{row['reading']}  词性：{row['pos']}"
        if level == "know":
            self.review_ok += 1
            self.set_feedback(self.review_status, self.review_result, "success", "答对了，记忆很稳。", f"{correct_text}\n建议：轻声把这个词读一遍，再进入下一词，会更容易留下痕迹。")
            self.toast.show_message("答对了，记忆很稳。")
            self.store.apply_review(row["word"], True)
            self.store.resolve_mistake(row["word"])
        elif level == "blur":
            self.review_ok += 1
            hint = self.confusion_hint(row)
            self.set_feedback(self.review_status, self.review_result, "warning", "这题有印象，但还不稳。", f"{correct_text}\n{hint}")
            self.toast.show_message("这题记作“模糊”，系统会让它更快再回来一次。")
            self.store.apply_review(row["word"], False)
            if self.should_promote_to_mistakes(row):
                self.store.mark_mistake(row["word"], row["meaning"])
        else:
            self.review_misses.append(f"{row['word']} → {row['meaning']}")
            hint = self.confusion_hint(row)
            self.set_feedback(self.review_status, self.review_result, "danger", "这题先别急，我们把它记稳。", f"{correct_text}\n{hint}")
            self.toast.show_message("这题先记下来，稍后再见一次。")
            self.store.apply_review(row["word"], False)
            if self.should_promote_to_mistakes(row):
                self.store.mark_mistake(row["word"], row["meaning"])
        self.review_i += 1
        self.show_continue_action(self.review_options, self.render_review, "继续下一词")

    def skip_review(self):
        self.toast.show_message("已跳过，这个词稍后还会再见。")
        self.review_i += 1
        self.render_review()

    def page_test(self):
        page, layout = self.scroll_page()
        top = QHBoxLayout()
        self.test_count = QSpinBox()
        self.test_count.setRange(1, 100)
        self.test_count.setValue(5)
        self.test_mode = QComboBox()
        self.test_mode.addItem("看日语选中文", "jp_to_cn")
        self.test_mode.addItem("看中文选日语", "cn_to_jp")
        self.test_mode.addItem("看读音选单词", "reading_to_word")
        self.test_mode.setCurrentIndex({"jp_to_cn": 0, "cn_to_jp": 1, "reading_to_word": 2}.get(self.store.setting("test_mode", "jp_to_cn"), 0))
        self.test_mode.currentIndexChanged.connect(lambda: self.store.set_setting("test_mode", self.test_mode.currentData()))
        start = RippleButton("开始自测")
        start.setProperty("primary", True)
        start.clicked.connect(self.start_test)
        top.addWidget(QLabel("题量"))
        top.addWidget(self.test_count)
        top.addWidget(QLabel("模式"))
        top.addWidget(self.test_mode)
        top.addWidget(start)
        top.addStretch()
        layout.addLayout(top)

        card = Card("随机自测", "可以切换不同方向来练。干扰项会尽量选得更像，答错会自动加入错题本。")
        self.test_word = QLabel("点击开始")
        self.test_word.setStyleSheet("font-size:34px;font-weight:900;")
        self.test_hint = QLabel("")
        self.test_status = QLabel("")
        self.test_status.setStyleSheet("font-size:18px;font-weight:800;")
        self.test_result = QLabel("")
        self.test_result.setWordWrap(True)
        self.test_result.setMinimumHeight(96)
        self.test_result.setStyleSheet("font-size:17px;line-height:1.7;padding:10px 2px;")
        self.test_options = QGridLayout()
        card.layout.addWidget(self.test_word)
        card.layout.addWidget(self.test_hint)
        card.layout.addWidget(self.test_status)
        card.layout.addWidget(self.test_result)
        card.layout.addLayout(self.test_options)
        layout.addWidget(card)
        return page

    def start_test(self):
        rows = self.store.vocab(order="RANDOM()", limit=self.test_count.value())
        if not rows:
            self.toast.show_message("词汇本还是空的，先加几个词再来。")
            return
        self.test_queue = rows
        self.test_i = 0
        self.test_ok = 0
        self.test_misses = []
        self.render_test()

    def render_test(self):
        if self.test_i >= len(self.test_queue):
            self.store.save_test(len(self.test_queue), self.test_ok, "test")
            summary = "；".join(self.test_misses[:5]) if self.test_misses else "这轮没有错题。"
            self.test_word.setText("测试完成")
            self.test_hint.setText(f"正确 {self.test_ok}/{len(self.test_queue)}")
            self.test_result.setText(f"复盘：{summary}")
            self.clear_layout(self.test_options)
            self.refresh_report()
            self.refresh_mistakes()
            return
        row = self.test_queue[self.test_i]
        mode = self.test_mode.currentData()
        if mode == "cn_to_jp":
            self.test_word.setText(row["meaning"])
            self.test_hint.setText("看中文，选最合适的日语单词。")
            pool = [r["word"] for r in self.store.vocab()]
            choices = self.engine.build_choices(row["word"], pool)
        elif mode == "reading_to_word":
            self.test_word.setText(row["reading"] or row["word"])
            self.test_hint.setText("看读音，选对应的单词。")
            pool = [r["word"] for r in self.store.vocab()]
            choices = self.engine.build_choices(row["word"], pool)
        else:
            self.test_word.setText(row["word"])
            self.test_hint.setText("看日语，选最合适的中文意思。")
            pool = [r["meaning"] for r in self.store.vocab()]
            choices = self.engine.build_choices(row["meaning"], pool)
        self.test_result.setText("")
        self.test_status.setText("")
        self.clear_layout(self.test_options)
        for i, choice in enumerate(choices):
            btn = RippleButton(choice)
            btn.setMinimumHeight(56)
            btn.clicked.connect(lambda _, c=choice, r=row: self.answer_test(c, r))
            self.test_options.addWidget(btn, i // 2, i % 2)

    def answer_test(self, choice: str, row: dict):
        mode = self.test_mode.currentData()
        target = row["meaning"] if mode == "jp_to_cn" else row["word"]
        ok = self.engine.answer_matches(choice, target) in {"exact", "close"}
        if ok:
            self.test_ok += 1
            self.store.resolve_mistake(row["word"])
            self.set_feedback(
                self.test_status,
                self.test_result,
                "success",
                "答对了。",
                f"单词：{row['word']}  读音：{row['reading']}  词性：{row['pos']}\n做得很好，停一秒确认一下，再继续下一题。",
            )
            self.toast.show_message("回答正确。")
        else:
            promoted = self.should_promote_to_mistakes(row)
            if promoted:
                self.store.mark_mistake(row["word"], row["meaning"])
            self.test_misses.append(f"{row['word']} → {row['meaning']}")
            if mode == "jp_to_cn":
                answer_text = f"正确答案：{row['meaning']}  读音：{row['reading']}  词性：{row['pos']}"
            else:
                answer_text = f"正确答案：{row['word']}  读音：{row['reading']}  释义：{row['meaning']}"
            self.set_feedback(
                self.test_status,
                self.test_result,
                "danger",
                "这题答错了，没关系。",
                f"{answer_text}\n{self.confusion_hint(row)}\n{'这次会进入错题本，后面会单独再见它。' if promoted else '这次先记成一次波动；如果连续两次卡住，再放进错题本会更合理。'}\n建议：先把读音读出来，再把正确意思完整说一遍，会比直接跳过更有用。",
            )
            self.toast.show_message("已记录这次失误。" if not promoted else "已加入错题本。")
        self.test_i += 1
        self.show_continue_action(self.test_options, self.render_test, "继续下一题")

    def page_mistakes(self):
        page, layout = self.scroll_page()
        top = QHBoxLayout()
        start = RippleButton("开始错题专项")
        start.setProperty("primary", True)
        start.clicked.connect(self.start_practice)
        review_now = RippleButton("错题加入今日复习")
        review_now.clicked.connect(self.schedule_mistakes_now)
        export = RippleButton("导出错题")
        export.setProperty("wood", True)
        export.clicked.connect(self.export_mistakes)
        self.practice_limit = QSpinBox()
        self.practice_limit.setRange(3, 50)
        self.practice_limit.setValue(10)
        top.addWidget(start)
        top.addWidget(QLabel("本轮题量"))
        top.addWidget(self.practice_limit)
        top.addWidget(review_now)
        top.addWidget(export)
        top.addStretch()
        layout.addLayout(top)

        card = Card("错题本", "错题不会自动消失。只有真正答对，它才会从这里温柔地退场。")
        self.mistake_table = self.make_table(["单词", "释义", "错误次数", "词性", "最近错误"])
        card.layout.addWidget(self.mistake_table)
        layout.addWidget(card)

        practice = Card("专项练习")
        self.practice_word = QLabel("点击开始")
        self.practice_word.setStyleSheet("font-size:30px;font-weight:900;")
        self.practice_status = QLabel("")
        self.practice_status.setStyleSheet("font-size:18px;font-weight:800;")
        self.practice_result = QLabel("")
        self.practice_result.setWordWrap(True)
        self.practice_result.setMinimumHeight(96)
        self.practice_result.setStyleSheet("font-size:17px;line-height:1.7;padding:10px 2px;")
        self.practice_options = QGridLayout()
        practice.layout.addWidget(self.practice_word)
        practice.layout.addWidget(self.practice_status)
        practice.layout.addWidget(self.practice_result)
        practice.layout.addLayout(self.practice_options)
        layout.addWidget(practice)
        self.refresh_mistakes()
        return page

    def refresh_mistakes(self):
        if hasattr(self, "mistake_table"):
            rows = []
            for r in self.store.mistakes():
                when = datetime.fromtimestamp(r["last_wrong_at"]).strftime("%Y-%m-%d %H:%M") if r["last_wrong_at"] else ""
                rows.append([r["word"], r["meaning"], int(r["wrong_count"]), r.get("pos") or "", when])
            self.fill_table(self.mistake_table, rows)
        self.refresh_dashboard_numbers()

    def start_practice(self):
        self.practice_queue = self.store.mistakes()[: self.practice_limit.value()]
        self.practice_i = 0
        self.practice_ok = 0
        self.practice_misses = []
        if not self.practice_queue:
            self.practice_word.setText("还没有错题")
            self.practice_result.setText("去做一轮自测，错题就会自动来到这里。")
            self.clear_layout(self.practice_options)
            return
        self.render_practice()

    def render_practice(self):
        if self.practice_i >= len(self.practice_queue):
            summary = "；".join(self.practice_misses[:5]) if self.practice_misses else "这轮错题都顺利消化了。"
            self.practice_word.setText("错题练习完成")
            self.practice_result.setText(f"复盘：{summary}")
            self.clear_layout(self.practice_options)
            self.refresh_mistakes()
            return

        row = self.practice_queue[self.practice_i]
        self.practice_word.setText(row["word"])
        self.practice_result.setText("")
        self.practice_status.setText("")
        self.clear_layout(self.practice_options)
        meanings = [r["meaning"] for r in self.store.vocab()]
        for i, choice in enumerate(self.engine.build_choices(row["meaning"], meanings)):
            btn = RippleButton(choice)
            btn.setMinimumHeight(56)
            btn.clicked.connect(lambda _, c=choice, r=row: self.answer_practice(c, r))
            self.practice_options.addWidget(btn, i // 2, i % 2)

    def schedule_mistakes_now(self):
        rows = self.store.mistakes()
        if not rows:
            self.toast.show_message("还没有错题可以加入今日复习。")
            return
        self.store.schedule_now([row["word"] for row in rows[: self.practice_limit.value()]])
        self.refresh_due()
        self.toast.show_message("这批错题已经加入今日复习。")

    def answer_practice(self, choice: str, row: dict):
        ok = self.engine.answer_matches(choice, row["meaning"]) in {"exact", "close"}
        if ok:
            self.practice_ok += 1
            self.store.resolve_mistake(row["word"])
            self.set_feedback(
                self.practice_status,
                self.practice_result,
                "success",
                "答对了，这条词正在慢慢稳定下来。",
                f"读音：{row.get('reading') or '-'}\n这次会把它的错题压力减轻一点；连续答稳几次，它就会自然退出错题本。",
            )
        else:
            self.store.mark_mistake(row["word"], row["meaning"])
            self.practice_misses.append(f"{row['word']} → {row['meaning']}")
            self.set_feedback(
                self.practice_status,
                self.practice_result,
                "danger",
                "这条词还需要再见几次。",
                f"正确答案：{row['meaning']}\n{self.confusion_hint(row)}",
            )
        self.practice_i += 1
        self.show_continue_action(self.practice_options, self.render_practice, "继续下一题")

    def export_mistakes(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出错题", str(self.base_dir / "错题导出.csv"), "CSV Files (*.csv)")
        if not path:
            return
        try:
            with Path(path).open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["单词", "释义", "错误次数", "词性", "最近错误"])
                for row in self.store.mistakes():
                    writer.writerow([
                        row["word"],
                        row["meaning"],
                        row["wrong_count"],
                        row.get("pos") or "",
                        datetime.fromtimestamp(row["last_wrong_at"]).strftime("%Y-%m-%d %H:%M") if row["last_wrong_at"] else "",
                    ])
            self.toast.show_message("错题已导出。")
        except Exception as exc:
            self.toast.show_message(f"导出失败：{exc}", 2400)

    def page_report(self):
        page, layout = self.scroll_page()
        self.report_card = Card("学习报告", "不只是统计数量，也帮你看见这段时间到底有没有稳稳往前走。")
        self.report_text = QLabel()
        self.report_text.setWordWrap(True)
        actions = QHBoxLayout()
        refresh = RippleButton("刷新报告")
        refresh.setProperty("primary", True)
        refresh.clicked.connect(self.refresh_report)
        export = RippleButton("导出记录")
        export.clicked.connect(self.export_report_csv)
        self.report_action_btn = RippleButton("去看看下一步")
        self.report_action_btn.setProperty("wood", True)
        self.report_action_btn.clicked.connect(self.open_report_action)
        actions.addWidget(refresh)
        actions.addWidget(export)
        actions.addWidget(self.report_action_btn)
        actions.addStretch()
        self.report_card.layout.addLayout(actions)
        self.report_card.layout.addWidget(self.report_text)
        layout.addWidget(self.report_card)

        self.trend_card = Card("正确率趋势", "每一次练习都不会白做，曲线能帮你看到变化。")
        self.trend_chart = TrendChart()
        self.trend_text = QLabel()
        self.trend_text.setWordWrap(True)
        self.trend_card.layout.addWidget(self.trend_chart)
        self.trend_card.layout.addWidget(self.trend_text)
        layout.addWidget(self.trend_card)

        self.distribution_card = Card("薄弱点分布", "错题和词性分布能帮你判断下一步应该把时间花在哪里。")
        self.distribution_chart = DistributionChart()
        self.distribution_card.layout.addWidget(self.distribution_chart)
        layout.addWidget(self.distribution_card)

        self.chart = QTableWidget(0, 4)
        self.chart.setHorizontalHeaderLabels(["时间", "模式", "题数", "正确率"])
        self.chart.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        record_card = Card("最近记录")
        record_card.layout.addWidget(self.chart)
        layout.addWidget(record_card)
        self.refresh_report()
        return page

    def refresh_report(self):
        vocab = self.store.vocab()
        mistakes = self.store.mistakes()
        mastered = sum(1 for r in vocab if r.get("mastered"))
        pos_counter = Counter(r.get("pos") or "未分类" for r in mistakes)
        weak = pos_counter.most_common(1)[0][0] if pos_counter else "暂时没有明显薄弱项"
        all_tests = self.store.tests(0)
        recent = all_tests[:7]
        previous = all_tests[7:14]
        recent_avg = sum(r["accuracy"] for r in recent) / len(recent) if recent else 0
        prev_avg = sum(r["accuracy"] for r in previous) / len(previous) if previous else 0
        delta = recent_avg - prev_avg if previous else 0
        completed_week = len([r for r in all_tests if datetime.fromtimestamp(r["created_at"]).isocalendar()[:2] == datetime.now().isocalendar()[:2]])
        due_count = len(self.store.due_reviews())
        if due_count >= 8:
            next_step = f"先把今天待复习的 {due_count} 个词消化掉，再决定要不要加新词。"
            self.report_action_target = "review"
            self.report_action_btn.setText("去完成复习")
        elif mistakes:
            next_step = "今天适合先做一轮错题专项，把容易混淆的词对先拆开。"
            self.report_action_target = "mistakes"
            self.report_action_btn.setText("去做错题专项")
        elif len(vocab) < 20:
            next_step = "现在词量还轻，适合继续从课文里稳稳收一批高频词。"
            self.report_action_target = "text_lab"
            self.report_action_btn.setText("去课文手札收词")
        else:
            next_step = "今天可以先复习，再新增 3-5 个词，保持输入和消化平衡。"
            self.report_action_target = "review"
            self.report_action_btn.setText("去开始复习")
        if recent:
            if delta > 3:
                encouragement = "你这周的正确率比上一段更稳，进步是看得见的。"
            elif delta < -3:
                encouragement = "这周状态有点累也没关系，先把错题消化掉，曲线通常会慢慢抬回来。"
            else:
                encouragement = "整体节奏很稳。这种不忽快忽慢的学习，往往最容易坚持。"
        else:
            encouragement = "等你做完几轮复习和自测，这里会长出属于你的学习曲线。"

        self.report_text.setText(
            f"词汇总数：{len(vocab)}\n"
            f"已掌握：{mastered}\n"
            f"学习中：{len(vocab) - mastered}\n"
            f"错题数：{len(mistakes)}\n"
            f"薄弱点提示：{weak}\n"
            f"本周完成练习：{completed_week} 次\n"
            f"与上一段相比：{delta:+.1f} 个百分点\n"
            f"下一步建议：{next_step}\n"
            f"鼓励：{encouragement}"
        )

        trend_rows = list(reversed(all_tests[:10]))
        labels = [datetime.fromtimestamp(item["created_at"]).strftime("%m-%d") for item in trend_rows]
        values = [item["accuracy"] for item in trend_rows]
        self.trend_chart.set_points(labels, values)
        if values:
            self.trend_text.setText(f"最近 {len(values)} 次练习平均正确率：{sum(values) / len(values):.1f}%")
        else:
            self.trend_text.setText("还没有足够的数据。做一两轮复习和自测后，这里会开始变得很有参考价值。")

        distribution = Counter()
        for row in mistakes:
            distribution[row.get("pos") or "未分类"] += int(row.get("wrong_count") or 0)
        self.distribution_chart.set_data(distribution.most_common(6))

        rows = self.store.tests(20)
        self.chart.setRowCount(len(rows))
        for r, item in enumerate(rows):
            values = [
                datetime.fromtimestamp(item["created_at"]).strftime("%m-%d %H:%M"),
                item["mode"],
                item["total"],
                f"{item['accuracy']:.1f}%",
            ]
            for c, value in enumerate(values):
                self.chart.setItem(r, c, SmartTableItem(value))

    def export_report_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出学习记录", str(self.base_dir / "学习记录导出.csv"), "CSV Files (*.csv)")
        if not path:
            return
        try:
            rows = self.store.tests(0)
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["时间", "模式", "题数", "正确数", "正确率"])
                for item in rows:
                    writer.writerow(
                        [
                            datetime.fromtimestamp(item["created_at"]).strftime("%Y-%m-%d %H:%M"),
                            item["mode"],
                            item["total"],
                            item["correct"],
                            f"{item['accuracy']:.1f}%",
                        ]
                    )
            self.toast.show_message("学习记录已导出。")
        except Exception as exc:
            self.toast.show_message(f"导出没有成功：{exc}", 2600)

    def open_report_action(self):
        target = getattr(self, "report_action_target", "dashboard")
        self.nav.select(target)

    def set_feedback(self, title_label: QLabel, body_label: QLabel, kind: str, title: str, body: str):
        palette = {
            "success": ("#2F7D57", "rgba(95, 186, 125, 0.14)", "rgba(95, 186, 125, 0.28)"),
            "warning": ("#9B785D", "rgba(155, 120, 93, 0.14)", "rgba(155, 120, 93, 0.24)"),
            "danger": ("#A65252", "rgba(182, 116, 116, 0.14)", "rgba(182, 116, 116, 0.26)"),
            "info": ("#4E728C", "rgba(126, 152, 168, 0.14)", "rgba(126, 152, 168, 0.24)"),
        }
        color, bg, border = palette.get(kind, palette["info"])
        title_label.setText(title)
        title_label.setStyleSheet(
            f"font-size:19px;font-weight:900;color:{color};"
            f"background:{bg};border:1px solid {border};border-radius:12px;padding:10px 14px;"
        )
        body_label.setText(body)
        body_label.setStyleSheet("font-size:17px;line-height:1.75;padding:12px 2px;")

    def show_continue_action(self, layout, callback, text: str):
        self.clear_layout(layout)
        btn = RippleButton(text)
        btn.setProperty("primary", True)
        btn.setMinimumHeight(54)
        btn.clicked.connect(callback)
        layout.addWidget(btn, 0, 0, 1, 2)

    def refresh_dashboard_numbers(self):
        if hasattr(self, "stat_vocab"):
            counts = [len(self.store.vocab()), len(self.store.due_reviews()), len(self.store.mistakes()), self.streak]
            for card, value in zip([self.stat_vocab, self.stat_due, self.stat_mistake, self.stat_streak], counts):
                label = next((w for w in card.findChildren(AnimatedNumberLabel)), None)
                if label:
                    label.set_value(value)
        self.refresh_light_state()

    def refresh_text_if_needed(self):
        if hasattr(self, "focus_table"):
            self.render_text_tables()
            self.refresh_furigana()

    def make_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(40)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setSortingEnabled(True)
        return table

    def fill_table(self, table: QTableWidget, rows: list[list]):
        table.setSortingEnabled(False)
        table.clearContents()
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = SmartTableItem(value)
                table.setItem(r, c, item)
        table.setSortingEnabled(True)

    def clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def auto_backup_if_needed(self):
        try:
            target = self.store.auto_backup_if_needed()
            if target:
                logging.info("Auto backup created: %s", target)
        except Exception:
            logging.exception("Auto backup failed")

    def toggle_focus_mode(self):
        enabled = self.store.setting("focus_mode", "0") != "1"
        self.store.set_setting("focus_mode", "1" if enabled else "0")
        self.restore_focus_mode()
        if enabled:
            self.toast.show_message("已进入专注学习：侧栏会收起，学习时只保留更核心的内容。")
        else:
            self.toast.show_message("已退出专注学习，完整信息已经恢复。")

    def restore_focus_mode(self):
        enabled = self.store.setting("focus_mode", "0") == "1"
        if hasattr(self, "nav"):
            self.nav.rhythm.setVisible(not enabled and not self.nav.collapsed)
            if enabled and not self.nav.collapsed:
                self.nav.set_collapsed(True)
                self.store.set_setting("sidebar_collapsed", "1")
                self.update_sidebar_button()
        if hasattr(self, "focus_mode_btn"):
            self.focus_mode_btn.setText("退出专注学习" if enabled else "开启专注学习")
        for widget in (getattr(self, "report_card", None), getattr(self, "distribution_card", None), getattr(self, "trend_card", None)):
            if widget:
                widget.setVisible(not enabled)

    def update_sidebar_button(self):
        collapsed = getattr(self, "nav", None).collapsed if hasattr(self, "nav") else False
        self.sidebar_btn.setText("展开侧栏" if collapsed else "收起侧栏")

    def toggle_sidebar(self):
        collapsed = self.nav.toggle_collapsed()
        self.store.set_setting("sidebar_collapsed", "1" if collapsed else "0")
        if self.store.setting("focus_mode", "0") == "1" and not collapsed:
            self.store.set_setting("focus_mode", "0")
            for widget in (getattr(self, "report_card", None), getattr(self, "distribution_card", None), getattr(self, "trend_card", None)):
                if widget:
                    widget.setVisible(True)
            if hasattr(self, "focus_mode_btn"):
                self.focus_mode_btn.setText("开启专注学习")
        self.update_sidebar_button()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "loading"):
            self.loading.setGeometry(self.rect())

    def eventFilter(self, obj, event):
        if obj is self.topbar or obj.parent() is self.topbar:
            if event.type() == event.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            elif event.type() == event.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton and not self.drag_pos.isNull():
                self.move(event.globalPosition().toPoint() - self.drag_pos)
                return True
            elif event.type() == event.Type.MouseButtonRelease:
                self.drag_pos = QPoint()
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self.save_window_geometry()
        if hasattr(self, "text_editor"):
            self.autosave_text()
        super().closeEvent(event)
