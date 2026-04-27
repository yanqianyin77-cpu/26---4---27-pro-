from __future__ import annotations

import csv
import json
import logging
import shutil
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import RLock


DEFAULT_REVIEW_STAGES = [10, 1440, 2880, 10080, 43200]

SAMPLE_TEXT = (
    "私は毎朝、近くの公園を散歩します。春になると桜が咲いて、"
    "町全体がやさしい色に包まれます。新しい言葉を少しずつ覚えることは、"
    "小さな道を毎日歩くことに似ています。"
)

SAMPLE_WORDS = [
    ("散歩", "散步", "日常,N5"),
    ("公園", "公园", "日常,N5"),
    ("桜", "樱花", "季节,N5"),
    ("覚える", "记住,掌握", "学习,动词"),
    ("言葉", "语言,词语", "学习,N5"),
]

SAMPLE_DICT = {
    "私": "我",
    "毎朝": "每天早上",
    "近く": "附近",
    "公園": "公园",
    "散歩": "散步",
    "春": "春天",
    "桜": "樱花",
    "咲く": "开花",
    "町": "城镇",
    "全体": "整体",
    "色": "颜色",
    "包む": "包围",
    "新しい": "新的",
    "言葉": "语言,词语",
    "少し": "一点",
    "覚える": "记住,掌握",
    "小さな": "小的",
    "道": "道路",
    "毎日": "每天",
    "歩く": "走",
    "似る": "相似",
}

BUILTIN_DICT = {
    "朝": "早晨",
    "春の朝": "春天的早晨",
    "花びら": "花瓣",
    "静か": "安静,宁静",
    "風": "风",
    "乗る": "乘,借助,附着",
    "流れる": "流动,流淌",
    "ベンチ": "长椅",
    "座る": "坐",
    "昨日": "昨天",
    "単語": "单词",
    "復習": "复习",
    "難しい": "困难的",
    "続ける": "继续",
    "自然": "自然,自然而然",
    "身につく": "掌握,学到手",
    "身に付く": "掌握,学到手",
    "きっと": "一定",
    "少しずつ": "一点一点地",
    "毎日": "每天",
    "散歩する": "散步",
    "公園": "公园",
    "桜": "樱花",
    "花": "花",
    "言う": "说",
    "話す": "说,讲话",
    "聞く": "听,询问",
    "見る": "看",
    "読む": "读",
    "書く": "写",
    "食べる": "吃",
    "飲む": "喝",
    "行く": "去",
    "来る": "来",
    "帰る": "回去",
    "会う": "见面",
    "使う": "使用",
    "作る": "制作",
    "始める": "开始",
    "終わる": "结束",
    "開ける": "打开",
    "閉める": "关闭",
    "入る": "进入",
    "出る": "出去,出现",
    "教える": "教,告诉",
    "習う": "学习",
    "勉強": "学习",
    "覚える": "记住,掌握",
    "忘れる": "忘记",
    "大切": "重要,珍贵",
    "必要": "必要",
    "簡単": "简单",
    "有名": "有名",
    "好き": "喜欢",
    "嫌い": "讨厌",
    "楽しい": "开心的",
    "嬉しい": "高兴的",
    "悲しい": "悲伤的",
    "新しい": "新的",
    "古い": "旧的",
    "高い": "高的,贵的",
    "安い": "便宜的",
    "多い": "多的",
    "少ない": "少的",
    "時間": "时间",
    "今日": "今天",
    "明日": "明天",
    "昨日": "昨天",
    "今週": "这周",
    "来週": "下周",
}


class DBStore:
    def __init__(self, base_dir: Path, data_dir: Path | None = None) -> None:
        self.base_dir = Path(base_dir)
        self.data_dir = Path(data_dir) if data_dir else (self.base_dir / "data")
        self._lock = RLock()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir = self.data_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "kotoba_note.db"
        self.init_db()
        self.migrate_legacy_once()
        self.seed_sample_once()
        self.ensure_builtin_dictionary()

    def connect(self) -> sqlite3.Connection:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def tx(self):
        with self._lock:
            conn = self.connect()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                logging.exception("Database transaction failed")
                raise
            finally:
                conn.close()

    def init_db(self) -> None:
        with self.tx() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS system_dict (
                    word TEXT PRIMARY KEY,
                    meaning TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS text_cache (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    content TEXT NOT NULL DEFAULT '',
                    updated_at REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS vocab (
                    word TEXT PRIMARY KEY,
                    meaning TEXT NOT NULL,
                    reading TEXT DEFAULT '',
                    base_form TEXT DEFAULT '',
                    pos TEXT DEFAULT '',
                    tags TEXT DEFAULT '',
                    example TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    priority INTEGER NOT NULL DEFAULT 1,
                    polite_form TEXT DEFAULT '',
                    te_form TEXT DEFAULT '',
                    ta_form TEXT DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review (
                    word TEXT PRIMARY KEY,
                    last_review_at REAL NOT NULL DEFAULT 0,
                    due_at REAL NOT NULL DEFAULT 0,
                    review_count INTEGER NOT NULL DEFAULT 0,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    stage_index INTEGER NOT NULL DEFAULT 0,
                    streak INTEGER NOT NULL DEFAULT 0,
                    wrong_streak INTEGER NOT NULL DEFAULT 0,
                    mastered INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(word) REFERENCES vocab(word) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS mistake (
                    word TEXT PRIMARY KEY,
                    meaning TEXT NOT NULL,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    last_wrong_at REAL NOT NULL DEFAULT 0,
                    FOREIGN KEY(word) REFERENCES vocab(word) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS trash_word (
                    word TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    deleted_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS test_record (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    total INTEGER NOT NULL,
                    correct INTEGER NOT NULL,
                    accuracy REAL NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'test'
                );
                CREATE TABLE IF NOT EXISTS checkin (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    last_date TEXT NOT NULL DEFAULT '',
                    streak INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_vocab_tags ON vocab(tags);
                CREATE INDEX IF NOT EXISTS idx_vocab_pos ON vocab(pos);
                CREATE INDEX IF NOT EXISTS idx_review_due ON review(due_at, mastered);
                CREATE INDEX IF NOT EXISTS idx_mistake_count ON mistake(wrong_count);
                INSERT OR IGNORE INTO text_cache(id, content, updated_at) VALUES(1, '', 0);
                INSERT OR IGNORE INTO checkin(id, last_date, streak) VALUES(1, '', 0);
                """
            )
        defaults = {
            "theme": "light",
            "furigana": "0",
            "daily_review_limit": "15",
            "daily_new_limit": "5",
            "review_stages": ",".join(map(str, DEFAULT_REVIEW_STAGES)),
            "legacy_migrated": "0",
            "sample_seeded": "0",
            "window_geometry": "",
            "first_run_done": "0",
        }
        with self.tx() as conn:
            for key, value in defaults.items():
                conn.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, value))

    def setting(self, key: str, default: str = "") -> str:
        try:
            with self._lock:
                with self.connect() as conn:
                    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default
        except Exception:
            logging.exception("Failed to read setting: %s", key)
            return default

    def set_setting(self, key: str, value: str) -> None:
        with self.tx() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )

    def review_stages(self) -> list[int]:
        raw = self.setting("review_stages", ",".join(map(str, DEFAULT_REVIEW_STAGES)))
        try:
            return [int(x.strip()) for x in raw.split(",") if x.strip()] or DEFAULT_REVIEW_STAGES[:]
        except ValueError:
            return DEFAULT_REVIEW_STAGES[:]

    def seed_sample_once(self) -> None:
        if self.setting("sample_seeded", "0") == "1":
            return
        try:
            if not self.text():
                self.save_text(SAMPLE_TEXT)
            with self.tx() as conn:
                for word, meaning in SAMPLE_DICT.items():
                    conn.execute("INSERT OR IGNORE INTO system_dict(word, meaning) VALUES(?, ?)", (word, meaning))
            if not self.vocab():
                for word, meaning, tags in SAMPLE_WORDS:
                    self.save_word({"word": word, "meaning": meaning, "tags": tags, "priority": 1})
            self.set_setting("sample_seeded", "1")
            logging.info("Sample data seeded")
        except Exception:
            logging.exception("Failed to seed sample data")

    def ensure_builtin_dictionary(self) -> None:
        version = "2"
        if self.setting("builtin_dict_version", "0") == version:
            return
        try:
            with self.tx() as conn:
                for word, meaning in {**SAMPLE_DICT, **BUILTIN_DICT}.items():
                    conn.execute("INSERT OR IGNORE INTO system_dict(word, meaning) VALUES(?, ?)", (word, meaning))
                conn.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ("builtin_dict_version", version),
                )
            logging.info("Builtin dictionary ensured")
        except Exception:
            logging.exception("Failed to ensure builtin dictionary")

    def migrate_legacy_once(self) -> None:
        if self.setting("legacy_migrated", "0") == "1":
            return
        legacy_base = self.base_dir.parent
        try:
            files = {
                "dict.txt": self._import_legacy_dict,
                "words.txt": self._import_legacy_vocab,
                "review_record.txt": self._import_legacy_reviews,
                "test_records.txt": self._import_legacy_tests,
                "last_text.txt": self._import_legacy_text,
                "mistakes.json": self._import_legacy_mistakes,
                "checkin.txt": self._import_legacy_checkin,
            }
            for name, loader in files.items():
                path = legacy_base / name
                if path.exists():
                    loader(path)
                    bak = path.with_suffix(path.suffix + ".bak")
                    shutil.copy2(path, bak)
            self.set_setting("legacy_migrated", "1")
        except Exception:
            logging.exception("Legacy data migration failed")

    def _import_legacy_dict(self, path: Path) -> None:
        with path.open(encoding="utf-8") as fh, self.tx() as conn:
            for line in fh:
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    conn.execute("INSERT OR IGNORE INTO system_dict(word, meaning) VALUES(?, ?)", tuple(parts))

    def _import_legacy_vocab(self, path: Path) -> None:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    self.save_word({"word": parts[0], "meaning": parts[1]})

    def _import_legacy_reviews(self, path: Path) -> None:
        with path.open(encoding="utf-8") as fh, self.tx() as conn:
            for line in fh:
                parts = line.strip().split()
                if len(parts) != 5:
                    continue
                word, last_ts, count, stage_idx, mastered = parts
                conn.execute(
                    """
                    INSERT INTO review(word, last_review_at, due_at, review_count, correct_count, wrong_count, stage_index, mastered)
                    VALUES(?, ?, ?, ?, 0, 0, ?, ?)
                    ON CONFLICT(word) DO UPDATE SET
                        last_review_at=excluded.last_review_at,
                        due_at=excluded.due_at,
                        review_count=excluded.review_count,
                        stage_index=excluded.stage_index,
                        mastered=excluded.mastered
                    """,
                    (
                        word,
                        float(last_ts),
                        float(last_ts),
                        int(count),
                        int(stage_idx),
                        1 if mastered == "True" else 0,
                    ),
                )

    def _import_legacy_tests(self, path: Path) -> None:
        with path.open(encoding="utf-8") as fh, self.tx() as conn:
            for line in fh:
                parts = line.strip().split(",")
                if len(parts) == 4:
                    ts, total, correct, acc = parts
                    conn.execute(
                        "INSERT INTO test_record(created_at, total, correct, accuracy, mode) VALUES(?, ?, ?, ?, 'test')",
                        (float(ts), int(total), int(correct), float(acc)),
                    )

    def _import_legacy_text(self, path: Path) -> None:
        self.save_text(path.read_text(encoding="utf-8"))

    def _import_legacy_mistakes(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        with self.tx() as conn:
            for row in data if isinstance(data, list) else []:
                word = row.get("word", "").strip()
                meaning = row.get("meaning", "").strip()
                if word and meaning:
                    conn.execute(
                        """
                        INSERT INTO mistake(word, meaning, wrong_count, last_wrong_at)
                        VALUES(?, ?, ?, ?)
                        ON CONFLICT(word) DO UPDATE SET
                            meaning=excluded.meaning,
                            wrong_count=excluded.wrong_count,
                            last_wrong_at=excluded.last_wrong_at
                        """,
                        (
                            word,
                            meaning,
                            int(row.get("wrong_count", 1)),
                            float(row.get("last_wrong_at", time.time())),
                        ),
                    )

    def _import_legacy_checkin(self, path: Path) -> None:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        last_date = lines[0] if lines else ""
        streak = int(lines[1]) if len(lines) > 1 else 0
        self.save_checkin(last_date, streak)

    def system_dict(self) -> dict[str, str]:
        try:
            with self._lock:
                with self.connect() as conn:
                    rows = conn.execute("SELECT word, meaning FROM system_dict ORDER BY word").fetchall()
            return {row["word"]: row["meaning"] for row in rows}
        except Exception:
            logging.exception("Failed to load system dictionary")
            return {}

    def resolve_meaning(self, word: str, base_form: str = "", reading: str = "", pos: str = "") -> str | None:
        candidates = []
        for item in (word.strip(), base_form.strip()):
            if item and item not in candidates:
                candidates.append(item)
        try:
            with self._lock:
                with self.connect() as conn:
                    for candidate in candidates:
                        row = conn.execute(
                            "SELECT meaning FROM vocab WHERE word=? AND meaning IS NOT NULL AND meaning<>'' AND meaning<>'待补充' LIMIT 1",
                            (candidate,),
                        ).fetchone()
                        if row:
                            return row["meaning"]
                    for candidate in candidates:
                        row = conn.execute("SELECT meaning FROM system_dict WHERE word=? LIMIT 1", (candidate,)).fetchone()
                        if row:
                            return row["meaning"]
                    if reading:
                        row = conn.execute(
                            "SELECT meaning FROM vocab WHERE reading=? AND meaning IS NOT NULL AND meaning<>'' AND meaning<>'待补充' LIMIT 1",
                            (reading,),
                        ).fetchone()
                        if row:
                            return row["meaning"]
        except Exception:
            logging.exception("Failed to resolve meaning for %s", word)
        for candidate in candidates:
            if candidate in BUILTIN_DICT:
                return BUILTIN_DICT[candidate]
        return None

    def text(self) -> str:
        with self._lock:
            with self.connect() as conn:
                row = conn.execute("SELECT content FROM text_cache WHERE id=1").fetchone()
        return row["content"] if row else ""

    def save_text(self, content: str) -> None:
        with self.tx() as conn:
            conn.execute(
                "UPDATE text_cache SET content=?, updated_at=? WHERE id=1",
                (content, time.time()),
            )

    def vocab(self, filters: dict | None = None, order: str = "created_at DESC", limit: int | None = None) -> list[dict]:
        sql = """
            SELECT v.*, r.review_count, r.correct_count, r.wrong_count, r.stage_index, r.mastered, r.due_at, r.last_review_at
            FROM vocab v
            LEFT JOIN review r ON r.word = v.word
        """
        params: list = []
        where: list[str] = []
        if filters:
            if filters.get("tag"):
                where.append("v.tags LIKE ?")
                params.append(f"%{filters['tag']}%")
            if filters.get("keyword"):
                where.append("(v.word LIKE ? OR v.meaning LIKE ? OR v.reading LIKE ?)")
                key = f"%{filters['keyword']}%"
                params.extend([key, key, key])
            if filters.get("pos"):
                where.append("v.pos = ?")
                params.append(filters["pos"])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {order}"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self._lock:
            with self.connect() as conn:
                rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_word(self, word: str) -> dict | None:
        with self._lock:
            with self.connect() as conn:
                row = conn.execute(
                    """
                    SELECT v.*, r.review_count, r.correct_count, r.wrong_count, r.stage_index, r.mastered, r.due_at, r.last_review_at
                    FROM vocab v
                    LEFT JOIN review r ON r.word = v.word
                    WHERE v.word=?
                    """,
                    (word,),
                ).fetchone()
        return dict(row) if row else None

    def save_word(self, data: dict) -> None:
        now = time.time()
        word = data["word"].strip()
        if not word:
            raise ValueError("单词不能为空")
        meaning = (data.get("meaning") or "").strip() or "待补充"
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO vocab(
                    word, meaning, reading, base_form, pos, tags, example, notes, priority,
                    polite_form, te_form, ta_form, created_at, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(word) DO UPDATE SET
                    meaning=excluded.meaning,
                    reading=excluded.reading,
                    base_form=excluded.base_form,
                    pos=excluded.pos,
                    tags=excluded.tags,
                    example=excluded.example,
                    notes=excluded.notes,
                    priority=excluded.priority,
                    polite_form=excluded.polite_form,
                    te_form=excluded.te_form,
                    ta_form=excluded.ta_form,
                    updated_at=excluded.updated_at
                """,
                (
                    word,
                    meaning,
                    data.get("reading", ""),
                    data.get("base_form", word),
                    data.get("pos", ""),
                    data.get("tags", ""),
                    data.get("example", ""),
                    data.get("notes", ""),
                    int(data.get("priority") or 1),
                    data.get("polite_form", ""),
                    data.get("te_form", ""),
                    data.get("ta_form", ""),
                    float(data.get("created_at") or now),
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO review(word, last_review_at, due_at, review_count, correct_count, wrong_count, stage_index, streak, wrong_streak, mastered)
                VALUES(?, 0, 0, 0, 0, 0, 0, 0, 0, 0)
                ON CONFLICT(word) DO NOTHING
                """,
                (word,),
            )

    def delete_words(self, words: list[str]) -> None:
        if not words:
            return
        with self.tx() as conn:
            for word in words:
                row = conn.execute(
                    """
                    SELECT v.*, r.review_count, r.correct_count, r.wrong_count, r.stage_index, r.mastered, r.due_at, r.last_review_at
                    FROM vocab v
                    LEFT JOIN review r ON r.word = v.word
                    WHERE v.word=?
                    """,
                    (word,),
                ).fetchone()
                if row:
                    conn.execute(
                        """
                        INSERT INTO trash_word(word, payload, deleted_at)
                        VALUES(?, ?, ?)
                        ON CONFLICT(word) DO UPDATE SET payload=excluded.payload, deleted_at=excluded.deleted_at
                        """,
                        (word, json.dumps(dict(row), ensure_ascii=False), time.time()),
                    )
                conn.execute("DELETE FROM vocab WHERE word=?", (word,))

    def trash_items(self) -> list[dict]:
        with self._lock:
            with self.connect() as conn:
                rows = conn.execute("SELECT word, payload, deleted_at FROM trash_word ORDER BY deleted_at DESC").fetchall()
        items = []
        for row in rows:
            payload = json.loads(row["payload"])
            payload["deleted_at"] = row["deleted_at"]
            items.append(payload)
        return items

    def restore_words(self, words: list[str]) -> int:
        restored = 0
        with self.tx() as conn:
            for word in words:
                row = conn.execute("SELECT payload FROM trash_word WHERE word=?", (word,)).fetchone()
                if not row:
                    continue
                payload = json.loads(row["payload"])
                self.save_word(payload)
                conn.execute("DELETE FROM trash_word WHERE word=?", (word,))
                restored += 1
        return restored

    def set_priority(self, words: list[str], priority: int) -> None:
        if not words:
            return
        with self.tx() as conn:
            conn.executemany("UPDATE vocab SET priority=?, updated_at=? WHERE word=?", [(priority, time.time(), word) for word in words])

    def set_mastered(self, words: list[str], mastered: bool) -> None:
        if not words:
            return
        with self.tx() as conn:
            if mastered:
                conn.executemany(
                    "UPDATE review SET mastered=1, due_at=? WHERE word=?",
                    [(time.time() + 365 * 24 * 3600, word) for word in words],
                )
            else:
                conn.executemany(
                    "UPDATE review SET mastered=0, due_at=0 WHERE word=?",
                    [(word,) for word in words],
                )

    def merge_tags(self, words: list[str], tags_text: str, replace: bool = False) -> int:
        if not words:
            return 0
        tags = [tag.strip() for tag in tags_text.replace("，", ",").split(",") if tag.strip()]
        updated = 0
        with self.tx() as conn:
            for word in words:
                row = conn.execute("SELECT tags FROM vocab WHERE word=?", (word,)).fetchone()
                if not row:
                    continue
                if replace:
                    merged = tags
                else:
                    current = [tag.strip() for tag in (row["tags"] or "").replace("，", ",").split(",") if tag.strip()]
                    merged = []
                    for tag in current + tags:
                        if tag not in merged:
                            merged.append(tag)
                conn.execute("UPDATE vocab SET tags=?, updated_at=? WHERE word=?", (", ".join(merged), time.time(), word))
                updated += 1
        return updated

    def schedule_now(self, words: list[str]) -> None:
        if not words:
            return
        with self.tx() as conn:
            conn.executemany(
                "UPDATE review SET due_at=0, mastered=0 WHERE word=?",
                [(word,) for word in words],
            )

    def due_reviews(self, limit: int | None = None) -> list[dict]:
        sql = """
            SELECT v.word, v.meaning, v.reading, v.pos, v.priority, r.review_count, r.correct_count, r.wrong_count,
                   r.stage_index, r.mastered, r.due_at
            FROM review r
            JOIN vocab v ON v.word = r.word
            WHERE r.mastered = 0 AND (r.due_at <= ? OR r.review_count = 0)
            ORDER BY v.priority DESC, r.due_at ASC, v.updated_at DESC
        """
        params: list = [time.time()]
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self._lock:
            with self.connect() as conn:
                rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def apply_review(self, word: str, correct: bool) -> None:
        stages = self.review_stages()
        now = time.time()
        with self.tx() as conn:
            row = conn.execute("SELECT * FROM review WHERE word=?", (word,)).fetchone()
            if not row:
                return
            review_count = int(row["review_count"]) + 1
            correct_count = int(row["correct_count"]) + (1 if correct else 0)
            wrong_count = int(row["wrong_count"]) + (0 if correct else 1)
            stage_index = int(row["stage_index"])
            streak = int(row["streak"])
            wrong_streak = int(row["wrong_streak"])
            if correct:
                streak += 1
                wrong_streak = 0
                if streak >= 2 and stage_index < len(stages) - 1:
                    stage_index += 1
                due_at = now + stages[min(stage_index, len(stages) - 1)] * 60
                mastered = 1 if stage_index >= len(stages) - 1 and streak >= 2 else 0
            else:
                wrong_streak += 1
                streak = 0
                stage_index = max(0, stage_index - 1)
                due_at = now + stages[stage_index] * 60
                mastered = 0
            conn.execute(
                """
                UPDATE review
                SET last_review_at=?, due_at=?, review_count=?, correct_count=?, wrong_count=?,
                    stage_index=?, streak=?, wrong_streak=?, mastered=?
                WHERE word=?
                """,
                (now, due_at, review_count, correct_count, wrong_count, stage_index, streak, wrong_streak, mastered, word),
            )

    def mark_mistake(self, word: str, meaning: str, count: int = 1, last_wrong_at: float | None = None) -> None:
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO mistake(word, meaning, wrong_count, last_wrong_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(word) DO UPDATE SET
                    meaning=excluded.meaning,
                    wrong_count=mistake.wrong_count + excluded.wrong_count,
                    last_wrong_at=excluded.last_wrong_at
                """,
                (word, meaning, count, float(last_wrong_at or time.time())),
            )

    def resolve_mistake(self, word: str) -> None:
        with self.tx() as conn:
            row = conn.execute("SELECT wrong_count FROM mistake WHERE word=?", (word,)).fetchone()
            if not row:
                return
            next_count = int(row["wrong_count"]) - 1
            if next_count <= 0:
                conn.execute("DELETE FROM mistake WHERE word=?", (word,))
            else:
                conn.execute("UPDATE mistake SET wrong_count=? WHERE word=?", (next_count, word))

    def mistakes(self) -> list[dict]:
        with self._lock:
            with self.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT m.word, m.meaning, m.wrong_count, m.last_wrong_at, v.reading, v.pos, v.priority
                    FROM mistake m
                    LEFT JOIN vocab v ON v.word = m.word
                    ORDER BY m.wrong_count DESC, m.last_wrong_at DESC
                    """
                ).fetchall()
        return [dict(row) for row in rows]

    def save_test(self, total: int, correct: int, mode: str = "test") -> None:
        accuracy = (correct / total * 100) if total else 0.0
        with self.tx() as conn:
            conn.execute(
                "INSERT INTO test_record(created_at, total, correct, accuracy, mode) VALUES(?, ?, ?, ?, ?)",
                (time.time(), total, correct, accuracy, mode),
            )

    def tests(self, limit: int = 80) -> list[dict]:
        with self._lock:
            with self.connect() as conn:
                if limit and limit > 0:
                    rows = conn.execute(
                        "SELECT * FROM test_record ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM test_record ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def checkin(self) -> dict:
        with self._lock:
            with self.connect() as conn:
                row = conn.execute("SELECT last_date, streak FROM checkin WHERE id=1").fetchone()
        return {"last_date": row["last_date"], "streak": int(row["streak"])} if row else {"last_date": "", "streak": 0}

    def save_checkin(self, last_date: str, streak: int) -> None:
        with self.tx() as conn:
            conn.execute("UPDATE checkin SET last_date=?, streak=? WHERE id=1", (last_date, streak))

    def do_checkin(self) -> int:
        today = date.today().isoformat()
        info = self.checkin()
        if info["last_date"] == today:
            return info["streak"]
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        streak = info["streak"] + 1 if info["last_date"] == yesterday else 1
        self.save_checkin(today, streak)
        return streak

    def export_csv(self, path: Path) -> None:
        rows = self.vocab(order="created_at DESC")
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["单词", "释义", "读音", "原形", "词性", "标签", "例句", "备注"])
            for row in rows:
                writer.writerow([
                    row["word"],
                    row["meaning"],
                    row.get("reading", ""),
                    row.get("base_form", ""),
                    row.get("pos", ""),
                    row.get("tags", ""),
                    row.get("example", ""),
                    row.get("notes", ""),
                ])

    def backup(self, path: Path | None = None) -> Path:
        target = path or (self.backup_dir / f"kotoba_note_{datetime.now():%Y%m%d_%H%M%S}.db")
        with self._lock:
            with self.connect() as conn:
                backup_conn = sqlite3.connect(target)
                conn.backup(backup_conn)
                backup_conn.close()
        return target

    def auto_backup_if_needed(self) -> Path | None:
        last = self.setting("last_auto_backup", "")
        today = date.today().isoformat()
        if last == today:
            return None
        target = self.backup()
        self.set_setting("last_auto_backup", today)
        return target

    def restore(self, backup_path: Path) -> None:
        backup_path = Path(backup_path)
        if not backup_path.exists():
            raise FileNotFoundError("备份文件不存在")
        temp_path = self.data_dir / f"restore_{int(time.time())}.db"
        shutil.copy2(backup_path, temp_path)
        try:
            with sqlite3.connect(temp_path) as conn:
                conn.execute("SELECT 1 FROM settings LIMIT 1")
            shutil.copy2(temp_path, self.db_path)
        finally:
            temp_path.unlink(missing_ok=True)
