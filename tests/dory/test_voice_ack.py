"""`voice_ack.ack_line`: a short request-specific line from the cheap model, "" for a stock phrase,
an over-long or failed answer (the caller then speaks a canned line)."""

import json
from types import SimpleNamespace

import pytest

from dory import voice_ack


def _fake(reply):
    def generate(client, model, contents, config):
        if isinstance(reply, Exception):
            raise reply
        assert "one moment" in contents and model == "cheap"
        return SimpleNamespace(text=json.dumps({"ack": reply}))

    return generate


@pytest.mark.parametrize(
    ("reply", "want"),
    [
        ("Checking Friday flights to Singapore.", "Checking Friday flights to Singapore."),
        ("  Looking up the hotel.\nmore", "Looking up the hotel."),
        ("One moment, checking.", ""),
        ("Just a sec.", ""),
        ("", ""),
        ("x" * 61, ""),
        (RuntimeError("down"), ""),
    ],
)
def test_ack_line(monkeypatch, reply, want):
    monkeypatch.setattr(voice_ack, "generate", _fake(reply))
    assert voice_ack.ack_line(object(), "cheap", "book the Friday flight", "en") == want


def test_make_ack_binds_client_and_model(monkeypatch):
    seen = {}

    def generate(client, model, contents, config):
        seen["model"] = model
        return SimpleNamespace(text=json.dumps({"ack": "Checking that booking."}))

    monkeypatch.setattr(voice_ack, "generate", generate)
    ack = voice_ack.make_ack(object(), "cheap")
    assert ack("book it", "th") == "Checking that booking." and seen["model"] == "cheap"
