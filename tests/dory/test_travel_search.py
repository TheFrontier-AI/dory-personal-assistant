"""The shared travel search behind the web cards and /dory flights | hotels (dory.travel_search)."""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from dory import travel_search as T

TODAY = date(2026, 10, 29)  # a Thursday
TUE = date(2026, 11, 3)


def fq(**kw):
    return T.FlightQuery(**{"depart": TUE, "adults": 2, **kw})


def hq(**kw):
    return T.HotelQuery(**{"check_in": TUE, "check_out": TUE + timedelta(days=3), **kw})


def every_flight(q, f=None):
    return (
        T.search_flights(q, f, limit=T.MAX_LIMIT)["results"]
        + T.search_flights(q, f, offset=T.MAX_LIMIT, limit=T.MAX_LIMIT)["results"]
    )


# ----------------------------------------------------------------------------- prices
def test_flight_total_is_per_traveller_times_travellers_and_taxes_add_up():
    for o in every_flight(fq(adults=3)):
        p = o["price"]
        assert p["currency"] == "THB" and p["taxes_included"] and p["travellers"] == 3
        assert p["total"] == p["per_traveller"] * 3
        r = T.fare_review(fq(adults=3), o["id"])["breakdown"]
        assert r["base_per_traveller"] + r["taxes_per_traveller"] == r["per_traveller"]
        assert r["total"] == r["per_traveller"] * 3


def test_flight_times_are_local_and_durations_consistent():
    by_id = {o["id"]: o for o in every_flight(fq())}
    sl = by_id["SL106-20261103-E"]  # BKK is UTC+7, SIN UTC+8: 14:35 + 2h25 + 1h = 18:00
    assert (sl["depart"], sl["arrive"], sl["duration_min"], sl["stops"]) == (
        "2026-11-03T14:35",
        "2026-11-03T18:00",
        145,
        0,
    )
    late = by_id["TR617-20261103-E"]  # lands after midnight
    assert late["arrive"] == "2026-11-04T00:55" and late["arrive_day_offset"] == 1
    mh = by_id["MH783-MH603-20261103-E"]
    assert mh["stops"] == 1 and mh["via"][0]["code"] == "KUL" and mh["via"][0]["layover_min"] == 135
    assert mh["duration_min"] == sum(s["minutes"] for s in mh["segments"]) + 135
    assert mh["segments"][1]["depart"] == "2026-11-03T14:30"  # 12:15 at KUL + the layover


def test_hotel_totals_are_nightly_times_nights_times_rooms():
    res = T.search_hotels(hq(rooms=2, guests=4), limit=T.MAX_LIMIT, today=TODAY)
    assert res["results"]
    for c in res["results"]:
        p = c["price"]
        assert p["currency"] == "THB" and p["taxes_included"]
        assert (p["nights"], p["rooms"]) == (3, 2)
        assert p["total"] == p["nightly"] * 3 * 2 == p["before_taxes"] + p["taxes"]


def test_cancellation_deadline_counts_back_from_check_in():
    flex = T.room_review(hq(), "harbourlight", "deluxe-king", TODAY)["room"]["cancellation"]
    assert flex == {"free": True, "until": "2026-10-31"}  # 3 days before check-in
    saver = T.room_review(hq(), "harbourlight", "deluxe-king-saver", TODAY)["room"]
    assert saver["cancellation"] == {"free": False, "until": None}
    # the free window already passed -> no longer free
    late = T.room_review(hq(), "harbourlight", "deluxe-king", date(2026, 11, 2))["room"]
    assert late["cancellation"]["free"] is False


# ----------------------------------------------------------------------------- filters and pages
def test_flight_filters_change_the_results():
    q = fq()
    assert T.search_flights(q)["total"] == 12
    nonstop = every_flight(q, T.FlightFilters(stops=["nonstop"]))
    assert len(nonstop) == 9 and all(o["stops"] == 0 for o in nonstop)
    morning = every_flight(q, T.FlightFilters(times=["morning"]))
    assert morning and all(int(o["depart"][11:13]) < 12 for o in morning)
    sq = every_flight(q, T.FlightFilters(airlines=["sq"]))
    assert {o["airline"]["code"] for o in sq} == {"SQ"}
    cheap = every_flight(q, T.FlightFilters(max_price=3000))
    assert cheap and all(o["price"]["per_traveller"] <= 3000 for o in cheap)
    business = every_flight(fq(cabin="business"))
    assert len(business) == 6 and not any(o["airline"]["low_cost"] for o in business)
    assert all(o["id"].endswith("-B") for o in business)


def test_flight_sorts_and_tags():
    cheapest = T.search_flights(fq(), T.FlightFilters(sort="cheapest"), limit=T.MAX_LIMIT)
    prices = [o["price"]["per_traveller"] for o in cheapest["results"]]
    assert prices == sorted(prices) and "cheapest" in cheapest["results"][0]["tags"]
    best = T.search_flights(fq())
    assert best["results"][0]["tags"][0] == "best_value"
    tags = [t for o in every_flight(fq()) for t in o["tags"]]
    assert sorted(tags) == ["best_value", "cheapest", "fastest"]  # each once


def test_pagination_reveals_more_without_repeats():
    q, seen = fq(), []
    page = T.search_flights(q, offset=0, limit=1)
    assert page["has_more"] and page["total"] == 12
    while True:
        seen += [o["id"] for o in page["results"]]
        if not page["has_more"]:
            break
        page = T.search_flights(q, offset=page["offset"] + page["limit"], limit=3)
    assert len(seen) == len(set(seen)) == 12
    assert T.search_flights(q, limit=999)["limit"] == T.MAX_LIMIT


def test_hotel_filters_pick_the_cheapest_matching_room():
    plain = {c["id"]: c for c in T.search_hotels(hq(), limit=10, today=TODAY)["results"]}
    assert plain["harbourlight"]["room"]["id"] == "deluxe-king-saver"
    free = T.search_hotels(hq(), T.HotelFilters(free_cancellation=True), limit=10, today=TODAY)
    by_id = {c["id"]: c for c in free["results"]}
    assert by_id["harbourlight"]["room"]["id"] == "deluxe-king"  # the flexible rate now
    assert "little-india-loft" in by_id and by_id["little-india-loft"]["room"]["id"] == "loft"
    assert all(c["cancellation"]["free"] for c in free["results"])
    breakfast = T.search_hotels(hq(), T.HotelFilters(breakfast=True), limit=10, today=TODAY)
    assert {c["id"] for c in breakfast["results"]} == {
        "harbourlight",
        "orchard-lantern",
        "bugis-garden",
        "heritage-house",
        "sentosa-shore",
    }
    four = T.search_hotels(hq(), T.HotelFilters(min_stars=4, min_score=8.8), today=TODAY)
    assert four["total"] == 3 and all(c["stars"] >= 4 for c in four["results"])
    cheap = T.search_hotels(hq(), T.HotelFilters(max_nightly=3000), limit=10, today=TODAY)
    assert all(c["price"]["nightly"] <= 3000 for c in cheap["results"])


def test_rooms_too_small_for_the_guests_are_left_out():
    four_in_one = hq(rooms=1, guests=4)
    ids = {c["id"] for c in T.search_hotels(four_in_one, limit=10, today=TODAY)["results"]}
    assert ids == {"orchard-lantern", "sentosa-shore"}
    rooms = T.hotel_rooms(four_in_one, "orchard-lantern", TODAY)["rooms"]
    assert [r["id"] for r in rooms] == ["family"]


def test_empty_reasons():
    assert T.search_flights(fq(destination="HKG"))["empty"] == "route"
    assert T.search_flights(fq(), T.FlightFilters(max_price=100))["empty"] == "filters"
    assert T.search_hotels(hq(city="HKG"), today=TODAY)["empty"] == "route"
    assert T.search_hotels(hq(), T.HotelFilters(max_nightly=100), today=TODAY)["empty"] == "filters"
    assert T.search_hotels(hq(rooms=1, guests=9), today=TODAY)["empty"] == "none"


# ----------------------------------------------------------------------------- selection
def test_selection_only_resolves_ids_of_this_search_and_never_books():
    first = T.search_flights(fq())["results"][0]
    review = T.fare_review(fq(), first["id"])
    assert review["flight"]["id"] == first["id"] and review["booked"] is False
    assert T.fare_review(fq(depart=TUE + timedelta(days=1)), first["id"]) is None  # other date
    assert T.fare_review(fq(cabin="business"), first["id"]) is None
    assert T.fare_review(fq(), "XX999-20261103-E") is None
    stay = T.room_review(hq(), "harbourlight", "bay-suite", TODAY)
    assert stay["booked"] is False and stay["hotel"]["price"]["nightly"] == 14900
    assert T.room_review(hq(), "harbourlight", "family", TODAY) is None  # another hotel's room
    assert T.hotel_rooms(hq(), "nope", TODAY) is None


def test_fare_rules_follow_the_airline_and_cabin():
    q = fq()
    low = T.fare_review(q, "FD355-20261103-E")["rules"]
    full = T.fare_review(q, "TG403-20261103-E")["rules"]
    biz = T.fare_review(fq(cabin="business"), "TG403-20261103-B")["rules"]
    assert low == {"change_fee": 900, "refund_fee": None}  # not refundable
    assert full == {"change_fee": 1500, "refund_fee": 2500}
    assert biz == {"change_fee": 0, "refund_fee": 1000}


# ----------------------------------------------------------------------------- per-person state
def test_sessions_are_isolated_per_owner_and_expire():
    now = [0.0]
    s = T.Sessions(ttl_s=60, clock=lambda: now[0])
    a = s.start("discord:1", "flights", fq())
    b = s.start("discord:2", "flights", fq(adults=1))
    assert a.sid != b.sid
    assert s.get(a.sid, "discord:2") is None  # someone else's search
    a.filters = T.FlightFilters(stops=["nonstop"])
    a.offset = 3
    got = s.get(a.sid, "discord:1")
    assert got is a and got.offset == 3 and s.get(b.sid, "discord:2").offset == 0
    assert s.get(b.sid, "discord:2").filters.stops == []
    now[0] = 59
    assert s.get(a.sid, "discord:1") is a  # a use keeps it alive
    now[0] = 118
    assert s.get(a.sid, "discord:1") is a and s.get(b.sid, "discord:2") is None  # b expired
    assert s.get("nope", "discord:1") is None


def test_sessions_drop_the_oldest_at_the_cap():
    s = T.Sessions(cap=2)
    first, *_ = [s.start("discord:1", "hotels", hq()) for _ in range(3)]
    assert s.get(first.sid, "discord:1") is None and len(s._items) == 2


# ----------------------------------------------------------------------------- validation
def test_queries_validate_their_input():
    with pytest.raises(ValidationError):
        fq(origin="BKK", destination="bkk")
    with pytest.raises(ValidationError):
        fq(origin="Bangkok")
    with pytest.raises(ValidationError):
        fq(adults=0)
    with pytest.raises(ValidationError):
        hq(check_out=TUE)
    with pytest.raises(ValidationError):
        hq(rooms=3, guests=2)
    assert fq(origin=" bkk ").origin == "BKK"
    assert T.date_problem(TODAY, TODAY - timedelta(days=1)) == "past_date"
    assert T.date_problem(TODAY, TODAY + timedelta(days=400)) == "too_far"
    assert T.date_problem(TODAY, TUE) is None


# ----------------------------------------------------------------------------- typed requests
def test_parse_the_sample_request():
    r = T.parse_request(
        "Find a flight from Bangkok to Singapore and a hotel in Singapore for 2 people next week.",
        TODAY,
    )
    assert r.flight == fq()
    assert r.hotel == hq(rooms=1, guests=2)


@pytest.mark.parametrize(
    "text,flight,hotel",
    [
        ("flights to Singapore on 12 Nov for three travellers", ("BKK", "SIN", "2026-11-12", 3), None),
        ("Book a business class flight Singapore to Bangkok tomorrow", ("SIN", "BKK", "2026-10-30", 1), None),
        ("any hotels in Singapore for 4 nights from 2026-11-10, 3 guests 2 rooms", None, ("SIN", "2026-11-10", 4, 2, 3)),
        ("หาเที่ยวบินจากกรุงเทพไปสิงคโปร์ 2 คน", ("BKK", "SIN", "2026-11-03", 2), None),
        ("flight from Bangkok to Hong Kong next Friday", ("BKK", "HKG", "2026-11-06", 1), None),
        ("Which flights go from Bangkok to Singapore tomorrow?", ("BKK", "SIN", "2026-10-30", 1), None),
    ],
)  # fmt: skip
def test_parse_variants(text, flight, hotel):
    r = T.parse_request(text, TODAY)
    if flight:
        f = r.flight
        assert (f.origin, f.destination, f.depart.isoformat(), f.adults) == flight
    else:
        assert r.flight is None
    if hotel:
        h = r.hotel
        assert (h.city, h.check_in.isoformat(), h.nights, h.rooms, h.guests) == hotel
    else:
        assert r.hotel is None


@pytest.mark.parametrize(
    "text",
    [
        "Summarise our hotel expenses in Singapore last month",
        "How many receipts from the Singapore flight?",
        "What's our travel policy for flights to Singapore?",
        "Find me a flight to Paris",
        # questions about a trip that exists or happened: the brain has list_trips and memory
        "Which hotel in Singapore did we book last time?",
        "When does the flight to Singapore leave?",
        "Did Peat stay at a hotel in Singapore?",
        "Where is my flight to Singapore booked?",
        "โรงแรมที่สิงคโปร์ที่จองแล้วชื่ออะไร",
        "What did I miss today?",
        "",
    ],
)
def test_not_a_travel_search(text):
    assert T.parse_request(text, TODAY) is None


# ----------------------------------------------------------------------------- sample status
def test_every_result_says_it_is_sample_data():
    status = {"source": "sample", "live_availability": False, "bookable": False}
    q, h = fq(), hq()
    first = T.search_flights(q)["results"][0]["id"]
    for res in (
        T.search_flights(q),
        T.search_hotels(h, today=TODAY),
        T.fare_review(q, first),
        T.hotel_rooms(h, "harbourlight", TODAY),
        T.room_review(h, "harbourlight", "deluxe-king", TODAY),
    ):
        assert {k: res["data"][k] for k in status} == status
        assert res["data"]["notice"] == T.DEMO_NOTICE
    assert all(c["fictional"] for c in T.search_hotels(h, limit=10, today=TODAY)["results"])


# ----------------------------------------------------------------------------- the AI's tools
def tools(owner="web:a@x", trips=None, render=True):
    ctx = T.CardCtx(owner=owner, today=TODAY, trips=trips or T.Trips(), render=render)
    return ctx, *T.card_tools(ctx)


def test_tools_ask_for_essentials_instead_of_guessing():
    ctx, flights, hotels = tools()
    r = flights(destination="Singapore")
    assert r["status"] == "need_details" and r["missing"] == ["origin", "depart_date"]
    assert hotels(city="SIN", check_in="2026-11-03")["missing"] == ["nights"]
    assert flights(origin="Paris", destination="SIN", depart_date="2026-11-03")["status"] == (
        "unknown_place"
    )
    assert flights(origin="BKK", destination="SIN", depart_date="3 Nov")["status"] == "invalid"
    past = flights(origin="BKK", destination="SIN", depart_date="2026-10-01")
    assert past["status"] == "invalid" and past["problem"] == "past_date"
    bad = flights(origin="BKK", destination="SIN", depart_date="2026-11-03", stops="direct")
    assert bad["status"] == "invalid" and "stops" in bad["problem"]
    assert ctx.cards == []  # nothing drawn until a search really ran


def test_tools_return_typed_results_and_record_cards():
    ctx, flights, _ = tools()
    r = flights(origin="Bangkok", destination="Singapore", depart_date="2026-11-03", travellers=2)
    assert r["status"] == "ok" and r["total"] == 12 and r["data"]["bookable"] is False
    top = r["top"][0]
    assert top["airline"] == "Thai Lion Air" and top["price_per_traveller"] == 3190
    assert top["total_for_all_travellers"] == 6380 and top["currency"] == "THB"
    assert "cards" in r["shown"]
    assert top["booking_ref"] == "BKKSIN.SL106-20261103-E.2"
    assert ctx.cards == [{"kind": "flights", "leg": "out", "query": fq().model_dump(mode="json"),
                          "filters": T.FlightFilters().model_dump(mode="json")}]  # fmt: skip
    route = flights(destination="HKG")
    assert route["status"] == "no_results" and route["empty"] == "route"


def test_refinements_continue_the_trip_and_keep_filters():
    ctx, flights, hotels = tools()
    flights(origin="BKK", destination="SIN", depart_date="2026-11-03", travellers=2)
    r = flights(stops="nonstop", sort="cheapest")
    assert r["total"] == 9 and r["query"]["adults"] == 2
    r = flights(travellers=3)  # same route and date: the filters stay
    assert r["filters"]["stops"] == ["nonstop"] and r["filters"]["sort"] == "cheapest"
    assert r["query"]["adults"] == 3
    r = flights(clear_filters=True)
    assert r["filters"]["stops"] == [] and r["total"] == 12
    r = flights(depart_date="2026-11-04", stops="1stop")  # another day, same route: kept
    assert r["filters"]["stops"] == ["1stop"] and r["filters"]["sort"] == "best"
    r = flights(sort="cheapest")
    assert r["filters"] == {**r["filters"], "stops": ["1stop"], "sort": "cheapest"}
    assert flights(destination="HKG")["filters"]["sort"] == "best"  # a new route starts fresh
    flights(destination="SIN")
    h = hotels(nights=3, free_cancellation=True)  # "a hotel there for 3 nights"
    assert h["query"] == {"city": "SIN", "check_in": "2026-11-04", "check_out": "2026-11-07",
                          "rooms": 2, "guests": 3, "nights": 3}  # fmt: skip
    assert all(x["free_cancellation"] for x in h["top"])
    moved = hotels(check_in="2026-11-05")  # nights and filters kept
    assert moved["query"]["check_out"] == "2026-11-08" and moved["filters"]["free_cancellation"]
    payload = T.travel_payload(T.tool_cards([flights, hotels]))
    assert payload["flights"]["depart"] == "2026-11-04" and payload["hotels"]["city"] == "SIN"
    assert payload["hotels"]["check_in"] == "2026-11-05"
    assert payload["hotel_filters"]["free_cancellation"] is True
    assert [c["kind"] for c in ctx.cards] == ["flights", "hotels"]  # latest search per kind


def test_trips_are_per_person_and_expire():
    now = [0.0]
    trips = T.Trips(ttl_s=60, clock=lambda: now[0])
    _, a_flights, _ = tools("discord:1", trips)
    _, _, b_hotels = tools("discord:2", trips)
    a_flights(origin="BKK", destination="SIN", depart_date="2026-11-03")
    assert b_hotels(nights=3)["status"] == "need_details"  # someone else's trip is not theirs
    _, _, a_hotels = tools("discord:1", trips)
    assert a_hotels(nights=3)["status"] == "ok"
    now[0] = 61
    assert a_hotels(nights=2)["status"] == "need_details"  # forgotten


def test_voice_turns_draw_nothing():
    ctx, flights, _ = tools(render=False)
    r = flights(origin="BKK", destination="SIN", depart_date="2026-11-03")
    assert "cards" not in r["shown"] and "voice" in r["shown"]


def test_tool_cards_and_payload_without_searches():
    _, flights, hotels = tools()
    assert T.tool_cards([flights, hotels]) == [] and T.travel_payload([]) is None
    assert T.tool_cards([print]) == []
    assert T.place_code("Singapore") == "SIN" and T.place_code("bkk") == "BKK"
    assert T.place_code("Suvarnabhumi Airport") == "BKK" and T.place_code("Atlantis") is None


def test_picks_from_the_cards_form_one_trip_per_person():
    trips = T.Trips()
    out, back = "BKKSIN.SL106-20261103-E.2", "SINBKK.SL107-20261106-E.2"
    room = "SIN.harbourlight.deluxe-king.20261103.3.1.2"
    assert trips.pick("discord:1", "nonsense", TODAY) is None
    assert trips.pick("discord:1", out, TODAY) == "flight"
    assert trips.pick("discord:1", back, TODAY) == "return"  # reverse route, later: the way back
    assert trips.pick("discord:1", room, TODAY) == "room"
    assert trips.picked("discord:1") == {"flight": out, "return": back, "room": room}
    assert trips.picked("discord:2") == {}  # someone else's picks are not theirs
    # another outbound on the same day keeps a way back that still fits; a later one drops it
    assert trips.pick("discord:1", "BKKSIN.FD355-20261103-E.2", TODAY) == "flight"
    assert trips.picked("discord:1")["return"] == back
    assert trips.pick("discord:1", "BKKSIN.SL106-20261107-E.2", TODAY) == "flight"
    assert "return" not in trips.picked("discord:1")
    # a way back picked with no outbound is just a flight
    assert trips.pick("discord:3", back, TODAY) == "flight"
    trips.unpick("discord:1", "flight", "room")
    assert trips.picked("discord:1") == {}
