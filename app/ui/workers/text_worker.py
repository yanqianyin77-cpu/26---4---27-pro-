from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot


class TextWorker(QObject):
    finished = Signal(list, str)

    def __init__(self, engine, text: str) -> None:
        super().__init__()
        self.engine = engine
        self.text = text

    @Slot()
    def run(self) -> None:
        try:
            words = self.engine.split_words(self.text)
            self.finished.emit(words, "")
        except Exception as exc:
            self.finished.emit([], str(exc))
