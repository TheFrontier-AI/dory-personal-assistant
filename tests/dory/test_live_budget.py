"""The live probes' spending cap (tests/dory/live_budget.py) refuses before it could overspend."""

import time

import pytest
from live_budget import BudgetExceeded, Meter


def test_meter_refuses_a_call_that_could_pass_the_cap():
    m = Meter(cap_usd=0.01)
    m._book("agent", {"prompt_tokens": 1000, "completion_tokens": 100}, 0, time.monotonic())
    assert round(m.spent, 6) == round((1000 * 1.40 + 100 * 4.40) / 1e6, 6)
    with pytest.raises(BudgetExceeded):
        m._admit("agent", 10_000_000)  # ~4M tokens worst case
    m2 = Meter(max_calls=1)
    m2._book("text", {}, 0, time.monotonic())
    with pytest.raises(BudgetExceeded):
        m2._admit("text", 10)


def test_missing_usage_books_the_worst_case():
    m = Meter()
    m._book("agent", None, 2500, time.monotonic())  # e.g. a stream: no usage reported
    assert m.calls[0]["prompt_tokens"] == 1001 and m.calls[0]["out_tokens"] == 4096
