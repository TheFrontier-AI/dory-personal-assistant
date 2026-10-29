"""Web chat + travel search, the conversational path: the message goes to Dory's brain, the brain
calls the validated `search_flights` / `search_hotels` tools (`travel_search.card_tools`), and the
cards they recorded come back as `travel` (stored on the turn). A scripted brain stands in for the
model: it calls the tool functions it is given in `extra_tools`, like a model would."""

from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_center_api import H, docs, w  # noqa: F401  (the command center fixtures)

from dory import travel_search, trips
from dory.config import Settings as DorySettings
from dory.guild_settings import GuildSettingsUpdate
from meeting_scribe import center, travel_api
from meeting_scribe.app import app

URL = "/api/center/orgs/org_t/chat"
FLIGHT = {
    "origin": "BKK", "destination": "SIN", "depart": "2026-11-03", "adults": 2, "cabin": "economy",
}  # fmt: skip
OUT = {"origin": "BKK", "destination": "SIN", "depart_date": "2026-11-03", "travellers": 2}
BACK = {"origin": "SIN", "destination": "BKK", "depart_date": "2026-11-06"}


@pytest.fixture
def brain(w, monkeypatch):  # noqa: F811
    """Message -> [(tool name, kwargs)] the brain calls, then it answers in one line."""
    monkeypatch.setattr(travel_api, "get_today", lambda: date(2026, 10, 27))
    # the headless bot's own clock too (its card tools and book_trip read it): the dates stay future
    monkeypatch.setattr(
        DorySettings, "now", lambda self: datetime(2026, 10, 27, 9, tzinfo=self.zone)
    )
    monkeypatch.setattr(center, "TRIPS", travel_search.Trips())
    # the headless bot (and its store) outlives the test: a fresh trip kind per test, or book_trip
    # would answer already_booked for a trip an earlier test made
    monkeypatch.setattr(trips, "TRIP_KIND", f"dory_trips_{uuid4().hex[:8]}")
    bot = center.get_bot()  # the headless bot is built once per process: drop its trips too
    if bot is not None:
        bot.__dict__.pop("travel_trips", None)
    script, seen, offered = {}, [], []

    def ask(settings, store, question, **kw):
        tools = {getattr(f, "__name__", ""): f for f in kw.get("extra_tools") or []}
        offered.append(set(tools))
        assert len([n for n in tools if n in travel_search.CARD_TOOL_NAMES]) <= 2
        for f in tools.values():  # qa.ask_async's rule: a plain yes after a quote is code's answer
            hook = getattr(f, "on_confirm", None)
            if hook and (text := hook(question)):
                seen.append([])
                return SimpleNamespace(text=text)
        got = [tools[name](**args) for name, args in script.get(question, [])]
        seen.append(got)
        if got and got[-1].get("status") == "need_details":
            return SimpleNamespace(text="Where are you flying to, and on which date?")
        return SimpleNamespace(text="Here is what I found." if got else "ans:" + question)

    app.dependency_overrides[center.get_ask] = lambda: ask
    return SimpleNamespace(script=script, seen=seen, offered=offered, bot=bot)


def say(w, text, who="mem", status=200):  # noqa: F811
    r = w.client.post(URL, json={"message": text}, headers=H[who])
    assert r.status_code == status, r.text
    return r.json()


def test_a_weather_answer_carries_its_card_and_history_keeps_it(w, brain, monkeypatch):  # noqa: F811
    from test_weather_cards import Net

    svc = Net().service()  # fake Open-Meteo
    monkeypatch.setattr(type(brain.bot), "_weather_service", lambda self: svc)
    ask = "What's the weather in Singapore this week?"
    brain.script[ask] = [("weather", {"place": "Singapore"})]
    got = say(w, ask)
    card = {"kind": "weather", "place": "Singapore", "lat": 1.2897, "lng": 103.8501, "days": 3}
    assert got["travel"]["weather"] == card and got["travel"]["flights"] is None
    assert got["travel"]["hotels"] is None and got["travel_fallback"] is False
    turns = w.client.get(URL + "/history", headers=H["mem"]).json()["turns"]
    assert turns[-1]["role"] == "dory" and turns[-1]["travel"]["weather"] == card


def test_a_trip_request_answered_without_a_search_still_draws_cards(w, brain):  # noqa: F811
    """The brain answered from earlier results in the chat and called no search: the reply is the
    brain's, and the cards come from the message (not the fallback: the AI did answer)."""
    got = say(w, "Any hotel and flight suggestions for Singapore on 2026-11-03 for 3 nights?")
    assert got["answer"].startswith("ans:") and got["travel_fallback"] is False
    assert got["travel"]["flights"]["destination"] == "SIN"
    assert got["travel"]["hotels"]["check_in"] == "2026-11-03"
    assert say(w, "thanks!")["travel"] is None  # not a trip: nothing drawn


def test_cards_come_from_the_brains_tool_call_with_its_filters(w, brain):  # noqa: F811
    ask = "Find non-stop flights from Bangkok to Singapore on 3 Nov for 2"
    brain.script[ask] = [
        ("search_flights", {"origin": "Bangkok", "destination": "Singapore",
                            "depart_date": "2026-11-03", "travellers": 2, "stops": "nonstop"}),
    ]  # fmt: skip
    got = say(w, ask)
    assert got["answer"] == "Here is what I found." and got["travel_fallback"] is False
    assert got["travel"]["flights"] == FLIGHT and got["travel"]["hotels"] is None
    assert got["travel"]["flight_filters"]["stops"] == ["nonstop"]
    assert brain.seen[-1][0]["shown"].startswith("The person sees these as interactive cards")
    turns = w.client.get(URL + "/history", headers=H["mem"]).json()["turns"]
    assert turns[-1]["travel"] == got["travel"] and turns[-2]["travel"] is None


def test_missing_details_get_one_question_and_no_cards(w, brain):  # noqa: F811
    brain.script["find me a flight"] = [("search_flights", {})]
    got = say(w, "find me a flight")
    assert brain.seen[-1][0]["status"] == "need_details"
    assert got["answer"] == "Where are you flying to, and on which date?"
    assert got["travel"] is None and got["travel_fallback"] is False


def test_the_trip_continues_for_the_same_person_only(w, brain):  # noqa: F811
    first, then = "flights BKK->SIN 2026-11-03 for 2", "and a hotel there for 3 nights"
    brain.script[first] = [
        ("search_flights", {"origin": "BKK", "destination": "SIN", "depart_date": "2026-11-03",
                            "travellers": 2}),
    ]  # fmt: skip
    brain.script[then] = [("search_hotels", {"nights": 3})]
    say(w, first)
    got = say(w, then)
    assert got["travel"]["hotels"] == {
        "city": "SIN", "check_in": "2026-11-03", "check_out": "2026-11-06", "rooms": 1,
        "guests": 2,
    }  # fmt: skip
    assert got["travel"]["flights"] is None  # this reply searched hotels only
    other = say(w, then, who="adm")  # someone else has no trip to continue
    assert other["travel"] is None and brain.seen[-1][0]["status"] == "need_details"


def test_brain_failure_on_a_trip_still_shows_cards_with_a_notice(w, brain):  # noqa: F811
    def down(*a, **kw):
        raise RuntimeError("model down")

    app.dependency_overrides[center.get_ask] = lambda: down
    ask = "Find a flight from Bangkok to Singapore and a hotel there for 2 people next week"
    got = say(w, ask)
    assert got["travel_fallback"] is True
    assert got["answer"].startswith("I couldn't interpret this with Dory's AI just now")
    assert "Bangkok (BKK) to Singapore (SIN) on Tue 3 Nov" in got["answer"]
    assert got["travel"]["flights"] == FLIGHT
    assert got["travel"]["hotels"]["check_out"] == "2026-11-06"
    assert got["travel"]["flight_filters"] == travel_search.FlightFilters().model_dump(mode="json")
    turns = w.client.get(URL + "/history", headers=H["mem"]).json()["turns"]
    assert turns[-1]["travel"] == got["travel"]
    assert "Bad Gateway" not in str(say(w, "receipts this month?", status=502))


def test_the_fallback_line_follows_the_company_language(w, brain):  # noqa: F811
    def down(*a, **kw):
        raise RuntimeError("model down")

    app.dependency_overrides[center.get_ask] = lambda: down
    w.guilds.save_settings(1000, GuildSettingsUpdate(default_language="th"), "boss@example.com")
    got = say(w, "หาโรงแรมที่สิงคโปร์ 2 คืน")
    assert "ตีความ" in got["answer"] and got["travel"]["flights"] is None
    assert got["travel"]["hotels"]["city"] == "SIN" and got["travel_fallback"] is True


def test_other_questions_still_reach_the_brain_without_cards(w, brain):  # noqa: F811
    got = say(w, "hotel receipts this month?")
    assert got["answer"] == "ans:hotel receipts this month?" and got["travel"] is None


def test_live_voice_gets_the_search_tools_but_no_cards(w, brain):  # noqa: F811
    brain.script["flights to Singapore on 3 Nov"] = [
        ("search_flights", {"origin": "BKK", "destination": "SIN", "depart_date": "2026-11-03"}),
    ]
    ctx = center.Ctx("mem@example.com", False, w.org, "member")
    ws = center.company_workspace(w.org)
    ask = app.dependency_overrides[center.get_ask]()
    text = center.answer_question(
        ctx, w.orgs, w.lib, ask, w.guilds, ws, "flights to Singapore on 3 Nov", spoken=True
    )  # what ask_dory calls: spoken, no travel_out
    assert text == "Here is what I found."
    result = brain.seen[-1][0]
    assert result["status"] == "ok" and result["shown"].startswith("Nothing is drawn (voice)")
    assert "card" not in result["shown"]


def test_one_tool_per_name_whatever_the_bot_brings():
    mine = travel_search.card_tools(
        travel_search.CardCtx("web:a@x", date(2026, 10, 27), travel_search.Trips())
    )
    theirs = travel_search.card_tools(
        travel_search.CardCtx("discord:1", date(2026, 10, 27), travel_search.Trips(), render=False)
    )
    kept, drawn = center.with_card_tools([*theirs], mine)
    assert kept == theirs and drawn == theirs  # the bot's own (render set by its `spoken`) stay
    tools, drawn = center.with_card_tools([print], mine)
    assert tools == [print, *mine] and drawn == mine  # web-only path: the web's own


def _refs(seen_turn):
    """The (booking_ref, total) of each search result's first offer, in call order."""
    return [(r["top"][0]["booking_ref"], r["top"][0].get("total_for_all_travellers")
             or r["top"][0]["total_for_stay"]) for r in seen_turn if r.get("top")]  # fmt: skip


def _trip(w, brain, purpose):  # noqa: F811
    ws = center.company_workspace(w.orgs.get(w.org.id))  # the Discord server the chat runs in
    rows = brain.bot.docs.find(trips.TRIP_KIND, ws.memory_id)
    (trip,) = [r for r in rows if r.get("purpose") == purpose]
    return trip


def _purpose(name: str) -> str:
    """The headless bot (and its trips) lives for the whole test process: a unique purpose per
    test run finds this test's trip, never another test's."""
    return f"{name} {uuid4().hex[:8]}"


def test_a_trip_is_searched_quoted_and_booked_in_the_web_chat(w, brain):  # noqa: F811
    """The headless path (a Discord-linked company): ONE search per job, the result's booking_ref
    goes to book_trip, the quote waits for a yes, and the yes is booked by code (sandbox)."""
    find, book = "flights BKK->SIN 2026-11-03 for 2 and a hotel for 3 nights", "book those two"
    brain.script[find] = [("search_flights", OUT), ("search_hotels", {"nights": 3})]
    got = say(w, find)
    assert (
        got["travel"]["flights"] == FLIGHT and got["travel"]["hotels"]["check_out"] == "2026-11-06"
    )
    (fref, ftotal), (href, htotal) = _refs(brain.seen[-1])
    assert fref == "BKKSIN.SL106-20261103-E.2" and href.startswith("SIN.harbourlight.")
    why = _purpose("Lumen kickoff")
    brain.script[book] = [("book_trip", {"flight_offer_id": fref, "hotel_offer_id": href,
                                         "purpose": why})]  # fmt: skip
    say(w, book)
    quote = brain.seen[-1][0]
    assert quote["status"] == "needs_confirmation"
    assert quote["quote"]["totals"] == [{"amount": ftotal + htotal, "currency": "THB"}]
    done = say(w, "yes")  # no model call: trips' on_confirm books the quote just shown
    assert brain.seen[-1] == [] and "sandbox" in done["answer"].lower()
    trip = _trip(w, brain, why)
    assert trip["references"]["flight"] in done["answer"]
    assert trip["references"]["hotel"] in done["answer"]
    receipts = [brain.bot.store.get(i) for i in trip["receipt_ids"]]
    assert sorted(r.total for r in receipts) == sorted([ftotal, htotal]) == [6380, 23070]
    assert all(r.currency == "THB" and r.category == "ค่าเดินทาง" for r in receipts)


def test_a_round_trip_books_both_legs_as_one_flight(w, brain):  # noqa: F811
    find, book = "round trip BKK SIN 3 to 6 Nov for 2", "book out and back"
    brain.script[find] = [("search_flights", OUT), ("search_flights", BACK)]
    got = say(w, find)
    assert got["travel"]["flights"] == FLIGHT
    assert got["travel"]["return_flights"] == {**FLIGHT, "origin": "SIN", "destination": "BKK",
                                               "depart": "2026-11-06"}  # fmt: skip
    (out, out_total), (back, back_total) = _refs(brain.seen[-1])
    assert back.startswith("SINBKK.") and back.endswith("-20261106-E.2")
    why = _purpose("Round trip")
    brain.script[book] = [("book_trip", {"flight_offer_id": out, "return_flight_offer_id": back,
                                         "purpose": why})]  # fmt: skip
    say(w, book)
    assert brain.seen[-1][0]["status"] == "needs_confirmation"
    done = say(w, "yes")
    assert "sandbox" in done["answer"].lower()
    trip = _trip(w, brain, why)  # the plain yes kept the way back
    assert trip["depart_date"] == "2026-11-03" and trip["return_date"] == "2026-11-06"
    assert [brain.bot.store.get(i).total for i in trip["receipt_ids"]] == [out_total + back_total]


def test_the_web_only_path_searches_but_cannot_book(w, brain, monkeypatch):  # noqa: F811
    monkeypatch.setattr(center, "get_bot", lambda: None)  # no headless bot: the lighter tool set
    brain.script["flights BKK->SIN"] = [("search_flights", OUT)]
    got = say(w, "flights BKK->SIN")
    assert got["travel"]["flights"] == FLIGHT
    result = brain.seen[-1][0]
    assert result["status"] == "ok" and "only book_trip" in result["rule"]
    assert {"search_flights", "search_hotels"} <= brain.offered[-1]
    assert "book_trip" not in brain.offered[-1]  # nothing books without the bot's trips tools


def test_the_web_only_path_has_the_weather_card_too(w, brain, monkeypatch):  # noqa: F811
    from test_weather_cards import Net

    monkeypatch.setattr(center, "get_bot", lambda: None)
    svc = Net().service()  # fake Open-Meteo, shared with the public weather route
    monkeypatch.setattr(travel_api, "get_weather", lambda: svc)
    brain.script["weather in Singapore"] = [("weather", {"place": "Singapore"})]
    got = say(w, "weather in Singapore")
    assert got["travel"]["weather"]["place"] == "Singapore" and "weather" in brain.offered[-1]
    monkeypatch.setattr(travel_api, "get_weather", lambda: None)  # DORY_WEATHER_PROVIDER=off
    say(w, "hello")
    assert "weather" not in brain.offered[-1]


def test_a_chat_yes_after_a_card_quote_or_booking_books_nothing(w, brain):  # noqa: F811
    """Card booking (`/travel/book`) and the chat's plain-yes shortcut must not cross: a "yes" in
    chat after a card quote, or after the card's Confirm, books nothing more."""
    ref = "BKKSIN.SL106-20261103-E.2"
    ws = center.company_workspace(w.orgs.get(w.org.id))
    before = {t["id"] for t in brain.bot.docs.find(trips.TRIP_KIND, ws.memory_id)}

    def mine():
        return [t for t in brain.bot.docs.find(trips.TRIP_KIND, ws.memory_id)
                if t["id"] not in before]  # fmt: skip

    def card(confirm):
        r = w.client.post("/api/center/orgs/org_t/travel/book", headers=H["mem"],
                          json={"flight_ref": ref, "purpose": "card", "confirm": confirm})  # fmt: skip
        assert r.status_code == 200, r.text
        return r.json()

    assert card(False)["status"] == "needs_confirmation"
    assert say(w, "yes")["answer"] == "ans:yes" and not mine()  # the brain answered, nothing booked
    assert card(True)["status"] == "booked" and len(mine()) == 1
    assert say(w, "yes")["answer"] == "ans:yes" and len(mine()) == 1
