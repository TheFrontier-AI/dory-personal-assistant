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
import time
from collections.abc import Callable
from typing import Any

from .i18n import CATALOG, t
from .nebius_vm import make_waker
from .voice_latency import Act
from .web_live import TOOL_TIMEOUT_S, WebLive

logger = logging.getLogger(__name__)
ACKS = sorted(k for k in CATALOG if k.startswith("ack_voice_"))
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
        ask: Callable[[str], str] | None = None,
        lang: str = "en",
    ):
        super().__init__(settings, None, instruction="", ask=ask or (lambda q: ""), out=out)
        self.url, self.lang = url, lang
        self.cascade = ask is not None  # a cascade server sends "heard": Dory's brain answers it
        self._answer: asyncio.Task | None = None
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
                logger.warning("glm voice: session error: %s: %s", type(e).__name__, e)
                code = error_code(e)
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
            if act is Act.VOICE:
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
                    self._start_answer(ws, text)
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
    def _start_answer(self, ws: Any, question: str) -> None:
        self._cancel_answer()
        self.timer.mark("tool_call")
        self._answer = asyncio.create_task(self._answer_turn(ws, question))

    def _cancel_answer(self) -> None:
        if self._answer is not None and not self._answer.done():
            self._answer.cancel()
        self._answer = None

    def filler(self) -> str:
        return t(random.choice(ACKS), self.lang) if ACKS else ""

    async def _answer_turn(self, ws: Any, question: str) -> None:
        """A filler at once (the brain takes seconds), then Dory's answer as a final say."""
        await self.out("thinking", question)
        try:
            if filler := self.filler():
                await ws.send(json.dumps({"type": "say", "text": filler, "final": False}))
            answer = await asyncio.wait_for(asyncio.to_thread(self.ask, question), TOOL_TIMEOUT_S)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("glm voice: ask failed (%s)", type(e).__name__)
            answer = ""
        self.timer.mark("tool_result")
        if not self._closing:
            text = (answer or "").strip() or t("glm_answer_failed", self.lang)
            await ws.send(json.dumps({"type": "say", "text": text, "final": True}))
