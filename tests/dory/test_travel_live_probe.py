"""LIVE probe (billed, deselected by default): Dory's real brain on Token Factory drives the travel
search -> cards -> sandbox booking flow, once through the WEBSITE chat route and once through the
DISCORD message path, on synthetic data only (in-memory stores, the sample catalogue, the sample
sandbox provider: a booking is a hash reference, no ticket, no money).

Every model call goes through `live_budget.Meter` (hard cap, see that file); the cap covers the
whole run. `PROBE_DRY=1` sends nothing and prints the request sizes (a free cost estimate).

    uv run pytest -m live tests/dory/test_travel_live_probe.py -s            # live, <= $2
    PROBE_DRY=1 uv run pytest -m live tests/dory/test_travel_live_probe.py -s

The report (per turn: tools called with their statuses, reply, cost) is printed and written to
$PROBE_OUT (default: a temp file)."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import GUILD as BOT_GUILD
from live_budget import BudgetExceeded, Meter
from test_center_api import H, docs, w  # noqa: F401  (the command center fixtures)
from test_coordinator import STAFF, world  # noqa: F401  (the real bot's fixtures)
from test_modes import bot  # noqa: F401
from test_travel_search_bot import Channel, _real

from dory import qa, travel_search, trips
from dory.config import Settings as DorySettings
from meeting_scribe import center, travel_api
from meeting_scribe.app import app

pytestmark = pytest.mark.live

DRY = os.environ.get("PROBE_DRY") == "1"
FULL = os.environ.get("PROBE_FULL") == "1"  # the whole ~140-tool assembly (about $0.20 a call)
METER = Meter(cap_usd=float(os.environ.get("PROBE_CAP_USD", "2.0")), max_calls=40, retries=1,
              dry=DRY)  # fmt: skip
REPORT: list[dict] = []
OUT = Path(os.environ.get("PROBE_OUT") or Path(tempfile.gettempdir()) / "dory-travel-probe.json")
TODAY = date(2026, 10, 27)
PRICE = re.compile(r"THB\s?([\d,]{3,})|([\d,]{3,})\s?THB|฿\s?([\d,]{3,})")


def live_settings(base: DorySettings) -> DorySettings:
    """The test settings plus the Token Factory brain from .env (the key is never printed)."""
    env = {}
    for line in Path(".env").read_text(encoding="utf-8").splitlines():
        k, _, v = line.partition("=")
        if k.strip().startswith("DORY_") and v.strip():
            env[k.strip()] = v.strip().strip('"').strip("'")
    key = env.get("DORY_NEBIUS_API_KEY", "")
    if not key:
        pytest.skip("DORY_NEBIUS_API_KEY is not in .env")
    upd = {"nebius_api_key": key}
    for field, name in (("brain_model", "DORY_BRAIN_MODEL"), ("fast_model", "DORY_FAST_MODEL"),
                        ("brain_effort", "DORY_BRAIN_EFFORT"), ("nebius_base_url", "DORY_NEBIUS_BASE_URL")):  # fmt: skip
        if env.get(name):
            upd[field] = env[name]
    return base.model_copy(update=upd)


def travel_only(dory_bot, guild_id: int) -> None:
    """Every feature off but travel on the synthetic server: the brain sees the travel tools and
    the always-on core instead of ~140 declarations, so both flows fit the cap (PROBE_FULL=1 keeps
    them all)."""
    if FULL or dory_bot is None:
        return
    from dory.guild_settings import FEATURES, GuildSettingsUpdate

    flags = {f: f == "travel" for f in FEATURES}
    dory_bot.guilds_store.save_settings(guild_id, GuildSettingsUpdate(features=flags), "probe")
    dory_bot.team._cache.clear()


def numbers_in(obj) -> set[int]:
    """Every integer anywhere in the tool results (the prices the reply may mention)."""
    out: set[int] = set()
    if isinstance(obj, dict):
        for v in obj.values():
            out |= numbers_in(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= numbers_in(v)
    elif isinstance(obj, int | float) and not isinstance(obj, bool):
        out.add(int(obj))
    return out


def invented_prices(text: str, results: list) -> list[int]:
    known = numbers_in(results)
    said = {int((a or b or c).replace(",", "")) for a, b, c in PRICE.findall(text or "")}
    return sorted(n for n in said if n not in known and n >= 100)


def record(channel: str, turn: str, text: str, calls: list, extra: dict | None = None) -> dict:
    row = {
        "channel": channel,
        "turn": turn,
        "tools": [{"name": n, "status": (r or {}).get("status")} for n, _, r in calls],
        "reply": (text or "")[:400],
        "invented_prices": invented_prices(text, [r for _, _, r in calls]),
        "spent_usd": round(METER.spent, 4),
        **(extra or {}),
    }
    REPORT.append(row)
    OUT.write_text(json.dumps({"rows": REPORT, "meter": METER.calls}, indent=1, default=str))
    print(f"\n[{channel}] {turn}\n  tools: {row['tools']}\n  reply: {row['reply']!r}\n"
          f"  invented prices: {row['invented_prices']}  spent: ${METER.spent:.4f}")  # fmt: skip
    return row


def wrap_tools(tools: list, calls: list) -> list:
    """Record each travel tool call (name, args, result) without changing what the model sees."""
    wanted = {*travel_search.CARD_TOOL_NAMES, "book_trip"}
    out = []
    for f in tools:
        name = getattr(f, "__name__", "")
        if name not in wanted:
            out.append(f)
            continue

        def logged(*a, _f=f, _n=name, **k):
            res = _f(*a, **k)
            calls.append((_n, k, res))
            return res

        logged.__name__, logged.__doc__ = name, f.__doc__
        logged.__signature__ = __import__("inspect").signature(f)
        for attr in ("cards", "ctx", "on_confirm", "dory_group", "outbox"):
            if hasattr(f, attr):
                setattr(logged, attr, getattr(f, attr))
        out.append(logged)
    return out


@pytest.fixture
def meter(monkeypatch):
    return METER.install(monkeypatch)


@pytest.fixture
def web(w, meter, monkeypatch):  # noqa: F811
    monkeypatch.setattr(travel_api, "get_today", lambda: TODAY)
    monkeypatch.setattr(
        DorySettings, "now", lambda self: datetime(2026, 10, 27, 9, tzinfo=self.zone)
    )
    monkeypatch.setattr(center, "TRIPS", travel_search.Trips())
    headless = center.get_bot()
    if headless is not None:
        headless.__dict__.pop("travel_trips", None)
    calls: list = []
    travel_only(headless, center.company_workspace(w.orgs.get(w.org.id)).memory_id)

    def ask(settings, store, question, **kw):
        kw["extra_tools"] = wrap_tools(list(kw.get("extra_tools") or []), calls)
        return qa.ask(live_settings(settings), store, question, **kw)

    app.dependency_overrides[center.get_ask] = lambda: ask
    return calls, headless


def web_turn(w, calls, text, who="mem"):  # noqa: F811
    before = len(calls)
    r = w.client.post("/api/center/orgs/org_t/chat", json={"message": text}, headers=H[who])
    body = r.json() if r.status_code == 200 else {"answer": f"HTTP {r.status_code}: {r.text[:200]}"}
    return body, calls[before:], r.status_code


def test_web_flow(w, web):  # noqa: F811
    """Website: search -> hotel "there" -> book the cheapest -> plain yes (code) -> clarification."""
    calls, headless = web
    steps = [
        ("search", "Find flights from Bangkok to Singapore on 2026-11-10 for 2 people."),
        ("hotel", "Also find a hotel there for 3 nights with free cancellation."),
        (
            "book",
            "Please book the cheapest of those flights and the cheapest of those hotels "
            "for the Lumen kickoff.",
        ),  # fmt: skip
        ("yes", "yes"),
    ]
    rows = []
    only = int(os.environ.get("PROBE_STEPS") or 0)  # e.g. 1 = the search turn only
    steps = steps[:only] if only else steps
    try:
        for name, text in steps:
            body, got, status = web_turn(w, calls, text)
            rows.append(record("web", name, body.get("answer", ""), got,
                               {"http": status, "travel": bool(body.get("travel")),
                                "travel_keys": sorted(k for k, v in (body.get("travel") or {}).items() if v)}))  # fmt: skip
        if only:
            return
        body, got, status = web_turn(w, calls, "Find me a flight.", who="adm")  # nothing known
        rows.append(record("web", "clarify", body.get("answer", ""), got,
                           {"http": status, "travel": bool(body.get("travel"))}))  # fmt: skip
    except BudgetExceeded as e:
        record("web", "STOPPED", str(e), [])
    if DRY:
        return
    ws = center.company_workspace(w.orgs.get(w.org.id))
    booked = [r for r in headless.docs.find(trips.TRIP_KIND, ws.memory_id) if r.get("purpose")]
    record("web", "result", f"trips booked: {len(booked)}", [],
           {"references": [t.get("references") for t in booked]})  # fmt: skip
    assert rows and rows[0]["travel"], "the brain did not search (no cards)"
    assert booked, "no sandbox booking was made"


async def discord_turn(bot, world, calls, text, who, history=""):  # noqa: F811
    """One Discord message to the real bot assembly (`_agent_kwargs`, typed chat) and the real
    brain; the cards the brain's searches recorded are posted like the reply path does."""
    kw, uid = _real(bot, world, spoken=False) if who == STAFF else _other(bot, world, who)
    kw["extra_tools"] = wrap_tools(list(kw["extra_tools"]), calls)
    before = len(calls)
    ans = await qa.ask_async(live_settings(bot.s), bot.store, text, guild_id=BOT_GUILD,
                             is_exec=False, user_id=uid, history=history, **kw)  # fmt: skip
    channel = Channel()
    await bot._post_travel_cards(SimpleNamespace(channel=channel), world.g.members[who], kw, "en")
    return ans, calls[before:], channel


def _other(bot, world, who):  # noqa: F811
    member = world.g.members[who]
    msg = bot.room_message(world.g, member, world.pub)
    kw = bot._agent_kwargs(msg, world.g, member, False, setting="en", lang="en", question="q",
                           memory=None, profile=None, spoken=False)  # fmt: skip
    return kw, kw.pop("user_id", who)


async def test_discord_flow(bot, world, meter):  # noqa: F811
    """Discord chat: search (cards posted, owner-bound) -> "book <ref>" (what the review card tells
    the person to say) -> plain yes (code) -> clarification for someone else."""
    calls: list = []
    history = ""
    travel_only(bot, BOT_GUILD)
    try:
        ans, got, channel = await discord_turn(
            bot, world, calls, "Find flights from Bangkok to Singapore on 2026-11-10 for 2 people.",
            STAFF)  # fmt: skip
        record("discord", "search", ans.text, got, {"cards_posted": len(channel.views),
                                                     "rounds": ans.rounds})  # fmt: skip
        history = f"user: Find flights from Bangkok to Singapore on 2026-11-10 for 2 people.\ndory: {ans.text}"
        refs = [r["top"][0]["booking_ref"] for n, _, r in got
                if n == "search_flights" and (r or {}).get("top")]  # fmt: skip
        if not refs and not DRY:
            pytest.fail("the brain did not call search_flights")
        ref = refs[-1] if refs else "BKKSIN.SL106-20261110-E.2"
        ans, got, _ = await discord_turn(bot, world, calls, f"book {ref}", STAFF, history)
        record("discord", "book", ans.text, got, {"rounds": ans.rounds})
        history += f"\nuser: book {ref}\ndory: {ans.text}"
        ans, got, _ = await discord_turn(bot, world, calls, "yes", STAFF, history)
        record("discord", "yes", ans.text, got, {"rounds": ans.rounds,
                                                  "code_tool_calls": ans.tool_calls})  # fmt: skip
        other = next(m for m in world.g.members if m != STAFF)
        ans, got, channel = await discord_turn(bot, world, calls, "Find me a flight.", other)
        record("discord", "clarify", ans.text, got, {"cards_posted": len(channel.views)})
    except BudgetExceeded as e:
        record("discord", "STOPPED", str(e), [])
    if DRY:
        return
    rows = [r for r in bot.docs.find(trips.TRIP_KIND, BOT_GUILD) if r.get("references")]
    record("discord", "result", f"trips booked: {len(rows)}", [],
           {"references": [r.get("references") for r in rows]})  # fmt: skip
    assert rows, "no sandbox booking was made"


def teardown_module(module):
    print("\n" + METER.report())
    OUT.write_text(json.dumps({"rows": REPORT, "meter": METER.calls}, indent=1, default=str))
    print(f"report: {OUT}")


RECOMMEND = [  # the way people ask for options, not "find" / "search"
    "Recommend some hotels in Singapore for 3 nights from 2026-11-10 for 2 people.",
    "Can you suggest flights from Bangkok to Singapore on 2026-11-10?",
    "I'm going to Singapore on 2026-11-10 for 3 nights. Any hotel and flight suggestions?",
]


def test_web_recommendations_draw_cards(w, web, monkeypatch):  # noqa: F811
    """Asking for suggestions must reach the card searches (PROBE_FULL=1: production's whole tool
    assembly). Every tool the model calls is recorded, not only the travel ones."""
    calls, _ = web
    seen: list[str] = []
    real = qa.ask

    def ask(settings, store, question, **kw):
        tools = wrap_tools(list(kw.get("extra_tools") or []), calls)
        names = sorted(getattr(f, "__name__", "") for f in tools)
        print(f"\n  offered {len(names)} tools; card tools offered:",
              [n for n in names if n in travel_search.CARD_TOOL_NAMES])  # fmt: skip

        def spy(f):
            n = getattr(f, "__name__", "")
            if n in travel_search.CARD_TOOL_NAMES or n == "book_trip":
                return f

            def g(*a, _f=f, _n=n, **k):
                seen.append(_n)
                return _f(*a, **k)

            g.__name__, g.__doc__ = n, f.__doc__
            g.__signature__ = __import__("inspect").signature(f)
            for attr in ("cards", "ctx", "on_confirm", "dory_group", "outbox"):
                if hasattr(f, attr):
                    setattr(g, attr, getattr(f, attr))
            return g

        kw["extra_tools"] = [spy(f) for f in tools]
        return real(live_settings(settings), store, question, **kw)

    app.dependency_overrides[center.get_ask] = lambda: ask
    for text in RECOMMEND:
        seen.clear()
        try:
            body, got, _ = web_turn(w, calls, text)
        except BudgetExceeded as e:
            pytest.skip(f"budget: {e}")
        travel = body.get("travel") or {}
        record("web-reco", text, body.get("answer", ""), got,
               {"other_tools": list(seen), "cards": [k for k, v in travel.items() if v]})  # fmt: skip
