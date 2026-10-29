"""Travel search API (`/api/travel/*`): sample data only, public but rate limited, validated, ONE
error shape, the sample-data status on every answer, Bangkok `today`."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from meeting_scribe import travel_api
from meeting_scribe.app import app

SAMPLE = {
    "source": "sample",
    "live_availability": False,
    "bookable": False,
    "notice": "Demo results—not live availability or a confirmed booking.",
}
TODAY = date(2026, 10, 27)  # a Tuesday; the sample trip departs Tuesday 3 Nov
FLIGHT = {"origin": "BKK", "destination": "SIN", "depart": "2026-11-03", "adults": 2}
HOTEL = {
    "city": "SIN",
    "check_in": "2026-11-03",
    "check_out": "2026-11-06",
    "rooms": 1,
    "guests": 2,
}


def use_limits(per_min=600, burst=200, global_per_min=6000, max_concurrent=8):
    limits = travel_api.Limits(per_min, burst, global_per_min, max_concurrent)
    app.dependency_overrides[travel_api.get_limits] = lambda: limits
    return limits


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STORE", "memory")
    app.dependency_overrides[travel_api.get_today] = lambda: TODAY
    use_limits()  # fresh buckets per test, roomy enough for every functional test here
    yield TestClient(app)
    app.dependency_overrides.pop(travel_api.get_today, None)
    app.dependency_overrides.pop(travel_api.get_limits, None)


def post(client, path, body, status=200, ip=None):
    headers = {"X-Forwarded-For": ip} if ip else None
    r = client.post("/api/travel" + path, json=body, headers=headers)
    assert r.status_code == status, r.text
    return r.json()


def is_error(body, code):
    """The ONE error shape of /api/travel, with the sample-data status."""
    assert set(body) == {"error", "data"} and body["data"] == SAMPLE, body
    assert body["error"]["code"] == code and body["error"]["message"], body
    return body["error"]


def test_airports_list_what_the_forms_offer(client):
    r = client.get("/api/travel/airports").json()
    assert {"code": "BKK", "city": "Bangkok", "airport": "Suvarnabhumi Airport"} in r["airports"]
    assert r["routes"] == [["BKK", "SIN"], ["SIN", "BKK"]]  # out and the way back
    assert r["hotel_cities"] == ["SIN"]
    assert r["data"] == SAMPLE


def test_every_answer_says_it_is_sample_data(client):
    q = {"query": FLIGHT}
    assert post(client, "/flights", q)["data"] == SAMPLE
    assert post(client, "/hotels", {"query": HOTEL})["data"] == SAMPLE
    assert post(client, "/flights/review", {**q, "id": "SL106-20261103-E"})["data"] == SAMPLE
    rooms = {"query": HOTEL, "hotel_id": "harbourlight"}
    assert post(client, "/hotels/rooms", rooms)["data"] == SAMPLE
    assert post(client, "/hotels/review", {**rooms, "room_id": "deluxe-king"})["data"] == SAMPLE


def test_a_client_over_its_rate_gets_429_and_another_client_is_still_served(client):
    use_limits(per_min=60, burst=2)
    q = {"query": FLIGHT, "limit": 1}
    post(client, "/flights", q, ip="203.0.113.7")
    post(client, "/flights", q, ip="203.0.113.7")
    r = client.post("/api/travel/flights", json=q, headers={"X-Forwarded-For": "203.0.113.7"})
    assert r.status_code == 429 and r.headers["Retry-After"] == "1"
    is_error(r.json(), "rate_limited")
    post(client, "/flights", q, ip="198.51.100.9")  # someone else
    # Cloud Run appends the real address: a forged first entry is still the same client
    r = client.post(
        "/api/travel/flights", json=q, headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.7"}
    )
    assert r.status_code == 429


def test_everyone_together_is_capped_too(client):
    use_limits(global_per_min=6)  # one request saved up for everyone
    post(client, "/flights", {"query": FLIGHT}, ip="203.0.113.1")
    r = client.post(
        "/api/travel/flights", json={"query": FLIGHT}, headers={"X-Forwarded-For": "203.0.113.2"}
    )
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    is_error(r.json(), "rate_limited")


def test_too_many_searches_at_once_get_503_busy(client):
    limits = use_limits(max_concurrent=1)
    limits.slots.acquire()  # a search still running
    r = client.post("/api/travel/flights", json={"query": FLIGHT})
    assert r.status_code == 503 and r.headers["Retry-After"] == "1"
    is_error(r.json(), "busy")
    limits.slots.release()
    post(client, "/flights", {"query": FLIGHT})
    post(client, "/flights", {"query": FLIGHT})  # the slot is given back after every request


def test_every_error_has_one_shape(client, monkeypatch):
    bad = is_error(post(client, "/flights", {"query": {**FLIGHT, "adults": 0}}, 422), "invalid")
    assert bad["fields"][0]["field"] == "query.adults" and "0" not in str(bad["fields"][0]["field"])
    extra = post(client, "/flights", {"query": FLIGHT, "admin": True}, 422)
    assert is_error(extra, "invalid")["fields"][0]["field"] == "admin"
    nested = post(client, "/flights", {"query": {**FLIGHT, "x": 1}}, 422)
    assert is_error(nested, "invalid")["fields"][0]["field"] == "query.x"
    long_airline = {"query": FLIGHT, "filters": {"airlines": ["X" * 50]}}
    is_error(post(client, "/flights", long_airline, 422), "invalid")
    r = client.post(
        "/api/travel/flights", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 422 and is_error(r.json(), "invalid")
    is_error(post(client, "/flights/review", {"query": FLIGHT, "id": "nope"}, 404), "not_found")
    is_error(client.get("/api/travel/nothing-here").json(), "not_found")
    huge = client.post(
        "/api/travel/flights", content=b" " * 20_000, headers={"Content-Type": "application/json"}
    )
    assert huge.status_code == 413 and is_error(huge.json(), "too_large")

    def boom(*a, **kw):
        raise RuntimeError("provider down")

    monkeypatch.setattr(travel_api.ts, "search_flights", boom)
    r = client.post("/api/travel/flights", json={"query": FLIGHT})
    assert r.status_code == 500 and is_error(r.json(), "server_error")
    assert "provider" not in r.text  # no internals


def test_other_routes_keep_their_own_error_bodies(client):
    r = client.get("/api/center/nowhere")
    assert r.status_code in (401, 404) and "error" not in r.json()


def test_flights_search_one_page_with_totals_for_every_traveller(client):
    r = post(client, "/flights", {"query": FLIGHT, "limit": 1})
    assert r["total"] == 12 and r["has_more"] and r["empty"] is None
    best = r["results"][0]
    assert best["id"] == "SL106-20261103-E" and "best_value" in best["tags"]
    assert best["price"] == {
        "currency": "THB", "per_traveller": 3190, "total": 6380, "travellers": 2,
        "taxes_included": True,
    }  # fmt: skip
    assert {a["code"] for a in r["airlines"]} >= {"SL", "TG", "SQ"} and r["price_range"]["min"]


def test_flight_filters_change_the_results_and_pagination_moves_on(client):
    nonstop = post(client, "/flights", {"query": FLIGHT, "filters": {"stops": ["nonstop"]}})
    assert nonstop["total"] == 9
    cheap = post(client, "/flights", {"query": FLIGHT, "filters": {"max_price": 3000}})
    assert cheap["total"] < 12 and all(
        o["price"]["per_traveller"] <= 3000 for o in cheap["results"]
    )
    none = post(client, "/flights", {"query": FLIGHT, "filters": {"max_price": 100}})
    assert none["total"] == 0 and none["empty"] == "filters"
    first = post(client, "/flights", {"query": FLIGHT, "offset": 0, "limit": 3})
    more = post(client, "/flights", {"query": FLIGHT, "offset": 3, "limit": 3})
    assert more["offset"] == 3 and len(more["results"]) == 3
    assert not {o["id"] for o in first["results"]} & {o["id"] for o in more["results"]}
    last = post(client, "/flights", {"query": FLIGHT, "offset": 10, "limit": 3})
    assert len(last["results"]) == 2 and not last["has_more"]


def test_flights_unknown_route_says_route(client):
    r = post(client, "/flights", {"query": {**FLIGHT, "origin": "HKG"}})
    assert r["total"] == 0 and r["empty"] == "route"


def test_flight_validation_and_date_codes(client):
    post(client, "/flights", {"query": {**FLIGHT, "adults": 0}}, 422)
    post(client, "/flights", {"query": {**FLIGHT, "destination": "BKK"}}, 422)
    post(client, "/flights", {"query": FLIGHT, "limit": 11}, 422)
    post(client, "/flights", {"query": FLIGHT, "offset": -1}, 422)
    post(client, "/flights", {"query": FLIGHT, "filters": {"sort": "random"}}, 422)
    past = post(client, "/flights", {"query": {**FLIGHT, "depart": "2026-10-26"}}, 422)
    assert past["error"]["code"] == "past_date" and past["data"] == SAMPLE
    far = post(client, "/flights", {"query": {**FLIGHT, "depart": "2028-01-01"}}, 422)
    assert far["error"]["code"] == "too_far"


def test_fare_review_is_never_a_booking_and_unknown_ids_are_404(client):
    r = post(client, "/flights/review", {"query": FLIGHT, "id": "SL106-20261103-E"})
    assert r["booked"] is False and r["sample"] is True
    b = r["breakdown"]
    assert b["base_per_traveller"] + b["taxes_per_traveller"] == 3190 and b["total"] == 6380
    assert r["rules"]["refund_fee"] is None  # low-cost fare: not refundable
    post(client, "/flights/review", {"query": FLIGHT, "id": "XX1-20261103-E"}, 404)
    post(client, "/flights/review", {"query": {**FLIGHT, "depart": "2026-01-01"}, "id": "x"}, 422)


def test_hotels_search_filters_and_pages(client):
    r = post(client, "/hotels", {"query": HOTEL, "limit": 1})
    top = r["results"][0]
    assert top["id"] == "harbourlight" and r["total"] == 8 and r["query"]["nights"] == 3
    assert top["price"]["nightly"] == 7690 and top["price"]["total"] == 23070
    free = post(client, "/hotels", {"query": HOTEL, "filters": {"free_cancellation": True}})
    assert free["total"] == 8 and all(c["cancellation"]["free"] for c in free["results"])
    assert free["results"][0]["price"]["total"] != 23070  # a refundable room costs more
    five = post(client, "/hotels", {"query": HOTEL, "filters": {"min_stars": 5}})
    assert {c["stars"] for c in five["results"]} == {5}
    page2 = post(client, "/hotels", {"query": HOTEL, "offset": 3, "limit": 3})
    assert page2["offset"] == 3 and top["id"] not in {c["id"] for c in page2["results"]}
    assert post(client, "/hotels", {"query": {**HOTEL, "city": "HKG"}})["empty"] == "route"


def test_hotel_validation_and_date_codes(client):
    post(client, "/hotels", {"query": {**HOTEL, "check_out": "2026-11-03"}}, 422)
    post(client, "/hotels", {"query": {**HOTEL, "rooms": 3, "guests": 2}}, 422)
    post(client, "/hotels", {"query": HOTEL, "filters": {"min_score": 11}}, 422)
    past = {**HOTEL, "check_in": "2026-10-20", "check_out": "2026-10-22"}
    assert post(client, "/hotels", {"query": past}, 422)["error"]["code"] == "past_date"


def test_rooms_and_room_review(client):
    r = post(client, "/hotels/rooms", {"query": HOTEL, "hotel_id": "harbourlight"})
    nightly = [x["price"]["nightly"] for x in r["rooms"]]
    assert nightly == sorted(nightly) and r["hotel"]["id"] == "harbourlight"
    post(client, "/hotels/rooms", {"query": HOTEL, "hotel_id": "nope"}, 404)
    rv = post(
        client, "/hotels/review",
        {"query": HOTEL, "hotel_id": "harbourlight", "room_id": "deluxe-king"},
    )  # fmt: skip
    assert rv["booked"] is False and rv["room"]["price"]["total"] == 8450 * 3
    assert rv["room"]["cancellation"] == {"free": True, "until": "2026-10-31"}
    post(
        client, "/hotels/review",
        {"query": HOTEL, "hotel_id": "harbourlight", "room_id": "nope"}, 404,
    )  # fmt: skip


def test_bangkok_today_is_a_date():
    assert isinstance(travel_api.get_today(), date)
