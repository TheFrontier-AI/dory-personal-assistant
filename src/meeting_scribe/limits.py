"""Rate limits shared by every web instance: one token bucket per (limiter, key), kept in the
DocStore, so a restart or a second instance never resets or multiplies a limit."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Any

from dory.coo_store import DocStore

KIND = "dory_rate_limits"


class TokenBucket:
    """One token every `rate_s` seconds, at most `burst` saved up, so a few tabs polling
    independently are not starved. Each key is ONE document `{tokens, at}` (wall clock, key =
    sha256 of limiter name and key), read and written in a transaction."""

    def __init__(
        self,
        rate_s: float = 2.0,
        burst: int = 3,
        name: str = "limit",
        clock: Callable[[], float] = time.time,
    ):
        self.rate_s, self.burst, self.name, self.clock = rate_s, burst, name, clock

    def take_tx(self, tx: Any, key: str) -> float:
        """Inside a transaction: 0.0 when a token was taken (allowed), else the seconds until
        the next one (nothing is written then)."""
        doc_key = hashlib.sha256(f"{self.name}\0{key}".encode()).hexdigest()
        t = self.clock()
        d = tx.get(KIND, 0, doc_key) or {"tokens": float(self.burst), "at": t}
        tokens = min(float(self.burst), d["tokens"] + max(0.0, t - d["at"]) / self.rate_s)
        if tokens < 1.0:
            return (1.0 - tokens) * self.rate_s
        tx.put(KIND, 0, doc_key, {"tokens": tokens - 1.0, "at": t})
        return 0.0

    def take(self, docs: DocStore, key: str) -> float:
        """`take_tx` in its own transaction. Blocking: call from a worker thread."""
        return docs.transact(lambda tx: self.take_tx(tx, key))
