"""Dory's GLM-4-Voice backend against a fake voice socket (protocol of deploy/glm_voice/server.py)."""

import asyncio
import contextlib
import json
import logging
import re
import time
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


def test_glm_voice_tells_once_then_keeps_trying_while_the_box_is_busy_or_off(monkeypatch):
    """`busy` (another call holds the server) and a refused connect (the box is off or booting)
    are said once, then retried every RETRY_S until the server answers or the call is closed;
    a server error of its own ends the call; past RETRY_MAX it gives up."""
    import dory.glm_voice as gv

    monkeypatch.setattr(gv, "RETRY_S", 0.01)
    monkeypatch.setattr(gv, "RETRY_MAX", 3)
    events = []

    async def out(kind, payload):
        events.append((kind, payload))

    attempts = {"n": 0}

    @contextlib.asynccontextmanager
    async def busy_then_refused_then_ready():
        attempts["n"] += 1
        if attempts["n"] == 1:
            yield FakeSocket([(lambda f: True, [json.dumps({"type": "error", "text": "busy"})])])
            return
        if attempts["n"] == 2:
            raise ConnectionRefusedError("down")
        yield FakeSocket([(lambda f: True, [json.dumps({"type": "ready"})])])

    class ConnectionClosedError(Exception):  # websockets' name: an open call the server closed
        pass

    class DroppingSocket(FakeSocket):
        async def __anext__(self):
            if not any(msgs for _, msgs in self.phases):  # nothing left to send: the server drops us
                raise ConnectionClosedError("received 1011 (internal error) keepalive ping timeout")
            return await super().__anext__()

    dropped = {"n": 0}

    @contextlib.asynccontextmanager
    async def dropped_then_ready():
        dropped["n"] += 1
        if dropped["n"] == 1:
            yield DroppingSocket([(lambda f: True, [json.dumps({"type": "ready"})])])
            return
        yield FakeSocket([(lambda f: True, [json.dumps({"type": "ready"})])])

    @contextlib.asynccontextmanager
    async def always_refused():
        raise ConnectionRefusedError("down")
        yield  # unreachable: keeps this an async generator for the context manager

    @contextlib.asynccontextmanager
    async def server_error():
        yield FakeSocket([(lambda f: True, [json.dumps({"type": "error", "text": "turn"})])])

    async def main():
        v = GlmVoice(_settings(), out=out, url="ws://x/voice", connect=busy_then_refused_then_ready)
        v.start()
        for _ in range(300):
            if ("ready", "") in events:
                break
            await asyncio.sleep(0.01)
        await v.close()
        assert attempts["n"] == 3
        assert events == [("error", "busy"), ("ready", "")]  # told once, then it recovered
        events.clear()
        d = GlmVoice(_settings(), out=out, url="ws://x/voice", connect=dropped_then_ready)
        d.start()
        for _ in range(300):
            if events.count(("ready", "")) >= 2:
                break
            await asyncio.sleep(0.01)
        await d.close()
        # a keepalive timeout mid-call (the server closed an open socket) reconnects: ready twice
        assert events == [("ready", ""), ("error", "voice_server_down"), ("ready", "")]
        events.clear()
        w = GlmVoice(_settings(), out=out, url="ws://x/voice", connect=always_refused)
        await asyncio.wait_for(w.start(), 5)  # RETRY_MAX attempts, then it gives up
        assert events == [("error", "voice_server_down")]
        events.clear()
        x = GlmVoice(_settings(), out=out, url="ws://x/voice", connect=server_error)
        await asyncio.wait_for(x.start(), 5)
        assert events == [("error", "turn")]  # the server's own error: no retry

    asyncio.run(main())


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


def test_glm_voice_cascade_answers_what_the_server_heard_and_fills_only_when_slow(monkeypatch):
    """The cascade server sends "heard"; a fast brain answer is spoken with no filler, a slow one
    gets one filler line first; the answer is spoken in its plain form; what was heard and said
    becomes the history of the next question; barge-in cancels a pending answer."""
    import dory.glm_voice as gv

    monkeypatch.setattr(gv, "FILLER_AFTER_S", 0.05)
    _caplog_lines, asked, events = [], [], []

    def ask(q: str, history: str) -> str:
        asked.append((q, history))
        if q == "and a hotel":
            time.sleep(0.2)  # a slow brain: the filler comes first
        return "**Two** in policy 🎉. Take the 08:00?"

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
            (
                lambda f: len([s for s in says(f) if s.get("final")]) >= 2,
                [
                    json.dumps({"type": "heard", "text": "book it"}),
                    json.dumps({"type": "interrupted"}),
                ],
            ),
        ]
    )

    @contextlib.asynccontextmanager
    async def connect():
        yield fake

    async def main():
        v = GlmVoice(_settings(), out=out, url="ws://x/voice", connect=connect, ask=ask, lang="en")
        v.start()
        for _ in range(400):
            if ("interrupted", "") in events:
                break
            await asyncio.sleep(0.01)
        await v.close()
        return v

    asyncio.run(main())
    said = says(fake)
    assert said[0] == {
        "type": "say",
        "text": "Two in policy. Take the 08:00?",
        "final": True,
    }  # fast: no filler
    assert said[1]["final"] is False and said[1]["text"]  # slow: a filler line first
    assert said[2]["final"] is True
    assert asked[0] == ("book my trip", "")
    assert asked[1][0] == "and a hotel" and "Person: book my trip" in asked[1][1]
    assert "Dory: **Two** in policy" in asked[1][1]  # the history keeps the brain's own words
    kinds = [k for k, _ in events]
    assert kinds[:3] == ["ready", "heard", "thinking"] and "audio" in kinds and "turn" in kinds
    assert (
        "answer",
        "**Two** in policy 🎉. Take the 08:00?",
    ) in events  # the original, for the chat echo
    assert "interrupted" in kinds


def test_glm_voice_greets_with_a_fixed_line_and_a_bare_ok_is_not_a_question():
    asked = []

    async def out(kind, payload):
        pass

    def has_say(f):
        return any(isinstance(x, str) and json.loads(x).get("type") == "say" for x in f.sent)

    fake = FakeSocket(
        [
            (
                lambda f: True,
                [
                    json.dumps({"type": "ready"}),
                    json.dumps({"type": "heard", "text": "ok"}),
                    json.dumps({"type": "heard", "text": "mm-hm"}),
                ],
            ),
            (has_say, [json.dumps({"type": "heard", "text": "ok"})]),
        ]
    )

    @contextlib.asynccontextmanager
    async def connect():
        yield fake

    async def main():
        v = GlmVoice(
            _settings(),
            out=out,
            url="ws://x/voice",
            connect=connect,
            ask=lambda q, h: asked.append(q) or "x",
            lang="en",
        )
        v.start()
        await asyncio.sleep(0.1)  # "ok" and "mm-hm" arrive while nothing was asked
        v.greet("en")
        for _ in range(100):  # then an "ok" answers the greeting's question
            if asked:
                break
            await asyncio.sleep(0.01)
        await v.close()
        return v

    v = asyncio.run(main())
    says_ = [
        json.loads(x)
        for x in fake.sent
        if isinstance(x, str) and json.loads(x).get("type") == "say"
    ]
    assert says_[0] == {"type": "say", "text": "Hi! How can I help?", "final": True}
    assert not any(isinstance(x, str) and json.loads(x).get("type") == "text" for x in fake.sent)
    assert asked == ["ok"]  # the first "ok" / "mm-hm" had no question pending; the last one answers
    assert "Dory: Hi! How can I help?" in v.history()


def test_spoken_form_reads_markdown_money_and_percent_as_words():
    from dory.glm_voice import spoken_form

    assert spoken_form(
        "**Booked!** 🎉 THB 13,700 total, 12% off. [map](http://x)\nAnything else?"
    ) == ("Booked! 13,700 baht total, 12 percent off. map. Anything else?")
