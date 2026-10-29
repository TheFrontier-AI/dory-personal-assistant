# ruff: noqa: F811, F401
"""Trips: sample provider, the Duffel and LiteAPI sandbox adapters (mocked transport) with the
fallback, and the tools through the bot's real wiring (confirm gate, approval gate, ledger receipts,
check-in reminder, trip record, profile). Offline."""

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


def _duffel_offer(oid, amount, slices):
    """A Duffel offer; `slices` = per slice, a list of (carrier, number, from, to, departs, arrives)."""
    seg = lambda c, n, o, d, t1, t2: {  # noqa: E731
        "marketing_carrier": {"iata_code": c, "name": "Duffel Airways"},
        "marketing_carrier_flight_number": n, "origin": {"iata_code": o},
        "destination": {"iata_code": d}, "departing_at": t1, "arriving_at": t2,
    }  # fmt: skip
    return {"id": oid, "total_amount": amount, "total_currency": "USD",
            "owner": {"iata_code": "ZZ", "name": "Duffel Airways"},
            "passengers": [{"id": "pas_1", "type": "adult"}],
            "slices": [{"duration": "PT2H25M", "segments": [seg(*s) for s in sl]} for sl in slices]}  # fmt: skip


def test_duffel_adapter_parses_offers_and_books_with_the_booking_reference():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "api.duffel.com" and req.headers["duffel-version"] == "v2"
        assert req.headers["authorization"] == "Bearer duffel_test_abc"
        body = json.loads(req.content)
        if req.url.path == "/air/offer_requests":
            assert req.url.params["return_offers"] == "true"
            assert [s["departure_date"] for s in body["data"]["slices"]] == [DEP, RET]
            assert body["data"]["cabin_class"] == "economy" and len(body["data"]["passengers"]) == 1
            out = [("ZZ", "1", "BKK", "SIN", f"{DEP}T08:00:00", f"{DEP}T11:25:00")]
            back = [("ZZ", "2", "SIN", "BKK", f"{RET}T12:25:00", f"{RET}T13:55:00")]
            return httpx.Response(201, json={"data": {"live_mode": False, "offers": [
                _duffel_offer("off_b", "310.00", [out, back]),
                _duffel_offer("off_a", "250.50", [out, back]),
            ]}})  # fmt: skip
        if req.url.path == "/air/orders":
            d = body["data"]
            assert d["type"] == "instant" and d["selected_offers"] == ["off_a"]
            assert d["payments"] == [{"type": "balance", "amount": "250.50", "currency": "USD"}]
            p = d["passengers"][0]
            assert (p["id"], p["given_name"], p["family_name"]) == ("pas_1", "MINT", "SRISUWAN")
            return httpx.Response(
                201, json={"data": {"id": "ord_1", "booking_reference": "RZPNX8"}}
            )
        raise AssertionError(req.url.path)

    d = trips.Duffel("duffel_test_abc", transport=httpx.MockTransport(handler))
    offers = d.flights("BKK", "SIN", DEP, RET, 1, "economy")
    assert [o.price for o in offers] == [250.5, 310.0]  # cheapest first
    o = offers[0]
    assert o.flights == ["ZZ1", "ZZ2"] and o.carrier_name == "Duffel Airways"
    assert o.duration_min == 145 and o.return_depart == f"{RET}T12:25:00" and o.currency == "USD"
    tr = {"first": "MINT", "last": "SRISUWAN", "email": "x@example.com", "phone": "+66812345678"}
    assert d.book_flight(o, tr).reference == "RZPNX8"


def test_iso_durations_with_days_and_seconds():
    assert trips._minutes("P1DT2H5M30S") == 1440 + 125 and trips._minutes("PT02H26M") == 146
    assert trips._minutes("") == 0


def test_duffel_refuses_live_tokens_and_live_answers():
    with pytest.raises(ValueError):
        trips.Duffel("duffel_live_abc")
    d = trips.Duffel("duffel_test_x", transport=httpx.MockTransport(
        lambda req: httpx.Response(201, json={"data": {"live_mode": True, "offers": []}})
    ))  # fmt: skip
    with pytest.raises(RuntimeError):
        d.flights("BKK", "SIN", DEP, "", 1, "economy")


def _liteapi(handler):
    return trips.LiteApi("sand_key", transport=httpx.MockTransport(handler))


def test_liteapi_adapter_parses_rates_and_books_through_prebook():
    def rate(tag, until):
        return {"name": "Deluxe King", "cancellationPolicies": {
            "refundableTag": tag, "cancelPolicyInfos": [{"cancelTime": until}]}}  # fmt: skip

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["x-api-key"] == "sand_key"
        body = json.loads(req.content)
        where = (req.url.host, req.url.path)
        if where == ("api.liteapi.travel", "/v3.0/hotels/rates"):
            assert body["iataCode"] == "SIN" and body["occupancies"] == [{"adults": 1}]
            assert (body["checkin"], body["checkout"]) == (DEP, RET)
            return httpx.Response(200, json={"sandbox": True, "data": [
                {"hotelId": "lp1", "roomTypes": [{"offerId": "OFF1", "rates": [rate("RFN", "2026-11-10 12:00:00")],
                                                  "offerRetailRate": [{"amount": 9000, "currency": "THB"}]}]},
                {"hotelId": "lp2", "roomTypes": [{"offerId": "OFF2", "rates": [rate("NRFN", "")],
                                                  "offerRetailRate": {"amount": 6000, "currency": "THB"}}]},
                {"hotelId": "lp3", "roomTypes": []},
            ], "hotels": [{"id": "lp1", "name": "The Fullerton Hotel", "address": "1 Fullerton Sq"}]})  # fmt: skip
        if where == ("book.liteapi.travel", "/v3.0/rates/prebook"):
            assert body == {"offerId": "OFF1", "usePaymentSdk": False}
            return httpx.Response(200, json={"data": {"prebookId": "PB1"}})
        if where == ("book.liteapi.travel", "/v3.0/rates/book"):
            assert body["prebookId"] == "PB1" and body["payment"] == {"method": "ACC_CREDIT_CARD"}
            assert body["holder"]["lastName"] == "SRISUWAN"
            assert body["guests"][0]["occupancyNumber"] == 1
            return httpx.Response(200, json={"sandbox": True, "data": {
                "bookingId": "BK1", "hotelConfirmationCode": "HC77", "status": "CONFIRMED"}})  # fmt: skip
        raise AssertionError(where)

    h = _liteapi(handler)
    offers = h.hotels("SIN", DEP, RET, 1)
    assert [(o.hotel_id, o.total) for o in offers] == [("lp2", 6000), ("lp1", 9000)]
    assert offers[0].name == "lp2" and offers[0].cancellation == "non-refundable"
    fullerton = offers[1]
    assert fullerton.name == "The Fullerton Hotel" and fullerton.price_per_night == 4500
    assert fullerton.cancellation == "free cancellation until 2026-11-10 12:00:00"
    b = h.book_hotel(fullerton, {"first": "MINT", "last": "SRISUWAN", "email": "x@example.com"})
    assert (b.reference, b.status, b.provider) == ("BK1", "CONFIRMED", "liteapi")


def test_liteapi_refuses_answers_outside_its_sandbox():
    h = _liteapi(lambda req: httpx.Response(200, json={"data": [], "sandbox": False}))
    with pytest.raises(RuntimeError):
        h.hotels("SIN", DEP, RET, 1)


def test_fallback_serves_the_sample_for_searches_but_never_fakes_a_booking(caplog):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/air/offer_requests":
            return httpx.Response(500)
        if req.url.path == "/air/orders":
            return httpx.Response(422, json={"errors": [{"message": "offer expired"}]})
        raise AssertionError(req.url.path)

    duffel = trips.Duffel("duffel_test_x", transport=httpx.MockTransport(handler))
    f = trips.Fallback(trips.Split(duffel, None))  # no hotel key: that half answers nothing
    flights = f.flights("BKK", "SIN", DEP, "", 1, "economy")
    assert flights and flights[0].provider == "sample"
    hotels = f.hotels("SIN", DEP, RET, 1)
    assert hotels and hotels[0].provider == "sample"
    assert f.book_flight(flights[0], {"last": "X"}).provider == "sample"  # sample offer, sample PNR
    assert "flights failed (HTTPStatusError)" in caplog.text and "hotels empty" in caplog.text
    raw = {"id": "off_1", "amount": "1.00", "currency": "USD", "passengers": ["pas_1"]}
    sandbox_offer = flights[0].model_copy(update={"provider": "duffel", "raw": raw})
    tr = {"first": "A", "last": "B", "email": "x@example.com", "phone": "+66812345678"}
    with pytest.raises(httpx.HTTPStatusError):  # the error surfaces; no sample PNR stands in for it
        f.book_flight(sandbox_offer, tr)


class _Settings:
    travel_provider = ""
    duffel_token = ""
    liteapi_key = ""


def test_make_provider_uses_free_sandboxes_only():
    assert isinstance(trips.make_provider(_Settings()), trips.SampleProvider)
    s = _Settings()
    s.duffel_token, s.liteapi_key = "duffel_test_x", "sand_key"
    p = trips.make_provider(s)
    assert isinstance(p, trips.Fallback) and p.name == "duffel+liteapi"
    s.duffel_token = "duffel_live_x"  # a live token could spend money: flights use the sample
    assert trips.make_provider(s).name == "liteapi"
    s.liteapi_key = ""
    assert isinstance(trips.make_provider(s), trips.SampleProvider)
    s.duffel_token, s.travel_provider = "duffel_test_x", "sample"
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
    # a re-search may quote another price or seat count for the same flight: still the same flight
    redo = trips.OFFERS._items[fid2][0]
    redo.price, redo.seats = redo.price + 850, 3
    assert tl2["book_trip"](fid2, hid2, "Lumen kickoff")["trip_id"] == done["trip_id"]
    alone = tl2["book_trip"](fid2)  # the flight alone: still that trip's flight
    assert alone["status"] == "already_booked" and alone["already"] == ["flight"]
    # only a new hotel: proposed, then booked on its own (the flight is not booked again)
    other = tl2["search_hotels"]("SIN", DEP, RET)["hotels"][2]["offer_id"]
    assert tl2["book_trip"](hotel_offer_id=other)["status"] == "needs_confirmation"
    hotel_only = tools(bot, world)["book_trip"](hotel_offer_id=other)
    assert hotel_only["status"] == "booked" and list(hotel_only["references"]) == ["hotel"]
    assert tools(bot, world)["list_trips"](upcoming=False)["count"] == 2


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


# ----------------------------------------------------------------------------- a plain yes, booked by code
@pytest.mark.parametrize(
    "text",
    ["Yes, confirm.", "yes book it", "Confirm", "ok", "Go ahead!", "yes please", "Dory, yes",
     "ยืนยันค่ะ", "จองเลย", "ใช่ค่ะ จองเลย", "ได้เลยค่ะ"],
)  # fmt: skip
def test_a_plain_yes_is_a_confirmation(text):
    assert trips.is_confirmation(text)


@pytest.mark.parametrize(
    "text",
    ["", "no", "please", "yes but the cheaper hotel", "confirm the hotel only", "yesterday",
     "what is the total?", "จองโรงแรมอื่น", "yes " * 20],
)  # fmt: skip
def test_anything_more_than_a_plain_yes_is_not(text):
    assert not trips.is_confirmation(text)


async def test_a_plain_yes_after_a_quote_is_booked_by_code_not_the_model(bot, world):
    tl = tools(bot, world)
    fid = tl["search_flights"]("BKK", "SIN", DEP, RET)["flights"][0]["offer_id"]
    hid = tl["search_hotels"]("SIN", DEP, RET)["hotels"][3]["offer_id"]
    assert tl["book_trip"](fid, hid, "Lumen kickoff")["status"] == "needs_confirmation"
    kw = kw_for(bot, world)  # the person's next message, through the real agent wiring
    uid = kw.pop("user_id", STAFF)
    ans = await qa.ask_async(
        bot.s, bot.store, "Yes, confirm.", guild_id=GUILD, is_exec=False, user_id=uid,
        model=object(), **kw,
    )  # fmt: skip
    assert ans.rounds == 0 and ans.tool_calls == [("book_trip", {})]  # the model was never asked
    trip = tools(bot, world)["list_trips"]()["trips"][0]
    assert ans.text.startswith("Booked!") and trip["id"] in ans.text
    assert trip["references"]["flight"] in ans.text and trip["references"]["hotel"] in ans.text
    assert "13,700.00 THB + 420.00 SGD" in ans.text
    assert "2026-11-11 08:00" in ans.text  # the stored check-in reminder, in Bangkok time


async def test_only_a_plain_yes_in_the_very_next_message_books(bot, world):
    tl = tools(bot, world)
    fid = tl["search_flights"]("BKK", "SIN", DEP, RET)["flights"][0]["offer_id"]
    assert tl["book_trip"](fid, "", "Lumen kickoff")["status"] == "needs_confirmation"
    assert tools(bot, world, who=BOSS)["book_trip"].on_confirm("yes") is None  # not BOSS's quote
    assert tools(bot, world)["book_trip"].on_confirm("yes, but the later flight") is None
    assert tools(bot, world)["book_trip"].on_confirm("Yes, confirm.") is None  # a message too late
    assert tools(bot, world)["list_trips"]()["count"] == 0


async def test_a_refused_booking_after_a_plain_yes_says_so(bot, world, monkeypatch):
    def refuse(offer, traveller):
        raise RuntimeError("hotel sold out")

    tl = tools(bot, world)
    fid = tl["search_flights"]("BKK", "SIN", DEP, RET)["flights"][0]["offer_id"]
    hid = tl["search_hotels"]("SIN", DEP, RET)["hotels"][3]["offer_id"]
    assert tl["book_trip"](fid, hid, "Lumen kickoff")["status"] == "needs_confirmation"
    monkeypatch.setattr(bot.trips_provider, "book_hotel", refuse)
    text = tools(bot, world)["book_trip"].on_confirm("yes")
    assert text.startswith("I couldn't book it") and "Booked before the error: flight " in text
    assert tools(bot, world)["list_trips"]()["count"] == 0


async def test_hotel_results_and_the_quote_say_they_are_sandbox(bot, world):
    tl = tools(bot, world)
    hotels = tl["search_hotels"]("SIN", DEP, RET)
    assert "sandbox" in hotels["note"]
    quote = tl["book_trip"]("", hotels["hotels"][0]["offer_id"], "x")
    assert quote["status"] == "needs_confirmation" and "sandbox quote" in quote["instruction"]
