"""The shared rate limiter: a token bucket kept in the DocStore, so a restart or a second web
instance never resets or multiplies a limit."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "dory"))

from fake_firestore import FakeFirestore  # noqa: E402

from dory.coo_store import FirestoreDocStore, SQLiteDocStore  # noqa: E402
from meeting_scribe.limits import KIND, TokenBucket  # noqa: E402


@pytest.fixture(params=["sqlite", "firestore"])
def docs(request):
    if request.param == "sqlite":
        return SQLiteDocStore(":memory:")
    return FirestoreDocStore(client=FakeFirestore())


def test_refills_one_token_per_rate(docs):
    t = [0.0]
    bucket = TokenBucket(rate_s=2.0, burst=3, clock=lambda: t[0])
    assert [bucket.take(docs, "a") for _ in range(3)] == [0.0, 0.0, 0.0]
    assert bucket.take(docs, "a") == pytest.approx(2.0)
    t[0] = 1.0
    assert bucket.take(docs, "a") == pytest.approx(1.0)
    t[0] = 2.0
    assert bucket.take(docs, "a") == 0.0 and bucket.take(docs, "b") == 0.0


def test_two_instances_share_one_count_per_limiter(docs):
    t = [100.0]
    first = TokenBucket(rate_s=10.0, burst=3, name="signup", clock=lambda: t[0])
    second = TokenBucket(rate_s=10.0, burst=3, name="signup", clock=lambda: t[0])  # a restart
    assert [b.take(docs, "me@x.com") for b in (first, second, first)] == [0.0, 0.0, 0.0]
    assert second.take(docs, "me@x.com") == pytest.approx(10.0)
    chat = TokenBucket(rate_s=10.0, burst=3, name="chat", clock=lambda: t[0])
    assert chat.take(docs, "me@x.com") == 0.0  # each limiter counts on its own
    assert all("me@x.com" not in key for key, _ in docs.find_items(KIND, 0))  # keys are hashed
