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
    TALKOVER_S,
    LiveAudioSource,
    Mixer,
)
from .meeting import _connected, _stop_playback, is_hush, parse_wake
from .naming import address_kind
from .voice_ack import make_ack
from .voice_latency import rms16
from .web_live import TOOL_TIMEOUT_S

logger = logging.getLogger(__name__)


def _company_lang(bot: Any, guild_id: int) -> str:
    """The company language (what Dory says in this room); English when unknown."""
    try:
        return resolve_lang(bot.team.current(guild_id).language_setting)
    except Exception:
        return "en"


class GlmRoom:
    def __init__(
        self, bot: Any, session: Any, connect: Any = None, post: Any = None, wake: bool = True
    ):
        """`wake`: somebody asked Dory into this room just now, so a stopped GPU box may be started
        once; a session resumed after a bot restart passes False (G1: nothing automatic wakes it)."""
        self.bot, self.session, self.post = bot, session, post
        self.mixer = Mixer()
        self._source: LiveAudioSource | None = None
        self._playing_src: LiveAudioSource | None = None
        self._last_voice = 0.0
        self._pump: asyncio.Task | None = None
        self._closing = False
        self._last_speaker = 0
        self._engaged_until, self._caller = 0.0, 0  # C5: the caller's follow-ups need no name
        self._hushed = False  # C6: silent until her name comes with words
        self._held: list[bytes] = []  # C7: room audio held while she speaks
        self._talk_run = 0.0
        s = bot.s
        self.lang = _company_lang(bot, getattr(session, "guild_id", 0))
        self.engaged_s = float(getattr(s, "engaged_timeout_seconds", 300.0))
        self.rms_min = float(getattr(s, "name_min_rms", 250.0))
        self.voice = GlmVoice(
            s,
            out=self._out,
            url=s.glm_voice_url,
            token=getattr(s, "glm_voice_token", ""),
            connect=connect,
            ask=self._ask_blocking,
            path="discord",
            lang=self.lang,
            on_heard=self._on_heard,
            wake_on_start=wake,
            wake_reason="room join",
            ack=make_ack(bot.llm, s.gate_model) if getattr(bot, "llm", None) is not None else None,
        )

    def start(self) -> None:
        self.voice.start()
        self._pump = asyncio.create_task(self._pump_mixer())

    def feed(self, user_id: int, pcm: bytes) -> None:
        """One 20 ms frame (48 kHz stereo) from a human, as the sink hands it over."""
        if not self._closing:
            if rms16(pcm) >= self.rms_min:  # who spoke = the last voiced frame, not any noise
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
                if self.session.speaking and not self._talks_over(chunk):
                    continue  # a cough or side talk while she speaks never reaches the server (C7)
                for held in self._held:
                    self.voice.feed(held)
                self._held.clear()
                self.voice.feed(chunk)
            elif now - self._last_voice < self.voice.mic_tail_s + SEND_INTERVAL_S:
                self.voice.feed(silence)

    def _talks_over(self, chunk: bytes) -> bool:
        """While she speaks: only TALKOVER_S of continuous voiced audio counts as the person taking
        the turn; the frames of that run are held and sent together so the transcript is whole."""
        n = len(chunk) / (LIVE_IN_RATE * 2)
        self._talk_run = self._talk_run + n if rms16(chunk) >= self.rms_min else 0.0
        if self._talk_run >= TALKOVER_S:
            self._talk_run = 0.0
            return True
        self._held = (self._held + [chunk])[-int(TALKOVER_S / SEND_INTERVAL_S) - 1 :]
        return False

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
        elif kind == "answer":  # rule 4: every spoken answer is also posted, as the brain wrote it
            if self.post is not None:
                with contextlib.suppress(Exception):
                    await self.post(t("voice_answer_echo", self.lang, text=payload))
        elif kind == "waking":  # the GPU box stopped itself while idle and is starting (~2 min)
            logger.info("glm room: waking the voice server (guild %s)", getattr(s, "guild_id", "?"))
            if self.post is not None:
                with contextlib.suppress(Exception):
                    await self.post(t("glm_waking", getattr(s, "lang", "en")))
        elif kind == "asleep":  # somebody talks to a sleeping box: say how to wake it (once)
            logger.info(
                "glm room: voice server asleep, hint posted (guild %s)", getattr(s, "guild_id", "?")
            )
            if self.post is not None:
                with contextlib.suppress(Exception):
                    await self.post(t("glm_asleep", getattr(s, "lang", "en")))
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

    # ---- who she answers (docs/voice_behaviour.md, C4-C6): decided from the ASR text
    def _on_heard(self, text: str) -> None:
        now = time.monotonic()
        speaker = self._last_speaker
        if is_hush(text):
            self.hush()
            return
        kind = address_kind(text)
        engaged = now < self._engaged_until and speaker == self._caller
        if self._hushed:
            if kind != "addressed" or not (parse_wake(text) or ""):
                return  # silent until her name comes WITH words
            self.clear_hush()
        if kind == "mentioned":
            return
        if kind == "unclear" and not engaged:
            if self._wake_policy() != "natural":
                self.voice.speak(t("meet_wake_spoken", self.lang))  # "Yes?", never an interruption
                return
        elif kind is None and not engaged:
            return
        self._engaged_until, self._caller = now + self.engaged_s, speaker
        if self.voice.answer(text, speaker=self._name_of(speaker)):
            self._engaged_until = 0.0  # she never got to answer: the name again, please (C5)

    def _wake_policy(self) -> str:
        try:
            return self.bot.team.wake_policy(self.session.guild_id)
        except Exception:
            return "strict"

    def _name_of(self, user_id: int) -> str:
        channel = getattr(self.session, "voice_channel", None)
        for m in getattr(channel, "members", None) or ():
            if m.id == user_id:
                return getattr(m, "display_name", "") or "Person"
        return "Person"

    # ---- the LiveVoice surface the room code calls in every mode
    def hush(self, fresh: bool = True) -> None:
        """ "Dory, be quiet": playback and the pending answer stop; nothing until her name with words."""
        self._hushed = True
        self._engaged_until = 0.0
        self.voice._cancel_answer()
        self.stop_playback()

    def clear_hush(self) -> None:
        self._hushed = False

    def note_caller(self, name: str) -> None:
        pass

    def forget_grace(self) -> None:
        pass

    def notify_state(self, on: bool, caller: str = "") -> None:
        pass

    def ensure_reply(self, *args: Any, **kwargs: Any) -> None:
        pass

    # ---- the brain (cascade server only: it sends "heard", GlmVoice asks, the answer is spoken)
    def _ask_blocking(self, question: str, history: str = "") -> str:
        """Called by GlmVoice from a worker thread: the agent runs on the bot's loop."""
        fut = asyncio.run_coroutine_threadsafe(self._ask(question, history), self.session.loop)
        return fut.result(timeout=TOOL_TIMEOUT_S)

    async def _ask(self, question: str, history: str = "") -> str:
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
            history=history,
            spoken=True,
        )
        logger.info(
            "glm room: answered in %.1fs (%d rounds, %d chars)",
            ans.seconds,
            ans.rounds,
            len(ans.text or ""),
        )  # counts only: the question and answer may hold personal data
        return (ans.text or "")[:ANSWER_MAX_CHARS]
