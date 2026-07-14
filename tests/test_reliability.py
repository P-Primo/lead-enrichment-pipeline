"""Unit tests for the reliability primitives.

Run: python -m unittest discover -s tests
No third-party test runner required.
"""
import unittest

from src.services.reliability import (
    DeadLetterQueue,
    DedupRegistry,
    PermanentError,
    QuotaExceededError,
    QuotaGate,
    RateLimiter,
    TransientError,
    with_retry,
)

NO_SLEEP = lambda _delay: None


class TestWithRetry(unittest.TestCase):
    def test_succeeds_first_try(self):
        calls = []
        result = with_retry(lambda a: calls.append(a) or "ok", sleeper=NO_SLEEP)
        self.assertEqual(result, "ok")
        self.assertEqual(calls, [1])

    def test_recovers_after_transient(self):
        def fn(attempt):
            if attempt < 3:
                raise TransientError("flaky")
            return "recovered"
        result = with_retry(fn, attempts=3, sleeper=NO_SLEEP)
        self.assertEqual(result, "recovered")

    def test_exhausts_and_raises(self):
        def fn(_attempt):
            raise TransientError("always down")
        with self.assertRaises(TransientError):
            with_retry(fn, attempts=3, sleeper=NO_SLEEP)

    def test_permanent_error_not_retried(self):
        calls = []
        def fn(attempt):
            calls.append(attempt)
            raise PermanentError("no data")
        with self.assertRaises(PermanentError):
            with_retry(fn, attempts=3, retry_on=(TransientError,), sleeper=NO_SLEEP)
        self.assertEqual(calls, [1])  # tried exactly once


class TestQuotaGate(unittest.TestCase):
    def test_charges_until_empty(self):
        gate = QuotaGate("test", remaining=2, unit_cost_usd=0.5)
        gate.charge()
        gate.charge()
        self.assertFalse(gate.can_afford())
        with self.assertRaises(QuotaExceededError):
            gate.charge()
        self.assertEqual(gate.spend_usd, 1.0)


class TestDedupRegistry(unittest.TestCase):
    def test_detects_and_records(self):
        reg = DedupRegistry(seed_keys=["seen.com"])
        self.assertTrue(reg.is_duplicate("seen.com"))
        self.assertFalse(reg.is_duplicate("fresh.com"))
        reg.add("fresh.com")
        self.assertTrue(reg.is_duplicate("fresh.com"))


class TestRateLimiter(unittest.TestCase):
    def test_caps_actions(self):
        limiter = RateLimiter(max_actions=2)
        self.assertTrue(limiter.allow())
        self.assertTrue(limiter.allow())
        self.assertFalse(limiter.allow())
        self.assertEqual(limiter.remaining, 0)


class TestDeadLetterQueue(unittest.TestCase):
    def test_collects_entries(self):
        dlq = DeadLetterQueue()
        dlq.add("L1", "enrich", "no_data", "detail")
        self.assertEqual(len(dlq), 1)
        self.assertEqual(dlq.entries[0].reason, "no_data")


if __name__ == "__main__":
    unittest.main()
