"""A Discord voice room on the GLM-4-Voice server: room frames up, server audio out, no Google."""

import asyncio
import contextlib
import json
from array import array
from datetime import UTC, datetime
from types import SimpleNamespace

from test_glm_voice import FakeSocket

from dory import glm_room
from dory.live_voice import SILENCE
from dory.voice_latency import MicGate


class FakeVC:
    def __init__(self):
        self.playing, self.played, self.stops = False, [], 0

    def is_connected(self):
        return True

    def is_playing(self):
        return self.playing

    def play(self, source, after=None):
        self.played.append(source)
        self.playing = True

    def stop(self):
        self.playing = False
        self.stops += 1


TONE = array("h", [2000, -2000] * 240).tobytes()  # 20 ms of 24 kHz mono audio from the server


def _frame48(amp: int) -> bytes:  # 20 ms of 48 kHz stereo s16le, as Discord hands it over
    return array("h", [amp, amp, -amp, -amp] * 480).tobytes()


def test_glm_room_sends_the_room_audio_and_plays_the_answer(monkeypatch):
    monkeypatch.setattr(glm_room, "SEND_INTERVAL_S", 0.01)
    monkeypatch.setattr(MicGate, "tail_s", property(lambda self: 0.05))  # the server VAD's tail
    fake = FakeSocket(
        [
            (lambda f: True, [json.dumps({"type": "ready"})]),
            (
                lambda f: any(
                    json.loads(x).get("type") == "end" for x in f.sent if isinstance(x, str)
                ),
                [TONE, TONE, json.dumps({"type": "turn"})],  # audible 24 kHz audio, not silence
            ),
        ]
    )

    @contextlib.asynccontextmanager
    async def connect():
        yield fake

    settings = SimpleNamespace(
        voice_reply=True,
        voice_mode="glm",
        glm_voice_url="ws://x/voice",
        glm_voice_token="t",
        live_web_silence_ms=800,
        live_voice="Leda",
        live_model="m",
        now=lambda: datetime(2026, 10, 26, tzinfo=UTC),
    )
    vc = FakeVC()

    async def main():
        session = SimpleNamespace(
            vc=vc,
            ending=False,
            loop=asyncio.get_running_loop(),
            speaking=False,
            speaking_since=0.0,
            guild_id=1,
        )
        room = glm_room.GlmRoom(SimpleNamespace(s=settings), session, connect=connect)
        room.start()
        for _ in range(5):  # 100 ms of one person talking
            room.feed(7, _frame48(3000))
            await asyncio.sleep(0.01)
        for _ in range(200):
            if vc.played and room._source is not None and room._source.buffered_bytes:
                break
            await asyncio.sleep(0.01)
        assert session.speaking is True
        frames = sum(1 for _ in range(10) if vc.played[0].read() not in (SILENCE, b""))
        await room.voice.out("interrupted", "")  # the person talked over her
        await room.close()
        return frames

    frames = asyncio.run(main())
    sent_bytes = [x for x in fake.sent if isinstance(x, bytes)]
    assert sent_bytes and all(len(x) % 2 == 0 for x in sent_bytes)  # 16 kHz mono mixed audio
    assert any(isinstance(x, str) and json.loads(x).get("type") == "end" for x in fake.sent)
    assert frames >= 1  # the server's 24 kHz audio reached the player as 48 kHz stereo frames
    assert vc.stops >= 1  # barge-in stopped the player


def test_glm_room_asks_the_same_agent_as_chat_and_rebinds_actions_to_the_speaker(monkeypatch):
    """`_ask` builds the chat agent for the lowest-ranked human present (safe to say aloud) and
    re-binds the actions to whoever spoke last; `_ask_blocking` serves GlmVoice's worker thread."""
    import threading

    from dory import qa, voice_actions

    calls = {"kw": [], "ask": [], "rebind": 0}
    boss = SimpleNamespace(id=1, bot=False, guild="G", display_name="Prae")
    staff = SimpleNamespace(id=2, bot=False, guild="G", display_name="Mint")
    channel = SimpleNamespace(members=[boss, staff, SimpleNamespace(id=9, bot=True)])

    class Team:
        def enabled(self, gid, flag):
            return True

        def current(self, gid):
            return SimpleNamespace(language_setting="en")

    async def room_memory_tools(guild, vc, humans, *also, asker=None):
        return "memory"

    bot = SimpleNamespace(
        s=SimpleNamespace(
            voice_mode="glm",
            glm_voice_url="ws://x/voice",
            glm_voice_token="t",
            live_web_silence_ms=800,
            live_voice="Leda",
            live_model="m",
            now=lambda: datetime(2026, 10, 26, tzinfo=UTC),
        ),  # fmt: skip
        store="store",
        team=Team(),
        is_exec_member=lambda m: m.id == 1,
        _ranks=lambda guild: {1: 10, 2: 1},
        _room_memory_tools=room_memory_tools,
        room_message=lambda guild, member, here, room=None: ("msg", member.id),
        _profile_of=lambda gid, uid: {"uid": uid},
        _agent_kwargs=lambda msg, guild, member, is_exec, **kw: (
            calls["kw"].append((member.id, is_exec, kw)) or {"extra_tools": [], "who": member.id}
        ),
    )
    guild = SimpleNamespace(get_channel=lambda cid: None)
    boss.guild = staff.guild = guild

    def fake_ask(settings, store, question, **kw):
        calls["ask"].append((question, kw))
        return SimpleNamespace(text="Booked, reference ABC123. " * 40, seconds=1.0, rounds=2)

    def fake_rebind(room_kw, speaker_kw):
        calls["rebind"] += 1
        return {**room_kw, "rebound_to": speaker_kw["who"]}

    monkeypatch.setattr(qa, "ask", fake_ask)
    monkeypatch.setattr(voice_actions, "rebind_actions", fake_rebind)

    @contextlib.asynccontextmanager
    async def connect():
        yield FakeSocket([(lambda f: True, [json.dumps({"type": "ready"})])])

    async def main():
        session = SimpleNamespace(vc=FakeVC(), ending=False, loop=asyncio.get_running_loop(),
                                  speaking=False, speaking_since=0.0, guild_id=1,
                                  voice_channel=channel, text_channel="text", language="en")  # fmt: skip
        room = glm_room.GlmRoom(bot, session, connect=connect)
        assert room.lang == "en" and room.voice.cascade is True
        room.feed(2, _frame48(3000))  # Mint spoke last
        result = {}

        def worker():
            result["text"] = room._ask_blocking("book my trip")

        t = threading.Thread(target=worker)
        t.start()
        while t.is_alive():
            await asyncio.sleep(0.01)
        return result["text"]

    text = asyncio.run(main())
    assert text.startswith("Booked, reference ABC123.") and len(text) <= 700
    # the agent was built for staff (lowest rank, is_exec False) and once more for the speaker
    assert [(m, e) for m, e, _ in calls["kw"]] == [(2, False), (2, False)] or calls["rebind"] == 0
    q, kw = calls["ask"][0]
    assert (
        q == "book my trip"
        and kw["spoken"] is True
        and kw["is_exec"] is False
        and kw["user_id"] == 0
    )
    assert kw["guild_id"] == 1
