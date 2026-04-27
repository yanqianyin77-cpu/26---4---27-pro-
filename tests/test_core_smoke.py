from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from app.core.engine import StudyEngine
from app.core.store import DBStore


class StudyEngineSmokeTests(unittest.TestCase):
    def setUp(self):
        self.engine = StudyEngine()

    def test_answer_matches_supports_exact_and_close(self):
        self.assertEqual(self.engine.answer_matches("樱花", "樱花"), "exact")
        self.assertEqual(self.engine.answer_matches("流动", "流动,流淌"), "exact")
        self.assertEqual(self.engine.answer_matches("流", "流动,流淌"), "close")

    def test_build_choices_keeps_correct_answer(self):
        choices = self.engine.build_choices("学习", ["学习", "散步", "樱花", "公园", "语言"])
        self.assertIn("学习", choices)
        self.assertGreaterEqual(len(choices), 2)


class DBStoreSmokeTests(unittest.TestCase):
    def setUp(self):
        self.base_dir = Path(__file__).resolve().parent / "_tmp_store_case"
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir, ignore_errors=True)
        self.store = DBStore(self.base_dir, data_dir=self.base_dir / "data")

    def tearDown(self):
        shutil.rmtree(self.base_dir, ignore_errors=True)

    def test_builtin_dictionary_can_resolve_common_word(self):
        meaning = self.store.resolve_meaning("流れる")
        self.assertTrue(meaning)
        self.assertIn("流", meaning)

    def test_review_stages_returns_default_sequence(self):
        stages = self.store.review_stages()
        self.assertIsInstance(stages, list)
        self.assertGreaterEqual(len(stages), 3)
        self.assertTrue(all(isinstance(item, int) for item in stages))


if __name__ == "__main__":
    unittest.main()
