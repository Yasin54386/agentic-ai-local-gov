"""Tests for the AI budget ledger — the hard spend ceiling.

Run with:  python -m unittest tests.test_budget -v
(no model or network needed — the ledger is pure SQLite + arithmetic).

The load-test guarantee from the Definition of Done lives here:
test_load_cannot_exceed_cap proves that repeatedly calling through the gate
cannot push spend past the monthly cap by more than a single call.
"""
import importlib
import os
import tempfile
import unittest


class BudgetTests(unittest.TestCase):
    def setUp(self):
        # Fresh ledger DB + known config per test.
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        os.environ["AI_DB_PATH"] = self._tmp.name
        os.environ["BUDGET_MONTHLY_AUD"] = "100"
        os.environ["USD_PER_AUD"] = "0.60"
        os.environ.pop("BUDGET_DAILY_AUD", None)
        os.environ["AI_DAILY_CALLS"] = "100000"  # high, so it isn't the binding cap
        import agent.budget as budget
        self.budget = importlib.reload(budget)

    def tearDown(self):
        os.unlink(self._tmp.name)
        for k in ("AI_DB_PATH", "BUDGET_MONTHLY_AUD", "USD_PER_AUD",
                  "BUDGET_DAILY_AUD", "AI_DAILY_CALLS"):
            os.environ.pop(k, None)

    def test_cost_math_haiku(self):
        # 1.5K fresh input + 2K cached read + 500 output on Haiku.
        c = self.budget.cost_usd("claude-haiku-4-5", 1500, 500, cache_read_tokens=2000)
        # 1500*1/1e6 + 2000*0.1/1e6 + 500*5/1e6 = 0.0015 + 0.0002 + 0.0025
        self.assertAlmostEqual(c, 0.0042, places=6)

    def test_unknown_model_priced_at_most_expensive(self):
        unknown = self.budget.cost_usd("some-future-model", 1000, 1000)
        haiku = self.budget.cost_usd("claude-haiku-4-5", 1000, 1000)
        self.assertGreaterEqual(unknown, haiku)

    def test_caps_scale_with_fx(self):
        self.assertAlmostEqual(self.budget.monthly_cap_usd(), 60.0)   # 100 AUD * 0.60
        self.assertAlmostEqual(self.budget.daily_cap_usd(), 2.0)      # 60 / 30

    def test_states_progress_ok_degraded_paused(self):
        os.environ["BUDGET_DAILY_AUD"] = "100000"  # isolate the monthly ceiling
        cap = self.budget.monthly_cap_usd()
        self.assertEqual(self.budget.status()["state"], "ok")
        # Push to ~85% of the monthly cap -> degraded (threshold 80%).
        self._spend_usd(cap * 0.85)
        self.assertEqual(self.budget.status()["state"], "degraded")
        # Push over 100% -> paused with reason "monthly".
        self._spend_usd(cap * 0.30)
        st = self.budget.status()
        self.assertEqual(st["state"], "paused")
        self.assertEqual(st["reason"], "monthly")
        with self.assertRaises(self.budget.BudgetExceededError):
            self.budget.check_allowed()

    def test_daily_subcap_pauses_before_monthly(self):
        os.environ["BUDGET_DAILY_AUD"] = "5"   # 5 AUD * 0.60 = 3 USD daily
        self._spend_usd(3.5)                    # over daily, far under monthly
        st = self.budget.status()
        self.assertEqual((st["state"], st["reason"]), ("paused", "daily"))

    def test_daily_call_ceiling(self):
        os.environ["AI_DAILY_CALLS"] = "3"
        for _ in range(3):
            self.budget.record("claude-haiku-4-5", 10, 10)
        st = self.budget.status()
        self.assertEqual((st["state"], st["reason"]), ("paused", "calls"))

    def test_load_cannot_exceed_cap(self):
        """DoD: a flood of calls through the gate can overshoot the cap by at
        most ONE call's cost, then halts — it cannot run spend away."""
        os.environ["BUDGET_DAILY_AUD"] = "100000"  # test the monthly ceiling itself
        os.environ["BUDGET_MONTHLY_AUD"] = "1"      # tiny cap -> same guarantee, fast
        cap = self.budget.monthly_cap_usd()
        per_call = self.budget.cost_usd("claude-haiku-4-5", 1500, 500, cache_read_tokens=2000)
        stopped = False
        for _ in range(100_000):            # "infinite" client load
            try:
                self.budget.check_allowed()  # the gate llm.messages_create runs
            except self.budget.BudgetExceededError:
                stopped = True
                break
            self.budget.record("claude-haiku-4-5", 1500, 500, cache_read_tokens=2000)
        self.assertTrue(stopped, "gate never tripped")
        spent = self.budget.monthly_cap_usd()  # cap; compute actual spend below
        actual = self.budget.status()["month_spend_aud"] * self.budget.usd_per_aud()
        self.assertLessEqual(actual, cap + per_call + 1e-9)

    # ── helper ────────────────────────────────────────────────────────────────
    def _spend_usd(self, usd_target: float):
        """Record synthetic output-only calls until ~usd_target is spent."""
        # 1 output token = 5/1e6 USD on Haiku; choose a chunk size.
        per = self.budget.cost_usd("claude-haiku-4-5", 0, 100_000)  # 0.5 USD
        n = max(1, int(usd_target / per))
        for _ in range(n):
            self.budget.record("claude-haiku-4-5", 0, 100_000)


if __name__ == "__main__":
    unittest.main()
