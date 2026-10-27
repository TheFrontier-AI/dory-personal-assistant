"""Dory's GLM-4-Voice backend against a fake voice socket (protocol of deploy/glm_voice/server.py)."""

import asyncio
import contextlib
import json
import logging
import re
from array import array
from datetime import UTC, datetime
from types import SimpleNamespace

from dory.glm_voice import GlmVoice


def _frame(amp: int, n: int = 640) -> bytes:
    return array("h", [amp, -amp] * (n // 2)).tobytes()


class FakeSocket:
    """Phases = (ready(fake) -> bool, messages): a phase is sent once its condition holds."""

    def __init__(self, phases):
        self.phases, self.sent = list(phases), []

    async def send(self, data):
        self.sent.append(data)

    def __aiter__(self):
        return self

    async def __anext__(self):
        while True:
            if not self.phases:
                await asyncio.sleep(0.01)
                continue
            ready, msgs = self.phases[0]
            if not ready(self):
                await asyncio.sleep(0.005)
                continue
            if not msgs:
                self.phases.pop(0)
                continue
            return msgs.pop(0)


def _settings():
    return SimpleNamespace(
        live_voice="Leda",
        live_model="m",
        live_web_silence_ms=800,
        now=lambda: datetime(2026, 10, 26, tzinfo=UTC),
    )


def test_glm_voice_speaks_the_server_protocol_and_logs_latency(caplog):
    caplog.set_level(logging.INFO, logger="dory.web_live")
    fake = FakeSocket(
        [
            (lambda f: True, [json.dumps({"type": "ready"})]),
            (
                lambda f: any(isinstance(x, bytes) for x in f.sent),  # a voiced frame arrived
                [
                    json.dumps({"type": "said", "text": "Hi there"}),
                    bytes(960),
                    json.dumps({"type": "turn"}),
                ],
            ),
        ]
    )
    events = []

    async def out(kind, payload):
        events.append((kind, payload if kind != "audio" else len(payload)))

    @contextlib.asynccontextmanager
    async def connect():
        yield fake

    async def main():
        v = GlmVoice(_settings(), out=out, url="ws://x/voice", token="t", connect=connect)
        v.greet("en")
        v.feed(_frame(0))  # quiet before anyone spoke: dropped by the mic gate
        v.feed(_frame(2000))
        v.start()
        for _ in range(100):
            if ("turn", "") in events:
                break
            await asyncio.sleep(0.01)
        await v.close()

    asyncio.run(main())
    texts = [json.loads(x) for x in fake.sent if isinstance(x, str)]
    assert texts[0]["type"] == "text" and texts[0]["text"].startswith("(The person just opened")
    assert [x for x in fake.sent if isinstance(x, bytes)] == [_frame(2000)]  # silence never sent
    assert events == [("ready", ""), ("said", "Hi there"), ("audio", 960), ("turn", "")]
    assert re.search(r"voice_latency path=web e2e_ms=\d+ speech_end->first_audio=\d+", caplog.text)


def test_glm_voice_reports_the_servers_error_and_connection_failures():
    events = []

    async def out(kind, payload):
        events.append((kind, payload))

    @contextlib.asynccontextmanager
    async def busy():
        yield FakeSocket([(lambda f: True, [json.dumps({"type": "error", "text": "busy"})])])

    @contextlib.asynccontextmanager
    async def refused():
        raise ConnectionRefusedError("down")
        yield  # unreachable: keeps this an async generator for the context manager

    async def main():
        v = GlmVoice(_settings(), out=out, url="ws://x/voice", connect=busy)
        await asyncio.wait_for(v.start(), 2)
        w = GlmVoice(_settings(), out=out, url="ws://x/voice", connect=refused)
        await asyncio.wait_for(w.start(), 2)

    asyncio.run(main())
    assert events == [("error", "busy"), ("error", "voice_server_down")]  # refused = the box is off


def test_glm_voice_wakes_a_stopped_box_before_connecting():
    class Waker:
        def __init__(self, up: bool):
            self.up, self.calls = up, []

        async def healthy(self):
            self.calls.append("healthy")
            return False

        async def ensure_running(self, *a, **k):
            self.calls.append("ensure_running")
            return self.up

    events = []

    async def out(kind, payload):
        events.append(kind)

    fake = FakeSocket([(lambda f: True, [json.dumps({"type": "ready"})])])

    @contextlib.asynccontextmanager
    async def connect():
        yield fake

    async def main():
        w = Waker(up=True)
        v = GlmVoice(_settings(), out=out, url="ws://x/voice", connect=connect, waker=w)
        v.start()
        for _ in range(100):
            if "ready" in events:
                break
            await asyncio.sleep(0.01)
        await v.close()
        assert w.calls == ["healthy", "ensure_running"]
        assert events[:2] == [
            "waking",
            "ready",
        ]  # the person sees why they wait, then the call opens
        events.clear()
        down = GlmVoice(
            _settings(), out=out, url="ws://x/voice", connect=connect, waker=Waker(False)
        )
        await asyncio.wait_for(down.start(), 2)

    asyncio.run(main())
    assert events == ["waking", "error"]  # the box never came up: an honest error, no hang


def test_glm_voice_cascade_answers_what_the_server_heard_with_a_filler_first(caplog):
    """The cascade server sends "heard"; GlmVoice speaks a filler at once, asks Dory's brain off the
    loop and sends the answer as the final say; barge-in cancels a pending answer."""
    caplog.set_level(logging.INFO, logger="dory.web_live")
    asked, events = [], []

    def ask(q: str) -> str:
        asked.append(q)
        return "Two in policy. Take the 08:00?"

    async def out(kind, payload):
        events.append((kind, payload))

    def says(f):
        return [
            json.loads(x)
            for x in f.sent
            if isinstance(x, str) and json.loads(x).get("type") == "say"
        ]

    fake = FakeSocket(
        [
            (
                lambda f: True,
                [
                    json.dumps({"type": "ready"}),
                    json.dumps({"type": "heard", "text": "book my trip"}),
                ],
            ),
            (
                lambda f: any(s.get("final") for s in says(f)),
                [
                    b"\x00\x01" * 480,
                    json.dumps({"type": "said", "text": "x"}),
                    json.dumps({"type": "turn"}),
                ],
            ),
            (lambda f: True, [json.dumps({"type": "heard", "text": "and a hotel"})]),
            (lambda f: len(says(f)) >= 3, [json.dumps({"type": "interrupted"})]),
        ]
    )

    @contextlib.asynccontextmanager
    async def connect():
        yield fake

    async def main():
        v = GlmVoice(_settings(), out=out, url="ws://x/voice", connect=connect, ask=ask, lang="en")
        v.start()
        for _ in range(300):
            if ("interrupted", "") in events:
                break
            await asyncio.sleep(0.01)
        await v.close()

    asyncio.run(main())
    first = says(fake)
    assert first[0]["final"] is False and first[0]["text"]  # a filler line before the brain answers
    assert first[1] == {"type": "say", "text": "Two in policy. Take the 08:00?", "final": True}
    assert asked[0] == "book my trip"
    kinds = [k for k, _ in events]
    assert kinds[:3] == ["ready", "heard", "thinking"] and "audio" in kinds and "turn" in kinds
    assert ("heard", "and a hotel") in events and "interrupted" in kinds
    assert any("voice_latency path=web" in r.message for r in caplog.records)
