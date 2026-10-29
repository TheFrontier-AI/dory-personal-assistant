"""The GPU voice box's lifecycle, run by the always-on bot (docs/voice_behaviour.md, G1-G5).

`_wake_voice_command`: a typed "@Dory wake up" is the explicit request that starts a sleeping box
(nothing automatic does). `_gpu_due`: once a minute `nebius_vm.IdleWatch` polls the voice server and
stops the VM after `IDLE_STOP_S` without activity, so nothing depends on a laptop being awake.
Both need the Nebius identity settings (`make_waker` returns None without them and nothing happens).
"""

from __future__ import annotations

import asyncio
import logging
import time

from .i18n import t
from .meeting import parse_voice_wake_command
from .nebius_vm import IdleWatch, make_waker

logger = logging.getLogger(__name__)

TICK_S = 60.0
_WAKES: set[asyncio.Task] = (
    set()
)  # a wake runs for minutes; keep a reference so it is not collected


class GpuLifecycleMixin:
    _gpu_watch: IdleWatch | None = None
    _gpu_next = 0.0

    async def _wake_voice_command(self, message) -> bool:
        """ "Dory, wake up" / "ดอรี่ ตื่น": start the voice box now. With a meeting in this channel the
        room's call is told to wake (it connects when the box is up); without one the box is started
        directly. Only where the GLM voice server is configured; otherwise the text goes on."""
        if message.guild is None or not parse_voice_wake_command(self._command_text(message)):
            return False
        waker = make_waker(self.s, getattr(self.s, "glm_voice_url", ""))
        if waker is None:
            return False
        gid, user = message.guild.id, message.author
        lang = self._person_lang(gid, user.id, message.content or "")
        if await waker.healthy():
            await message.reply(t("glm_wake_awake", lang), mention_author=False)
            return True
        reason = f"typed command by user {user.id}"
        session = self.meetings.session_for_channel(message.channel.id)
        voice = getattr(getattr(session, "live", None), "voice", None)
        if voice is not None and hasattr(voice, "request_wake"):
            voice.request_wake(reason)
        else:
            task = asyncio.create_task(waker.ensure_running(reason=reason))
            _WAKES.add(task)
            task.add_done_callback(_WAKES.discard)
        await message.reply(t("glm_wake_ack", lang), mention_author=False)
        return True

    async def _gpu_due(self) -> None:
        """One idle-stop poll a minute. Never raises: the tick must not stop for the GPU."""
        now = time.monotonic()
        if now < self._gpu_next:
            return
        self._gpu_next = now + TICK_S
        try:
            if self._gpu_watch is None:
                waker = make_waker(self.s, getattr(self.s, "glm_voice_url", ""))
                if waker is None:
                    self._gpu_next = now + 10 * TICK_S  # not configured: look again rarely
                    return
                self._gpu_watch = IdleWatch(waker)
            await self._gpu_watch.tick()
        except Exception as e:
            logger.warning("gpu lifecycle: poll failed: %s", type(e).__name__)
