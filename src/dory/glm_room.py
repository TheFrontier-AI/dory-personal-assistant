"""Discord voice rooms on the self-hosted GLM-4-Voice server (`deploy/glm_voice`): no Google call
anywhere in the room (owner, 26 Oct 2026: "Discord voice with GLM-4-Voice on Nebius, no Vertex AI").

`voice_mode = "glm"`: `MeetingManager._start_live` makes a `GlmRoom` instead of a `LiveVoice`. The
room's mixed audio (`live_voice.Mixer`, 16 kHz mono) goes to `GlmVoice` (the web client: mic gate,
stage timer, the server's socket protocol) and the server's 24 kHz audio comes back through
`live_voice.LiveAudioSource` on the voice client. On the GLM-4-Voice server: English small talk, no
tools. On the cascade sidecar (`cascade.py`, 27 Oct 2026) the server sends what it heard and `_ask`
runs the SAME text agent as a chat message from this room (`bot._agent_kwargs`, lowest-ranked human
present as the asker, actions re-bound to whoever spoke last), so flights get booked by voice. No
transcripts, no minutes, no wake word (Dory answers whoever talks), one room per server at a time.
The room code's calls that only make sense for Gemini Live (`hush`, `notify_state`, ...) are no-ops.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from .glm_voice import GlmVoice
from .i18n import resolve_lang, t
from .live_voice import (
    ANSWER_MAX_CHARS,
    LIVE_IN_RATE,
    PLAY_RETRIES,
    SEND_INTERVAL_S,
    LiveAudioSource,
    Mixer,
)
from .meeting import _connected, _stop_playback
from .web_live import TOOL_TIMEOUT_S

logger = logging.getLogger(__name__)


def _company_lang(bot: Any, guild_id: int) -> str:
    """The company language (what Dory says in this room); English when unknown."""
    try:
        return resolve_lang(bot.team.current(guild_id).language_setting)
    except Exception:
        return "en"


class GlmRoom:
    def __init__(self, bot: Any, session: Any, connect: Any = None, post: Any = None):
        self.bot, self.session, self.post = bot, session, post
        self.mixer = Mixer()
        self._source: LiveAudioSource | None = None
        self._playing_src: LiveAudioSource | None = None
        self._last_voice = 0.0
        self._pump: asyncio.Task | None = None
        self._closing = False
        self._last_speaker = 0
        s = bot.s
        self.lang = _company_lang(bot, getattr(session, "guild_id", 0))
        self.voice = GlmVoice(
            s,
            out=self._out,
            url=s.glm_voice_url,
            token=getattr(s, "glm_voice_token", ""),
            connect=connect,
            ask=self._ask_blocking,
            lang=self.lang,
        )

    def start(self) -> None:
        self.voice.start()
        self._pump = asyncio.create_task(self._pump_mixer())

    def feed(self, user_id: int, pcm: bytes) -> None:
        """One 20 ms frame (48 kHz stereo) from a human, as the sink hands it over."""
        if not self._closing:
            self._last_speaker = user_id
            self.mixer.feed(user_id, pcm)

    async def _pump_mixer(self) -> None:
        """Every SEND_INTERVAL_S the mixed room audio goes to the socket. Discord sends no frames
        while nobody talks, so after the last voice this sends silence for the mic gate's tail: the
        gate then sends the server its stream end and the server answers."""
        silence = bytes(int(LIVE_IN_RATE * SEND_INTERVAL_S) * 2)
        while not self._closing:
            await asyncio.sleep(SEND_INTERVAL_S)
            chunk = self.mixer.pop()
            now = time.monotonic()
            if chunk:
                self._last_voice = now
                self.voice.feed(chunk)
            elif now - self._last_voice < self.voice.mic_tail_s + SEND_INTERVAL_S:
                self.voice.feed(silence)

    # ---- what the server sends back
    async def _out(self, kind: str, payload: Any) -> None:
        s = self.session
        if kind == "audio":
            if s.ending or not _connected(s.vc):
                return
            src = self._source
            if src is None or not src.feed(payload):
                src = self._source = LiveAudioSource()
                src.feed(payload)
            self._ensure_playing(src)
        elif kind == "interrupted":
            self.stop_playback()
        elif kind == "turn":
            if self._source is not None:
                self._source.finish()
        elif kind == "waking":  # the GPU box stopped itself while idle and is starting (~2 min)
            logger.info("glm room: waking the voice server (guild %s)", getattr(s, "guild_id", "?"))
            if self.post is not None:
                with contextlib.suppress(Exception):
                    await self.post(t("glm_waking", getattr(s, "lang", "en")))
        elif kind == "ready":
            logger.info("glm room: connected (guild %s)", getattr(s, "guild_id", "?"))
        elif kind == "error":
            logger.warning("glm room: voice server error: %s", payload)

    def _ensure_playing(self, src: LiveAudioSource, retries: int = PLAY_RETRIES) -> None:
        s = self.session
        if src is not self._source or src.ended or s.ending or not _connected(s.vc):
            return
        if self._playing_src is src and s.vc.is_playing():
            return
        if s.vc.is_playing():  # the previous source is still winding down
            if retries > 0:
                s.loop.call_later(0.05, self._ensure_playing, src, retries - 1)
            return
        try:
            s.vc.play(src, after=lambda err, src=src: self._after_threadsafe(src, err))
        except Exception as e:
            logger.warning("glm room: could not start playback: %s", e)
            return
        self._playing_src = src
        s.speaking, s.speaking_since = True, time.monotonic()

    def _after_threadsafe(self, src: LiveAudioSource, err: Exception | None) -> None:
        with contextlib.suppress(RuntimeError):  # loop already closed
            self.session.loop.call_soon_threadsafe(self._on_play_end, src, err)

    def _on_play_end(self, src: LiveAudioSource, err: Exception | None) -> None:
        if err:
            logger.warning("glm room: playback error: %s", err)
        if self._playing_src is src:
            self._playing_src = None
            self.session.speaking = False
        if self._source is src and src.ended:
            self._source = None

    def stop_playback(self) -> None:
        """Barge-in or leaving: drop what is queued and stop playing now."""
        src, self._source = self._source, None
        if src is not None:
            src.clear()
            src.finish()
        if self._playing_src is not None:
            _stop_playback(self.session.vc)
            self._playing_src = None
            self.session.speaking = False

    async def close(self) -> None:
        self._closing = True
        if self._pump is not None:
            self._pump.cancel()
            await asyncio.gather(self._pump, return_exceptions=True)
        await self.voice.close()
        self.stop_playback()

    # ---- the LiveVoice surface the room code calls in every mode: nothing to do on this backend
    def hush(self, fresh: bool = True) -> None:
        self.stop_playback()

    def clear_hush(self) -> None:
        pass

    def note_caller(self, name: str) -> None:
        pass

    def forget_grace(self) -> None:
        pass

    def notify_state(self, on: bool, caller: str = "") -> None:
        pass

    def ensure_reply(self, *args: Any, **kwargs: Any) -> None:
        pass

    # ---- the brain (cascade server only: it sends "heard", GlmVoice asks, the answer is spoken)
    def _ask_blocking(self, question: str) -> str:
        """Called by GlmVoice from a worker thread: the agent runs on the bot's loop."""
        fut = asyncio.run_coroutine_threadsafe(self._ask(question), self.session.loop)
        return fut.result(timeout=TOOL_TIMEOUT_S)

    async def _ask(self, question: str) -> str:
        """The same text agent as a chat message from this room (`bot._agent_kwargs`), built for
        the lowest-ranked human present so every read is safe to say aloud; the outward actions
        are re-bound to whoever spoke last, as `LiveVoice._ask_dory` does."""
        from .qa import ask
        from .voice_actions import rebind_actions

        bot, s = self.bot, self.session
        humans = [m for m in s.voice_channel.members if not getattr(m, "bot", False)]
        if not question.strip() or not humans or not bot.team.enabled(s.guild_id, "qa"):
            return ""
        guild = humans[0].guild
        everyone_exec = all(bot.is_exec_member(m) for m in humans)
        ranks = await asyncio.to_thread(bot._ranks, guild) if len(humans) > 1 else {}
        asker = min(humans, key=lambda h: ranks.get(h.id, -1))
        speaker = next((h for h in humans if h.id == self._last_speaker), asker)
        here = guild.get_channel(getattr(s, "minutes_channel_id", 0) or 0) or s.text_channel
        memory = await bot._room_memory_tools(guild, s.voice_channel, humans, asker=asker)
        setting = getattr(s, "language", None) or self.lang

        def agent_for(member, is_exec: bool, profile) -> dict:
            return bot._agent_kwargs(
                bot.room_message(guild, member, here, room={h.id for h in humans}),
                guild,
                member,
                is_exec,
                setting=setting,
                lang=self.lang,
                question=question,
                memory=memory,
                profile=profile,
                files=[],
                spoken=True,
            )

        known = len(humans) == 1 or speaker.id == asker.id
        kw = agent_for(
            asker, everyone_exec, bot._profile_of(s.guild_id, speaker.id) if known else None
        )
        if speaker.id != asker.id:
            kw = rebind_actions(kw, agent_for(speaker, bot.is_exec_member(speaker), None))
        ans = await asyncio.to_thread(
            ask,
            bot.s,
            bot.store,
            question,
            guild_id=s.guild_id,
            **kw,
            is_exec=everyone_exec,
            user_id=humans[0].id if (everyone_exec or len(humans) == 1) else 0,
            spoken=True,
        )
        logger.info(
            "glm room: answered in %.1fs (%d rounds, %d chars)",
            ans.seconds,
            ans.rounds,
            len(ans.text or ""),
        )  # counts only: the question and answer may hold personal data
        return (ans.text or "")[:ANSWER_MAX_CHARS]
