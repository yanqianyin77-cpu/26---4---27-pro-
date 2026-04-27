from __future__ import annotations

# noinspection PyUnresolvedReferences
from PySide6.QtCore import QPoint, QThread, Qt, QTimer, Signal, QObject
# noinspection PyUnresolvedReferences
from PySide6.QtGui import QColor, QPainter
# noinspection PyUnresolvedReferences
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.config import SPLASH_TIMEOUT_MS
from app.core.engine import StudyEngine
from app.core.store import DBStore


class InitWorker(QObject):
    progress = Signal(float)
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(self, base_dir, data_dir):
        super().__init__()
        self.base_dir = base_dir
        self.data_dir = data_dir

    def run(self):
        try:
            self.progress.emit(0.15)
            store = DBStore(self.base_dir, self.data_dir)
            self.progress.emit(0.62)
            engine = StudyEngine()
            self.progress.emit(1.0)
            self.finished.emit(store, engine)
        except Exception as exc:
            self.failed.emit(str(exc))


class SplashScreen(QWidget):
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(self, base_dir, data_dir) -> None:
        super().__init__()
        self.base_dir = base_dir
        self.data_dir = data_dir
        self._progress = 0.0
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(500, 340)

        self.logo = QLabel("言")
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo.setStyleSheet(
            "font-size:42px;font-weight:900;color:white;"
            "background:#9B785D;border-radius:44px;min-width:88px;min-height:88px;"
        )
        self.title = QLabel("Kotoba Note")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet("font-size:30px;font-weight:800;color:#33424B;letter-spacing:1px;")
        self.subtitle = QLabel("言 葉 の 手 帳")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setStyleSheet("color:#6E7C84;letter-spacing:5px;")
        self.quote = QLabel("正在准备你的学习手帐…")
        self.quote.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quote.setStyleSheet("color:#9B785D;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 54, 0, 48)
        layout.setSpacing(8)
        layout.addWidget(self.logo, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addStretch()
        layout.addWidget(self.quote)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(
            lambda: self.failed.emit("启动超时，请检查数据库或依赖是否正常。")
        )

    def start(self) -> None:
        self.setWindowOpacity(0.86)
        self.show()
        self.timer.start(24)
        self.timeout_timer.start(SPLASH_TIMEOUT_MS)
        self.thread = QThread(self)
        self.worker = InitWorker(self.base_dir, self.data_dir)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.set_progress)
        self.worker.finished.connect(self._finished)
        self.worker.failed.connect(self._failed)
        self.thread.start()

    def set_progress(self, value: float) -> None:
        self._progress = value
        if value < 0.3:
            self.quote.setText("正在读取数据库…")
        elif value < 0.8:
            self.quote.setText("正在预热分词器…")
        else:
            self.quote.setText("正在打开主界面…")
        self.update()

    def _finished(self, store, engine) -> None:
        self.timeout_timer.stop()
        self.thread.quit()
        self.thread.wait(1200)
        self.finished.emit(store, engine)

    def _failed(self, message: str) -> None:
        self.timeout_timer.stop()
        self.thread.quit()
        self.thread.wait(1200)
        self.failed.emit(message)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(250, 247, 241, 232))
        painter.setPen(QColor(255, 255, 255, 128))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 24, 24)
        x0, x1, y = 100, 400, 270
        painter.setPen(QColor(126, 152, 168, 75))
        painter.drawLine(x0, y, x1, y)
        dot_x = x0 + int((x1 - x0) * self._progress)
        painter.setBrush(QColor(217, 197, 166))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(dot_x, y), 5, 5)
