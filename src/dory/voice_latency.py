"""Per-turn latency marks and the web mic gate: pure, no I/O, never any audio content.

`StageTimer` keeps the monotonic marks of ONE spoken turn (speech end, tool call, tool result,
first audio) and renders one log line, `voice_latency path=<discord|web> e2e_ms=<n> a->b=<ms> ...`,
so `grep voice_latency` gives p50 / p95 for either path. `MicGate` decides, per browser frame, what
the web path forwards to the Live session: voiced frames, then silence for `tail_s` so the
server-side VAD can end the turn, then one `audio_stream_end`; nothing while the person is quiet.
"""

from __future__ import annotations

import math
import time
from array import array
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from itertools import pairwise


@dataclass
class StageTimer:
    path: str  # "discord" | "web"
    clock: Callable[[], float] = time.monotonic
    marks: dict[str, float] = field(default_factory=dict)

    def mark(self, stage: str, at: float | None = None) -> None:
        """The FIRST time a stage is seen counts (the first audio chunk of the answer)."""
        self.marks.setdefault(stage, self.clock() if at is None else at)

    def touch(self, stage: str) -> None:
        """The LAST time counts (every voiced frame moves the speech end)."""
        self.marks[stage] = self.clock()

    def ms(self, a: str, b: str) -> int | None:
        if a in self.marks and b in self.marks:
            return round((self.marks[b] - self.marks[a]) * 1000)
        return None

    def line(self) -> str:
        e2e = self.ms("speech_end", "first_audio")
        order = sorted(self.marks, key=self.marks.__getitem__)
        parts = [f"voice_latency path={self.path} e2e_ms={'-' if e2e is None else e2e}"]
        parts += [f"{a}->{b}={self.ms(a, b)}" for a, b in pairwise(order)]
        return " ".join(parts)

    def reset(self) -> None:
        self.marks.clear()


class Act(Enum):
    VOICE = "voice"  # send: the person is speaking
    TAIL = "tail"  # send: the silence the server VAD needs to end the turn
    END = "end"  # send this frame, then audio_stream_end once
    DROP = "drop"  # the person is quiet: nothing goes up


def rms16(frame: bytes) -> float:
    a = array("h", frame[: len(frame) - len(frame) % 2])
    return math.sqrt(math.sumprod(a, a) / len(a)) if a else 0.0


@dataclass
class MicGate:
    # shortcut: a fixed RMS threshold is not a VAD, a speaker below it is never heard; upgrade to
    # Silero VAD once the false-start / missed-speech rates are measured (Phase B).
    silence_ms: int = 800
    rms_min: float = 250.0
    extra_tail_s: float = 0.8  # the same margin as live_voice._idle_s
    _last_voice: float | None = None
    _ended: bool = True

    @property
    def tail_s(self) -> float:
        return max(1.0, self.silence_ms / 1000 + self.extra_tail_s)

    def on_frame(self, frame: bytes, now: float) -> Act:
        if rms16(frame) >= self.rms_min:
            self._last_voice, self._ended = now, False
            return Act.VOICE
        if self._ended or self._last_voice is None:
            return Act.DROP
        if now - self._last_voice < self.tail_s:
            return Act.TAIL
        self._ended = True
        return Act.END
