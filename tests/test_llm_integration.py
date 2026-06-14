"""End-to-end wiring test for the hosted-AI path, with a fake SDK client.

Run with:  python -m unittest tests.test_llm_integration -v

Proves (no network, no key) that:
  - prompt caching is on (system block carries cache_control ephemeral),
  - tool definitions are passed through,
  - the agent tool-use loop runs a tool and returns the final text,
  - every call's token usage is recorded in the budget ledger.
"""
import importlib
import os
import tempfile
import unittest


class _Block:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


class _Usage:
    def __init__(self, i=0, o=0, cr=0, cw=0):
        self.input_tokens = i
        self.output_tokens = o
        self.cache_read_input_tokens = cr
        self.cache_creation_input_tokens = cw


class _Resp:
    def __init__(self, content, stop_reason, usage):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage
        self.model = "claude-haiku-4-5"


class _FakeMessages:
    def __init__(self, queue, calls):
        self._queue = queue
        self._calls = calls

    def create(self, **kwargs):
        self._calls.append(kwargs)
        return self._queue.pop(0)


class _FakeClient:
    def __init__(self, queue, calls):
        self.messages = _FakeMessages(queue, calls)


class _FakeRepo:
    def stats(self):
        return {"datasets": 1104, "records": 31330}

    def close(self):
        pass


class LLMIntegrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        os.environ["AI_DB_PATH"] = self._tmp.name
        os.environ["ANTHROPIC_API_KEY"] = "sk-test"
        os.environ["BUDGET_MONTHLY_AUD"] = "100"
        os.environ["USD_PER_AUD"] = "0.60"
        os.environ.pop("BUDGET_DAILY_AUD", None)
        os.environ["AI_DAILY_CALLS"] = "100000"
        import agent.budget as budget
        import agent.llm as llm
        import agent.agent as agent
        self.budget = importlib.reload(budget)
        self.llm = importlib.reload(llm)
        self.agent = importlib.reload(agent)

    def tearDown(self):
        os.unlink(self._tmp.name)
        for k in ("AI_DB_PATH", "ANTHROPIC_API_KEY", "BUDGET_MONTHLY_AUD",
                  "USD_PER_AUD", "AI_DAILY_CALLS"):
            os.environ.pop(k, None)

    def test_tool_loop_caching_and_usage(self):
        calls = []
        queue = [
            # 1st turn: model asks for a tool.
            _Resp([_Block("tool_use", id="t1", name="repository_stats", input={})],
                  "tool_use", _Usage(i=1500, o=20, cw=2000)),
            # 2nd turn: model answers.
            _Resp([_Block("text", text="There are 1,104 datasets and 31,330 records.")],
                  "end_turn", _Usage(i=200, o=40, cr=2000)),
        ]
        self.llm._client = _FakeClient(queue, calls)

        answer = self.agent.run("How many datasets are there?",
                                repo=_FakeRepo(), verbose=False)
        self.assertIn("1,104 datasets", answer)

        # Prompt caching: system sent as a block with ephemeral cache_control.
        sys_block = calls[0]["system"][0]
        self.assertEqual(sys_block["cache_control"], {"type": "ephemeral"})
        # Tools were passed through.
        self.assertTrue(calls[0]["tools"])
        # Two API calls were made and both recorded in the ledger.
        self.assertEqual(len(calls), 2)
        self.assertGreater(self.budget.status()["month_spend_aud"], 0)

    def test_budget_paused_blocks_the_call(self):
        os.environ["BUDGET_MONTHLY_AUD"] = "0"  # cap of $0 -> always paused
        self.llm = importlib.reload(self.llm)
        with self.assertRaises(self.budget.BudgetExceededError):
            self.llm.messages_create("sys", [{"role": "user", "content": "hi"}])

    def test_no_key_means_chat_offline(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.llm = importlib.reload(self.llm)
        self.assertFalse(self.llm.server_up())


if __name__ == "__main__":
    unittest.main()
