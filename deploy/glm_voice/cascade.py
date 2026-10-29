"""Cascade voice sidecar for Dory: speech-to-text -> Dory's text brain (tools) -> text-to-speech.

GLM-4-Voice (`server.py`) cannot call tools, so a voice turn that must book a flight, read the
calendar or file a receipt runs here instead: the utterance is transcribed on this GPU (NVIDIA
Parakeet-TDT 0.6B v3 through NeMo, or faster-whisper), the text goes to Dory as {"type": "heard"},
Dory's own agent answers (the same `ask_dory` brain as every chat message), and whatever Dory sends
back as {"type": "say"} is spoken sentence by sentence (Kokoro-82M, or NVIDIA Magpie) as PCM16 24 kHz.
Runs next to `server.py` (same folder, its own venv: `install.sh` makes `~/cascade/.venv`), listens on
:8766, same bearer token (`GLM_VOICE_TOKEN`) and the same idle stop, so `glm_voice.GlmVoice` switches
between the two servers by URL alone.

Up (from Dory): PCM16 mono 16 kHz frames (binary) while the person speaks, {"type": "end"} (mic
gate's stream end), {"type": "text", "text"} (a typed turn: answered like speech, i.e. echoed as
"heard"), {"type": "say", "text", "final": bool} (speak this; a filler while the brain works is a
non-final say), {"type": "close"}.
Down: {"type": "ready"}, {"type": "heard", "text"}, PCM16 mono 24 kHz (binary), {"type": "said",
"text"} after each say, {"type": "turn"} after a final say, {"type": "interrupted"} when the person
talks over her, {"type": "error", "text"}.
Pure parts (`split_sentences`, `Endpointer` from server.py, `FakeEngines`) run anywhere:
`python cascade.py --selftest`. Audio is never written to disk.
"""

# no `from __future__ import annotations`: FastAPI resolves the `ws: WebSocket` annotation at runtime
import argparse
import asyncio
import json
import logging
import math
import os
import re
import shlex
import subprocess
import time
from array import array
from collections.abc import Iterator
from typing import Any

from server import IDLE_SHUTDOWN_CMD, IN_RATE, OUT_RATE, TOKEN, Endpointer

log = logging.getLogger("glm_cascade")

SAY_MAX_CHARS = 1200  # a spoken answer; Dory's brain already keeps voice answers short
SENTENCE_MAX = 220
_SENT = re.compile(r"(?<=[.!?。！？])\s+|\n+")


# ---- pure parts -------------------------------------------------------------------------------
def split_sentences(text: str, limit: int = SENTENCE_MAX) -> list[str]:
    """Sentences to synthesize one by one (the first chunk is what the person hears first)."""
    out: list[str] = []
    for part in _SENT.split(text or ""):
        part = part.strip()
        while len(part) > limit:  # a very long sentence: cut at the last space before the limit
            cut = part.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            out.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            out.append(part)
    return out


def tone(seconds: float = 0.1, hz: float = 440.0) -> bytes:
    n = int(OUT_RATE * seconds)
    return array(
        "h", [int(8000 * math.sin(2 * math.pi * hz * i / OUT_RATE)) for i in range(n)]
    ).tobytes()


class FakeEngines:
    """Stand-in for the models: a fixed transcript, a short tone per sentence (tests, selftest)."""

    name = "fake"

    def __init__(self, heard: str = "hello dory") -> None:
        self.heard, self.spoken = heard, []

    def transcribe(self, pcm: bytes) -> str:
        return self.heard

    def synth(self, sentence: str) -> Iterator[bytes]:
        self.spoken.append(sentence)
        yield tone()


def selftest() -> None:
    assert split_sentences("Hi. How are you?  Fine!\nBye") == [
        "Hi.",
        "How are you?",
        "Fine!",
        "Bye",
    ]
    assert split_sentences("") == []
    long = "word " * 100
    parts = split_sentences(long.strip(), limit=50)
    assert all(len(p) <= 50 for p in parts) and " ".join(parts) == long.strip()
    assert len(tone(0.5)) == OUT_RATE // 2 * 2
    ep = Endpointer()
    loud, quiet = array("h", [3000] * 320).tobytes(), bytes(640)
    assert ep.on_frame(loud, 0.0) == "start"
    for i in range(20):
        ep.on_frame(loud, 0.02 * (i + 1))
    assert ep.on_frame(quiet, 2.0) == "end" and ep.take()
    f = FakeEngines("book my trip")
    assert f.transcribe(b"") == "book my trip" and list(f.synth("Sure."))
    print("cascade selftest ok")


# ---- the models (GPU) --------------------------------------------------------------------------
class Engines:
    """Loaded once at start, warmed up once. ASR: `parakeet` (NeMo, nvidia/parakeet-tdt-0.6b-v3,
    CC-BY-4.0, English + 24 European languages) or `whisper` (faster-whisper large-v3-turbo, Thai
    too). TTS: `kokoro` (hexgrad/Kokoro-82M, Apache-2.0, 24 kHz native) or `magpie`
    (nvidia/magpie_tts_multilingual_357m through NeMo, 22.05 kHz resampled to 24 kHz)."""

    def __init__(self, asr: str = "parakeet", tts: str = "kokoro", voice: str = "af_bella,af_heart",
                 device: str = "cuda", speed: float = 1.08) -> None:  # fmt: skip
        import numpy as np

        self.np, self.asr_kind, self.tts_kind, self.voice, self.device = np, asr, tts, voice, device
        self.speed = speed  # Kokoro only; 1.05-1.1 is lively, 0.9-0.95 calm, over 1.15 rushes
        t0 = time.monotonic()
        if asr == "parakeet":
            import nemo.collections.asr as nemo_asr

            self.asr = nemo_asr.models.ASRModel.from_pretrained(
                model_name=os.environ.get("CASCADE_ASR_MODEL", "nvidia/parakeet-tdt-0.6b-v3")
            )
            self.asr.eval()
        elif asr == "whisper":
            from faster_whisper import WhisperModel

            self.asr = WhisperModel(os.environ.get("CASCADE_ASR_MODEL", "large-v3-turbo"),
                                    device=device, compute_type="float16")  # fmt: skip
        else:
            raise SystemExit(f"unknown asr {asr}")
        if tts == "kokoro":
            from huggingface_hub import hf_hub_download
            from kokoro import KPipeline

            for v in voice.split(
                ","
            ):  # fetched up front: the pipeline's own download hung (28 Oct)
                hf_hub_download("hexgrad/Kokoro-82M", f"voices/{v.strip()}.pt")
            self.tts = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", device=device)
        elif tts == "magpie":
            from nemo.collections.tts.models import MagpieTTSModel

            self.tts = (
                MagpieTTSModel.from_pretrained("nvidia/magpie_tts_multilingual_357m")
                .to(device)
                .eval()
            )
        else:
            raise SystemExit(f"unknown tts {tts}")
        log.info("engines loaded asr=%s tts=%s ms=%d", asr, tts, (time.monotonic() - t0) * 1000)
        t0 = time.monotonic()
        self.transcribe(bytes(IN_RATE * 2))  # one warm-up each: the first call is seconds slower
        for _ in self.synth("Ready."):
            pass
        log.info("engines warm ms=%d", (time.monotonic() - t0) * 1000)

    def transcribe(self, pcm: bytes) -> str:
        audio = self.np.frombuffer(pcm, dtype=self.np.int16).astype(self.np.float32) / 32768.0
        if self.asr_kind == "parakeet":
            out = self.asr.transcribe([audio], batch_size=1, verbose=False)
            return (out[0].text if out else "").strip()
        segments, _info = self.asr.transcribe(audio, beam_size=1)
        return " ".join(s.text.strip() for s in segments).strip()

    def synth(self, sentence: str) -> Iterator[bytes]:
        np = self.np
        if self.tts_kind == "kokoro":
            # `voice` may be "a,b": kokoro averages the packs (a softer blend of the A-grade voice)
            for r in self.tts(sentence, voice=self.voice, speed=self.speed, split_pattern=None):
                if r.audio is not None:
                    yield (r.audio.clamp(-1, 1).numpy() * 32767).astype(np.int16).tobytes()
            return
        import torchaudio

        speakers = {"aria": 0, "jason": 1, "john": 2, "leo": 3, "sofia": 4}
        audio, audio_len = self.tts.do_tts(sentence, language="en", apply_TN=True,
                                           speaker_index=speakers.get(self.voice.lower(), 4))  # fmt: skip
        wav = audio[0, : int(audio_len[0])].float().cpu()
        wav24 = torchaudio.functional.resample(wav, 22050, OUT_RATE)
        yield (wav24.clamp(-1, 1).numpy() * 32767).astype(np.int16).tobytes()


# ---- the socket -------------------------------------------------------------------------------
def make_app(engines: Any, idle_shutdown_min: int = 0, max_calls: int = 4, gap_ms: int = 250):
    """`max_calls` concurrent sockets (the web call and a Discord room at the same time; the
    engines are shared and fast), unlike GLM-4-Voice's one stream per GPU. `gap_ms` of silence
    follows every sentence but the last of a say (kokoro inserts none), so a list of facts breathes."""
    gap = bytes(int(OUT_RATE * gap_ms / 1000) * 2)
    from contextlib import asynccontextmanager

    from fastapi import FastAPI, WebSocket
    from starlette.websockets import WebSocketDisconnect

    busy = asyncio.Semaphore(max_calls)  # locked() = every slot taken
    last_active = {"at": time.monotonic()}

    async def idle_watch() -> None:
        while True:
            await asyncio.sleep(60)
            idle_s = time.monotonic() - last_active["at"]
            if not busy.locked() and idle_s > idle_shutdown_min * 60:
                if not IDLE_SHUTDOWN_CMD:
                    log.warning(
                        "idle for %d min and no GLM_IDLE_SHUTDOWN_CMD: the GPU bills on",
                        idle_s // 60,
                    )
                    last_active["at"] = time.monotonic()
                    continue
                log.warning("idle for %d min: running %s", idle_s // 60, IDLE_SHUTDOWN_CMD)
                subprocess.run(shlex.split(IDLE_SHUTDOWN_CMD), check=False)
                return

    @asynccontextmanager
    async def lifespan(_app):
        watcher = asyncio.create_task(idle_watch()) if idle_shutdown_min > 0 else None
        yield
        if watcher is not None:
            watcher.cancel()

    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {
            "ok": True,
            "busy": busy.locked(),
            "calls": max_calls - busy._value,
            "max_calls": max_calls,
            "mode": "cascade",
            "engines": getattr(engines, "name", "gpu"),
        }

    @app.websocket("/voice")
    async def voice(ws: WebSocket):
        if not TOKEN or ws.headers.get("authorization") != f"Bearer {TOKEN}":
            await ws.close(code=4401)
            return
        if busy.locked():
            await ws.accept()
            await ws.send_json({"type": "error", "text": "busy"})
            await ws.close(code=4409)
            return
        async with busy:
            last_active["at"] = time.monotonic()
            await ws.accept()
            await ws.send_json({"type": "ready"})
            ep = Endpointer()
            says: asyncio.Queue = asyncio.Queue()
            speaker: asyncio.Task | None = None
            talking = {"now": False}  # a say is being synthesized or sent

            async def speak_loop() -> None:
                """One say after another; each is synthesized sentence by sentence off the loop."""
                while True:
                    text, final = await says.get()
                    talking["now"] = True
                    t0 = time.monotonic()
                    sentences = split_sentences(text)
                    for i, sentence in enumerate(sentences):
                        if i and gap:
                            await ws.send_bytes(gap)
                        for chunk in await asyncio.to_thread(
                            lambda s=sentence: list(engines.synth(s))
                        ):
                            await ws.send_bytes(chunk)
                    await ws.send_json({"type": "said", "text": text})
                    log.info(
                        "said chars=%d final=%s ms=%d",
                        len(text),
                        final,
                        (time.monotonic() - t0) * 1000,
                    )
                    if final:
                        await ws.send_json({"type": "turn", "text": ""})
                    talking["now"] = says.qsize() > 0

            async def interrupt() -> None:
                """The person talks: drop what is queued, stop what is being spoken."""
                nonlocal speaker
                # only while she speaks or has a say queued: a voice in a quiet room is a new
                # question, never a cancellation of the answer the brain is still writing
                pending = not says.empty() or talking["now"]
                if not pending:
                    return
                while not says.empty():
                    says.get_nowait()
                if speaker is not None and not speaker.done():
                    speaker.cancel()
                    await asyncio.gather(speaker, return_exceptions=True)
                talking["now"] = False
                speaker = asyncio.create_task(speak_loop())
                if pending:
                    await ws.send_json({"type": "interrupted", "text": ""})
                    log.info("interrupted")

            speaker = asyncio.create_task(speak_loop())
            try:
                while True:
                    msg = await ws.receive()
                    if msg["type"] == "websocket.disconnect":
                        break
                    data, text = msg.get("bytes"), msg.get("text")
                    act = None
                    if data:
                        act = ep.on_frame(data, time.monotonic())
                        if act == "start":
                            await interrupt()
                    elif text:
                        ev = json.loads(text)
                        kind = ev.get("type")
                        if kind == "close":
                            break
                        if kind == "end":
                            act = ep.end()
                        elif kind == "text" and str(ev.get("text", "")).strip():
                            await interrupt()
                            await ws.send_json(
                                {"type": "heard", "text": str(ev["text"]).strip()[:500]}
                            )
                        elif kind == "say" and str(ev.get("text", "")).strip():
                            says.put_nowait(
                                (
                                    str(ev["text"]).strip()[:SAY_MAX_CHARS],
                                    bool(ev.get("final", True)),
                                )
                            )
                    if act == "end":
                        pcm = ep.take()
                        if pcm:
                            t0 = time.monotonic()
                            heard = await asyncio.to_thread(engines.transcribe, pcm)
                            log.info(
                                "asr ms=%d chars=%d", (time.monotonic() - t0) * 1000, len(heard)
                            )
                            if heard:
                                await ws.send_json({"type": "heard", "text": heard[:500]})
            except WebSocketDisconnect:
                pass
            finally:
                last_active["at"] = time.monotonic()
                if speaker is not None:
                    speaker.cancel()
                    await asyncio.gather(speaker, return_exceptions=True)

    return app


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument(
        "--asr", default=os.environ.get("CASCADE_ASR", "parakeet"), choices=("parakeet", "whisper")
    )
    ap.add_argument(
        "--tts", default=os.environ.get("CASCADE_TTS", "kokoro"), choices=("kokoro", "magpie")
    )
    ap.add_argument("--voice", default=os.environ.get("CASCADE_VOICE", "af_bella,af_heart"))
    ap.add_argument("--speed", type=float, default=float(os.environ.get("CASCADE_SPEED", "1.08")))
    ap.add_argument(
        "--gap-ms", type=int, default=int(os.environ.get("CASCADE_SENTENCE_GAP_MS", "250"))
    )
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--idle-shutdown-min", type=int, default=0)
    ap.add_argument("--max-calls", type=int, default=int(os.environ.get("CASCADE_MAX_CALLS", "4")))
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    if not TOKEN:
        raise SystemExit("set GLM_VOICE_TOKEN")
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    engines = Engines(a.asr, a.tts, a.voice, a.device, a.speed)
    uvicorn.run(
        make_app(engines, a.idle_shutdown_min, a.max_calls, a.gap_ms),
        host=a.host,
        port=a.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
