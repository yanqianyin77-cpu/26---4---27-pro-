from dataclasses import dataclass, field


@dataclass
class VocabItem:
    word: str
    meaning: str
    reading: str = ""
    base_form: str = ""
    pos: str = ""
    tags: str = ""
    example: str = ""
    note: str = ""
    priority: int = 1
    polite_form: str = ""
    te_form: str = ""
    ta_form: str = ""


@dataclass
class ReviewItem:
    word: str
    meaning: str
    reading: str
    pos: str
    priority: int
    review_count: int
    stage_index: int
    due_at: float
    mastered: int


@dataclass
class TextAnalysisResult:
    words: list[str] = field(default_factory=list)
    focus_rows: list[tuple] = field(default_factory=list)
    freq_rows: list[tuple] = field(default_factory=list)
