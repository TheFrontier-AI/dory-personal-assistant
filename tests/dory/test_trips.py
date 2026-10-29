# ruff: noqa: F811, F401
"""Trips: sample provider, the Duffel and LiteAPI sandbox adapters (mocked transport) with the
fallback, and the tools through the bot's real wiring (confirm gate, approval gate, ledger receipts,
check-in reminder, trip record, profile). Offline."""

import json
from datetime import UTC, datetime, timedelta

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
def kw_for(bot, world, who=STAFF, is_exec=False, spoken=False):
    """Typed chat (`spoken` False) or voice (True): both builders get THE flight / hotel search
    (dory.travel_search's card tools) and book_trip, which books their booking_refs."""
    member = world.g.members[who]
    msg = bot.room_message(world.g, member, world.pub)
    return bot._agent_kwargs(
        msg, world.g, member, is_exec, setting="en", lang="en", question="q", memory=None,
        profile=None, spoken=spoken,
    )  # fmt: skip


def tools(bot, world, who=STAFF, is_exec=False, spoken=False):
    return {f.__name__: f for f in kw_for(bot, world, who, is_exec, spoken)["extra_tools"]}


def said(tl, text="Go ahead and book it for the kickoff"):
    """The person's next message as `qa.ask_async` hands it to the tools before the model runs; a
    wordy yes is not booked by code, so the model's own book_trip call is what books."""
    assert tl["book_trip"].on_confirm(text) is None
    return tl


def trip(tl):
    """Out on DEP, back on RET (the second search is the way back) and Bugis Garden's cheapest
    room for those nights: the search results' booking_refs."""
    out = tl["search_flights"](origin="BKK", destination="SIN", depart_date=DEP)["top"][0]
    back = tl["search_flights"](origin="SIN", destination="BKK", depart_date=RET)["top"][0]
    room = tl["search_hotels"](hotel_id="bugis-garden")["rooms"][0]  # SIN, DEP -> RET: the trip
    return out, back, room


def room_of(tl, hotel_id):
    """The cheapest room of `hotel_id` for DEP -> RET in Singapore."""
    got = tl["search_hotels"](city="SIN", check_in=DEP, check_out=RET, hotel_id=hotel_id)
    return got["rooms"][0]


def checkin_at(out) -> datetime:
    """24 h before the first flight, which departs at Bangkok time (UTC+7)."""
    return datetime.fromisoformat(f"{out['depart']}+07:00") - timedelta(hours=24)


@pytest.mark.parametrize("spoken", [False, True])
async def test_tools_are_registered_and_the_flag_removes_them(bot, world, spoken):
    names = [f.__name__ for f in kw_for(bot, world, spoken=spoken)["extra_tools"]]
    assert {"search_flights", "search_hotels", "book_trip", "travel_profile", "list_trips"} <= set(
        names
    )
    assert names.count("search_flights") == names.count("search_hotels") == 1  # ONE search each
    assert {"book_trip", "travel_profile"} <= ACTION_TOOL_NAMES
    assert "search_flights" not in ACTION_TOOL_NAMES  # a read stays in the room agent
    bot.guilds_store.save_settings(GUILD, GuildSettingsUpdate(features={"travel": False}), "x")
    bot.team._cache.clear()
    assert not set(tools(bot, world, spoken=spoken)) & {"search_flights", "book_trip"}


async def test_the_one_search_validates_and_returns_booking_refs(bot, world):
    tl = tools(bot, world)
    assert tl["search_flights"](destination="SIN")["status"] == "need_details"  # no trip yet
    bad = tl["search_flights"](origin="BKK", destination="BKK", depart_date=DEP)
    assert bad["status"] == "invalid"
    past = tl["search_flights"](origin="BKK", destination="SIN", depart_date="2026-01-01")
    assert past["problem"] == "past_date"
    deck = tl["search_flights"](origin="BKK", destination="SIN", depart_date=DEP, cabin="deck")
    assert deck["status"] == "invalid"
    where = tl["search_flights"](origin="BKK", destination="Atlantis", depart_date=DEP)
    assert where["status"] == "unknown_place"
    res = tl["search_flights"](origin="BKK", destination="SIN", depart_date=DEP)
    f = res["top"][0]
    assert res["status"] == "ok" and res["total"] == 12 and res["data"]["bookable"] is False
    assert f["booking_ref"] == f"BKKSIN.{f['id']}.1" and "raw" not in f
    assert f["total_for_all_travellers"] == f["price_per_traveller"] and f["currency"] == "THB"
    none = tl["search_flights"](origin="BKK", destination="HKG", depart_date=DEP)
    assert none["status"] == "no_results" and none["empty"] == "route"
    same_day = tl["search_hotels"](city="SIN", check_in=DEP, check_out=DEP)
    assert same_day["status"] == "invalid"
    hres = tl["search_hotels"](city="SIN", check_in=DEP, check_out=RET)
    assert hres["status"] == "ok" and hres["top"][0]["booking_ref"].startswith("SIN.")


async def test_book_trip_confirms_then_books_files_receipts_and_sets_the_reminder(bot, world):
    tl = tools(bot, world)
    out, back, room = trip(tl)
    fid, rid, hid = out["booking_ref"], back["booking_ref"], room["booking_ref"]
    fares = out["total_for_all_travellers"] + back["total_for_all_travellers"]
    assert tl["book_trip"]()["status"] == "error"
    assert tl["book_trip"](return_flight_offer_id=rid)["status"] == "error"  # no outbound
    for gone in ("F999", "BKKSIN.XX1-20261112-E.1", "BKKSIN.SL106-20261001-E.1"):
        assert tl["book_trip"](gone)["status"] == "expired"  # malformed / unknown / past
    first = tl["book_trip"](fid, hid, "Lumen kickoff", return_flight_offer_id=rid)
    assert first["status"] == "needs_confirmation"
    assert first["quote"]["totals"] == [
        {"amount": fares + room["total_for_stay"], "currency": "THB"}
    ]  # priced again from the catalogue: out + back + the stay, one currency
    # the same request id again is still the proposal; a later message (new tools) confirms
    again = tl["book_trip"](fid, hid, "Lumen kickoff", return_flight_offer_id=rid)
    assert again["status"] == "needs_confirmation"
    done = said(tools(bot, world))["book_trip"](
        fid, hid, "Lumen kickoff", return_flight_offer_id=rid
    )
    assert done["status"] == "booked" and done["provider"] == "sample"
    assert len(done["references"]["flight"]) == 6 and len(done["references"]["hotel"]) == 8
    assert len(done["filed_receipts"]) == 2
    r = bot.store.get(done["filed_receipts"][0])
    assert r.category == "ค่าเดินทาง" and r.vendor == out["airline"] and r.total == fares
    assert "Lumen kickoff" in r.notes and done["references"]["flight"] in r.notes
    h = bot.store.get(done["filed_receipts"][1])
    assert h.currency == "THB" and h.vendor == "Bugis Garden Hotel"
    assert h.total == room["total_for_stay"]
    rem = bot.reminder_book.get(GUILD, done["checkin_reminder"])
    assert rem["kind"] == "once"
    assert rem["next_at"] == checkin_at(out).astimezone(UTC).isoformat(timespec="seconds")
    assert out["flights"][0].replace(" ", "") in rem["message"] and rem["user_id"] == STAFF
    record = bot.docs.get(trips.TRIP_KIND, GUILD, done["trip_id"])
    assert (record["destination"], record["depart_date"], record["return_date"]) == (
        "SIN",
        DEP,
        RET,
    )
    # a colleague sees the trip without amounts; the traveller and executives with them
    other = tools(bot, world, who=BOSS)["list_trips"]()
    assert other["trips"][0]["user_name"] and "totals" not in other["trips"][0]
    assert tools(bot, world, who=BOSS, is_exec=True)["list_trips"]()["trips"][0]["totals"]
    assert tools(bot, world)["list_trips"]()["trips"][0]["references"] == done["references"]
    assert tools(bot, world)["list_trips"](upcoming=False)["count"] == 1
    # asked again (a second "yes", a voice retry): the same trip, never a second booking
    for _ in range(2):
        again = tools(bot, world)["book_trip"](
            fid, hid, "Lumen kickoff", return_flight_offer_id=rid
        )
        assert again["status"] == "already_booked" and again["trip_id"] == done["trip_id"]
        assert again["references"] == done["references"]
    # the same flights and room found by a new search (the same refs) are still that trip
    tl2 = tools(bot, world)
    out2, back2, room2 = trip(tl2)
    assert (out2["booking_ref"], back2["booking_ref"], room2["booking_ref"]) == (fid, rid, hid)
    alone = tl2["book_trip"](fid, return_flight_offer_id=rid)  # the flights alone: still booked
    assert alone["status"] == "already_booked" and alone["already"] == ["flight"]
    # only a new hotel: proposed, then booked on its own (the flights are not booked again)
    other = room_of(tl2, "riverside-inn")["booking_ref"]
    assert tl2["book_trip"](hotel_offer_id=other)["status"] == "needs_confirmation"
    hotel_only = said(tools(bot, world))["book_trip"](hotel_offer_id=other)
    assert hotel_only["status"] == "booked" and list(hotel_only["references"]) == ["hotel"]
    assert tools(bot, world)["list_trips"](upcoming=False)["count"] == 2


async def test_a_booking_ref_is_a_public_sample_fare_anyone_can_book_for_themselves(bot, world):
    """A booking_ref names a catalogue fare, priced again at booking: another person can book the
    same ref for themselves (their own trip, the same price). Search state stays per person
    (tests/dory/test_travel_search.py)."""
    found = tools(bot, world)["search_flights"](origin="BKK", destination="SIN", depart_date=DEP)
    fid, price = found["top"][0]["booking_ref"], found["top"][0]["price_per_traveller"]
    assert tools(bot, world, who=BOSS)["book_trip"](fid)["status"] == "needs_confirmation"
    done = said(tools(bot, world, who=BOSS))["book_trip"](fid)
    assert done["status"] == "booked"
    record = bot.docs.get(trips.TRIP_KIND, GUILD, done["trip_id"])
    assert record["user_id"] == BOSS and record["totals"] == [{"amount": price, "currency": "THB"}]


async def test_book_trip_refuses_an_approval_that_is_not_approved_or_not_mine(bot, world):
    tl = tools(bot, world)
    hid = tl["search_hotels"](city="SIN", check_in=DEP, check_out=RET)["top"][0]["booking_ref"]
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
    done = said(tools(bot, world))["book_trip"](hotel_offer_id=hid, approval_id=mine.id)
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


@pytest.mark.parametrize("spoken", [False, True])  # typed chat and voice both book by code
async def test_a_plain_yes_after_a_quote_is_booked_by_code_not_the_model(bot, world, spoken):
    tl = tools(bot, world, spoken=spoken)
    out = tl["search_flights"](origin="BKK", destination="SIN", depart_date=DEP)["top"][0]
    room = tl["search_hotels"](check_out=RET, hotel_id="bugis-garden")["rooms"][0]
    quote = tl["book_trip"](out["booking_ref"], room["booking_ref"], "Lumen kickoff")
    assert quote["status"] == "needs_confirmation"
    kw = kw_for(bot, world, spoken=spoken)  # the person's next message, the real agent wiring
    uid = kw.pop("user_id", STAFF)
    ans = await qa.ask_async(
        bot.s, bot.store, "Yes, confirm.", guild_id=GUILD, is_exec=False, user_id=uid,
        model=object(), **kw,
    )  # fmt: skip
    assert ans.rounds == 0 and ans.tool_calls == [("book_trip", {})]  # the model was never asked
    trip_ = tools(bot, world)["list_trips"]()["trips"][0]
    assert ans.text.startswith("Booked!") and trip_["id"] in ans.text
    assert trip_["references"]["flight"] in ans.text and trip_["references"]["hotel"] in ans.text
    assert f"{out['total_for_all_travellers'] + room['total_for_stay']:,.2f} THB" in ans.text
    assert checkin_at(out).strftime("%Y-%m-%d %H:%M") in ans.text  # the reminder, Bangkok time
    assert "sandbox booking" in ans.text and "no money is charged" in ans.text


async def test_a_plain_yes_books_the_round_trip_it_quoted(bot, world):
    tl = tools(bot, world)
    out, back, room = trip(tl)
    quote = tl["book_trip"](
        out["booking_ref"], room["booking_ref"], "Lumen kickoff",
        return_flight_offer_id=back["booking_ref"],
    )  # fmt: skip
    assert quote["status"] == "needs_confirmation"
    assert tools(bot, world)["book_trip"].on_confirm("yes").startswith("Booked!")
    booked = tools(bot, world)["list_trips"]()["trips"][0]
    assert back["flights"][0].replace(" ", "") in booked["flights"]  # the way back was booked too


async def test_adding_the_way_back_is_a_new_quote_that_needs_its_own_yes(bot, world):
    tl = tools(bot, world)
    out, back, _ = trip(tl)
    assert tl["book_trip"](out["booking_ref"])["status"] == "needs_confirmation"
    later = said(tools(bot, world))["book_trip"](
        out["booking_ref"], return_flight_offer_id=back["booking_ref"]
    )
    assert later["status"] == "needs_confirmation"  # another itinerary, another price: ask again


async def test_only_a_plain_yes_in_the_very_next_message_books(bot, world):
    tl = tools(bot, world)
    fid = tl["search_flights"](origin="BKK", destination="SIN", depart_date=DEP)["top"][0][
        "booking_ref"
    ]
    assert tl["book_trip"](fid, "", "Lumen kickoff")["status"] == "needs_confirmation"
    assert tools(bot, world, who=BOSS)["book_trip"].on_confirm("yes") is None  # not BOSS's quote
    assert tools(bot, world)["book_trip"].on_confirm("yes, but the later flight") is None
    assert tools(bot, world)["book_trip"].on_confirm("Yes, confirm.") is None  # a message too late
    assert tools(bot, world)["list_trips"]()["count"] == 0


async def test_a_card_click_books_without_a_typed_message(bot, world):
    """The person's own Confirm booking click on a travel card (web or Discord, no model) is the
    request to book: a quote first, then a NEW request books it; the plain tool never does."""
    out = tools(bot, world)["search_flights"](origin="BKK", destination="SIN", depart_date=DEP)
    fid = out["top"][0]["booking_ref"]
    assert tools(bot, world)["book_trip"].clicked(fid, "", "x")["status"] == "needs_confirmation"
    done = tools(bot, world)["book_trip"].clicked(fid, "", "x")
    assert done["status"] == "booked" and done["provider"] == "sample"


async def test_a_hotel_refused_after_the_flight_keeps_the_flight_booked_once(
    bot, world, monkeypatch
):
    real, flights_bought = bot.trips_provider.book_flight, []

    def count(offer, traveller):
        flights_bought.append(offer.offer_id)
        return real(offer, traveller)

    def refuse(offer, traveller):
        raise RuntimeError("hotel sold out")

    tl = tools(bot, world)
    out, _, room = trip(tl)
    fid, hid, fare = out["booking_ref"], room["booking_ref"], out["total_for_all_travellers"]
    assert tl["book_trip"](fid, hid, "Lumen kickoff")["status"] == "needs_confirmation"
    monkeypatch.setattr(bot.trips_provider, "book_flight", count)
    monkeypatch.setattr(bot.trips_provider, "book_hotel", refuse)
    text = tools(bot, world)["book_trip"].on_confirm("yes")
    # the booked flight is recorded: trip, receipt and check-in reminder (DEF-01: it was lost)
    [trip_] = bot.docs.find(trips.TRIP_KIND, GUILD)
    assert list(trip_["references"]) == ["flight"] and trip_["hotel"] is None
    assert len(trip_["receipt_ids"]) == 1 and trip_["reminder_id"]
    assert trip_["totals"] == [{"amount": fare, "currency": "THB"}]
    assert text.startswith("Only part of the trip is booked") and "NOT booked: the hotel" in text
    assert trip_["references"]["flight"] in text and f"{fare:,.2f} THB" in text
    # a retry of the same flight and hotel never buys the flight again
    again = said(tools(bot, world))["book_trip"](fid, hid, "Lumen kickoff")
    assert again["status"] == "already_booked" and again["already"] == ["flight"]
    assert flights_bought == [fid.upper()] and len(bot.docs.find(trips.TRIP_KIND, GUILD)) == 1


async def test_the_model_hears_what_is_booked_and_a_refused_flight_books_nothing(
    bot, world, monkeypatch
):
    tried = []

    def refuse(offer, traveller):
        tried.append(offer.offer_id)
        raise RuntimeError("refused")

    tl = tools(bot, world)
    flights = tl["search_flights"](origin="BKK", destination="SIN", depart_date=DEP)["top"]
    f1, f2 = flights[0]["booking_ref"], flights[1]["booking_ref"]
    h1, h2 = (room_of(tl, h)["booking_ref"] for h in ("bugis-garden", "riverside-inn"))
    assert tl["book_trip"](f1, h1, "x")["status"] == "needs_confirmation"
    monkeypatch.setattr(bot.trips_provider, "book_hotel", refuse)
    res = said(tools(bot, world))["book_trip"](f1, h1, "x")
    assert res["status"] == "partial" and res["not_booked"] == ["hotel"]
    assert (
        list(res["references"]) == ["flight"] and "Never say the whole trip" in res["instruction"]
    )
    # the flight itself is refused: nothing is booked, the hotel is not even tried
    tl2 = tools(bot, world)
    assert tl2["book_trip"](f2, h2, "y")["status"] == "needs_confirmation"
    monkeypatch.setattr(bot.trips_provider, "book_flight", refuse)
    tried.clear()
    res = said(tools(bot, world))["book_trip"](f2, h2, "y")
    assert res == {"status": "failed", "error": "the booking service refused"}
    assert tried == [f2.upper()] and len(bot.docs.find(trips.TRIP_KIND, GUILD)) == 1
    text = trips._confirm_reply(trips.TripsCtx(GUILD, STAFF, "Mint", False, "en", None, bot.docs,
                                bot.store, bot.secretary_state, "r", bot.s.now), res)  # fmt: skip
    assert text.startswith("I couldn't book it") and "nothing is booked" in text


# ----------------------------------------------------------------------------- only a booking request books (DEF-03)
@pytest.mark.parametrize(
    "text",
    ["Yes, confirm.", "Go ahead and book both for the kickoff", "Please book it",
     "confirmed, go ahead", "ยืนยันการจองค่ะ", "โอเค จองให้หน่อย"],
)  # fmt: skip
def test_a_booking_request_asks_to_book(text):
    assert trips.asks_to_book(text)


@pytest.mark.parametrize(
    "text",
    ["What did I just book, and what will you remind me about?", "what did I just book",
     "tell me what I booked", "Yes but the cheaper hotel", "Don't book it yet", "wait",
     "Switch to the second hotel", "How much is it in baht", "จองอะไรไปแล้วบ้าง", "ไม่ต้องจองค่ะ",
     "จองแล้วหรือยัง", "Thanks!", "", None],
)  # fmt: skip
def test_a_question_a_refusal_or_a_change_does_not(text):
    assert not trips.asks_to_book(text)


async def test_a_question_while_a_quote_waits_never_books_it(bot, world):
    tl = tools(bot, world)
    out, _, room = trip(tl)
    fid, hid = out["booking_ref"], room["booking_ref"]
    assert tl["book_trip"](fid, hid, "Lumen kickoff")["status"] == "needs_confirmation"
    # the next message is a question; the model calls book_trip again with the same arguments
    asked = said(tools(bot, world), "What did I just book, and what will you remind me about?")
    again = asked["book_trip"](fid, hid, "Lumen kickoff")
    assert (
        again["status"] == "needs_confirmation"
        and "Do NOT say it is booked" in again["instruction"]
    )
    assert bot.docs.find(trips.TRIP_KIND, GUILD) == []  # (building tools would count as a message)
    # the quote was shown again, so a plain yes right after it books it, once
    text = tools(bot, world)["book_trip"].on_confirm("yes")
    assert text.startswith("Booked!") and len(bot.docs.find(trips.TRIP_KIND, GUILD)) == 1


async def test_a_confirmed_quote_books_even_when_the_purpose_is_reworded(bot, world):
    tl = tools(bot, world)
    fid = tl["search_flights"](origin="BKK", destination="SIN", depart_date=DEP)["top"][0][
        "booking_ref"
    ]
    assert tl["book_trip"](fid, "", "Client kickoff")["status"] == "needs_confirmation"
    asked = said(tools(bot, world), "What did I just book?")
    assert asked["book_trip"](fid, "", "client kickoff")["status"] == "needs_confirmation"
    done = said(tools(bot, world), "Go ahead and book it")["book_trip"](
        fid, "", "the client kickoff"
    )
    assert done["status"] == "booked" and done["purpose"] == "the client kickoff"


async def test_a_call_with_no_message_heard_never_books(bot, world):
    tl = tools(bot, world)
    fid = tl["search_flights"](origin="BKK", destination="SIN", depart_date=DEP)["top"][0][
        "booking_ref"
    ]
    assert tl["book_trip"](fid, "", "Lumen kickoff")["status"] == "needs_confirmation"
    for _ in range(2):  # later requests whose message was never handed to the tools
        assert (
            tools(bot, world)["book_trip"](fid, "", "Lumen kickoff")["status"]
            == "needs_confirmation"
        )
    assert tools(bot, world)["list_trips"]()["count"] == 0


async def test_hotel_results_and_the_quote_say_they_are_sandbox(bot, world):
    tl = tools(bot, world)
    hotels = tl["search_hotels"](city="SIN", check_in=DEP, check_out=RET)
    assert hotels["data"]["bookable"] is False and hotels["data"]["source"] == "sample"
    quote = tl["book_trip"]("", hotels["top"][0]["booking_ref"], "x")
    assert quote["status"] == "needs_confirmation" and "sandbox quote" in quote["instruction"]
