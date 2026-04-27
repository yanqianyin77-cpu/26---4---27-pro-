from __future__ import annotations

import logging
import random
import re
from collections import Counter
from datetime import date
from functools import lru_cache
from threading import RLock

from janome.tokenizer import Tokenizer


QUOTES = [
    ("千里の道も一歩から", "千里之行，始于足下"),
    ("失敗は成功のもと", "失败是成功之母"),
    ("継続は力なり", "坚持就是力量"),
    ("石の上にも三年", "功夫不负有心人"),
    ("努力に勝る天才なし", "没有比努力更厉害的天才"),
    ("苦あれば楽あり", "有苦才有乐"),
    ("時は金なり", "一寸光阴一寸金"),
    ("天は自ら助くる者を助く", "天助自助者"),
    ("七転び八起き", "百折不挠"),
    ("今日も一歩ずつ", "今天也一步一步来"),
]

SMALL_BUT_IMPORTANT = {"食", "見", "聞", "言", "行", "来", "木", "火", "水", "金", "土", "日", "月"}
PUNCT_KEEP = {"・", "〜", "～", "「", "」", "『", "』", "、", "。"}


class StudyEngine:
    def __init__(self) -> None:
        self._lock = RLock()
        try:
            self.tokenizer = Tokenizer()
        except Exception as exc:
            logging.exception("Janome initialization failed")
            raise RuntimeError(f"Janome 初始化失败：{exc}") from exc

    @staticmethod
    def daily_quote() -> tuple[str, str]:
        rng = random.Random(date.today().toordinal())
        return rng.choice(QUOTES)

    @staticmethod
    def katakana_to_hiragana(text: str) -> str:
        return "".join(chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in text)

    @staticmethod
    def normalize_text(text: str) -> str:
        return (
            text.strip()
            .replace("；", ";")
            .replace("，", ",")
            .replace("、", ",")
            .replace("：", ":")
            .replace("（", "(")
            .replace("）", ")")
            .replace("。", "")
            .replace("！", "")
            .replace("？", "")
            .replace(" ", "")
            .lower()
        )

    @staticmethod
    def looks_like_japanese(text: str) -> bool:
        return any(
            ("\u3040" <= ch <= "\u30ff") or ("\u4e00" <= ch <= "\u9fff")
            for ch in text
        )

    def split_words(self, text: str) -> list[str]:
        cleaned = text.strip()
        if not cleaned:
            return []
        if not self.looks_like_japanese(cleaned):
            return []
        if len(cleaned) > 20000:
            raise RuntimeError("课文太长了，建议分段分析，每次控制在 20000 字以内。")
        words: list[str] = []
        try:
            with self._lock:
                for token in self.tokenizer.tokenize(cleaned):
                    surface = token.surface.strip()
                    if not surface or surface in PUNCT_KEEP:
                        continue
                    pos = token.part_of_speech.split(",")[0]
                    if pos in {"助詞", "助動詞", "記号", "感動詞"}:
                        continue
                    base = token.base_form.strip() if token.base_form and token.base_form != "*" else surface
                    if len(base) <= 1 and base not in SMALL_BUT_IMPORTANT and pos not in {"名詞", "動詞"}:
                        continue
                    words.append(base)
        except Exception as exc:
            logging.exception("Text tokenization failed")
            raise RuntimeError(f"课文分析失败：{exc}") from exc
        return words

    def word_frequency(self, text: str, limit: int = 40) -> list[tuple[str, int]]:
        return Counter(self.split_words(text)).most_common(limit)

    @lru_cache(maxsize=4096)
    def get_word_detail(self, word: str) -> dict[str, str]:
        try:
            with self._lock:
                token = next(iter(self.tokenizer.tokenize(word)))
            reading = token.reading if token.reading and token.reading != "*" else "无"
            base_form = token.base_form if token.base_form and token.base_form != "*" else word
            pos = token.part_of_speech.split(",")[0] if token.part_of_speech else "无"
            return {"reading": self.katakana_to_hiragana(reading), "base_form": base_form, "pos": pos}
        except Exception:
            logging.exception("Failed to get word detail: %s", word)
            return {"reading": "-", "base_form": word, "pos": "-"}

    def annotate_text(self, text: str, mode: str = "off", known_words: set[str] | None = None) -> str:
        if mode == "off":
            return text
        annotated: list[str] = []
        try:
            with self._lock:
                for token in self.tokenizer.tokenize(text):
                    surface = token.surface
                    reading = token.reading if token.reading and token.reading != "*" else ""
                    needs_hint = mode == "all" or (mode == "new_only" and surface not in (known_words or set()))
                    if reading and needs_hint and any("\u4e00" <= ch <= "\u9fff" for ch in surface):
                        annotated.append(f"{surface}({self.katakana_to_hiragana(reading)})")
                    else:
                        annotated.append(surface)
        except Exception:
            logging.exception("Failed to annotate text")
            return text
        return "".join(annotated)

    def answer_matches(self, answer: str, meaning: str) -> str:
        ans = self.normalize_text(answer)
        targets = [chunk.strip() for chunk in re.split(r"[,/;|]", self.normalize_text(meaning)) if chunk.strip()]
        if not targets:
            targets = [self.normalize_text(meaning)]
        if ans in targets:
            return "exact"
        for target in targets:
            if ans and (ans in target or target in ans):
                return "close"
        if any(self._similar(ans, target) for target in targets):
            return "close"
        return "wrong"

    @staticmethod
    def _similar(a: str, b: str) -> bool:
        if not a or not b:
            return False
        if abs(len(a) - len(b)) > 1:
            return False
        diff = sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))
        return diff <= 1

    def build_choices(self, correct_meaning: str, all_meanings: list[str]) -> list[str]:
        def score(item: str) -> tuple[int, int]:
            overlap = len(set(item) & set(correct_meaning))
            return overlap, -abs(len(item) - len(correct_meaning))

        pool = [m for m in dict.fromkeys(all_meanings) if m and m != correct_meaning]
        pool.sort(key=score, reverse=True)
        choices = [correct_meaning] + pool[:3]
        while len(choices) < min(4, len(set(all_meanings))):
            extra = next((item for item in pool if item not in choices), None)
            if not extra:
                break
            choices.append(extra)
        random.shuffle(choices)
        return choices

    def infer_verb_forms(self, word: str, pos: str) -> dict[str, str]:
        if "動詞" not in pos and "动词" not in pos:
            return {"polite": "", "te": "", "ta": ""}
        if word.endswith("する"):
            return {"polite": word[:-2] + "します", "te": word[:-2] + "して", "ta": word[:-2] + "した"}
        if word in {"来る", "くる"}:
            return {"polite": "きます", "te": "きて", "ta": "きた"}
        if word == "行く":
            return {"polite": "行きます", "te": "行って", "ta": "行った"}
        if word.endswith("る"):
            stem = word[:-1]
            return {"polite": stem + "ます", "te": stem + "て", "ta": stem + "た"}
        if word.endswith(("う", "つ", "る")):
            stem = word[:-1]
            return {"polite": stem + "います", "te": stem + "って", "ta": stem + "った"}
        if word.endswith(("む", "ぶ", "ぬ")):
            stem = word[:-1]
            return {"polite": stem + "みます", "te": stem + "んで", "ta": stem + "んだ"}
        if word.endswith("く"):
            stem = word[:-1]
            return {"polite": stem + "きます", "te": stem + "いて", "ta": stem + "いた"}
        if word.endswith("ぐ"):
            stem = word[:-1]
            return {"polite": stem + "ぎます", "te": stem + "いで", "ta": stem + "いだ"}
        if word.endswith("す"):
            stem = word[:-1]
            return {"polite": stem + "します", "te": stem + "して", "ta": stem + "した"}
        return {"polite": "", "te": "", "ta": ""}
