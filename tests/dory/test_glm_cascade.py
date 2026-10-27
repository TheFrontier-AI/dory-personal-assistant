"""The cascade voice sidecar (deploy/glm_voice/cascade.py) over FastAPI's test client with fake
engines: utterance -> heard, say -> audio + said (+ turn when final), barge-in -> interrupted,
typed text -> heard, bearer token, one call at a time. Offline, no GPU."""

import importlib.util
import json
import sys
from array import array
from pathlib import Path

import pytest
from starlette.testclient import TestClient

HERE = Path(__file__).resolve().parents[2] / "deploy" / "glm_voice"


@pytest.fixture(scope="module")
def cascade(monkeypatch_module=None):
    sys.path.insert(0, str(HERE))
    import os

    os.environ["GLM_VOICE_TOKEN"] = "tok"
    spec = importlib.util.spec_from_file_location("cascade", HERE / "cascade.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.TOKEN = "tok"
    return mod


def _loud(n: int = 320) -> bytes:
    return array("h", [3000, -3000] * (n // 2)).tobytes()


def _recv_until(ws, kind: str, limit: int = 50):
    """Messages until one JSON event of `kind` (audio frames are collected as b'audio')."""
    got = []
    for _ in range(limit):
        m = ws.receive()
        if m.get("bytes") is not None:
            got.append(("audio", len(m["bytes"])))
            continue
        ev = json.loads(m["text"])
        got.append((ev["type"], ev.get("text", "")))
        if ev["type"] == kind:
            return got
    raise AssertionError(f"no {kind} in {got}")


def test_split_sentences_and_selftest(cascade):
    assert cascade.split_sentences("Booked. Reference ABC123! Anything else?") == [
        "Booked.", "Reference ABC123!", "Anything else?",
    ]  # fmt: skip
    cascade.selftest()


def test_cascade_turn_heard_say_turn_and_barge_in(cascade):
    engines = cascade.FakeEngines("book my trip for the lumen kickoff")
    app = cascade.make_app(engines)
    with TestClient(app) as client:
        with client.websocket_connect("/voice", headers={"Authorization": "Bearer tok"}) as ws:
            assert json.loads(ws.receive_text()) == {"type": "ready"}
            for _ in range(30):  # 600 ms of speech, then Dory's mic gate says the stream ended
                ws.send_bytes(_loud())
            ws.send_text(json.dumps({"type": "end"}))
            got = _recv_until(ws, "heard")
            assert got[-1] == ("heard", "book my trip for the lumen kickoff")
            # Dory speaks a filler, then the answer: audio per sentence, said per say, turn at the end
            ws.send_text(json.dumps({"type": "say", "text": "One moment.", "final": False}))
            ws.send_text(
                json.dumps({"type": "say", "text": "Two in policy. Take the 08:00?", "final": True})
            )
            got = _recv_until(ws, "turn")
            kinds = [k for k, _ in got]
            assert kinds.count("audio") == 3 and kinds.count("said") == 2 and kinds[-1] == "turn"
            assert engines.spoken == ["One moment.", "Two in policy.", "Take the 08:00?"]
            # a typed turn is echoed as heard (Dory's brain answers it the same way)
            ws.send_text(json.dumps({"type": "text", "text": "and a hotel"}))
            assert _recv_until(ws, "heard")[-1] == ("heard", "and a hotel")
            # barge-in: speech while something is queued -> interrupted, the queue is dropped
            ws.send_text(json.dumps({"type": "say", "text": "A long answer. " * 40, "final": True}))
            ws.send_bytes(_loud())
            got = _recv_until(ws, "interrupted", limit=200)
            assert ("interrupted", "") in got
            ws.send_text(json.dumps({"type": "close"}))
        assert client.get("/health").json()["busy"] is False


def test_cascade_refuses_a_bad_token_and_a_second_caller(cascade):
    app = cascade.make_app(cascade.FakeEngines())
    with TestClient(app) as client:
        with (
            pytest.raises(Exception),  # noqa: B017 - the server closes with 4401 before accepting
            client.websocket_connect("/voice", headers={"Authorization": "Bearer nope"}) as ws,
        ):
            ws.receive_text()
        with client.websocket_connect("/voice", headers={"Authorization": "Bearer tok"}) as first:
            first.receive_text()
            assert client.get("/health").json()["busy"] is True
            with client.websocket_connect(
                "/voice", headers={"Authorization": "Bearer tok"}
            ) as second:
                assert json.loads(second.receive_text()) == {"type": "error", "text": "busy"}
            first.send_text(json.dumps({"type": "close"}))
