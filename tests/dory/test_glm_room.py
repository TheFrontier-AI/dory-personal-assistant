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
        assert room.voice.timer.line().startswith("voice_latency path=discord")
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


def _room(monkeypatch, *, policy="strict", members=()):
    """A room with a fake bot and session; the brain is a stub that records questions."""
    monkeypatch.setattr(glm_room, "SEND_INTERVAL_S", 0.01)
    asked, posted, spoken = [], [], []

    class Team:
        def enabled(self, gid, flag):
            return True

        def current(self, gid):
            return SimpleNamespace(language_setting="en")

        def wake_policy(self, gid):
            return policy

    bot = SimpleNamespace(
        s=SimpleNamespace(
            voice_mode="glm",
            glm_voice_url="ws://x/voice",
            glm_voice_token="t",
            live_web_silence_ms=800,
            live_voice="Leda",
            live_model="m",
            engaged_timeout_seconds=300.0,
            name_min_rms=250.0,
            now=lambda: datetime(2026, 10, 26, tzinfo=UTC),
        ),  # fmt: skip
        team=Team(),
    )
    channel = SimpleNamespace(members=list(members))

    @contextlib.asynccontextmanager
    async def connect():
        yield FakeSocket([(lambda f: True, [json.dumps({"type": "ready"})])])

    async def post(text):
        posted.append(text)

    session = SimpleNamespace(vc=FakeVC(), ending=False, loop=None, speaking=False,
                              speaking_since=0.0, guild_id=1, voice_channel=channel,
                              text_channel="text", language="en")  # fmt: skip
    room = glm_room.GlmRoom(bot, session, connect=connect, post=post)
    room._ask_blocking = lambda q, h="": asked.append((q, h)) or "answer"
    room.voice.answer = lambda text, speaker="Person": asked.append((text, speaker))
    room.voice.speak = lambda text: spoken.append(text)
    return room, asked, spoken, posted


def test_glm_room_answers_only_when_addressed_and_follows_up_without_the_name(monkeypatch):
    mint = SimpleNamespace(id=2, bot=False, display_name="Mint")
    boom = SimpleNamespace(id=3, bot=False, display_name="Boom")
    room, asked, spoken, _ = _room(monkeypatch, members=[mint, boom])
    room._last_speaker = 2
    room._on_heard("Dory booked it yesterday, nice.")  # about her: nothing
    room._on_heard("so what time is the kickoff?")  # not for her, nobody engaged: nothing
    assert asked == [] and spoken == []
    room._on_heard("Dory, book my trip for the Lumen kickoff.")  # addressed: the caller is Mint
    assert asked == [("Dory, book my trip for the Lumen kickoff.", "Mint")]
    room._on_heard("and a hotel near Marina Bay")  # Mint's follow-up: no name needed
    assert asked[-1] == ("and a hotel near Marina Bay", "Mint")
    room._last_speaker = 3
    room._on_heard("I think it is Thursday")  # Boom, not engaged, no name: nothing
    assert len(asked) == 2
    room._on_heard("can Dory check that for us?")  # a mention shaped like a request: "Yes?"
    assert spoken == ["Yes? Go ahead."] and len(asked) == 2
    room._on_heard("Dory, who else is going?")  # Boom addresses her: he is the caller now
    assert asked[-1] == ("Dory, who else is going?", "Boom") and room._caller == 3


def test_glm_room_natural_policy_answers_an_unclear_mention_without_asking(monkeypatch):
    room, asked, spoken, _ = _room(monkeypatch, policy="natural")
    room._on_heard("can Dory check that for us?")
    assert asked == [("can Dory check that for us?", "Person")] and spoken == []


def test_glm_room_hush_stops_everything_until_the_name_with_words(monkeypatch):
    room, asked, spoken, _ = _room(monkeypatch)
    room._on_heard("Dory, what did we spend?")
    assert len(asked) == 1
    room._on_heard("Dory, be quiet")
    assert room._hushed is True and room._engaged_until == 0.0
    room._on_heard("what about the hotel?")  # the caller's follow-up: still silent
    room._on_heard("Dory?")  # a bare name does not wake her
    assert len(asked) == 1 and spoken == []
    room._on_heard("Dory, book the hotel")  # her name WITH words: she is back
    assert asked[-1] == ("Dory, book the hotel", "Person") and room._hushed is False


def test_glm_room_holds_side_talk_while_she_speaks_and_echoes_answers(monkeypatch):
    room, asked, spoken, posted = _room(monkeypatch)
    fed = []
    room.voice.feed = lambda chunk: fed.append(chunk)
    room.session.speaking = True
    loud, quiet = _frame48(3000), _frame48(0)
    for _ in range(5):  # 100 ms of someone's voice while she speaks: held, not sent
        room.feed(7, loud)
    chunk = room.mixer.pop()
    assert chunk and not room._talks_over(chunk) and fed == []
    for _ in range(45):  # 0.9 s of continuous voice: the person takes the turn
        room.feed(7, loud)
    taken = False
    while chunk := room.mixer.pop():
        taken = taken or room._talks_over(chunk)
    assert taken is True
    room.session.speaking = False
    assert room._talks_over(room.mixer.feed(7, quiet) or _frame48(0)) is False

    async def echo():
        await room._out("answer", "**Booked.** Reference ABC123")

    asyncio.run(echo())
    assert posted == ["💬 **Dory:** **Booked.** Reference ABC123"]
