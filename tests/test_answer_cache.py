"""Tests for the repeat-answer cache — layer 2 of the routing pyramid.

Run with:  python -m unittest tests.test_answer_cache -v
"""
import importlib
import os
import tempfile
import unittest


class AnswerCacheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        os.environ["AI_DB_PATH"] = self._tmp.name
        import agent.answer_cache as ac
        self.ac = importlib.reload(ac)

    def tearDown(self):
        os.unlink(self._tmp.name)
        os.environ.pop("AI_DB_PATH", None)

    def test_normalize_is_case_and_punctuation_insensitive(self):
        a = self.ac.normalize("How much did KARAMA spend??")
        b = self.ac.normalize("  how much did karama spend  ")
        self.assertEqual(a, b)

    def test_put_then_get_round_trip(self):
        self.ac.put("How much did Karama spend?", "About $1.2M.")
        self.assertEqual(self.ac.get("how much did karama spend"), "About $1.2M.")

    def test_miss_returns_none(self):
        self.assertIsNone(self.ac.get("a question never stored"))

    def test_empty_inputs_are_ignored(self):
        self.ac.put("", "x")
        self.ac.put("q", "")
        self.assertIsNone(self.ac.get(""))
        self.assertIsNone(self.ac.get("q"))

    def test_live_questions_get_short_ttl(self):
        self.assertEqual(self.ac.ttl_for("what's the weather today"), self.ac.LIVE_TTL_S)
        self.assertEqual(self.ac.ttl_for("is there a flood risk now"), self.ac.LIVE_TTL_S)
        self.assertEqual(self.ac.ttl_for("how do I register a dog"), self.ac.STATIC_TTL_S)

    def test_expired_entry_is_not_served(self):
        self.ac.LIVE_TTL_S = -1   # force immediate expiry for live questions
        self.ac.put("weather today in Darwin", "Sunny.")
        self.assertIsNone(self.ac.get("weather today in darwin"))

    def test_hits_are_counted(self):
        self.ac.put("static fact about darwin", "It is hot.")
        self.ac.get("static fact about darwin")
        self.ac.get("STATIC fact about Darwin")
        self.assertEqual(self.ac.stats()["hits"], 2)


if __name__ == "__main__":
    unittest.main()
