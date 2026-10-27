"""The web Live call on self-hosted GLM-4-Voice (`deploy/glm_voice/server.py`) instead of Gemini Live.

Same browser protocol and the same `out(kind, payload)` events as `WebLive`, so `center.py` swaps the
backend when `DORY_GLM_VOICE_URL` is set. Two servers speak this protocol: GLM-4-Voice itself
(`server.py`: English and Chinese small talk, no tools, "heard" never fires) and the cascade sidecar
(`cascade.py`, 27 Oct 2026: speech-to-text on the GPU, then "heard"; with `ask` set, Dory's own
text brain answers, a short filler is spoken at once (`ack_voice_*`), and the answer goes back as
{"type": "say", "final": true} to be spoken). Audio is never stored or logged.

Up: PCM16 mono 16 kHz frames (binary) while the person speaks (`voice_latency.MicGate`), then one
{"type": "end"}; typed turns and the greeting cue as {"type": "text", "text"}. Down: PCM16 mono 24 kHz
(binary) and {"type": "ready" | "said" | "interrupted" | "turn" | "error", "text"}. Before connecting,
a `nebius_vm.VmWaker` (when the Nebius identity settings exist) starts a stopped GPU box and emits
("waking", "") while it boots (about two minutes); "error" "voice_server_down" when it never comes up.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .i18n import CATALOG, t
from .meeting import MeetingManager, Transcript
from .nebius_vm import make_waker
from .speech import speakable
from .voice_latency import Act
from .web_live import TOOL_TIMEOUT_S, WebLive

logger = logging.getLogger(__name__)
ACKS = sorted(k for k in CATALOG if k.startswith("ack_voice_"))
FILLER_AFTER_S = 1.0  # a fast answer needs no filler; a slow one gets one line (C8)
FILLER_MEMORY = 3  # never the same canned line as the last three
HISTORY_WINDOW_S, HISTORY_MAX_CHARS = 180.0, 3000  # as LiveVoice._ask_dory (C9)
PERSON, DORY = "Person", "Dory"
_CUR = {"THB": "baht", "฿": "baht", "USD": "dollars", "$": "dollars", "EUR": "euros", "€": "euros"}
_CUR_RE = re.compile(r"(THB|USD|EUR|[฿$€])\s?(\d[\d,]*(?:\.\d+)?)")


def spoken_form(text: str) -> str:
    """What the TTS reads: `speech.speakable` (markdown, links, emoji, unspoken symbols gone), then
    currencies and percentages as words; Kokoro reads a bare 4-digit number as a year, so the
    thousands separators stay."""
    s = re.sub(r"\s*\n+\s*", ". ", text).replace("..", ".")  # a line break is a sentence end
    s = _CUR_RE.sub(lambda m: f"{m[2]} {_CUR[m[1]]}", speakable(s))
    s = re.sub(r"(\d)\s?%", r"\1 percent", s)
    return re.sub(r"\s+([.,!?])", r"\1", s).strip()  # a removed emoji leaves no gap before the stop


def is_ack(text: str) -> bool:
    """ "ok" / "got it" / "mm-hm" on its own (C5): not a question."""
    return bool(MeetingManager._ACK_RE.match(text or "")) or (text or "").strip().lower() in (
        "mm-hm", "mhm", "uh-huh", "mm", "hmm",
    )  # fmt: skip


# the box is off, still booting, or not listening on that port: one code the pages can word
DOWN_ERRORS = (ConnectionRefusedError, ConnectionResetError, TimeoutError, OSError)
RETRY_S = 10.0  # between connection attempts while the box is off, booting or taken by another call
RETRY_MAX = 180  # 30 min of trying, as long as the room or the call lives (`close` ends it sooner)


def error_code(e: BaseException) -> str:
    """What the person is told: `voice_server_down` for every "no server there" failure (the VM is
    stopped, still installing, or the port is wrong), the exception's name for anything else."""
    if isinstance(e, DOWN_ERRORS):
        return "voice_server_down"
    status = getattr(e, "status_code", None) or getattr(
        getattr(e, "response", None), "status_code", None
    )
    if status in (502, 503, 504):
        return "voice_server_down"
    return type(e).__name__


class GlmVoice(WebLive):
    """A `WebLive` whose session is the GLM-4-Voice socket: the queue, the mic gate, the stage timer
    and the lifecycle (`start` / `feed` / `say` / `greet` / `close`) are inherited; the Gemini config,
    tool calls and resumption are not used."""

    def __init__(
        self,
        settings: Any,
        *,
        out,
        url: str,
        token: str = "",
        connect=None,
        waker: Any = None,
        ask: Callable[[str, str], str] | None = None,
        lang: str = "en",
        path: str = "web",
        on_heard: Callable[[str], None] | None = None,
    ):
        """`ask(question, history)` is Dory's brain for a cascade server; `on_heard(text)`, when
        given (a Discord room), decides what to do with an utterance and calls `answer` / `speak`
        itself; without it everything heard is answered (the web call, C3)."""
        super().__init__(settings, None, instruction="", ask=ask or (lambda q, h: ""), out=out)
        self.url, self.lang, self.on_heard = url, lang, on_heard
        self.transcript = Transcript()  # what this call heard and said, memory only (C9)
        self._recent_fillers: list[str] = []
        self.last_said = ""
        if path != "web":  # a Discord room logs `voice_latency path=discord`, as LiveVoice does
            from .voice_latency import StageTimer

            self.timer = StageTimer(path)
        self.cascade = ask is not None  # a cascade server sends "heard": Dory's brain answers it
        self._answer: asyncio.Task | None = None
        self._ws: Any = None
        self._connect = connect or (lambda: self._ws_connect(url, token))
        # scale-to-zero: with the Nebius identity settings, a stopped GPU box is started on demand
        self.waker = waker if waker is not None else make_waker(settings, url)

    @staticmethod
    def _ws_connect(url: str, token: str):
        import websockets  # uvicorn's dependency, imported here so tests need no network stack

        return websockets.connect(
            url, additional_headers={"Authorization": f"Bearer {token}"}, max_size=None
        )

    async def run(self) -> None:
        """One connection to the voice server; while the box is off, still booting or taken by
        another call (`busy`) this keeps trying every RETRY_S, so a Discord room that started
        before the GPU came up, or while the web call held the server, recovers by itself. The
        person is told once (the first failure); nothing retries after `close`."""
        failures = 0
        while not self._closing:
            code = ""
            try:
                if self.waker is not None and not await self.waker.healthy():
                    # the box stopped itself while idle: wake it and tell the person why they wait
                    await self.out("waking", "")
                    if not await self.waker.ensure_running():
                        await self.out("error", "voice_server_down")
                        return
                async with self._connect() as ws:
                    self._ws = ws
                    sender = asyncio.create_task(self._send(ws))
                    try:
                        code = await self._receive(ws)
                    finally:
                        sender.cancel()
                        self._cancel_answer()
                        await asyncio.gather(sender, return_exceptions=True)
                if code != "busy":
                    return  # the server closed the call, or reported an error of its own
            except asyncio.CancelledError:
                raise
            except Exception as e:
                code = error_code(e)
                # one warning per outage, then debug: a box that is off is retried for 30 minutes
                logger.log(
                    logging.DEBUG if failures and code == "voice_server_down" else logging.WARNING,
                    "glm voice: session error: %s: %s",
                    type(e).__name__,
                    e,
                )
                if code != "voice_server_down":
                    with contextlib.suppress(Exception):
                        await self.out("error", code)
                    return
            failures += 1
            if failures == 1:
                with contextlib.suppress(Exception):
                    await self.out("error", code)
            if failures > RETRY_MAX:
                return
            await asyncio.sleep(RETRY_S)

    async def _send(self, ws: Any) -> None:
        while not self._closing:
            item = await self._in.get()
            if item is None:
                return
            if isinstance(item, tuple):  # ("text", str): a typed or cued turn
                await ws.send(json.dumps({"type": "text", "text": item[1]}))
                continue
            act = self._gate.on_frame(item, time.monotonic())
            if act is Act.DROP:
                continue
            if act is Act.VOICE and self._answer is None:
                # voiced frames while Dory already answers (echo, a cough) are not the question's end
                self.timer.touch("speech_end")
            await ws.send(item)
            if act is Act.END:
                await ws.send(json.dumps({"type": "end"}))

    async def _receive(self, ws: Any) -> str:
        """Until the socket closes; returns "busy" when the server refused the call for another one
        (worth retrying), "error" for the server's other errors, "" otherwise."""
        async for message in ws:
            if self._closing:
                return ""
            if isinstance(message, bytes | bytearray):
                self.timer.mark("first_audio")
                await self.out("audio", bytes(message))
                continue
            ev = json.loads(message)
            kind, text = str(ev.get("type", "")), str(ev.get("text", "") or "")
            if kind in ("ready", "said"):
                await self.out(kind, text)
            elif kind == "heard":
                await self.out("heard", text)
                if self.cascade and text:
                    if self.on_heard is not None:
                        self.on_heard(text)
                    else:
                        self.answer(text)
            elif kind == "interrupted":
                self._cancel_answer()
                await self.out("interrupted", "")
                self._end_turn()
            elif kind == "turn":
                self.turns += 1
                await self.out("turn", "")
                self._end_turn()
            elif kind == "error":
                if text == "busy":
                    return "busy"
                await self.out("error", text or "glm_voice")
                return "error"
        return ""

    # ---- cascade: the brain answers what the server heard
    def greet(self, lang: str = "en") -> None:
        """A fixed warm line (C3), not a brain turn; the Gemini path keeps its cue."""
        if self.cascade:
            self.speak(t("meet_greet_spoken", lang))
        else:
            super().greet(lang)

    def answer(self, question: str, speaker: str = PERSON) -> None:
        """Dory's brain answers this utterance (a bare "ok" is only answered when she just asked
        something). Called by the room's gate or, on the web, for everything heard."""
        history = self.history()  # what came before this question
        self.transcript.add(datetime.now(UTC), speaker, question)
        if is_ack(question) and not self.last_said.rstrip().endswith("?"):
            return
        self._cancel_answer()
        self.timer.mark("tool_call")
        self._answer = asyncio.create_task(self._answer_turn(self._ws, question, history))

    def speak(self, text: str) -> None:
        """Say a line as it is (a greeting, "Yes?"), no brain."""
        if self._ws is not None and not self._closing and text.strip():
            self.last_said = text
            self.transcript.add(datetime.now(UTC), DORY, text)
            asyncio.ensure_future(self._say(self._ws, text, final=True))

    async def _say(self, ws: Any, text: str, *, final: bool) -> None:
        with contextlib.suppress(Exception):  # the socket may be gone: the retry loop handles it
            await ws.send(json.dumps({"type": "say", "text": spoken_form(text), "final": final}))

    def history(self) -> str:
        return self.transcript.history(
            datetime.now(UTC), window_s=HISTORY_WINDOW_S, max_chars=HISTORY_MAX_CHARS
        )

    def _cancel_answer(self) -> None:
        if self._answer is not None and not self._answer.done():
            self._answer.cancel()
        self._answer = None

    def filler(self) -> str:
        """One short line, never one of the last three."""
        keys = [k for k in ACKS if k not in self._recent_fillers] or ACKS
        if not keys:
            return ""
        key = random.choice(keys)
        self._recent_fillers = (self._recent_fillers + [key])[-FILLER_MEMORY:]
        return t(key, self.lang)

    async def _answer_turn(self, ws: Any, question: str, history: str = "") -> None:
        """The brain answers; a filler only when it takes longer than FILLER_AFTER_S (C8); the
        answer is spoken in its plain form (C10) and remembered (C9)."""
        await self.out("thinking", question)
        job = asyncio.ensure_future(asyncio.to_thread(self.ask, question, history))
        try:
            try:
                answer = await asyncio.wait_for(asyncio.shield(job), FILLER_AFTER_S)
            except TimeoutError:
                if filler := self.filler():
                    await self._say(ws, filler, final=False)
                answer = await asyncio.wait_for(job, TOOL_TIMEOUT_S - FILLER_AFTER_S)
        except asyncio.CancelledError:
            job.cancel()
            raise
        except Exception as e:
            logger.warning("glm voice: ask failed (%s)", type(e).__name__)
            answer = ""
        self.timer.mark("tool_result")
        if not self._closing:
            text = (answer or "").strip() or t("glm_answer_failed", self.lang)
            self.last_said = text
            self.transcript.add(datetime.now(UTC), DORY, text)
            await self.out("answer", text)  # the original text, for the room's chat echo (C10)
            await self._say(ws, text, final=True)
