from __future__ import annotations

# noinspection PyUnresolvedReferences
from PySide6.QtCore import QObject, Signal


class TextWorker(QObject):
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, engine, text: str):
        super().__init__()
        self.engine = engine
        self.text = text

    def run(self):
        try:
            self.finished.emit(self.engine.split_words(self.text))
        except Exception as exc:
            self.failed.emit(str(exc))
