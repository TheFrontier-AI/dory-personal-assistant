# Dory voice-to-voice: research, design and phased plan

Date: 2026-10-25. Prepared for the owner of Dory (Thai/English Discord bot + web command center) ahead of the
Nebius x NVIDIA hackathon deadline (2026-10-30 10:00 PDT) and the Gemini Live 2.5 model retirement (2026-12-13).

**How to read this.** Every claim carries one of four labels. **Confirmed** = a peer-reviewed paper, an official
page read on 2026-10-25, or Dory's code (file:line on branch `rename/dory`). **Assumption** = our reading of
confirmed inputs (arithmetic, interpretation). **Recommendation** = a design choice we argue for. **Hypothesis** =
untested; a probe or a measurement is named. Citations `[@key]` resolve in `references.bib`; `(preprint)` marks
work without a peer-reviewed venue, which we weight lower. Evidence files: `../phase0_current_system/` (code audit),
`../phase1_frontier/` (papers 2025-2026 + managed APIs), `../phase2_survey/` (82-paper database), `../phase3_deep_dive/`
(12 papers read in full), `../phase4_code/` (NVIDIA/Nebius stack, 82 repositories), `../phase5_synthesis/`.

---

## Executive summary

1. **Keep the architecture Dory already has, fix its engineering.** Dory runs a speech-to-speech voice layer (Gemini
   Live native audio) that delegates thinking to a text brain through one tool, `ask_dory`. This is the design
   OpenAI formalised as GPT-Live "delegation" and the one the peer-reviewed evidence favours for an assistant that
   must answer correctly: on VoiceBench a Whisper + 8B-LLM cascade scores 79.1 against 37.5 for LLaMA-Omni and 27.5 for
   Moshi, and end-to-end tuning broke safety (refusal 98 % -> 11 %) [@chen2024voicebench]. End-to-end duplex models
   are 0.5-1 s faster but interrupt a thinking pause 93-98 % of the time [@lin2025full], and none of them speaks Thai.
2. **Thai decides everything.** Confirmed today: Gemini Live and OpenAI gpt-realtime are the only speech-to-speech
   products with Thai in and out; no open end-of-turn model, no open streaming Thai TTS with a permissive licence, no
   NVIDIA TTS and no NVIDIA speech-to-speech model covers Thai; Nebius Token Factory serves no speech model at all (live
   `GET /v1/models`, 30 ids). The only NVIDIA-architected Thai speech component with evidence is SCB10X's **Typhoon ASR
   Realtime** (NeMo FastConformer-Transducer, 114M, CC-BY-4.0, streaming, CER 6.8-13.9 by set) [@sirichotedumrong2026typhoon] (preprint).
3. **Dory's latency is unmeasured and its biggest waste is turn-end detection.** The code logs only brain seconds and
   one partial Discord line; the web path waits 2,000 ms of silence before a turn ends (`web_live.py:38`) against
   Google's recommended 500-800 ms, streams zeros while muted, blocks barge-in during a tool call and cannot reconnect.
   Phase A fixes these with config and ~200 lines, behind flags, before the hackathon.
4. **The Nebius/NVIDIA showcase that is real in five days:** one Nebius L40S ($1.55/GPU-h, Confirmed list price)
   running Typhoon ASR Realtime for Thai transcripts and captions, replacing the duplicate per-segment Gemini ASR, with
   the Nemotron 3 Super brain already on Token Factory. A Thai-on-Nemotron-Speech path needs a fine-tune of the
   "adaptation-ready" Thai tier of Nemotron 3.5 ASR Streaming and is not feasible by 2026-10-30 (Assumption).
5. **Targets.** The industry's sub-800 ms p50 is a cascade-on-nearby-GPUs number; every managed speech-to-speech model
   measures 0.6-1.3 s time-to-first-audio on its own (Secondary, Artificial Analysis). Dory's Phase A/B targets are
   therefore relative and measured (halve turn-end wait, p50 ≤ 1.5 s non-tool turns), and sub-800 ms is the Phase C
   experiment's bar, not a promise.

---

## Facts that frame every decision (Confirmed unless noted)

| Fact | Source |
| --- | --- |
| Both Dory voice paths use `gemini-live-2.5-flash-native-audio` at `us-central1`, voice Leda; one tool `ask_dory` to the ADK agent (Nemotron 3 Super on Token Factory when `DORY_NEBIUS_API_KEY` is set) | `config.py:92-94`, `llm.py:48-64`, phase 0 |
| That Vertex model retires **2026-12-13**; the GA model is `gemini-3.8-live` (native audio only, no half-cascade line; `thinking_level` unsupported; tools `NON_BLOCKING` by default; "polite interruption downgrade"; `proactive_audio` permanently on; `enable_affective_dialog` must not be passed) | Vertex 3.8 guide and model pages updated 2026-10-22 (phase 1 industry [S12][S14][S3]) |
| Gemini Live: Thai in and out (99 languages; `th-TH` on Vertex), 16 kHz PCM in / 24 kHz out, send 20-40 ms chunks, server VAD `silence_duration_ms` default ~800 ms (recommended 500-800), connection ~10 min with `GoAway`, resumption handles 2 h, 15 min audio-only without compression | same |
| Price: $3 / $12 per 1M audio tokens in / out at 25 tokens/s -> **$0.011 per 50/50 conversation minute**, $0.0135 always-on; Vertex re-bills the session context every turn | pricing pages 2026-10-22; arithmetic = Assumption |
| Measured TTFA: Gemini 3.8 Live 1.18 s, Gemini 2.5 native audio 0.63 s, GPT-Realtime-2.1 0.97-1.21 s, GPT-Live-1 1.24-1.34 s, Eleven Realtime v1 Max 0.57 s | Artificial Analysis, **Secondary** |
| Nebius Token Factory: 30 serverless models, 58 dedicated-endpoint templates, **zero speech / audio**; no realtime or WebSocket API; GPU VMs: L40S from $1.55/GPU-h, H100 $4.50, H200 $5.40, B200 $8.50; regions eu / us / uk / me, **no Southeast Asia** | live API calls + nebius.com/prices, phase 4 |
| NVIDIA speech with Thai: only Parakeet 1.1B RNNT Multilingual NIM (`th-TH` in `type=default`, Thai WER unpublished, gated card) and Nemotron 3.5 ASR Streaming (Thai = adaptation-ready = fine-tune first). No NVIDIA TTS has Thai. PersonaPlex / VoiceChat-11B / Nano Omni are English only | NIM support matrices (2026-10-07), HF cards, phase 4 |
| NVIDIA reference voice agent = Pipecat-based `nemotron-voice-agent` v2.3.0 (ASR Streaming -> Nemotron 3.5 Lightning -> Magpie), 0.86-0.93 s end-to-end on 4x B200 (units unstated, Assumption = seconds); ACE examples archived 2026-07-17 | build.nvidia.com, GitHub |
| No open end-of-turn model lists Thai (Smart Turn v3.2: 23 languages; LiveKit v1: 14; Flux multi: 10); Silero VAD v6 (MIT, <1 ms per chunk) is language-agnostic | phase 4 D, phase 1 industry |
| Python: 3.15.0 shipped 2026-10-09; torch has no cp315 wheels; vllm / livekit-agents / py-cord / moshi exclude 3.15; kokoro `<3.13`. **Pin 3.12** (Dory's current pin) | PyPI JSON 2026-10-25, phase 4 |
| Dory's Discord capture decrypts DAVE itself (`davey 0.1.7`) and decodes Opus per user; the ecosystem's DAVE risk on `discord-ext-voice-recv` is mitigated in this tree | `meeting.py:677-721`; phase 5 reconciliation |

---

# Phase A — Measure and harden what exists (now -> 2026-10-30)

### A.1 Goals and success criteria

Goal: make every voice turn measurable, remove the avoidable dead air and waste on the web path, move the Live
model to the supported id behind config, and stand up the one Nebius/NVIDIA speech component that is real for Thai.
Hackathon-safe: every change behind a setting with today's behaviour as the default where a regression could show
in a demo; offline tests only; no change to `models.py`.

Success criteria (all **Recommendation**, measurable on 2026-10-30):

| Criterion | How checked |
| --- | --- |
| One `voice_latency path=… e2e_ms=…` log line per turn on both paths, with per-stage ms | grep the bot and web logs after a 5-minute demo on each path |
| Web turn-end silence ≤ 800 ms (from 2,000) with no rise in cut-offs during Thai pauses on a 20-turn scripted run | `StageTimer` p50 before/after; count of "interrupted while still talking" events |
| Zero Live input tokens while the web mic is muted or idle | `usage_metadata` per turn (prompt audio tokens) during a 2-minute muted interval |
| Barge-in works while `ask_dory` runs on the web (receiver never blocked > 100 ms) | offline test with a slow fake tool + `interrupted` event; manual demo |
| Web call survives a `GoAway` / reconnect with the mic queue intact | offline test with `FakeLive` raising `go_away`; manual 12-minute call |
| `live_model=gemini-3.8-live` works on both paths behind config; 2.5 id stays the default until the `live_eval` run passes (billed, approval) | `tests/dory/live_eval` once; config flags gated on model id |
| Typhoon ASR Realtime serving Thai transcripts from a Nebius L40S; CER vs Gemini measured on one stored meeting | `jiwer` CER report; log line `asr backend=typhoon ms=…` per segment |
| A speech probe script prints TTFA and one ASR segment time against the configured endpoints | `scripts/dory_voice_probe.py` run once (billed, approval) |

### A.2 Assumptions and questions requiring clarification

Assumptions we proceed on (state them in the demo): Thai is the demo language; the Discord room and the web panel both
need to work; the owner accepts one Nebius GPU VM at ~$37/day for the hackathon window; the Gemini Live model id can be
changed for a billed `live_eval` run with the owner's approval.

Questions for the owner (answers change Phase B scope, not Phase A):

1. Is the **hackathon demo** the Discord voice room, the web Live panel, or both? (Instrumentation covers both; polish one.)
2. Is **Thai-only** acceptable for the demo, with English as a stretch? (A Nemotron ASR + Magpie English path on the same L40S is optional.)
3. **Budget**: is one L40S (~$37-44/day on-demand) for 5 days acceptable; may it stay on after the hackathon (Phase C)?
4. **Concurrency target** for Phase B: how many simultaneous web calls and Discord rooms must work? (Today: one web call per person in one process; one Discord room per bot account per guild.)
5. **Data residency**: is Live audio processed in `us-central1` acceptable for the company's data, or must Phase B test `asia-southeast1` / `global` for `gemini-3.8-live` (region check marks were unreadable on the locations page)?
6. May the per-segment Gemini transcription be **turned off** in live mode once Typhoon ASR serves it (it also feeds the name backup and minutes), or must both run until CER is proven?
7. Are the "~1.5 s live / ~11 s classic" figures in `config.py:88-90` from any measurement we can read, or comments only?
8. Is a billed `live_eval` run (real Gemini Live + Cloud TTS) authorised this week, and roughly how many minutes?

### A.3 Recommended architecture and rationale

No architectural change in Phase A. Both paths stay: browser / Discord audio -> Gemini Live (server VAD, native audio
out) -> `ask_dory` -> ADK agent on Nemotron -> tool response -> model speech. Phase A adds:

- a `StageTimer` per turn on both paths (one log line, counts only, never content),
- a mic gate on the web path (send while voiced + tail, one `audio_stream_end`, drop while muted / idle),
- a configurable web `silence_duration_ms` (default 800, today 2,000),
- a non-blocking tool runner on the web path (copying the Discord `_on_tool_call` shape, `live_voice.py:2109-2125`) with cancellation on `interrupted`,
- session resumption + reconnect on the web path (copying `LiveVoice.run`, `live_voice.py:1272-1311`),
- `live_model` switchable to `gemini-3.8-live` with the 2.5-only flags gated on the model id,
- an ASR backend switch in `transcribe_heard` (`meeting.py:596-611`): `DORY_ASR_URL` set -> Typhoon ASR service on Nebius, else today's Gemini path; Gemini stays the fallback on any error,
- a probe script for speech endpoints.

Rationale: phase 0 found these eight items to be the highest-value, lowest-risk changes (improvements #1-#4, #7, #10),
the literature says the controller and the measurement, not the model family, decide manners and latency
[@lin2025full] [@ma2024language], and the vendor guidance (500-800 ms silence, 20-40 ms chunks, NON_BLOCKING tools) is
explicit and current.

### A.4 Alternatives considered

| Alternative | Pros | Cons | Decision |
| --- | --- | --- | --- |
| Replace Gemini Live with an ASR -> Nemotron -> TTS cascade on Nebius for the demo | all-Nebius story; control | no Thai TTS on NVIDIA; no Thai EoT model; classic path is ~11 s today and nothing streams; 5 days | No (Phase C experiment) |
| Switch to OpenAI gpt-realtime-2.1 / gpt-live-1 | semantic VAD; Thai; same delegation pattern | $0.048-0.05/min vs $0.011; new vendor; no Nebius story | No |
| Fine-tune Nemotron 3.5 ASR Streaming on Thai (adaptation-ready tier) | real "Thai on Nemotron Speech" | ≥10 h labelled audio floor, tokenizer-ready 40-locale fine-tune + export + eval; not a week's work (Assumption) | No (Phase C candidate) |
| Parakeet 1.1B RNNT Multilingual NIM for Thai | NVIDIA-branded Thai ASR, streaming | Thai WER unpublished (gated card), 13-50 GB pulls, NVAIE for production | Probe only if time remains |
| Batch web frames to 100-200 ms | fewer API sends | conflicts with Google's 20-40 ms guidance; adds up to 200 ms | No; stop sending zeros instead |
| Do nothing on the model id until December | zero risk this week | leaves 6 weeks for an untested migration; 3.8's NON_BLOCKING default changes tool behaviour | No; land behind config now |

### A.5 Implementation plan (prioritised; S < 1 day, M 1-2 days)

| # | Task | Where (phase 0 refs) | Effort | Risk | Owner-visible result |
| --- | --- | --- | --- | --- | --- |
| A1 | `StageTimer`: marks `speech_end` (last voiced frame sent), `tool_call`, `tool_result`, `first_audio` (first model chunk accepted), `first_play` (first non-silent `LiveAudioSource.read` / browser `metric` message); one log line per turn; p50/p95 by `scripts` grep | `live_voice.py:1577-1580`, `2302-2306`, `542-559`, `2578-2602`; `web_live.py:235-260`; `center.html:2039-2049` (post `{"type":"metric","first_play_ms":…}`); `meeting.py:2185`; `speech.py:257` | S | low | numbers |
| A2 | Web `silence_duration_ms` -> setting `live_web_silence_ms` default **800**; keep start sensitivity HIGH, end LOW; record cut-off events | `web_live.py:38`, `177-190`; `config.py` | S | medium (Thai pause cut-offs) | ~1.2 s less dead air per web turn (Assumption) |
| A3 | Mic gate: browser stops posting frames while muted (`center.html:1952-1967`); server `MicGate` in `_send` sends while voiced + tail (`max(1.0, silence/1000 + 0.8)` s, same as `live_voice._idle_s`), then one `audio_stream_end`, then drops | `web_live.py:210-223` | S | low | idle input tokens -> 0 |
| A4 | `ToolRunner`: `ask_dory` as a background task, `send_tool_response` later; cancel on `interrupted` and on `close`; declare `behavior: NON_BLOCKING` when the model is 3.8 | `web_live.py:239-240`, `262-280` | S | low | barge-in during thinking |
| A5 | Web resumption + reconnect loop with `BACKOFF_S` (0.5, 1, 2, 4), resumption handle, `GoAway` -> reconnect, keep the mic queue; browser shows "reconnecting" instead of ending | `web_live.py:160-175`, `193-208`; `center.py:4476-4496`; `center.html:2082-2098` | M | medium | calls survive 10-minute connection limit |
| A6 | `live_model` to `gemini-3.8-live` behind config; gate `proactive_audio` / `enable_affective_dialog` on `model.startswith("gemini-3.8")`; run `live_eval` once (billed, approval); keep 2.5 as rollback until 2026-12-13 | `config.py:92`; `live_voice.py:1257-1261`; `web_live.py:160-175` | S + eval | medium (behaviour change) | supported model, measured TTFA delta |
| A7 | **Nebius showcase**: provision `gpu-l40s-a` (eu-north1), run a tiny FastAPI service (`POST /transcribe` 16 kHz WAV -> text; NeMo `ASRModel.from_pretrained("scb10x/typhoon-asr-realtime")`); Dory: `DORY_ASR_URL` backend in `transcribe_heard`, Gemini fallback, per-segment `asr backend=… ms=…` log; CER vs Gemini on one stored meeting with `jiwer` (CER; PyThaiNLP `newmm` for WER) | `meeting.py:596-611`, `883-893`; new `scripts/dory_asr_eval.py` (read-only on Firestore) | M | medium (eu RTT ~150-250 ms per segment, Assumption; model load) | Thai transcripts on Nebius + NVIDIA architecture |
| A8 | `scripts/dory_voice_probe.py`: one Live round trip (connect ms, TTFA for a canned Thai utterance) + one ASR segment against both backends; prints ms only | new; pattern of `scripts/dory_nemotron_probe.py` | S | low (billed, approval) | the numbers for the pitch |

Deferred to Phase B on purpose: resampling fix (#5), server-side stop on code barge-in (#6, API semantics unverified),
monitor telemetry (#8), dedicated executor (#9), removing the duplicate ASR entirely (#7 second half).

### A.6 Code examples (typed, tested, runnable)

The five examples below live in `examples/voice_examples.py` next to this report and pass on Python 3.12 with
`uv run --no-project --python 3.12 --with pytest python -I -m pytest -q docs/research/voice-to-voice/phase6_report/examples`
(5 passed on 2026-10-25). They are stdlib only and match the repo's style (asyncio, dataclasses, offline pytest).
Nothing under `src/` or `tests/` was changed; wiring them in is Phase A work.

**A1. `StageTimer`** — one log line per turn, never content.

```python
import logging, time
from collections.abc import Callable
from dataclasses import dataclass, field

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
        parts += [f"{a}->{b}={self.ms(a, b)}" for a, b in zip(order, order[1:])]
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
```

Wiring: Discord `speech_end` = last `Mixer.pop` with voice in `_sender` (`live_voice.py:1577-1580`); `first_audio` =
first chunk accepted by `_gate_audio`; `first_play` = first non-silence `LiveAudioSource.read`. Web: `speech_end` =
the `MicGate` `SEND_END` frame; `first_audio` = first binary chunk in `_on_message`; `first_play` from the browser's
`metric` message. Log at `turn_complete`.

**A3. `MicGate`** — stop streaming silence; mirror of `live_voice._sender`'s idle tail for the web path.

```python
import math
from array import array
from dataclasses import dataclass
from enum import Enum


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
```

`shortcut: RMS threshold 250 is Dory's name-gate value (config name_min_rms), not a VAD; upgrade to Silero VAD in Phase B when the false-start rate is measured.`

**A4. `ToolRunner`** — `ask_dory` off the receive loop, cancelled on interruption.

```python
import asyncio
from collections.abc import Callable


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
        except Exception:  # the person must hear an honest failure
            log.warning("ask_dory failed (%s)", call_id)
            await self._respond(call_id, {"error": "could not get the answer right now"})
        finally:
            self._jobs.pop(call_id, None)

    def interrupt(self) -> int:
        n = len(self._jobs)
        for t in self._jobs.values():
            t.cancel()
        return n


def test_tool_runner_cancels_on_interrupt():
    async def main():
        sent: list[tuple[str, dict]] = []

        async def respond(cid: str, body: dict) -> None:
            sent.append((cid, body))

        async def slow(_: str) -> str:
            await asyncio.sleep(10)
            return "late"

        r = ToolRunner(slow, respond)
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
```

On `gemini-3.8-live` the tool declaration carries `behavior: NON_BLOCKING` (the default) and the response
`scheduling: WHEN_IDLE`, so a late answer waits for the person to finish (Confirmed in the 3.8 guide). `ask` wraps
today's `asyncio.to_thread(self.ask, question)` with `TOOL_TIMEOUT_S` 90 unchanged.

**A7 (sketch, not a test): ASR backend switch** in `transcribe_heard` (`meeting.py:596-611`): when `settings.asr_url`
is set, POST the FLAC bytes to it with a 10 s timeout and parse `{"text": …}`; on any exception log
`asr backend=typhoon failed=<ExceptionType>` and fall through to the Gemini call that exists today. One function,
one setting, one log line; no new abstraction.

### A.7 Performance risks, bottlenecks, mitigations

| Risk | Evidence | Mitigation |
| --- | --- | --- |
| Cutting web silence to 800 ms clips Thai thinking pauses | Google: 100-200 ms fragments utterances; Full-Duplex-Bench shows even Gemini Live misses turns 35 % of the time on real conversation [@lin2025full] | start at 800, measure cut-offs with `StageTimer` + `interrupted` counts; 600 only if the rate holds |
| `gemini-3.8-live` TTFA is ~0.5 s slower than 2.5 native audio | AA 1.18 vs 0.63 s (Secondary) | measure on Dory's turns before switching the default; fillers for tool turns; 2.5 stays rollback until 2026-12-13 |
| Typhoon ASR on eu-north1 adds RTT per segment | no SEA region (Confirmed); 150-250 ms Assumption | transcripts are not on the live-turn path; batch segments ≤ 20 s already; Gemini fallback |
| Event-loop CPU: pure-Python mixing per 20 ms frame per speaker | `live_voice.py:435-490` | not touched in A (Phase B #5); watch loop lag in the `StageTimer` deltas |
| Reconnect loop re-sends buffered mic audio out of order | `WebLive.feed` drops oldest at 200 frames | drain the queue to the new session in order; `audio_stream_end` resets the turn |
| `live_eval` costs and flakiness | real Live + Cloud TTS | one run, owner approval, counters already in `voice_harness.py` |

### A.8 Security, privacy, operational considerations

- No new data at rest: audio is never persisted on either path today (memory-only `Transcript`, 3 h) and the Typhoon
  service must keep that: process in memory, return text, log counts only.
- The Nebius VM is a new network boundary: bind the ASR service to a private address or protect it with a shared
  token in `DORY_ASR_TOKEN` (Secret Manager, never on a command line), TLS via Cloud Run egress or an SSH tunnel for
  the hackathon; firewall to the bot's egress IP.
- `StageTimer` and the mic gate log numbers only; never transcript text.
- Keep `max-instances=1` on the web service (finalize lock + `_live_open`) until Phase B moves Live out.
- Model-id change is a behaviour change: announce in the demo notes; keep the rollback id in config.
- Costs: Live input tokens fall (mic gate); one L40S ≈ $37/day; `live_eval` minutes are billed; the probe script is billed.

### A.9 Evaluation metrics and benchmark methodology

| Metric | Definition | How (Phase A) |
| --- | --- | --- |
| E2E latency | `speech_end -> first_audio` and `-> first_play`, per path, p50 / p95 over ≥ 20 turns | `StageTimer` lines; grep to a small script |
| Turn-end wait | `speech_end -> server turn end` proxy = `speech_end -> first_audio` minus model TTFA from the probe | same |
| Cut-off rate | `interrupted` events raised by the server while the person was still speaking / total turns | log counter |
| Idle cost | prompt audio tokens per minute while muted (`usage_metadata`) | before/after A3 |
| Thai ASR quality | CER (jiwer) of Typhoon vs Gemini against a human-checked reference on one stored meeting; WER with PyThaiNLP `newmm` as a secondary | `scripts/dory_asr_eval.py` (read-only) |
| Brain latency | existing "ask_dory answered in %.1fs" | unchanged |

### A.10 Next steps

1. Confirm questions 1-3 and 8 (demo path, Thai-only, GPU budget, `live_eval` approval).
2. Land A1-A4 (one PR, offline tests), then A5-A6 (second PR), then A7-A8 (third PR + the Nebius VM).
3. Run the probe and a 20-turn scripted demo on each path; paste the `voice_latency` p50/p95 into the pitch.

---

# Phase B — Production voice service (November -> 2026-12-13)

### B.1 Goals and success criteria

Goal: a voice path that is observable, bounded, recoverable and affordable, with the Gemini 2.5 Live id gone before
its retirement. Success (Recommendation): p50 ≤ 1.5 s / p95 ≤ 2.5 s `speech_end -> first_play` on non-tool turns on
both paths (Assumption: reachable with 3.8 Live + 700-800 ms silence); barge-in stop-playback < 200 ms locally;
zero sessions lost to `GoAway`; every voice session visible in `/center` monitor with reconnects, fallbacks and job
counts; load test of 20 concurrent web calls on one instance without transcription stalls; per-org and per-guild voice
minute caps enforced; audio never persisted (documented and tested).

### B.2 Assumptions and questions

Assumptions: the owner wants Discord and web both in production; Firestore remains the one store; Cloud Run stays the
platform. Questions: concurrency target (A.2 #4); data residency (A.2 #5); whether a second Cloud Run service for web
Live is acceptable (cost, ops); whether helper bot accounts (`VoicePool`) exist in production (phase 0 open question 7).

### B.3 Recommended architecture

Smallest change first, larger one only if the load test fails:

- **B-small (default):** keep voice in the bot process and the web service; add a dedicated `ThreadPoolExecutor` for
  voice ASR/TTS/`qa.ask` (`meeting.py:2185`, `live_voice.py:2442`), replace the pure-Python DSP with `audioop.ratecv`
  (already in the lock as `audioop-lts`) or numpy, bound every queue with a logged drop counter (`QUEUE_MAX` 60,
  `MAX_QUEUE` 200 exist), and implement graceful shutdown: SIGTERM -> stop accepting, finish or cancel tool jobs,
  close Live sessions, persist meeting records (`MeetingManager.shutdown` exists, `meeting.py:1776-1807`).
- **B-large (if the load test fails):** move web Live to its own Cloud Run service (`dory-live`, WebSocket, session
  affinity), with `_live_open` in a Firestore document instead of a process set, so the finalize-locked web service no
  longer shares CPU with audio. Discord voice cannot leave the bot's gateway session; parallel rooms scale with
  `VoicePool` helper accounts (exists) and, if ever needed, a second worker pool running only helper accounts that call
  the main bot for `ask_dory` over HTTP (a real architecture change: labelled Recommendation-if-needed).
- **Turn-end for Thai:** Gemini server VAD at 600-800 ms, start sensitivity HIGH, end LOW; a Silero VAD gate on the
  server side of the web path (replacing the RMS shortcut) to stop false starts; no semantic EoT (none exists for Thai).
- **Barge-in:** keep Dory's engineered controller (partner-only, RMS + duration, stop words) which the evidence favours
  [@lin2025full]; add the server-side stop so the muted turn stops billing (verify `activity_end` / cancel semantics
  first, phase 0 #6); cancel `ask_dory` on interruption on both paths.
- **Model:** `gemini-3.8-live` default on both paths; remove the 2.5 id and the affective flags before 2026-12-13.
- **ASR:** Typhoon ASR Realtime on Nebius for transcripts / captions (Phase A), duplicate Gemini per-segment ASR off in
  live mode once CER is proven; Typhoon Whisper Large-v3 (offline) as the accuracy pass for minutes if the licence allows.
- **TTS (classic / fillers):** Chirp 3 HD streaming in `asia-southeast1` (GA, Thai) instead of whole-utterance REST at
  `global` (`speech.py:212-244`), so fillers and classic answers start in tens of ms.

### B.4 Alternatives considered

| Alternative | Pros | Cons | Decision |
| --- | --- | --- | --- |
| Pipecat or LiveKit Agents as the orchestrator | VAD, interruption, transports, telemetry built in; NVIDIA's own reference uses Pipecat | neither has Thai turn detection; Discord voice receive is not a transport they ship; rewrite of a 6,000-line working path | Not in B; evaluate in C as the harness for the cascade experiment |
| OpenTelemetry tracing for every stage | per-stage spans | Dory has no collector; the workflow monitor exists and is the owner's dashboard | Log lines + monitor source first; OTel only if a collector appears |
| Free-threaded Python for the audio path | parallel DSP | GIL re-enables on any unmarked extension; no cp314t for sherpa-onnx; torch no cp315 | No; stay 3.12, use the executor |
| Self-host the whole loop on one H100 | residency, cost at scale | no Thai TTS / EoT; $108/day idle; nemotron-voice-agent needs 4x B200 for 0.9 s | No (Phase C decides with data) |

### B.5 Implementation plan

| # | Task | Where | Effort |
| --- | --- | --- | --- |
| B1 | Dedicated voice executor; `audioop.ratecv` resampling and vectorised mix; browser `AudioContext({sampleRate:16000})` where supported | `meeting.py:2185`, `live_voice.py:435-490`, `450-457`, `center.html:1955-1965` | M |
| B2 | Graceful shutdown + bounded queues with drop counters; `interrupted` cancels `ask_dory` on Discord too | `meeting.py:1776-1807`, `live_voice.py:1679`, `2650-2678` | M |
| B3 | Monitor: register a `voice` source in `monitor_sources.py` (session start/end, mode live/classic, reconnects, fallbacks, jobs, dropped segments, p50/p95 e2e from `StageTimer`); heartbeat voice counters; attention rules (stuck > 30 min, fallback rate > 20 %) | `monitor_sources.py`, `monitor_bot.py`, `meeting.py:1444-1557` | M |
| B4 | Load tests: synthetic PCM clients against `/live` with `FakeLive` (CPU / loop lag), then a 10-minute billed run with 5 real sessions (approval); Discord via `tests/dory/live_eval` | new `scripts/dory_live_load.py` | M |
| B5 | Cost caps: per-org and per-guild voice minutes per day in `dory_media_usage` (same `StoredDailyBudget` pattern as images); polite refusal line in i18n (th + en) | `imagegen_bot.py` pattern, `center.py:4389-4437`, `meeting.py` join | S |
| B6 | WebSocket hardening: per-person connect rate (`TokenBucket` from `monitor_api.py`), origin check, 30 min cap (exists), idle timeout, `_live_open` in Firestore if B-large | `center.py:4389-4437` | S |
| B7 | Data governance: document "audio never persisted" and test it (no file writes in the voice modules); Live transcripts follow guild `memory_retention_days`; residency decision from A.2 #5 (test `asia-southeast1` / `global` for 3.8 Live) | docs + tests | S |
| B8 | Model migration complete: 3.8 default, 2.5 removed, flags gone; Chirp 3 HD streaming for classic TTS and fillers | `config.py`, `speech.py:212-244` | M |
| B9 | Server-side stop on code barge-in (after verifying semantics in a probe) and removal of the duplicate ASR in live mode | `live_voice.py:2650-2657`, `meeting.py:2181-2187` | S + probe |
| B10 | Upstream watch: `discord-ext-voice-recv` and `davey` releases vs discord.py DAVE changes; pin and test on each bump | `pyproject.toml` | S recurring |

### B.6 Code examples

The Phase A examples carry over (StageTimer feeds B3; ToolRunner's `interrupt()` is B2 on Discord). The one new
piece is the Silero end-pointer the web path uses instead of the RMS shortcut (probabilities injected, so the test is offline):

```python
from dataclasses import dataclass
from enum import Enum


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


def enumerate_probs(probs: list[float], chunk_ms: int = 32):
    for i, p in enumerate(probs):
        yield i * chunk_ms, p


def test_end_pointer_emits_once_and_ignores_blips():
    ep = EndPointer(silence_ms=600, min_speech_ms=200)
    out = [ep.push(p, t) for t, p in enumerate_probs([0.9] * 20 + [0.1] * 30)]  # 32 ms chunks
    assert out[0] is Turn.START
    assert out.count(Turn.END) == 1
    assert out.index(Turn.END) == 20 + 600 // 32  # first chunk at or past 600 ms of silence
    blip = EndPointer(silence_ms=600, min_speech_ms=200)
    out2 = [blip.push(p, t) for t, p in enumerate_probs([0.9] * 3 + [0.1] * 30)]  # 96 ms blip
    assert Turn.END not in out2
```

`prob` comes from `silero_vad` (`model(chunk, 16000).item()`, 512-sample chunks at 16 kHz = 32 ms; MIT, <1 ms per
chunk, Confirmed README). On the Discord path the same class can gate `audio_stream_end` instead of the fixed 1.8 s
tail in `_sender`.

### B.7 Performance risks, bottlenecks, mitigations

| Risk | Mitigation |
| --- | --- |
| Loop lag from DSP + 25 sends/s per web session + Discord frames per speaker | B1 executor and vectorised DSP; load test B4 before raising caps; B-large if lag > 50 ms at target concurrency |
| Thread-pool starvation across chat and voice | dedicated executor sized from the load test; log queue depth |
| Live connection churn (~10 min) under load | resumption handles (Phase A5) + jittered reconnects; cap reconnects per session |
| Cost growth with session length (per-turn context re-billing, Hypothesis 1.5-3x) | context-window compression on (exists); B5 caps; read `usage_metadata` per turn into the monitor |
| Thai cut-offs after shortening silence | measure cut-off rate per week; keep 700-800 ms unless the rate is < 5 % |
| Nebius GPU idle cost | scale to zero outside office hours (cron), or fall back to Gemini ASR when the VM is off |

### B.8 Security, privacy, operational considerations

- WebSocket: Bearer + org + licence checks exist (`center.py:4389-4437`); add connect rate limit, origin check, idle
  timeout; one session per person must survive a second instance (Firestore flag) before any scale-out.
- Secrets: the Nebius ASR token and any new keys only via Secret Manager (`scripts/deploy.sh` pattern: add a version
  only when none exists); never logged.
- Privacy: audio never persisted (test); transcripts and Live transcriptions follow the guild's retention; the `voice`
  monitor source carries account keys and counts only (monitor rules, `monitor.py`).
- Residency: Live audio processed in `us-central1` today; decide with A.2 #5; Chirp 3 HD and Typhoon can run in Asia / EU.
- Operations: runbook for Live outages (classic fallback exists), model retirements (calendar the 2026-12-13 date),
  Nebius VM restart (model warm-up time logged), cost alerts from the daily caps.
- Abuse: caps per org/guild/person; refuse new sessions over cap with an i18n line; `TokenBucket` on connects.

### B.9 Evaluation metrics and benchmark methodology

| Metric | Target (label) | Method |
| --- | --- | --- |
| `speech_end -> first_play` p50 / p95, non-tool turns, per path | ≤ 1.5 s / ≤ 2.5 s (Recommendation; Assumption reachable) | `StageTimer` over a weekly 50-turn scripted Thai set + production logs |
| Time to first audio (model only) | measured, not targeted (Secondary baseline 1.18 s for 3.8) | probe script weekly |
| Barge-in stop time | < 200 ms from `interrupted` / code trigger to silence (Recommendation) | `StageTimer` mark `barge_in -> stopped` |
| Cut-off rate on Thai pauses | < 5 % of turns (Recommendation) | counter |
| Thai CER (transcripts) | ≤ Gemini's on the same meeting; absolute ≤ 10 CER on clean meeting audio (Hypothesis, Typhoon reports 6.8-13.9 by set) | `jiwer` on consented clips with human reference |
| TTS quality proxy | UTMOS ≥ 3.5 on Thai samples (Hypothesis: UTMOS is English-trained; use as a relative gate only) + a 5-person Thai MOS panel | `speechmos` / listening test |
| Task accuracy | ≥ 90 % correct on a 50-item Thai spoken business QA set (VoiceBench-style, translated AlpacaEval items + Dory ledger questions), GPT-judge + human spot check (Recommendation) | monthly |
| Concurrent sessions | 20 web calls + 2 Discord rooms on one instance with loop lag < 50 ms (Recommendation) | B4 load test |
| CPU / memory | < 70 % CPU, no growth over a 30-minute call (Recommendation) | Cloud Run metrics |
| Error / recovery | < 1 % sessions ended by error; reconnect < 5 s (Recommendation) | monitor source |
| Cost per conversation minute | Gemini floor $0.011 (Confirmed inputs); all-in ≤ $0.03 including brain tokens and ASR (Recommendation); measured from `usage_metadata` + Nebius hours / stream-minutes | monthly |

### B.10 Next steps

1. Answer A.2 #4 and #5 (concurrency, residency) to pick B-small vs B-large and the Live region.
2. B1-B3 first (they make B4 measurable), then B4 decides B-large, then B5-B10.
3. Calendar 2026-12-01 as the last day to flip the default model and remove the 2.5 id.

---

# Phase C — Hybrid cascade option (2027 Q1, experimental)

### C.1 Goals and success criteria

Goal: find out, with Dory's own numbers, whether a Thai cascade (self-hosted streaming Thai ASR -> Nemotron brain ->
streaming Thai TTS, Silero end-pointing) beats Gemini Live on latency, cost or control at equal answer quality.
Decision gate (Recommendation): adopt the cascade for a path only if, on the same 50-turn Thai set, it is ≥ 300 ms
faster at p50, no worse on task accuracy and cut-off rate, and ≤ cost per minute at the expected concurrency.
Sub-800 ms p50 is the stretch bar [industry "800 ms rule", Secondary]; the evidence says it needs Bangkok-side GPUs
and a fast brain (section 4.3 of the synthesis).

### C.2 Assumptions and questions

Assumptions: Nebius still has no SEA region (adds RTT to every stage); Chirp 3 HD remains the only production-grade
streaming Thai TTS; Nemotron on Token Factory streams tokens. Questions: is a Google-hosted TTS acceptable inside an
otherwise self-hosted cascade, or must Thai TTS be open (F5-TTS-THAI, weaker, not streaming)? Is a GPU closer to
Thailand available (any provider) for the latency experiment? Does the company want residency enough to pay for an
idle GPU?

### C.3 Recommended architecture (experiment)

```
mic / Discord 16 kHz ─► Silero VAD EndPointer (600 ms) ─► Typhoon ASR Realtime (streaming partials, L40S)
        │                                                   │ final text at turn_end (+ partials for early LLM start)
        │                                                   ▼
        │                                     Nemotron 3 Super (Token Factory, streamed tokens, same ADK tools)
        │                                                   │ sentence_chunker (≥ 24 chars at a clause break)
        │                                                   ▼
        │                                     Chirp 3 HD streaming th-TH (asia-southeast1)  [or F5-TTS-THAI if open-only]
        ▼                                                   ▼
   barge-in: VAD speech_start while speaking ─► cancel LLM stream + TTS, flush playout (< 200 ms)
   English turns: Nemotron ASR Streaming + Magpie via NeMo-Speech.cpp on the same L40S (optional)
```

Rationale: this is family C in the taxonomy, the convergent design of the 2025-2026 literature (cascade kept for
intelligence and tools, VAD gate replaced by a learned or at least tuned end-pointer, every stage streaming)
[@yang2026duplexcascade] (preprint), [@noroozi2024stateful], [@shikhar2025llmvox], [@du2024cosyvoice] (preprint). For
Thai the end-pointer is silence-only (no model exists) and the TTS is Google's unless open voices improve.
Alternative understanding stage to A/B: Ultravox-8B on vLLM (MIT, Thai audio in, text out) replacing ASR + brain for
simple turns; it is the only open audio-LLM with Thai input and a commercial licence (phase 4).

### C.4 Alternatives considered

| Alternative | Pros | Cons | Decision |
| --- | --- | --- | --- |
| Fine-tune Nemotron 3.5 ASR Streaming on Thai (adaptation-ready tier) | true "Thai on Nemotron Speech", 80 ms chunks, NIM / NeMo-Speech.cpp serving | needs ≥ 10 h labelled Thai (Common Voice th, FLEURS, Gowajee exist), tokenizer-ready fine-tune, export, eval; Typhoon's ~10k h corpus is not public | Run as a side experiment if the team has the data budget; Typhoon is the baseline |
| Open Thai S2S (Typhoon2-Audio) | one model | speech output CC-BY-NC; no realtime story; 8B | No |
| Full-duplex English demo (Moshi / PersonaPlex / VoiceChat-11B) | true barge-in, 200-450 ms | English only; 7-11B GPU; no Thai | Demo only, if ever |
| Pipecat as the experiment harness | Smart Turn for English, transports, metrics; NVIDIA's blueprint shape | no Thai turn model; Discord transport to write | Yes for the harness (ESPnet-SDS is the academic alternative) |

### C.5 Implementation plan

| # | Task | Effort |
| --- | --- | --- |
| C1 | Thai eval set: 50 consented meeting-style turns (Thai, some code-switching), human reference transcripts, expected answers; VoiceBench-style 50 Thai QA items; Full-Duplex-Bench-style pause and interruption clips (TOR and latency protocol from [@lin2025full]) | M |
| C2 | Streaming Typhoon ASR service with partials (WebSocket), on the Phase A L40S | M |
| C3 | Cascade runner (Pipecat pipeline or a small asyncio pipeline reusing `qa.ask_async` with token streaming) + `sentence_chunker` + Chirp 3 HD streaming + Silero `EndPointer`; barge-in = cancel + flush | L |
| C4 | A/B harness: same audio into Gemini Live (3.8) and the cascade; `StageTimer` on both; CER, task accuracy, TOR, cut-offs, cost | M |
| C5 | Optional: Nemotron ASR + Magpie English path via NeMo-Speech.cpp; Ultravox understanding stage; Nemotron 3.5 ASR Thai fine-tune | L each |
| C6 | Decision memo against the gate in C.1 | S |

### C.6 Code example — Thai-aware sentence chunker for streaming TTS (tested)

```python
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
```

`shortcut: clause breaks only at spaces and punctuation; Thai particles (ค่ะ/ครับ/นะ) are not boundaries here, upgrade with PyThaiNLP sentence segmentation if TTS prosody suffers.`

### C.7 Performance risks, bottlenecks, mitigations

| Risk | Evidence | Mitigation |
| --- | --- | --- |
| Cascade is not faster than Gemini Live from Thailand | every stage adds network to eu-north1 + us/asia Google TTS; NVIDIA needed 4x B200 for 0.9 s | measure first (C4); try a Thailand-adjacent GPU; accept "not faster, but cheaper/controllable" as a valid outcome |
| Silence-only end-pointing cuts Thai pauses | no Thai EoT model; VAD "trigger-happy" on backchannels [@xia2026semantic] | 600-800 ms; partial-transcript heuristics (sentence-final particles) as a cheap semantic hint; measure TOR |
| TTS first-packet latency | CosyVoice 2 gives a formula not a number (preprint); F5-TTS-THAI has no latency figure | Chirp 3 HD streaming; chunk at ≥ 24 chars; measure TTFA per chunk |
| Streaming LLM tokens with tool calls | tool rounds block speech | speak a filler on the first tool call (Dory's `FillerWriter` exists); stream only the final answer |
| GPU idle cost | L40S $37/day | share with Phase A ASR; scale to zero off-hours |

### C.8 Security, privacy, operational considerations

Same rules as Phase B, plus: the cascade keeps a text trace of every turn (ASR partials + LLM tokens), which is a
privacy gain (auditable, redactable) and a retention duty (apply the guild's retention; never persist audio);
all three stages can be placed in-region, which is the cascade's real residency argument; model licences: Typhoon ASR
CC-BY-4.0 (attribution), Nemotron OpenMDW / NVIDIA Open Model Licence, Magpie NVIDIA Open Model Licence, Silero MIT,
F5-TTS-THAI CC-BY-4.0 (weights) — avoid OpenJaiTTS / ThonburianTTS / Typhoon2-Audio speech-out (non-commercial).

### C.9 Evaluation metrics and benchmark methodology

Same metric definitions as B.9, applied as a paired comparison on the C1 set: `speech_end -> first_play` p50/p95,
TTFA per stage (ASR final, LLM first token, TTS first packet), TOR on pauses and latency after interruption (protocol
of [@lin2025full]), CER (jiwer; PyThaiNLP `newmm` WER secondary), task accuracy (GPT-judge + human), UTMOS and a
Thai MOS panel, cost per minute (Nebius hours / stream-minutes + Token Factory tokens + Chirp characters, with the
800-characters-per-spoken-minute Thai assumption measured on Dory's transcripts), concurrency per L40S. Report both
arms with identical audio and identical brain prompts; publish the raw `voice_latency` lines with the memo.

### C.10 Next steps

1. Decide the open-only vs Google-TTS question (C.2) and whether residency justifies an idle GPU.
2. Build C1 (the Thai eval set) during Phase B; it is also what B.9 needs.
3. Run C2-C4 in January 2027; write the decision memo against the C.1 gate.

---

## Measurable targets (one table)

| Target | Value | Label | Notes |
| --- | --- | --- | --- |
| E2E `speech_end -> first_audio`, non-tool turns | industry: p50 < 800 ms, p95 < 1,500 ms | Recommendation (industry, Secondary source) | not reachable with any managed S2S model alone (TTFA 0.6-1.3 s, Secondary) |
| Dory Phase A | measured; web turn-end wait cut by ≥ 1 s | Recommendation | from 2,000 ms silence to 800 |
| Dory Phase B | p50 ≤ 1.5 s, p95 ≤ 2.5 s per path | Recommendation; reachability Assumption | 3.8 Live TTFA 1.18 s (Secondary) + 0.7-0.8 s silence |
| Dory Phase C (cascade) | p50 ≤ 1.2 s; stretch < 0.8 s | Hypothesis | needs nearby GPU + fast brain |
| Time to first audio (model) | measured weekly; baseline 1.18 s (3.8), 0.63 s (2.5) | Secondary | probe script |
| Thai ASR CER | Typhoon ≤ Gemini on the same meeting; ≤ 10 on clean meeting audio | Hypothesis | Typhoon paper: 6.8-13.9 by set (preprint) |
| TTS quality | UTMOS ≥ 3.5 relative gate + Thai MOS panel ≥ 4.0 / 5 | Hypothesis (UTMOS English-trained) | |
| Task accuracy | ≥ 90 % on a 50-item Thai spoken QA set | Recommendation | VoiceBench-style; cascade baseline 79 on English VoiceBench (Confirmed) |
| Concurrent sessions | 20 web + 2 Discord rooms per instance, loop lag < 50 ms | Recommendation | B4 load test |
| GPU utilisation (L40S) | ≥ 30 % during office hours or scale to zero | Recommendation | Nebius bills idle |
| CPU / memory (web + bot) | < 70 % CPU; flat memory over a 30-minute call | Recommendation | |
| Error rate / recovery | < 1 % sessions ended by error; reconnect < 5 s | Recommendation | |
| Cost per conversation minute | Gemini Live floor $0.011 (50/50) / $0.0135 always-on; all-in ≤ $0.03 | Confirmed inputs; Assumption arithmetic; Recommendation cap | + Vertex per-turn context re-billing (Hypothesis 1.5-3x), + brain tokens, + ASR; Nebius L40S ≈ $0.026 per busy stream-minute at 1 stream, $0.0026 at 10 |

Arithmetic (Assumption, from confirmed list prices): Gemini audio 25 tokens/s; in = 25 x 60 x 0.5 x $3 / 1e6 =
$0.00225; out = 25 x 60 x 0.5 x $12 / 1e6 = $0.009; total $0.01125 per 50/50 minute; always-on in = $0.0045 -> $0.0135.
L40S $1.55 / 60 = $0.0258 per GPU-minute, divided by concurrent streams.

---

## Clarification questions for the owner (collected)

1. Demo path: Discord room, web Live panel, or both?
2. Thai-only for the demo, English as a stretch?
3. GPU budget: one L40S for the hackathon week; keep it after?
4. Concurrency target for production (web calls, Discord rooms)?
5. Data residency: is `us-central1` Live processing acceptable; test an Asia / global region?
6. May the per-segment Gemini ASR be switched off in live mode once Typhoon CER is proven?
7. Are the "~1.5 s / ~11 s" comments backed by any measurement?
8. Authorise one billed `live_eval` run and the probe script this week?
9. Phase C: Google TTS inside the cascade acceptable, or open-only?
10. Does residency justify an idle GPU, or is cost per minute the only criterion?

---

## Skills found (skills.sh, searched 2026-10-25; none installed)

Reputable, official-publisher hits relevant to this work. Install with `npx skills add <owner/repo@skill> -g -y` if wanted.

| Skill | Installs | Why it is relevant |
| --- | --- | --- |
| `google-gemini/gemini-skills@gemini-api-dev` | 25.1K | official Gemini API skill; Live API changes (3.8) |
| `elevenlabs/skills@text-to-speech` | 16.6K | Thai TTS alternative (v3/v4 voices) |
| `elevenlabs/skills@speech-to-text` | 11.7K | Scribe v2 Realtime Thai |
| `elevenlabs/skills@agents` | 11K | managed cascade reference |
| `elevenlabs/skills@speech-engine` | 6.3K | Realtime v1 (S2S) reference |
| `livekit/agent-skills@livekit-agents` | 4.1K | official LiveKit Agents (Phase C harness alternative) |
| `openai/skills@transcribe` | 3.9K | gpt-live-transcribe reference |
| `openai/skills@speech` | 3.5K | OpenAI TTS / Realtime reference |
| `pipecat-ai/skills@init`, `@talk`, `@deploy` | < 100 each | official Pipecat (NVIDIA's blueprint orchestrator), low install count |

Local skills already installed and used in this research: `nemotron-voice-agent-builder`, `nemotron-speech`,
`nemotron-asr-finetune`, `gemini-live-api`, `nebius-dedicated-endpoint`, `vllm` (none mentions Thai; each says to
fetch the NVIDIA support matrix rather than trust the skill text, which this research did).

---

## Appendix: files, citations, reproducibility

- Evidence: `../phase0_current_system/dory_voice_stack.md`, `../phase1_frontier/frontier.md`,
  `../phase1_frontier/industry_frontier.md`, `../phase2_survey/survey.md`, `../paper_db.jsonl` (82 papers, 51
  peer-reviewed), `../phase3_deep_dive/selection.md` + `deep_dive.md` (12 full-text notes), `../phase4_code/code_repos.md`
  (82 repositories + Python matrix), `../phase4_code/nvidia_nebius_stack.md`, `../phase5_synthesis/synthesis.md` + `gaps.md`.
- Citation keys in this report and in `synthesis.md` / `gaps.md` are those of `references.bib` (generated from
  `paper_db.jsonl`; two entries added by hand: Thai EoT arXiv 2510.04016 and i-LAVA arXiv 2509.20971). `deep_dive.md`
  uses longer keys for the same papers (e.g. `lin2025fullduplexbench` = `lin2025full`, `fang2025llamaomni` =
  `fang2024llama`, `radford2023robust` = `radford2022robust`, `manakul2025enhancing` = `manakul2024enhancing`,
  `qwen2025qwen25omni` = `xu2025qwen`, `wang2024turntaking` = `wang2024turn`).
- Code examples: `examples/voice_examples.py` (5 tests, pass on Python 3.12, stdlib + pytest).
- Prices, model ids and versions were read on 2026-10-25 and will drift; re-check before quoting.
