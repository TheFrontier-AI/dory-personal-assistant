"""Voice latency marks and the web mic gate (pure), and their wiring in WebLive (fake session)."""

import asyncio
import contextlib
import logging
import re
import threading
from array import array
from datetime import UTC, datetime
from types import SimpleNamespace

from dory import web_live
from dory.voice_latency import Act, MicGate, StageTimer


def test_stage_timer_one_line_per_turn():
    ticks = iter([10.0, 10.5, 10.9, 11.0, 11.3, 11.6])
    t = StageTimer("web", clock=lambda: next(ticks))
    t.touch("speech_end")
    t.touch("speech_end")  # the LAST voiced frame is the speech end
    for s in ("tool_call", "tool_result", "first_audio", "first_audio"):
        t.mark(s)  # a repeated first_audio must not move the mark
    assert t.ms("speech_end", "first_audio") == 800
    assert t.line() == (
        "voice_latency path=web e2e_ms=800 speech_end->tool_call=400 "
        "tool_call->tool_result=100 tool_result->first_audio=300"
    )
    t.reset()
    assert t.line() == "voice_latency path=web e2e_ms=-"


def _frame(amp: int, n: int = 640) -> bytes:
    return array("h", [amp, -amp] * (n // 2)).tobytes()


def test_mic_gate_voice_tail_end_drop():
    g = MicGate(silence_ms=800, rms_min=250.0)
    quiet, loud, soft = _frame(0), _frame(2000), _frame(100)
    assert g.tail_s == 1.6
    assert g.on_frame(quiet, 0.0) is Act.DROP  # nothing said yet: never stream silence
    assert g.on_frame(loud, 0.04) is Act.VOICE
    assert g.on_frame(soft, 0.08) is Act.TAIL  # below the threshold counts as silence
    assert g.on_frame(quiet, 1.0) is Act.TAIL  # inside the 1.6 s tail
    assert g.on_frame(quiet, 1.7) is Act.END  # tail over: this frame, then one stream end
    assert g.on_frame(quiet, 1.8) is Act.DROP
    assert g.on_frame(loud, 2.0) is Act.VOICE  # the stream reopens


# ---- WebLive wiring


def _msg(**kw):
    base = dict(go_away=None, tool_call=None, tool_call_cancellation=None, server_content=None)
    return SimpleNamespace(**{**base, **kw})


def _call(cid: str, question: str):
    return SimpleNamespace(
        function_calls=[SimpleNamespace(id=cid, name="ask_dory", args={"question": question})]
    )


def _answer(data: bytes, turn_complete: bool = True):
    return SimpleNamespace(
        interrupted=False,
        model_turn=SimpleNamespace(parts=[SimpleNamespace(inline_data=SimpleNamespace(data=data))]),
        input_transcription=None,
        output_transcription=None,
        turn_complete=turn_complete,
    )


class FakeLive:
    """Phases = (ready(fake) -> bool, messages): a phase is played once its condition holds."""

    def __init__(self, phases):
        self.phases, self.audio, self.ends, self.tools = list(phases), [], 0, []

    async def send_realtime_input(self, audio=None, audio_stream_end=None):
        if audio is not None:
            self.audio.append(len(audio.data))
        if audio_stream_end:
            self.ends += 1

    async def send_client_content(self, turns=None, turn_complete=True):
        pass

    async def send_tool_response(self, function_responses):
        self.tools.append(function_responses[0].response)

    async def receive(self):
        if not self.phases:
            await asyncio.sleep(0.01)
            return
        ready, msgs = self.phases.pop(0)
        while not ready(self):
            await asyncio.sleep(0.005)
        for m in msgs:
            yield m


def _web(fake: FakeLive, ask, out):
    s = SimpleNamespace(
        live_voice="Leda", live_model="m", now=lambda: datetime(2026, 10, 25, tzinfo=UTC)
    )

    @contextlib.asynccontextmanager
    async def connect(cfg):
        yield fake

    return web_live.WebLive(s, client=None, instruction="x", ask=ask, out=out, connect=connect)


def test_web_live_gates_the_mic_and_logs_one_latency_line_per_turn(caplog):
    caplog.set_level(logging.INFO, logger="dory.web_live")
    fake = FakeLive(
        [
            (lambda f: bool(f.audio), [_msg(tool_call=_call("c1", "ยอดขายเดือนนี้"))]),
            (lambda f: bool(f.tools), [_msg(server_content=_answer(bytes(960)))]),
        ]
    )
    events = []

    async def out(kind, payload):
        events.append(kind)

    async def main():
        w = _web(fake, ask=lambda q: "ok", out=out)
        w.feed(_frame(0))  # quiet before anyone spoke: dropped
        w.feed(_frame(2000))  # voice: sent, and it is the speech end
        w.start()
        for _ in range(100):
            if "turn" in events:
                break
            await asyncio.sleep(0.01)
        await w.close()

    asyncio.run(main())
    assert fake.audio == [1280] and fake.tools == [{"answer": "ok"}]
    assert events[:2] == ["ready", "thinking"] and events[-2:] == ["audio", "turn"]
    assert re.search(
        r"voice_latency path=web e2e_ms=\d+ speech_end->tool_call=\d+ "
        r"tool_call->tool_result=\d+ tool_result->first_audio=\d+",
        caplog.text,
    )


def test_web_live_reconnects_with_the_resumption_handle_and_keeps_the_mic(monkeypatch):
    monkeypatch.setattr(web_live, "BACKOFF_S", (0.0,))
    first = FakeLive(
        [
            (
                lambda f: True,
                [
                    _msg(session_resumption_update=SimpleNamespace(new_handle="h1")),
                    _msg(go_away=SimpleNamespace(time_left=None)),
                ],
            )
        ]
    )
    second = FakeLive([(lambda f: bool(f.audio), [_msg(server_content=_answer(bytes(960)))])])
    fakes, configs, events = [first, second], [], []

    @contextlib.asynccontextmanager
    async def connect(cfg):
        configs.append(cfg)
        yield fakes.pop(0)

    async def out(kind, payload):
        events.append(kind)

    async def main():
        s = SimpleNamespace(
            live_voice="Leda", live_model="m", now=lambda: datetime(2026, 10, 26, tzinfo=UTC)
        )
        w = web_live.WebLive(
            s, client=None, instruction="x", ask=lambda q: "", out=out, connect=connect
        )
        w.start()
        for _ in range(100):
            if "reconnecting" in events:
                break
            await asyncio.sleep(0.01)
        w.feed(_frame(2000))  # said while the next connection opens: it must get there
        for _ in range(100):
            if "turn" in events:
                break
            await asyncio.sleep(0.01)
        await w.close()

    asyncio.run(main())
    assert events == ["ready", "reconnecting", "ready", "audio", "turn"]
    assert configs[0].session_resumption.handle is None
    assert configs[1].session_resumption.handle == "h1"  # the conversation continues
    assert first.audio == [] and second.audio == [1280]


def test_web_live_tool_call_runs_in_background_and_server_cancellation_stops_it():
    fake = FakeLive(
        [
            (lambda f: True, [_msg(tool_call=_call("c1", "ยอดขาย"))]),
            (lambda f: True, [_msg(tool_call_cancellation=SimpleNamespace(ids=["c1"]))]),
        ]
    )
    release = threading.Event()

    def slow_ask(q: str) -> str:
        release.wait(5)
        return "late"

    async def out(kind, payload):
        pass

    async def main():
        w = _web(fake, ask=slow_ask, out=out)
        w.start()
        for _ in range(100):  # the receive loop was never blocked by the running tool
            if not w._tools and w.turns == 0 and fake.phases == []:
                break
            await asyncio.sleep(0.01)
        assert w._tools == {}
        release.set()
        await asyncio.sleep(0.05)
        assert fake.tools == []  # nothing is sent for a cancelled job
        await w.close()

    asyncio.run(main())
