"""Runnable copies of the code examples in phase6_report/report.md (stdlib only, Python 3.12)."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from array import array
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from itertools import pairwise

import pytest

# ---------------------------------------------------------------- Example 1: StageTimer

log = logging.getLogger("dory.voice.latency")


@dataclass
class StageTimer:
    """Per-turn latency marks; one log line per turn, counts only, never content."""

    path: str  # "discord" | "web"
    clock: Callable[[], float] = time.monotonic
    marks: dict[str, float] = field(default_factory=dict)

    def mark(self, stage: str) -> None:
        self.marks.setdefault(stage, self.clock())  # first occurrence wins

    def ms(self, a: str, b: str) -> int | None:
        if a in self.marks and b in self.marks:
            return round((self.marks[b] - self.marks[a]) * 1000)
        return None

    def line(self) -> str:
        e2e = self.ms("speech_end", "first_audio")
        parts = [f"voice_latency path={self.path} e2e_ms={'-' if e2e is None else e2e}"]
        order = list(self.marks)
        parts += [f"{a}->{b}={self.ms(a, b)}" for a, b in pairwise(order)]
        return " ".join(parts)

    def log(self) -> None:
        log.info(self.line())


def test_stage_timer_line():
    ticks = iter([10.0, 10.9, 11.0, 11.3, 11.6])
    t = StageTimer("web", clock=lambda: next(ticks))
    for s in ("speech_end", "tool_call", "tool_result", "first_audio", "first_audio"):
        t.mark(s)  # the repeated first_audio must not move the mark
    assert t.ms("speech_end", "first_audio") == 1300
    assert t.line() == (
        "voice_latency path=web e2e_ms=1300 speech_end->tool_call=900 "
        "tool_call->tool_result=100 tool_result->first_audio=300"
    )
    assert StageTimer("discord").line() == "voice_latency path=discord e2e_ms=-"


# ---------------------------------------------------------------- Example 2: MicGate


class Act(Enum):
    SEND = "send"
    SEND_END = "send_end"  # send this frame, then audio_stream_end once
    DROP = "drop"


def rms16(frame: bytes) -> float:
    a = array("h", frame)
    return math.sqrt(sum(x * x for x in a) / len(a)) if a else 0.0


@dataclass
class MicGate:
    """Decide per browser frame whether to forward it to the Live session.

    Sends while voiced and for `tail_s` after the last voice (the server VAD needs the
    silence to end the turn), then one stream end, then drops until voice returns.
    """

    silence_ms: int = 800
    rms_min: float = 250.0
    extra_tail_s: float = 0.8  # same margin as live_voice._idle_s
    muted: bool = False
    _last_voice: float | None = None
    _ended: bool = True

    @property
    def tail_s(self) -> float:
        return max(1.0, self.silence_ms / 1000 + self.extra_tail_s)

    def on_frame(self, frame: bytes, now: float) -> Act:
        if not self.muted and rms16(frame) >= self.rms_min:
            self._last_voice, self._ended = now, False
            return Act.SEND
        if self._ended or self._last_voice is None:
            return Act.DROP
        if now - self._last_voice < self.tail_s:
            return Act.SEND
        self._ended = True
        return Act.SEND_END


def _frame(amp: int, n: int = 640) -> bytes:
    return array("h", [amp, -amp] * (n // 2)).tobytes()


def test_mic_gate_voice_tail_end_drop():
    g = MicGate(silence_ms=800)
    quiet, loud = _frame(0), _frame(2000)
    assert g.on_frame(quiet, 0.0) is Act.DROP  # nothing said yet: never stream zeros
    assert g.on_frame(loud, 0.04) is Act.SEND
    assert g.on_frame(quiet, 1.0) is Act.SEND  # inside the 1.6 s tail
    assert g.on_frame(quiet, 1.7) is Act.SEND_END  # tail over: one stream end
    assert g.on_frame(quiet, 1.8) is Act.DROP
    g.muted = True
    assert g.on_frame(loud, 2.0) is Act.DROP  # muted: loud frames are not voice
    g.muted = False
    assert g.on_frame(loud, 2.1) is Act.SEND


# ---------------------------------------------------------------- Example 3: EndPointer


class Turn(Enum):
    START = "speech_start"
    END = "turn_end"


@dataclass
class EndPointer:
    """Silence end-pointing on per-chunk speech probabilities (Silero VAD or any VAD).

    Thai has no open semantic end-of-turn model, so this is the whole turn detector;
    `silence_ms` is the one knob (industry guidance 500-800 ms).
    """

    silence_ms: int = 600
    min_speech_ms: int = 200
    threshold: float = 0.5
    _speech_start: float | None = None
    _last_speech: float | None = None

    def push(self, prob: float, now_ms: float) -> Turn | None:
        if prob >= self.threshold:
            started = self._speech_start is None
            if started:
                self._speech_start = now_ms
            self._last_speech = now_ms
            return Turn.START if started else None
        if self._speech_start is None or self._last_speech is None:
            return None
        if now_ms - self._last_speech < self.silence_ms:
            return None
        long_enough = self._last_speech - self._speech_start >= self.min_speech_ms
        self._speech_start = self._last_speech = None
        return Turn.END if long_enough else None


def test_end_pointer_emits_once_and_ignores_blips():
    ep = EndPointer(silence_ms=600, min_speech_ms=200)
    out = [ep.push(p, t) for t, p in enumerate_probs([0.9] * 20 + [0.1] * 30)]  # 32 ms chunks
    assert out[0] is Turn.START
    assert out.count(Turn.END) == 1
    assert out.index(Turn.END) == 20 + 600 // 32  # first chunk at or past 600 ms of silence
    blip = EndPointer(silence_ms=600, min_speech_ms=200)
    out2 = [blip.push(p, t) for t, p in enumerate_probs([0.9] * 3 + [0.1] * 30)]  # 96 ms blip
    assert Turn.END not in out2


def enumerate_probs(probs: list[float], chunk_ms: int = 32):
    for i, p in enumerate(probs):
        yield i * chunk_ms, p


# ---------------------------------------------------------------- Example 4: non-blocking tool call


class ToolRunner:
    """Run ask_dory off the receive loop; cancel it when the person interrupts."""

    def __init__(
        self, ask: Callable[[str], asyncio.Future], respond: Callable[[str, dict], asyncio.Future]
    ):
        self._ask, self._respond = ask, respond
        self._jobs: dict[str, asyncio.Task[None]] = {}

    def start(self, call_id: str, question: str) -> None:
        self._jobs[call_id] = asyncio.create_task(self._run(call_id, question))

    async def _run(self, call_id: str, question: str) -> None:
        try:
            answer = await self._ask(question)
            await self._respond(call_id, {"answer": answer})
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - the person must hear an honest failure
            log.warning("ask_dory failed (%s)", call_id)
            await self._respond(call_id, {"error": "could not get the answer right now"})
        finally:
            self._jobs.pop(call_id, None)

    def interrupt(self) -> int:
        n = len(self._jobs)
        for t in self._jobs.values():
            t.cancel()
        return n


async def _slow_ask(_: str) -> str:
    await asyncio.sleep(10)
    return "late"


def test_tool_runner_cancels_on_interrupt():
    async def main():
        sent: list[tuple[str, dict]] = []

        async def respond(cid: str, body: dict) -> None:
            sent.append((cid, body))

        r = ToolRunner(_slow_ask, respond)
        r.start("c1", "ยอดขายเดือนนี้")
        await asyncio.sleep(0)  # the receive loop keeps running: start() did not block
        assert r.interrupt() == 1
        await asyncio.sleep(0)
        assert sent == []  # nothing is sent for a cancelled job

        async def fast(_: str) -> str:
            return "ok"

        r2 = ToolRunner(fast, respond)
        r2.start("c2", "q")
        await asyncio.sleep(0.01)
        assert sent == [("c2", {"answer": "ok"})]

    asyncio.run(main())


# ---------------------------------------------------------------- Example 5: Thai sentence chunker


_BREAKS = frozenset(" \n。.!?…ฯ")


def sentence_chunker(*, min_chars: int = 24):
    """Pure splitter for the streaming-TTS feeder: `push(text) -> chunks`, `flush() -> rest`.

    Thai writes spaces between clauses, not words, so a space after >= min_chars is a
    safe TTS boundary; the remainder is flushed by `flush()`.
    """

    buf: list[str] = []
    size = 0

    def push(piece: str) -> list[str]:
        nonlocal size
        out: list[str] = []
        for ch in piece:
            buf.append(ch)
            size += 1
            if ch in _BREAKS and size >= min_chars:
                out.append("".join(buf).strip())
                buf.clear()
                size = 0
        return out

    def flush() -> list[str]:
        nonlocal size
        rest = "".join(buf).strip()
        buf.clear()
        size = 0
        return [rest] if rest else []

    return push, flush


def test_sentence_chunks_thai_and_english():
    push, flush = sentence_chunker(min_chars=24)
    out: list[str] = []
    for piece in [
        "สรุปยอดขาย",
        "เดือนนี้ 120,000 บาท ",
        "เพิ่มขึ้น 8% จากเดือนก่อน ",
        "Next: ",
        "call the supplier",
    ]:
        out += push(piece)
    out += flush()
    assert out == [
        "สรุปยอดขายเดือนนี้ 120,000",
        "บาท เพิ่มขึ้น 8% จากเดือนก่อน",
        "Next: call the supplier",  # no terminator: flushed at the end of the answer
    ]
    assert flush() == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
