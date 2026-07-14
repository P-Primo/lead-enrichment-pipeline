"""Reliability primitives — the core of this project.

These are the patterns that separate a demo script from something you'd
trust against paid third-party APIs in production:

* QuotaGate      -- never make a paid call you can't afford; fail safe.
* with_retry     -- retry transient failures with exponential backoff.
* DeadLetterQueue-- capture failed records with a reason instead of losing them.
* DedupRegistry  -- never process (or contact) the same entity twice.
* RateLimiter    -- respect a per-run send cap; defer the overflow.

Everything here is dependency-injectable (e.g. the sleeper in `with_retry`)
so the behaviour is unit-testable without real time or real network.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from typing import Callable, Iterable, List, Optional


# ---- Error taxonomy -------------------------------------------------------

class TransientError(Exception):
    """Temporary failure — safe to retry (timeout, 5xx, rate-limit)."""


class PermanentError(Exception):
    """Deterministic failure — retrying will not help (no data found, 4xx)."""


class QuotaExceededError(Exception):
    """A provider is out of credits. Stop; do not burn the record."""


# ---- Quota gating ---------------------------------------------------------

@dataclass
class QuotaGate:
    """Tracks remaining credits for a single paid provider.

    Check `can_afford()` BEFORE every call. This is the difference between
    "we stopped cleanly with 200 leads left to do tomorrow" and "we melted
    the monthly budget at 3am and corrupted half the run".
    """
    name: str
    remaining: int
    cost_per_call: int = 1
    unit_cost_usd: float = 0.0
    charged_calls: int = 0

    def can_afford(self) -> bool:
        return self.remaining >= self.cost_per_call

    def charge(self) -> int:
        if not self.can_afford():
            raise QuotaExceededError(
                f"{self.name}: out of credits (remaining={self.remaining})"
            )
        self.remaining -= self.cost_per_call
        self.charged_calls += 1
        return self.remaining

    @property
    def spend_usd(self) -> float:
        return round(self.charged_calls * self.unit_cost_usd, 4)


# ---- Retry with backoff ---------------------------------------------------

def with_retry(
    fn: Callable[[int], "object"],
    *,
    attempts: int = 3,
    base_delay: float = 0.0,
    factor: float = 2.0,
    retry_on: tuple = (TransientError,),
    sleeper: Callable[[float], None] = time.sleep,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
):
    """Call ``fn(attempt)`` up to ``attempts`` times.

    ``fn`` receives the 1-based attempt number so callers can vary behaviour
    per attempt. Only exceptions in ``retry_on`` are retried; anything else
    (e.g. PermanentError) propagates immediately. Backoff is
    ``base_delay * factor**(attempt-1)``.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return fn(attempt)
        except retry_on as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt == attempts:
                break
            delay = base_delay * (factor ** (attempt - 1))
            if on_retry:
                on_retry(attempt, exc, delay)
            if delay:
                sleeper(delay)
    assert last_exc is not None
    raise last_exc


# ---- Dead-letter queue ----------------------------------------------------

@dataclass
class DeadLetterEntry:
    lead_id: str
    stage: str
    reason: str
    detail: str = ""


class DeadLetterQueue:
    """Failed records go here with a reason — never silently dropped."""

    def __init__(self) -> None:
        self.entries: List[DeadLetterEntry] = []

    def add(self, lead_id: str, stage: str, reason: str, detail: str = "") -> None:
        self.entries.append(DeadLetterEntry(lead_id, stage, reason, detail))

    def __len__(self) -> int:
        return len(self.entries)

    def write_jsonl(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            for entry in self.entries:
                fh.write(json.dumps(asdict(entry)) + "\n")


# ---- Dedup registry -------------------------------------------------------

class DedupRegistry:
    """Set of already-seen keys. Seed it with prior runs to stay idempotent."""

    def __init__(self, seed_keys: Optional[Iterable[str]] = None) -> None:
        self._seen = set(seed_keys or [])

    def is_duplicate(self, key: str) -> bool:
        return key in self._seen

    def add(self, key: str) -> None:
        self._seen.add(key)

    def __len__(self) -> int:
        return len(self._seen)


# ---- Rate limiter ---------------------------------------------------------

class RateLimiter:
    """Simple per-run cap (e.g. a daily outreach send limit)."""

    def __init__(self, max_actions: int) -> None:
        self.max_actions = max_actions
        self.used = 0

    def allow(self) -> bool:
        if self.used >= self.max_actions:
            return False
        self.used += 1
        return True

    @property
    def remaining(self) -> int:
        return max(0, self.max_actions - self.used)
