# ruff: noqa: F811, F401
"""Trips: sample provider, the Amadeus adapter (mocked transport) with its fallback, and the tools
through the bot's real wiring (confirm gate, approval gate, ledger receipts, check-in reminder,
trip record, profile). Offline."""

import json

import httpx
import pytest
from conftest import GUILD
from test_coordinator import BOSS, STAFF, world
from test_modes import bot

from dory import qa, trips
from dory.approvals import Approval
from dory.guild_settings import GuildSettingsUpdate
from dory.voice_actions import ACTION_TOOL_NAMES

DEP, RET = "2026-11-12", "2026-11-14"  # the bot fixture's clock is 2026-10-14


def test_sample_provider_is_deterministic_and_mirrors_the_return_leg():
    p = trips.SampleProvider()
    out = p.flights("BKK", "SIN", DEP, RET, 1, "economy")
    assert [o.carrier for o in out] == ["TG", "SQ", "TG", "SQ", "SQ"]
    first = out[0]
    assert first.flights == ["TG403", "TG404"] and first.price == 13700 and first.currency == "THB"
    assert first.depart == f"{DEP}T08:00:00" and first.return_depart == f"{RET}T08:00:00"
    back = p.flights("SIN", "BKK", DEP, "", 1, "business")[0]
    assert back.flights == ["TG404"] and back.price == round(6850 * 2.8)
    assert p.flights("BKK", "XXX", DEP, "", 1, "economy") == []
    hotels = p.hotels("SIN", DEP, RET, 1)
    assert (
        hotels[0].name == "Marina Bay Sands" and hotels[0].nights == 2 and hotels[0].total == 1378
    )
    assert hotels[0].currency == "SGD"
    tr = {"first": "MINT", "last": "SRISUWAN"}
    assert p.book_flight(first, tr).reference == p.book_flight(first, tr).reference
    assert len(p.book_flight(first, tr).reference) == 6
    assert len(p.book_hotel(hotels[0], tr).reference) == 8


def _amadeus(handler):
    return trips.Amadeus(
        "id", "secret", transport=httpx.MockTransport(handler), clock=lambda: 1000.0
    )


def test_amadeus_adapter_parses_offers_and_books_with_the_pnr():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path, dict(req.headers)))
        if req.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 1799})
        if req.url.path == "/v2/shopping/flight-offers":
            assert req.url.params["currencyCode"] == "THB" and req.url.params["returnDate"] == RET
            seg = lambda c, n, o, d, t1, t2: {  # noqa: E731
                "carrierCode": c, "number": n, "departure": {"iataCode": o, "at": t1},
                "arrival": {"iataCode": d, "at": t2},
            }  # fmt: skip
            return httpx.Response(200, json={"data": [{
                "id": "1", "validatingAirlineCodes": ["TG"], "numberOfBookableSeats": 4,
                "price": {"grandTotal": "9400.00", "currency": "THB"},
                "itineraries": [
                    {"duration": "PT2H25M", "segments": [seg("TG", "403", "BKK", "SIN", f"{DEP}T08:00:00", f"{DEP}T11:25:00")]},
                    {"duration": "PT2H30M", "segments": [seg("TG", "404", "SIN", "BKK", f"{RET}T12:25:00", f"{RET}T13:55:00")]},
                ],
            }], "dictionaries": {"carriers": {"TG": "THAI AIRWAYS INTERNATIONAL"}}})  # fmt: skip
        if req.url.path == "/v1/shopping/flight-offers/pricing":
            assert req.headers["x-http-method-override"] == "GET"
            body = json.loads(req.content)
            return httpx.Response(
                200, json={"data": {"flightOffers": body["data"]["flightOffers"]}}
            )
        if req.url.path == "/v1/booking/flight-orders":
            body = json.loads(req.content)
            assert body["data"]["travelers"][0]["name"] == {
                "firstName": "MINT",
                "lastName": "SRISUWAN",
            }
            return httpx.Response(
                201, json={"data": {"id": "eJzTd9", "associatedRecords": [{"reference": "2ZYVAL"}]}}
            )
        raise AssertionError(req.url.path)

    a = _amadeus(handler)
    offers = a.flights("BKK", "SIN", DEP, RET, 1, "economy")
    assert len(offers) == 1
    o = offers[0]
    assert o.flights == ["TG403", "TG404"] and o.carrier_name == "Thai Airways International"
    assert o.duration_min == 145 and o.price == 9400 and o.return_depart == f"{RET}T12:25:00"
    tr = {"first": "MINT", "last": "SRISUWAN", "email": "x@example.com", "phone": "+66812345678"}
    assert a.book_flight(o, tr).reference == "2ZYVAL"
    assert [c[1] for c in calls].count("/v1/security/oauth2/token") == 1  # the token is reused


def test_fallback_serves_the_sample_on_errors_and_empty_answers(caplog):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 1799})
        if req.url.path == "/v2/shopping/flight-offers":
            return httpx.Response(500)
        if req.url.path.endswith("/hotels/by-city"):
            return httpx.Response(200, json={"data": []})
        raise AssertionError(req.url.path)

    f = trips.Fallback(_amadeus(handler))
    flights = f.flights("BKK", "SIN", DEP, "", 1, "economy")
    assert flights and flights[0].provider == "sample"
    hotels = f.hotels("SIN", DEP, RET, 1)
    assert hotels and hotels[0].provider == "sample"
    assert (
        f.book_flight(flights[0], {"last": "X"}).provider == "sample"
    )  # never the sandbox for a sample offer
    assert "flights failed (HTTPStatusError)" in caplog.text and "hotels empty" in caplog.text


class _Settings:
    travel_provider = ""
    amadeus_client_id = ""
    amadeus_client_secret = ""
    amadeus_base = ""


def test_make_provider_picks_sample_without_a_key_and_the_sandbox_with_one():
    assert isinstance(trips.make_provider(_Settings()), trips.SampleProvider)
    s = _Settings()
    s.amadeus_client_id, s.amadeus_client_secret = "id", "secret"
    assert isinstance(trips.make_provider(s), trips.Fallback)
    s.travel_provider = "sample"
    assert isinstance(trips.make_provider(s), trips.SampleProvider)


# ----------------------------------------------------------------------------- tools via the bot
def kw_for(bot, world, who=STAFF, is_exec=False):
    member = world.g.members[who]
    msg = bot.room_message(world.g, member, world.pub)
    return bot._agent_kwargs(
        msg, world.g, member, is_exec, setting="en", lang="en", question="q", memory=None,
        profile=None,
    )  # fmt: skip


def tools(bot, world, who=STAFF, is_exec=False):
    return {f.__name__: f for f in kw_for(bot, world, who, is_exec)["extra_tools"]}


async def test_tools_are_registered_and_the_flag_removes_them(bot, world):
    names = set(tools(bot, world))
    assert {"search_flights", "search_hotels", "book_trip", "travel_profile", "list_trips"} <= names
    assert {"book_trip", "travel_profile"} <= ACTION_TOOL_NAMES
    assert "search_flights" not in ACTION_TOOL_NAMES  # a read stays in the room agent
    bot.guilds_store.save_settings(GUILD, GuildSettingsUpdate(features={"travel": False}), "x")
    bot.team._cache.clear()
    assert not set(tools(bot, world)) & {"search_flights", "book_trip"}


async def test_search_validates_and_returns_sample_offers(bot, world):
    tl = tools(bot, world)
    assert tl["search_flights"]("BKK", "BKK", DEP)["status"] == "error"
    assert "past" in tl["search_flights"]("BKK", "SIN", "2026-01-01")["error"]
    assert tl["search_flights"]("BKK", "SIN", DEP, "2026-11-11")["status"] == "error"
    assert tl["search_flights"]("BKK", "SIN", DEP, cabin="deck")["status"] == "error"
    res = tl["search_flights"]("BKK", "SIN", DEP, RET)
    assert res["status"] == "ok" and res["source"] == "sample" and len(res["flights"]) == 5
    f = res["flights"][0]
    assert f["offer_id"].startswith("F") and "raw" not in f and f["price"] == 13700
    assert tl["search_flights"]("BKK", "XXX", DEP)["status"] == "none"
    assert tl["search_hotels"]("SIN", DEP, DEP)["status"] == "error"
    hres = tl["search_hotels"]("SIN", DEP, RET)
    assert hres["status"] == "ok" and hres["hotels"][0]["offer_id"].startswith("H")


async def test_book_trip_confirms_then_books_files_receipts_and_sets_the_reminder(bot, world):
    tl = tools(bot, world)
    fid = tl["search_flights"]("BKK", "SIN", DEP, RET)["flights"][0]["offer_id"]
    hid = tl["search_hotels"]("SIN", DEP, RET)["hotels"][3]["offer_id"]  # Carlton City, in policy
    assert tl["book_trip"]()["status"] == "error"
    assert tl["book_trip"]("F999")["status"] == "expired"
    # another person (or another server) cannot book an offer that was shown to Mint
    assert tools(bot, world, who=BOSS)["book_trip"](fid)["status"] == "expired"
    first = tl["book_trip"](fid, hid, "Lumen kickoff")
    assert first["status"] == "needs_confirmation"
    assert first["quote"]["totals"] == [
        {"amount": 13700, "currency": "THB"},
        {"amount": 420, "currency": "SGD"},
    ]
    # the same request id again is still the proposal; a later message (new tools) confirms
    assert tl["book_trip"](fid, hid, "Lumen kickoff")["status"] == "needs_confirmation"
    done = tools(bot, world)["book_trip"](fid, hid, "Lumen kickoff")
    assert done["status"] == "booked" and done["provider"] == "sample"
    assert len(done["references"]["flight"]) == 6 and len(done["references"]["hotel"]) == 8
    assert len(done["filed_receipts"]) == 2
    r = bot.store.get(done["filed_receipts"][0])
    assert r.category == "ค่าเดินทาง" and r.vendor == "Thai Airways" and r.total == 13700
    assert "Lumen kickoff" in r.notes and done["references"]["flight"] in r.notes
    assert bot.store.get(done["filed_receipts"][1]).currency == "SGD"
    rem = bot.reminder_book.get(GUILD, done["checkin_reminder"])
    assert (
        rem["kind"] == "once" and rem["next_at"] == "2026-11-11T01:00:00+00:00"
    )  # 08:00 Bangkok, 24 h before
    assert "TG403" in rem["message"] and rem["user_id"] == STAFF
    trip = bot.docs.get(trips.TRIP_KIND, GUILD, done["trip_id"])
    assert (
        trip["destination"] == "SIN" and trip["depart_date"] == DEP and trip["return_date"] == RET
    )
    # a colleague sees the trip without amounts; the traveller and executives with them
    other = tools(bot, world, who=BOSS)["list_trips"]()
    assert other["trips"][0]["user_name"] and "totals" not in other["trips"][0]
    assert tools(bot, world, who=BOSS, is_exec=True)["list_trips"]()["trips"][0]["totals"]
    assert tools(bot, world)["list_trips"]()["trips"][0]["references"] == done["references"]
    assert tools(bot, world)["list_trips"](upcoming=False)["count"] == 1
    # asked again (a second "yes", a voice retry): the same trip, never a second booking
    for _ in range(2):
        again = tools(bot, world)["book_trip"](fid, hid, "Lumen kickoff")
        assert again["status"] == "already_booked" and again["trip_id"] == done["trip_id"]
        assert again["references"] == done["references"]
    # the same flight and hotel found by a new search (new offer ids) is still that trip
    tl2 = tools(bot, world)
    fid2 = tl2["search_flights"]("BKK", "SIN", DEP, RET)["flights"][0]["offer_id"]
    hid2 = tl2["search_hotels"]("SIN", DEP, RET)["hotels"][3]["offer_id"]
    assert (fid2, hid2) != (fid, hid)
    assert tl2["book_trip"](fid2, hid2, "Lumen kickoff")["trip_id"] == done["trip_id"]
    alone = tl2["book_trip"](fid2)  # the flight alone: still that trip's flight
    assert alone["status"] == "already_booked" and alone["already"] == ["flight"]
    other = tl2["search_hotels"]("SIN", DEP, RET)["hotels"][2]["offer_id"]  # another hotel
    assert tl2["book_trip"](hotel_offer_id=other)["status"] == "needs_confirmation"
    assert tools(bot, world)["list_trips"](upcoming=False)["count"] == 1


async def test_book_trip_refuses_an_approval_that_is_not_approved_or_not_mine(bot, world):
    tl = tools(bot, world)
    hid = tl["search_hotels"]("SIN", DEP, RET)["hotels"][0]["offer_id"]
    pending = bot.approvals.create(
        Approval(guild_id=GUILD, requester_id=STAFF, approver_id=BOSS, title="hotel")
    )
    assert tl["book_trip"](hotel_offer_id=hid, approval_id="nope")["reason"] == "approval_unknown"
    assert (
        tl["book_trip"](hotel_offer_id=hid, approval_id=pending.id)["reason"] == "approval_pending"
    )
    bot.approvals.decide(pending.id, "declined")
    assert (
        tl["book_trip"](hotel_offer_id=hid, approval_id=pending.id)["reason"] == "approval_declined"
    )
    theirs = bot.approvals.create(
        Approval(guild_id=GUILD, requester_id=BOSS, approver_id=BOSS, title="x")
    )
    bot.approvals.decide(theirs.id, "approved")
    assert (
        tl["book_trip"](hotel_offer_id=hid, approval_id=theirs.id)["reason"] == "approval_unknown"
    )
    mine = bot.approvals.create(
        Approval(guild_id=GUILD, requester_id=STAFF, approver_id=BOSS, title="hotel")
    )
    bot.approvals.decide(mine.id, "approved")
    assert (
        tl["book_trip"](hotel_offer_id=hid, approval_id=mine.id)["status"] == "needs_confirmation"
    )
    done = tools(bot, world)["book_trip"](hotel_offer_id=hid, approval_id=mine.id)
    assert (
        done["status"] == "booked" and "checkin_reminder" not in done
    )  # hotel only: no flight reminder
    assert bot.docs.get(trips.TRIP_KIND, GUILD, done["trip_id"])["approval_id"] == mine.id


async def test_travel_profile_round_trip_and_passport_name_feeds_the_booking(bot, world):
    tl = tools(bot, world)
    assert tl["travel_profile"]()["empty"] is True
    saved = tl["travel_profile"]("passport name SRISUWAN/MINT, window seat, vegetarian meal")
    assert saved["status"] == "saved" and "window seat" in saved["profile"]
    assert tl["travel_profile"]()["profile"] == saved["profile"]
    ctx = trips.TripsCtx(GUILD, STAFF, "Mint S", False, "en", None, bot.docs, bot.store,
                         bot.secretary_state, "r", bot.s.now)  # fmt: skip
    assert (
        trips.traveller_for(ctx)["first"] == "MINT"
        and trips.traveller_for(ctx)["last"] == "SRISUWAN"
    )
    assert tl["travel_profile"](clear=True)["status"] == "cleared"
    assert trips.traveller_for(ctx) == {"first": "MINT", "last": "S", "email": "traveller@example.com",
                                        "phone": "+66812345678"}  # fmt: skip


def test_prompt_section_rides_on_the_travel_tools(bot):
    assert "book_trip" not in qa.system_prompt(bot.s, scoped=False)
    on = qa.system_prompt(bot.s, scoped=False, travel=True)
    assert "book_trip" in on and "Shall I book it?" in on
