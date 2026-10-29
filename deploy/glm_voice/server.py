"""GLM-4-Voice voice server for Dory's web Live call: English small talk, no tools (owner, 26 Oct 2026).

Runs INSIDE a GLM-4-Voice checkout (https://github.com/zai-org/GLM-4-Voice) on a GPU machine, next to
its `model_server.py`; see README.md in this folder. Headless copy of the repo's `web_demo.py`
generation loop: utterance -> Whisper-VQ speech tokens -> prompt -> streamed token ids from
model_server -> CosyVoice decoder blocks -> 22.05 kHz wav -> 24 kHz PCM16 to Dory.

One WebSocket `/voice` at a time (one GPU, one stream), `Authorization: Bearer <GLM_VOICE_TOKEN>`.
Dory sends PCM16 mono 16 kHz frames (binary) and JSON {"type": "text", "text"} (a typed turn or the
greeting cue), {"type": "end"} (her mic gate's stream end), {"type": "close"}. It gets PCM16 mono
24 kHz (binary) and JSON {"type": "ready" | "said" | "interrupted" | "turn" | "error", "text"}.
Pure parts (`Endpointer`, `build_prompt`, `split_token`, `pcm16`) run anywhere:
`python server.py --selftest`. Audio is never written anywhere but a temp file that is deleted.
"""

# no `from __future__ import annotations`: FastAPI resolves the `ws: WebSocket` annotation at runtime,
# and WebSocket is imported inside make_app (the pure parts must import without FastAPI)
import argparse
import asyncio
import json
import logging
import math
import os
import re
import shlex
import subprocess
import tempfile
import time
from array import array
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("glm_voice")

IN_RATE, OUT_RATE, DECODER_RATE = 16_000, 24_000, 22_050
MODEL_SERVER = os.environ.get("GLM_MODEL_SERVER", "http://localhost:10000/generate_stream")
TOKEN = os.environ.get("GLM_VOICE_TOKEN", "")
# Never a Linux shutdown: Nebius treats it as a failure, reboots the VM and bills on. The command
# is the Nebius API stop (install.sh sets it); empty = log only.
IDLE_SHUTDOWN_CMD = os.environ.get("GLM_IDLE_SHUTDOWN_CMD", "")
MAX_NEW_TOKENS = 600  # a spoken answer; web_demo used 2000
TEMPERATURE, TOP_P = 0.2, 0.8  # web_demo defaults
BLOCK_SIZES = (25, 50, 100, 150, 200)  # decoder blocks, as web_demo: small first for a quick start
HISTORY_MAX_CHARS = (
    12_000  # the prompt is text + audio tokens; beyond this the conversation restarts
)
FORMAT_RULE = (
    "Do it step by step. First, think about the instruction and respond in a interleaved manner, "
    "with 13 text token followed by 26 audio tokens. "
)
# shortcut: the persona rides on the model's own format prompt (unverified with this model's
# training); if answers degrade, drop it and keep the format rule alone.
PERSONA = (
    "You are Dory, a cheerful company assistant on a voice call. Answer briefly in spoken English, "
    "one or two sentences, and never read lists."
)
AUDIO_TOKEN = re.compile(r"<\|audio_(\d+)\|>")


# ---- pure parts -------------------------------------------------------------------------------
def rms16(frame: bytes) -> float:
    a = array("h", frame[: len(frame) - len(frame) % 2])
    return math.sqrt(sum(x * x for x in a) / len(a)) if a else 0.0  # 3.11 has no math.sumprod


@dataclass
class Endpointer:
    """Collect one utterance from 16 kHz PCM16 frames: it starts at the first voiced frame and ends
    after `silence_s` of quiet (or Dory's explicit end). Too short = noise, dropped."""

    rms_min: float = 250.0
    silence_s: float = 0.8
    min_speech_s: float = 0.3
    _buf: bytearray = field(default_factory=bytearray)
    _speaking: bool = False
    _last_voice: float = 0.0
    _voiced_bytes: int = 0

    def on_frame(self, frame: bytes, now: float) -> str | None:
        """Returns "start" on the first voiced frame of an utterance, "end" when it is over."""
        voiced = rms16(frame) >= self.rms_min
        if voiced:
            self._last_voice = now
            self._voiced_bytes += len(frame)
        if not self._speaking:
            if not voiced:
                return None
            self._speaking = True
            self._buf += frame
            return "start"
        self._buf += frame
        if not voiced and now - self._last_voice >= self.silence_s:
            return "end"
        return None

    def end(self) -> str | None:
        """Dory's mic gate said the stream ended: close the utterance if one is open."""
        return "end" if self._speaking else None

    def take(self) -> bytes:
        """The utterance's PCM (empty when it was too short to be speech) and reset."""
        pcm = bytes(self._buf) if self._voiced_bytes >= self.min_speech_s * IN_RATE * 2 else b""
        self._buf, self._speaking, self._voiced_bytes = bytearray(), False, 0
        return pcm


def build_prompt(history: str, user_input: str, audio: bool) -> str:
    """The exact prompt shape of web_demo.inference_fn, with Dory's persona on the format prompt."""
    kind = "speech" if audio else "text"
    system = f"User will provide you with a {kind} instruction. {FORMAT_RULE}{PERSONA}"
    inputs = history.strip()
    if "<|system|>" not in inputs:
        inputs += f"<|system|>\n{system}"
    return inputs + f"<|user|>\n{user_input}<|assistant|>streaming_transcription\n"


def split_token(token_id: int, audio_offset: int) -> tuple[str, int]:
    """("audio", index) for a speech token, ("text", id) otherwise."""
    return ("audio", token_id - audio_offset) if token_id >= audio_offset else ("text", token_id)


def pcm16(samples) -> bytes:
    """float samples in [-1, 1] (numpy array or list) -> PCM16 little-endian bytes."""
    out = array("h", (int(max(-1.0, min(1.0, float(x))) * 32767) for x in samples))
    return out.tobytes()


def selftest() -> None:
    quiet, loud = bytes(1280), array("h", [3000, -3000] * 320).tobytes()
    ep = Endpointer(silence_s=0.8)
    assert ep.on_frame(quiet, 0.0) is None and ep.take() == b""  # quiet: nothing starts
    assert ep.on_frame(loud, 0.0) == "start"
    for i in range(1, 10):  # 0.36 s of speech
        assert ep.on_frame(loud, i * 0.04) is None
    assert ep.on_frame(quiet, 0.5) is None  # inside the silence window
    assert ep.on_frame(quiet, 1.2) == "end"
    pcm = ep.take()
    assert len(pcm) == 12 * 1280 and ep.take() == b""  # the utterance, then reset
    ep.on_frame(loud, 2.0)
    assert ep.end() == "end" and len(ep.take()) == 0  # one 40 ms blip is not speech
    p = build_prompt("", "<|begin_of_audio|><|audio_1|><|end_of_audio|>", audio=True)
    assert p.startswith("<|system|>\nUser will provide you with a speech instruction.")
    assert "Dory" in p and p.endswith("<|assistant|>streaming_transcription\n")
    p2 = build_prompt(p + "hello<|user|>", "hi", audio=False)
    assert p2.count("<|system|>") == 1  # history keeps its one system prompt
    assert split_token(151352, 151350) == ("audio", 2) and split_token(7, 151350) == ("text", 7)
    assert pcm16([0.0, 1.0, -2.0]) == array("h", [0, 32767, -32767]).tobytes()
    print("selftest ok")


# ---- the GPU side ------------------------------------------------------------------------------
class Models:
    """Everything web_demo.initialize_fn loads, once per process."""

    def __init__(self, model_path: str, tokenizer_path: str, flow_path: str, device: str = "cuda"):
        import sys

        sys.path.insert(0, "./cosyvoice")
        sys.path.insert(0, "./third_party/Matcha-TTS")
        from flow_inference import AudioDecoder
        from speech_tokenizer.modeling_whisper import WhisperVQEncoder
        from transformers import AutoTokenizer, WhisperFeatureExtractor

        self.device = device
        self.glm_tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        self.decoder = AudioDecoder(
            config_path=os.path.join(flow_path, "config.yaml"),
            flow_ckpt_path=os.path.join(flow_path, "flow.pt"),
            hift_ckpt_path=os.path.join(flow_path, "hift.pt"),
            device=device,
        )
        self.whisper = WhisperVQEncoder.from_pretrained(tokenizer_path).eval().to(device)
        self.features = WhisperFeatureExtractor.from_pretrained(tokenizer_path)
        self.audio_offset = self.glm_tokenizer.convert_tokens_to_ids("<|audio_0|>")
        self.end_token = self.glm_tokenizer.convert_tokens_to_ids("<|user|>")

    def speech_tokens(self, pcm: bytes) -> str:
        """16 kHz PCM16 -> "<|begin_of_audio|><|audio_n|>...<|end_of_audio|>" (empty = nothing heard)."""
        import soundfile as sf
        from speech_tokenizer.utils import extract_speech_token

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            sf.write(path, array("h", pcm), IN_RATE, subtype="PCM_16")
            tokens = extract_speech_token(self.whisper, self.features, [path])[0]
        finally:
            os.unlink(path)
        if not tokens:
            return ""
        return "<|begin_of_audio|>" + "".join(f"<|audio_{x}|>" for x in tokens) + "<|end_of_audio|>"


class Turn:
    """One generation, run on a worker thread; `cancel()` stops it at the next token."""

    def __init__(self, models: Models, prompt: str):
        self.m, self.prompt, self.cancelled = models, prompt, False
        self.completion: list[int] = []

    def cancel(self) -> None:
        self.cancelled = True

    def run(self, emit) -> None:
        """emit(kind, payload): ("said", text delta) | ("audio", 24 kHz PCM16 bytes) | ("turn", "")."""
        import requests
        import torch
        import torchaudio

        m, dev = self.m, self.m.device
        body = {
            "prompt": self.prompt,
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "max_new_tokens": MAX_NEW_TOKENS,
        }
        text_tokens: list[int] = []
        audio_tokens: list[int] = []
        said = ""
        prompt_feat = torch.zeros(1, 0, 80).to(dev)
        prompt_tokens = torch.zeros(1, 0, dtype=torch.int64).to(dev)
        mels: list[Any] = []
        block_idx, finalize = 0, False
        uid = f"turn-{time.time_ns()}"
        with requests.post(MODEL_SERVER, json=body, stream=True, timeout=120) as resp:
            for line in resp.iter_lines():
                if self.cancelled:
                    return
                if not line:
                    continue
                token_id = json.loads(line).get("token_id")
                if token_id is None:  # the model server's error line
                    emit("error", "model_server")
                    return
                if token_id == m.end_token:
                    finalize = True
                if len(audio_tokens) >= BLOCK_SIZES[block_idx] or (finalize and audio_tokens):
                    block_idx = min(block_idx + 1, len(BLOCK_SIZES) - 1)
                    tts_token = torch.tensor(audio_tokens, device=dev).unsqueeze(0)
                    if mels:
                        prompt_feat = torch.cat(mels, dim=-1).transpose(1, 2)
                    with torch.no_grad():
                        speech, mel = m.decoder.token2wav(
                            tts_token,
                            uuid=uid,
                            prompt_token=prompt_tokens,
                            prompt_feat=prompt_feat,
                            finalize=finalize,
                        )
                        wav24 = torchaudio.functional.resample(
                            speech.float().cpu(), DECODER_RATE, OUT_RATE
                        )
                    mels.append(mel)
                    prompt_tokens = torch.cat((prompt_tokens, tts_token), dim=-1)
                    audio_tokens = []
                    if not self.cancelled:
                        emit("audio", pcm16(wav24[0].numpy()))
                if finalize:
                    break
                self.completion.append(token_id)
                kind, value = split_token(token_id, m.audio_offset)
                if kind == "audio":
                    audio_tokens.append(value)
                else:
                    text_tokens.append(value)
                    if len(text_tokens) % 13 == 0:  # the model writes text in 13-token blocks
                        full = m.glm_tokenizer.decode(
                            text_tokens, spaces_between_special_tokens=False
                        )
                        emit("said", full[len(said) :])
                        said = full
        full = m.glm_tokenizer.decode(text_tokens, spaces_between_special_tokens=False)
        if full[len(said) :]:
            emit("said", full[len(said) :])
        if not self.cancelled:
            emit("turn", "")


def make_app(models: Models, idle_shutdown_min: int = 0):
    """`idle_shutdown_min` > 0: with no call for that long the machine runs IDLE_SHUTDOWN_CMD (the
    Nebius API stop, set by install.sh), so a forgotten demo GPU stops billing by the hour."""
    from contextlib import asynccontextmanager

    from fastapi import FastAPI, WebSocket
    from starlette.websockets import WebSocketDisconnect

    busy = asyncio.Lock()
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
                    last_active["at"] = (
                        time.monotonic()
                    )  # say it once per idle period, not every minute
                    continue
                log.warning("idle for %d min: running %s", idle_s // 60, IDLE_SHUTDOWN_CMD)
                # the operator's own command from the environment, run without a shell
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
        calls = int(busy.locked())  # one call at a time; same keys as the cascade's /health
        idle_s = round(time.monotonic() - last_active["at"], 1) if calls else None
        return {"ok": True, "busy": busy.locked(), "calls": calls, "idle_s": idle_s}

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
            loop = asyncio.get_running_loop()
            ep = Endpointer()
            history = ""
            turn: Turn | None = None
            gen: asyncio.Future | None = None

            def emit_for(t: Turn):
                def emit(kind: str, payload) -> None:
                    if t.cancelled:
                        return
                    coro = (
                        ws.send_bytes(payload)
                        if kind == "audio"
                        else ws.send_json({"type": kind, "text": payload})
                    )
                    asyncio.run_coroutine_threadsafe(coro, loop)

                return emit

            async def interrupt() -> None:
                nonlocal turn
                if turn is not None and gen is not None and not gen.done():
                    turn.cancel()
                    await ws.send_json({"type": "interrupted", "text": ""})
                    log.info("turn interrupted")

            async def start_turn(user_input: str, audio: bool) -> None:
                nonlocal history, turn, gen
                t0 = time.monotonic()
                history = "" if len(history) > HISTORY_MAX_CHARS else history
                prompt = build_prompt(history, user_input, audio)
                turn = Turn(models, prompt)
                gen = loop.run_in_executor(None, turn.run, emit_for(turn))

                def done(fut: asyncio.Future, t: Turn = turn, p: str = prompt) -> None:
                    nonlocal history
                    err = fut.exception()
                    if err is not None:
                        log.warning("turn failed: %s", type(err).__name__)
                        asyncio.ensure_future(ws.send_json({"type": "error", "text": "turn"}))
                    elif not t.cancelled:
                        history = p + models.glm_tokenizer.decode(
                            t.completion, spaces_between_special_tokens=False
                        )
                    log.info(
                        "turn done ms=%d cancelled=%s", (time.monotonic() - t0) * 1000, t.cancelled
                    )

                gen.add_done_callback(done)

            try:
                while True:
                    msg = await ws.receive()
                    if msg["type"] == "websocket.disconnect":
                        break
                    last_active["at"] = time.monotonic()  # audio or a typed turn = activity
                    data, text = msg.get("bytes"), msg.get("text")
                    act = None
                    if data:
                        act = ep.on_frame(data, time.monotonic())
                        if act == "start":
                            await interrupt()
                    elif text:
                        ev = json.loads(text)
                        if ev.get("type") == "close":
                            break
                        if ev.get("type") == "end":
                            act = ep.end()
                        elif ev.get("type") == "text" and str(ev.get("text", "")).strip():
                            await interrupt()
                            await start_turn(str(ev["text"]).strip()[:500], audio=False)
                    if act == "end":
                        pcm = ep.take()
                        if pcm:
                            tokens = await asyncio.to_thread(models.speech_tokens, pcm)
                            if tokens:
                                await start_turn(tokens, audio=True)
            except WebSocketDisconnect:
                pass
            finally:
                last_active["at"] = time.monotonic()
                if turn is not None:
                    turn.cancel()

    return app


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--model-path", default="THUDM/glm-4-voice-9b")
    ap.add_argument("--tokenizer-path", default="THUDM/glm-4-voice-tokenizer")
    ap.add_argument("--flow-path", default="./glm-4-voice-decoder")
    ap.add_argument("--device", default="cuda")
    ap.add_argument(
        "--idle-shutdown-min",
        type=int,
        default=0,
        help="power the machine off after this many minutes without a call (0 = never)",
    )
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    if not TOKEN:
        raise SystemExit("set GLM_VOICE_TOKEN")
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    models = Models(a.model_path, a.tokenizer_path, a.flow_path, a.device)
    uvicorn.run(make_app(models, a.idle_shutdown_min), host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
