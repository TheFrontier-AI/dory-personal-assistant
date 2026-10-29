"""Travel search for the "Talk to Dory" cards (pure, no discord import).

ONE sample catalogue (Bangkok -> Singapore flights, Singapore hotels) and the search logic that both
platforms render: the web chat cards (`meeting_scribe/travel_api.py`, `static/center.html`) and the
Discord `/dory flights` and `/dory hotels` commands (`travel_search_bot.py`). Everything returns
plain JSON-ready dicts with raw numbers; each platform words them in its own language.

Prices are samples in THB that already include taxes and fees, availability is not live and nothing
here books anything (the sandbox booking of the voice demo lives in `trips.py`). Hotel names are
fictional on purpose: a review score next to a real hotel's name would be a made-up review. A real
provider plugs in at `flight_offers` / `hotel_offers`: map its offers (e.g. `trips.Duffel`,
`trips.LiteApi`) into the same dicts and keep the ids stable.
"""

from __future__ import annotations

import math
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CURRENCY = "THB"
# what a person may choose as their preferred currency (the sign-up page, My profile and the server share it;
# a test keeps the two pages' copies equal to this one)
CURRENCIES = (
    "THB",
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "SGD",
    "HKD",
    "MYR",
    "VND",
    "CNY",
    "KRW",
    "AUD",
    "CAD",
    "CHF",
    "INR",
    "IDR",
    "PHP",
    "NZD",
    "TWD",
)
MAX_LIMIT = 10
MAX_NIGHTS = 30
MAX_DAYS_AHEAD = 330
# per traveller, inside every fare: Thai departure charge 730 + other 280 (sample)
FLIGHT_TAXES = 1010
HOTEL_TAX_RATE = 0.199  # Singapore "++": 10% service charge, then 9% GST on top (1.10 * 1.09)

# code -> (city, airport, UTC offset in hours)
AIRPORTS = {
    "BKK": ("Bangkok", "Suvarnabhumi Airport", 7),
    "SIN": ("Singapore", "Singapore Changi Airport", 8),
    "KUL": ("Kuala Lumpur", "Kuala Lumpur International Airport", 8),
    "SGN": ("Ho Chi Minh City", "Tan Son Nhat International Airport", 7),
    "HKG": ("Hong Kong", "Hong Kong International Airport", 8),
    "NRT": ("Tokyo", "Narita International Airport", 9),
}
AIRLINES = {
    "FD": "Thai AirAsia", "AK": "AirAsia", "TG": "Thai Airways", "SQ": "Singapore Airlines",
    "MH": "Malaysia Airlines", "VN": "Vietnam Airlines", "TR": "Scoot", "SL": "Thai Lion Air",
}  # fmt: skip
LOW_COST = {"FD", "AK", "TR", "SL"}
SAMPLE_ROUTES = {("BKK", "SIN"), ("SIN", "BKK")}  # out and back: round trips book both
DEMO_NOTICE = "Demo results—not live availability or a confirmed booking."
# on every result, so no client can mistake a sample for live inventory or a booking
DATA_STATUS = {"source": "sample", "live_availability": False, "bookable": False,
               "notice": DEMO_NOTICE}  # fmt: skip
HOTEL_CITIES = {"SIN"}

# (flight numbers, departure HH:MM at the origin, legs (from, to, minutes), layover minutes,
#  per-traveller fare incl. taxes by cabin, cabin bag kg, checked bag kg (0 = not included), meal)
_FLIGHTS = [
    (("FD355",), "06:10", (("BKK", "SIN", 140),), 0, {"economy": 2890}, 7, 0, "for_sale"),
    (("AK881", "AK713"), "07:00", (("BKK", "KUL", 125), ("KUL", "SIN", 65)), 135,
     {"economy": 2650}, 7, 0, "for_sale"),
    (("TG403",), "08:00", (("BKK", "SIN", 145),), 0, {"economy": 6850, "business": 18900}, 7, 30,
     "included"),
    (("MH783", "MH603"), "09:05", (("BKK", "KUL", 130), ("KUL", "SIN", 70)), 135,
     {"economy": 4980, "business": 13400}, 7, 30, "included"),
    (("SQ711",), "09:25", (("BKK", "SIN", 145),), 0, {"economy": 7450, "business": 21300}, 7, 30,
     "included"),
    (("VN610", "VN655"), "10:40", (("BKK", "SGN", 90), ("SGN", "SIN", 125)), 120,
     {"economy": 4450, "business": 12600}, 7, 23, "included"),
    (("TR615",), "12:40", (("BKK", "SIN", 150),), 0, {"economy": 3450}, 10, 0, "for_sale"),
    (("TG409",), "13:30", (("BKK", "SIN", 145),), 0, {"economy": 7900, "business": 19800}, 7, 30,
     "included"),
    (("SL106",), "14:35", (("BKK", "SIN", 145),), 0, {"economy": 3190}, 7, 20, "for_sale"),
    (("SQ715",), "18:10", (("BKK", "SIN", 145),), 0, {"economy": 8600, "business": 22900}, 7, 30,
     "included"),
    (("FD357",), "19:45", (("BKK", "SIN", 140),), 0, {"economy": 3290}, 7, 0, "for_sale"),
    (("TR617",), "21:30", (("BKK", "SIN", 145),), 0, {"economy": 2990}, 10, 0, "for_sale"),
]  # fmt: skip
# Singapore -> Bangkok, the way back (SIN is UTC+8, BKK UTC+7: an hour "gained")
_RETURN_FLIGHTS = [
    (("FD358",), "07:20", (("SIN", "BKK", 140),), 0, {"economy": 3190}, 7, 0, "for_sale"),
    (("AK714", "AK882"), "08:15", (("SIN", "KUL", 65), ("KUL", "BKK", 125)), 140,
     {"economy": 2590}, 7, 0, "for_sale"),
    (("FD356",), "10:30", (("SIN", "BKK", 140),), 0, {"economy": 2790}, 7, 0, "for_sale"),
    (("MH604", "MH784"), "11:10", (("SIN", "KUL", 70), ("KUL", "BKK", 130)), 130,
     {"economy": 5080, "business": 13600}, 7, 30, "included"),
    (("TG404",), "12:25", (("SIN", "BKK", 145),), 0, {"economy": 6950, "business": 19100}, 7, 30,
     "included"),
    (("SQ712",), "13:20", (("SIN", "BKK", 145),), 0, {"economy": 7550, "business": 21500}, 7, 30,
     "included"),
    (("TR616",), "17:05", (("SIN", "BKK", 150),), 0, {"economy": 3390}, 10, 0, "for_sale"),
    (("TG410",), "18:20", (("SIN", "BKK", 145),), 0, {"economy": 7800, "business": 19600}, 7, 30,
     "included"),
    (("SL107",), "19:10", (("SIN", "BKK", 145),), 0, {"economy": 3090}, 7, 20, "for_sale"),
    (("SQ716",), "21:40", (("SIN", "BKK", 145),), 0, {"economy": 8450, "business": 22700}, 7, 30,
     "included"),
]  # fmt: skip
_SCHEDULES = {("BKK", "SIN"): _FLIGHTS, ("SIN", "BKK"): _RETURN_FLIGHTS}

# Fictional hotels in real Singapore neighbourhoods. Rooms: (id, name, beds, m2, max guests,
# breakfast, free-cancellation days before check-in (None = non-refundable), per room per night THB
# incl. taxes and fees)
_HOTELS = [
    ("harbourlight", "Harbourlight Marina Hotel", "Marina Bay", 5, 9.1, 4812,
     ("wifi", "pool", "gym", "spa", "restaurant"), 222, (
         ("deluxe-king", "Deluxe King", "1 king bed", 32, 2, False, 3, 8450),
         ("deluxe-king-saver", "Deluxe King, Saver rate", "1 king bed", 32, 2, False, None, 7690),
         ("bay-suite", "Bay View Suite with breakfast", "1 king bed + sofa bed", 58, 3, True, 3, 14900),
     )),
    ("orchard-lantern", "The Orchard Lantern", "Orchard Road", 4, 8.6, 2931,
     ("wifi", "pool", "gym", "breakfast"), 32, (
         ("superior-twin-bb", "Superior Twin with breakfast", "2 single beds", 26, 2, True, 2, 5250),
         ("superior-twin", "Superior Twin, room only", "2 single beds", 26, 2, False, None, 4590),
         ("family", "Family Room with breakfast", "1 queen + 2 single beds", 38, 4, True, 2, 7800),
     )),
    ("bugis-garden", "Bugis Garden Hotel", "Bugis", 4, 8.3, 1604,
     ("wifi", "gym", "restaurant"), 140, (
         ("deluxe-queen", "Deluxe Queen", "1 queen bed", 24, 2, False, 1, 3980),
         ("deluxe-queen-bb", "Deluxe Queen with breakfast", "1 queen bed", 24, 2, True, 1, 4460),
     )),
    ("riverside-inn", "Clarke Quay Riverside Inn", "Clarke Quay", 3, 7.9, 988,
     ("wifi", "bar"), 190, (
         ("double-saver", "Standard Double, Saver rate", "1 double bed", 18, 2, False, None, 2950),
         ("double", "Standard Double", "1 double bed", 18, 2, False, 1, 3290),
     )),
    ("heritage-house", "Tanjong Pagar Heritage House", "Tanjong Pagar", 4, 9.0, 742,
     ("wifi", "breakfast", "terrace"), 18, (
         ("heritage-queen", "Heritage Queen with breakfast", "1 queen bed", 22, 2, True, 2, 4720),
     )),
    ("sentosa-shore", "Sentosa Shore Resort", "Sentosa", 5, 8.8, 3377,
     ("wifi", "pool", "spa", "beach", "shuttle"), 170, (
         ("garden-king", "Garden King", "1 king bed", 40, 3, False, 5, 9800),
         ("ocean-suite", "Ocean Suite with breakfast", "1 king bed + sofa bed", 70, 4, True, 5, 15600),
     )),
    ("jewel-gate", "Jewel Gate Airport Hotel", "Changi", 3, 8.1, 2210,
     ("wifi", "gym", "shuttle"), 200, (
         ("standard-queen", "Standard Queen", "1 queen bed", 20, 2, False, 1, 3420),
     )),
    ("little-india-loft", "Little India Loft", "Little India", 2, 7.4, 512,
     ("wifi",), 12, (
         ("loft-saver", "Double Loft, Saver rate", "1 double bed", 14, 2, False, None, 1850),
         ("loft", "Double Loft", "1 double bed", 14, 2, False, 1, 2090),
     )),
]  # fmt: skip


# ----------------------------------------------------------------------------- queries and filters
def _iata(v: str) -> str:
    v = (v or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", v):
        raise ValueError("use a 3-letter airport or city code, e.g. BKK")
    return v


class FlightQuery(BaseModel):
    origin: str = "BKK"
    destination: str = "SIN"
    depart: date
    adults: int = Field(1, ge=1, le=9)
    cabin: Literal["economy", "business"] = "economy"

    @field_validator("origin", "destination")
    @classmethod
    def _codes(cls, v: str) -> str:
        return _iata(v)

    @model_validator(mode="after")
    def _route(self):
        if self.origin == self.destination:
            raise ValueError("origin and destination must differ")
        return self


class HotelQuery(BaseModel):
    city: str = "SIN"
    check_in: date
    check_out: date
    rooms: int = Field(1, ge=1, le=4)
    guests: int = Field(2, ge=1, le=12)

    @field_validator("city")
    @classmethod
    def _code(cls, v: str) -> str:
        return _iata(v)

    @model_validator(mode="after")
    def _stay(self):
        if not 1 <= (self.check_out - self.check_in).days <= MAX_NIGHTS:
            raise ValueError(f"check-out must be 1 to {MAX_NIGHTS} nights after check-in")
        if self.guests < self.rooms:
            raise ValueError("every room needs at least one guest")
        return self

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days


class FlightFilters(BaseModel):
    sort: Literal["best", "cheapest", "fastest", "earliest"] = "best"
    stops: list[Literal["nonstop", "1stop"]] = Field(default_factory=list, max_length=2)
    times: list[Literal["morning", "afternoon", "evening"]] = Field(
        default_factory=list, max_length=3
    )
    airlines: list[str] = Field(default_factory=list, max_length=len(AIRLINES))
    max_price: int | None = Field(None, ge=0, le=1_000_000)  # per traveller


class HotelFilters(BaseModel):
    sort: Literal["recommended", "price", "rating"] = "recommended"
    min_stars: int | None = Field(None, ge=1, le=5)
    min_score: float | None = Field(None, ge=0, le=10)
    free_cancellation: bool = False
    breakfast: bool = False
    max_nightly: int | None = Field(None, ge=0, le=1_000_000)  # per room per night


def date_problem(today: date, *days: date) -> str | None:
    """`past_date` / `too_far` for the platforms to word, else None."""
    if any(d < today for d in days):
        return "past_date"
    if any(d > today + timedelta(days=MAX_DAYS_AHEAD) for d in days):
        return "too_far"
    return None


# ----------------------------------------------------------------------------- flights
def place(code: str) -> dict:
    city, airport, _ = AIRPORTS.get(code, (code, code, 0))
    return {"code": code, "city": city, "airport": airport}


def _hm(s: str) -> timedelta:
    h, m = s.split(":")
    return timedelta(hours=int(h), minutes=int(m))


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="minutes")


def flight_offers(q: FlightQuery) -> list[dict]:
    """Every sample offer for the query, unfiltered, in schedule order. Arrival times are local
    to the arrival airport (BKK is UTC+7, SIN UTC+8, KUL UTC+8, SGN UTC+7)."""
    if (q.origin, q.destination) not in SAMPLE_ROUTES:
        return []
    out = []
    for numbers, dep, legs, layover, fares, cabin_kg, checked_kg, meal in _SCHEDULES[
        (q.origin, q.destination)
    ]:
        per = fares.get(q.cabin)
        if per is None:
            continue
        t, segs = datetime.combine(q.depart, datetime.min.time()) + _hm(dep), []
        for i, (a, b, minutes) in enumerate(legs):
            if i:
                t += timedelta(minutes=layover)
            arr = t + timedelta(minutes=minutes, hours=AIRPORTS[b][2] - AIRPORTS[a][2])
            segs.append({"flight": numbers[i][:2] + " " + numbers[i][2:], "from": place(a),
                         "to": place(b), "depart": _iso(t), "arrive": _iso(arr),
                         "minutes": minutes})  # fmt: skip
            t = arr
        code = numbers[0][:2]
        fid = f"{'-'.join(numbers)}-{q.depart:%Y%m%d}-{q.cabin[0].upper()}"
        out.append({
            "id": fid,
            # everything book_trip needs to price it again: route, flight, date, cabin, travellers
            "booking_ref": f"{q.origin}{q.destination}.{fid}.{q.adults}",
            "kind": "flight",
            "airline": {"code": code, "name": AIRLINES[code], "low_cost": code in LOW_COST},
            "flights": [s["flight"] for s in segs],
            "origin": place(q.origin),
            "destination": place(q.destination),
            "depart": segs[0]["depart"],
            "arrive": segs[-1]["arrive"],
            "arrive_day_offset": (t.date() - q.depart).days,
            "duration_min": sum(m for _, _, m in legs) + layover * (len(legs) - 1),
            "stops": len(legs) - 1,
            "via": [{**place(b), "layover_min": layover} for _, b, _ in legs[:-1]],
            "segments": segs,
            "cabin": q.cabin,
            "travellers": q.adults,
            "baggage": {"cabin_kg": cabin_kg, "checked_kg": checked_kg},
            "meal": meal,
            "price": {"currency": CURRENCY, "per_traveller": per, "total": per * q.adults,
                      "travellers": q.adults, "taxes_included": True},  # fmt: skip
            "tags": [],
            "sample": True,
        })  # fmt: skip
    return out


def time_window(iso: str) -> str:
    hour = int(iso[11:13])
    return "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"


def value_score(o: dict) -> int:
    """Lower is better: the fare plus 20 THB a minute, 900 per stop and 500 without a checked bag."""
    return (o["price"]["per_traveller"] + 20 * o["duration_min"] + 900 * o["stops"]
            + (0 if o["baggage"]["checked_kg"] else 500))  # fmt: skip


def _flight_ok(o: dict, f: FlightFilters) -> bool:
    stops = "nonstop" if o["stops"] == 0 else "1stop"
    return (
        (not f.stops or stops in f.stops)
        and (not f.times or time_window(o["depart"]) in f.times)
        and (not f.airlines or o["airline"]["code"] in {a.upper() for a in f.airlines})
        and (f.max_price is None or o["price"]["per_traveller"] <= f.max_price)
    )


_FLIGHT_SORTS: dict[str, Callable[[dict], tuple]] = {
    "best": lambda o: (value_score(o), o["depart"]),
    "cheapest": lambda o: (o["price"]["per_traveller"], o["depart"]),
    "fastest": lambda o: (o["duration_min"], o["depart"]),
    "earliest": lambda o: (o["depart"],),
}


def _tag(hits: list[dict], tag: str, key: Callable[[dict], tuple]) -> None:
    if hits:
        min(hits, key=key)["tags"].append(tag)


def _page(hits: list[dict], every: list[dict], offset: int, limit: int, unknown: bool) -> dict:
    offset, limit = max(0, offset), max(1, min(limit, MAX_LIMIT))
    return {
        "results": hits[offset : offset + limit],
        "total": len(hits),
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < len(hits),
        "empty": None if hits else ("route" if unknown else "filters" if every else "none"),
        "currency": CURRENCY,
        "sample": True,
        "data": dict(DATA_STATUS),
    }


def search_flights(
    q: FlightQuery, f: FlightFilters | None = None, offset: int = 0, limit: int = 3
) -> dict:
    """One page of filtered, sorted offers. `empty`: `route` (no sample data for that route),
    `filters` (the filters removed everything), `none` (no offer in that cabin)."""
    f = f or FlightFilters()
    every = flight_offers(q)
    hits = sorted((o for o in every if _flight_ok(o, f)), key=_FLIGHT_SORTS[f.sort])
    _tag(hits, "best_value", _FLIGHT_SORTS["best"])
    _tag(hits, "cheapest", _FLIGHT_SORTS["cheapest"])
    _tag(hits, "fastest", _FLIGHT_SORTS["fastest"])
    prices = [o["price"]["per_traveller"] for o in every]
    airlines = sorted({o["airline"]["code"] for o in every})
    return {
        "kind": "flights",
        "query": q.model_dump(mode="json"),
        "filters": f.model_dump(mode="json"),
        **_page(hits, every, offset, limit, (q.origin, q.destination) not in SAMPLE_ROUTES),
        "airlines": [{"code": c, "name": AIRLINES[c]} for c in airlines],
        "price_range": {"min": min(prices), "max": max(prices)} if prices else None,
    }


def fare_review(q: FlightQuery, flight_id: str) -> dict | None:
    """The mock itinerary and fare review for one offer of this query (None = not one of its ids).
    Not a booking: `booked` is always False."""
    o = next((x for x in flight_offers(q) if x["id"] == flight_id), None)
    if o is None:
        return None
    per = o["price"]["per_traveller"]
    business, low = o["cabin"] == "business", o["airline"]["low_cost"]
    return {
        "flight": o,
        "breakdown": {
            "currency": CURRENCY,
            "base_per_traveller": per - FLIGHT_TAXES,
            "taxes_per_traveller": FLIGHT_TAXES,
            "per_traveller": per,
            "travellers": q.adults,
            "total": per * q.adults,
        },
        # fees per traveller; None = not allowed
        "rules": {
            "change_fee": 0 if business else 900 if low else 1500,
            "refund_fee": None if low else 1000 if business else 2500,
        },
        "booked": False,
        "sample": True,
        "data": dict(DATA_STATUS),
    }


# ----------------------------------------------------------------------------- hotels
@dataclass(frozen=True)
class _Room:
    id: str
    name: str
    beds: str
    size_m2: int
    max_guests: int
    breakfast: bool
    free_days: int | None
    nightly: int


def _rooms(hotel: tuple) -> list[_Room]:
    return [_Room(*r) for r in hotel[8]]


def room_view(r: _Room, q: HotelQuery, today: date, hotel_id: str) -> dict:
    until = q.check_in - timedelta(days=r.free_days) if r.free_days is not None else None
    free = until is not None and until >= today  # a window already gone is non-refundable now
    before_tax = round(r.nightly / (1 + HOTEL_TAX_RATE))
    units = q.nights * q.rooms
    return {
        "id": r.id,
        "booking_ref": f"{q.city}.{hotel_id}.{r.id}.{q.check_in:%Y%m%d}.{q.nights}.{q.rooms}.{q.guests}",
        "name": r.name,
        "beds": r.beds,
        "size_m2": r.size_m2,
        "max_guests": r.max_guests,
        "breakfast": r.breakfast,
        "cancellation": {"free": free, "until": until.isoformat() if free else None},
        "price": {
            "currency": CURRENCY,
            "nightly": r.nightly,
            "nights": q.nights,
            "rooms": q.rooms,
            "total": r.nightly * units,
            "before_taxes": before_tax * units,
            "taxes": (r.nightly - before_tax) * units,
            "taxes_included": True,
        },
    }


def _fits(r: _Room, q: HotelQuery) -> bool:
    return math.ceil(q.guests / q.rooms) <= r.max_guests


def _room_ok(r: _Room, room: dict, f: HotelFilters) -> bool:
    return (
        (not f.free_cancellation or room["cancellation"]["free"])
        and (not f.breakfast or r.breakfast)
        and (f.max_nightly is None or r.nightly <= f.max_nightly)
    )


def _hotel_card(h: tuple, q: HotelQuery, room: dict) -> dict:
    hid, name, area, stars, score, count, amenities, hue, _ = h
    return {
        "id": hid,
        "kind": "hotel",
        "name": name,
        "area": area,
        "city": AIRPORTS[q.city][0],
        "stars": stars,
        "review": {"score": score, "scale": 10, "count": count},
        "amenities": list(amenities),
        "photo_hue": hue,
        "check_in": q.check_in.isoformat(),
        "check_out": q.check_out.isoformat(),
        "nights": q.nights,
        "rooms": q.rooms,
        "guests": q.guests,
        "room": room,  # the cheapest room that fits the guests and the filters
        "price": room["price"],
        "cancellation": room["cancellation"],
        "tags": [],
        "sample": True,
        "fictional": True,  # invented property: its rating and review count are samples too
    }


def _hotel_hits(q: HotelQuery, f: HotelFilters, today: date) -> tuple[list[dict], list[dict]]:
    if q.city not in HOTEL_CITIES:
        return [], []
    every, hits = [], []
    for h in _HOTELS:
        fitting = [(r, room_view(r, q, today, h[0])) for r in _rooms(h) if _fits(r, q)]
        if not fitting:
            continue
        every.append(_hotel_card(h, q, min(fitting, key=lambda x: x[0].nightly)[1]))
        ok = [x for x in fitting if _room_ok(x[0], x[1], f)]
        if not ok:
            continue
        card = _hotel_card(h, q, min(ok, key=lambda x: x[0].nightly)[1])
        if (f.min_stars is None or card["stars"] >= f.min_stars) and (
            f.min_score is None or card["review"]["score"] >= f.min_score
        ):
            hits.append(card)
    return every, hits


def recommended_score(c: dict) -> float:
    """Higher is better: guest score, stars, and a little for a lower nightly rate."""
    return c["review"]["score"] * 10 + c["stars"] * 2 - c["price"]["nightly"] / 1000


_HOTEL_SORTS: dict[str, Callable[[dict], tuple]] = {
    "recommended": lambda c: (-recommended_score(c), c["name"]),
    "price": lambda c: (c["price"]["nightly"], c["name"]),
    "rating": lambda c: (-c["review"]["score"], -c["review"]["count"], c["name"]),
}


def search_hotels(
    q: HotelQuery,
    f: HotelFilters | None = None,
    offset: int = 0,
    limit: int = 3,
    today: date | None = None,
) -> dict:
    f, today = f or HotelFilters(), today or date.today()
    every, hits = _hotel_hits(q, f, today)
    hits.sort(key=_HOTEL_SORTS[f.sort])
    _tag(hits, "popular", lambda c: (-c["review"]["count"],))
    _tag(hits, "top_rated", _HOTEL_SORTS["rating"])
    _tag(hits, "cheapest", _HOTEL_SORTS["price"])
    nightly = [c["price"]["nightly"] for c in every]
    return {
        "kind": "hotels",
        "query": {**q.model_dump(mode="json"), "nights": q.nights},
        "filters": f.model_dump(mode="json"),
        **_page(hits, every, offset, limit, q.city not in HOTEL_CITIES),
        "price_range": {"min": min(nightly), "max": max(nightly)} if nightly else None,
    }


def _hotel(hotel_id: str) -> tuple | None:
    return next((h for h in _HOTELS if h[0] == hotel_id), None)


def hotel_rooms(q: HotelQuery, hotel_id: str, today: date | None = None) -> dict | None:
    """Every room of one hotel for the stay, cheapest first; rooms too small for the guests are
    left out. None = unknown hotel or a city without sample data."""
    h, today = _hotel(hotel_id), today or date.today()
    if h is None or q.city not in HOTEL_CITIES:
        return None
    rooms = sorted((r for r in _rooms(h) if _fits(r, q)), key=lambda r: r.nightly)
    views = [room_view(r, q, today, h[0]) for r in rooms]
    if not views:
        return {"hotel": None, "rooms": [], "sample": True, "data": dict(DATA_STATUS)}
    return {"hotel": _hotel_card(h, q, views[0]), "rooms": views, "sample": True,
            "data": dict(DATA_STATUS)}  # fmt: skip


def room_review(
    q: HotelQuery, hotel_id: str, room_id: str, today: date | None = None
) -> dict | None:
    """The stay review for one room (None = not a room of this hotel that fits). Not a booking."""
    got = hotel_rooms(q, hotel_id, today)
    room = next((r for r in (got or {}).get("rooms", []) if r["id"] == room_id), None)
    if room is None:
        return None
    return {"hotel": {**got["hotel"], "room": room, "price": room["price"],
                      "cancellation": room["cancellation"]},
            "room": room, "booked": False, "sample": True, "data": dict(DATA_STATUS)}  # fmt: skip


# ----------------------------------------------------------------------------- per-person state
@dataclass
class Session:
    sid: str
    owner: str  # e.g. "discord:<user id>"; only this owner can read or change it
    kind: Literal["flights", "hotels"]
    query: FlightQuery | HotelQuery
    filters: FlightFilters | HotelFilters
    offset: int = 0
    selected: str | None = None  # flight id or "hotel_id/room_id"
    expires: float = 0.0
    extra: dict = field(default_factory=dict)


class Sessions:
    """Search state for platforms that keep it on the server (Discord). The session id goes into
    component custom ids; `get` returns None for an unknown, expired or someone else's session,
    so one person's buttons can never read or move another person's search. Process memory only:
    a restart expires every search (the platform says so and offers a new one)."""

    def __init__(
        self, ttl_s: float = 1800.0, clock: Callable[[], float] = time.monotonic, cap: int = 2000
    ):
        self.ttl, self.clock, self.cap = ttl_s, clock, cap
        self._items: dict[str, Session] = {}
        self._lock = threading.Lock()

    def start(self, owner: str, kind, query, filters=None) -> Session:
        default = FlightFilters() if kind == "flights" else HotelFilters()
        s = Session(secrets.token_hex(5), owner, kind, query, filters or default)
        with self._lock:
            now = self.clock()
            for sid in [k for k, v in self._items.items() if v.expires <= now]:
                del self._items[sid]
            while len(self._items) >= self.cap:  # dicts keep insertion order: drop the oldest
                del self._items[next(iter(self._items))]
            s.expires = now + self.ttl
            self._items[s.sid] = s
        return s

    def get(self, sid: str, owner: str) -> Session | None:
        with self._lock:
            s = self._items.get(sid)
            now = self.clock()
            if s is None or s.owner != owner or s.expires <= now:
                return None
            s.expires = now + self.ttl  # every use keeps it alive
            return s


# ----------------------------------------------------------------------------- web chat requests
CITY_ALIASES = {
    "BKK": ("bangkok", "bkk", "กรุงเทพ", "สุวรรณภูมิ"),
    "SIN": ("singapore", "sin", "สิงคโปร์"),
    "KUL": ("kuala lumpur", "kul", "กัวลาลัมเปอร์"),
    "HKG": ("hong kong", "hkg", "ฮ่องกง"),
    "NRT": ("tokyo", "nrt", "โตเกียว"),
}
_FLIGHT_WORDS = re.compile(
    r"\b(flights?|fly|flying|plane tickets?|airfares?)\b|เที่ยวบิน|ตั๋วเครื่องบิน|บินไป"
)
_HOTEL_WORDS = re.compile(r"\b(hotels?|accommodation|place to stay|somewhere to stay)\b|โรงแรม|ที่พัก")
# a question about a trip that exists or happened belongs to the brain (list_trips, memory)
_ABOUT_A_TRIP = re.compile(r"\b(did|was|were|stayed|booked|already|last (time|trip)|when (does|is|do)|where (is|was)|what time|my (flight|hotel|booking|trip))\b|จองแล้ว|ที่จองไว้|ครั้งที่แล้ว|ครั้งก่อน|เมื่อไหร่|กี่โมง")  # fmt: skip
_NOT_A_SEARCH = re.compile(r"\b(receipts?|expenses?|invoices?|claims?|spent|spend|reimburse\w*|policy)\b|ใบเสร็จ|ค่าใช้จ่าย|เบิก")  # fmt: skip
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
_PEOPLE = re.compile(r"\b(\d{1,2}|one|two|three|four|five|six)\s+(people|persons|passengers|"
                     r"travell?ers|adults|guests|of us|pax)\b|(\d{1,2})\s*คน")  # fmt: skip
_NIGHTS = re.compile(r"\b(\d{1,2}|one|two|three|four|five|six)\s+nights?\b|(\d{1,2})\s*คืน")
_ROOMS = re.compile(r"\b(\d)\s+rooms\b|(\d)\s*ห้อง")
_ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_DAY_MONTH = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")[a-z]*\b")
_MONTH_DAY = re.compile(r"\b(" + "|".join(_MONTHS) + r")[a-z]*\s+(\d{1,2})\b")
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass
class TripRequest:
    flight: FlightQuery | None
    hotel: HotelQuery | None


def next_week_tuesday(today: date) -> date:
    """The default departure: Tuesday of next week (a work trip, editable on every platform)."""
    return today + timedelta(days=7 - today.weekday() + 1)


def _num(s: str | None) -> int | None:
    return None if s is None else _NUMBERS.get(s) or (int(s) if s.isdigit() else None)


def _cities(text: str) -> list[tuple[int, str]]:
    found = []
    for code, names in CITY_ALIASES.items():
        for n in names:
            for m in re.finditer(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", text):
                found.append((m.start(), code))
    return sorted(found)


def _when(text: str, today: date) -> date:
    if m := _ISO.search(text):
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            pass
    day_month = _DAY_MONTH.search(text)
    month_day = _MONTH_DAY.search(text)
    if day_month or month_day:
        day, mon = (day_month[1], day_month[2]) if day_month else (month_day[2], month_day[1])
        try:
            d = date(today.year, _MONTHS.index(mon[:3]) + 1, int(day))
            return d if d >= today else d.replace(year=today.year + 1)
        except ValueError:
            pass
    if "tomorrow" in text or "พรุ่งนี้" in text:
        return today + timedelta(days=1)
    for i, name in enumerate(_WEEKDAYS):
        if re.search(r"\b" + name + r"\b", text):
            ahead = (i - today.weekday()) % 7 or 7
            return today + timedelta(days=ahead + (7 if "next " + name in text else 0))
    return next_week_tuesday(today)  # "next week" and no date at all


def parse_request(text: str, today: date) -> TripRequest | None:
    """A typed flight / hotel search ("Find a flight from Bangkok to Singapore and a hotel there for
    2 people next week") -> the queries, or None when it is not one (the brain answers then).
    Narrow on purpose: a flight or hotel word, a known city, and no expense words."""
    low = " ".join((text or "").lower().split())
    wants_flight, wants_hotel = bool(_FLIGHT_WORDS.search(low)), bool(_HOTEL_WORDS.search(low))
    if not (wants_flight or wants_hotel) or _NOT_A_SEARCH.search(low) or _ABOUT_A_TRIP.search(low):
        return None
    cities = _cities(low)
    if not cities:
        return None
    origin = next(
        (c for p, c in cities if re.search(r"(from|จาก)\s*$", low[max(0, p - 6) : p])), None
    )
    dest = next((c for p, c in cities if re.search(r"(to|ไป)\s*$", low[max(0, p - 4) : p])), None)
    dest = dest or next((c for _, c in cities if c != origin), None)
    origin = origin or ("BKK" if dest != "BKK" else "SIN")
    if dest is None:
        return None
    m = _PEOPLE.search(low)
    people = max(1, min(_num(m and (m[1] or m[3])) or 1, 9))
    m = _NIGHTS.search(low)
    nights = max(1, min(_num(m and (m[1] or m[2])) or 3, MAX_NIGHTS))
    m = _ROOMS.search(low)
    rooms = max(1, min(_num(m and (m[1] or m[2])) or math.ceil(people / 2), 4, people))
    day = max(_when(low, today), today)
    flight = (
        FlightQuery(origin=origin, destination=dest, depart=day, adults=people,
                    cabin="business" if re.search(r"\bbusiness class\b|ชั้นธุรกิจ", low) else "economy")
        if wants_flight else None
    )  # fmt: skip
    hotel_city = dest
    if wants_hotel and not wants_flight:  # "a hotel in Singapore": the one city named
        hotel_city = cities[-1][1]
    hotel = (
        HotelQuery(city=hotel_city, check_in=day, check_out=day + timedelta(days=nights),
                   rooms=rooms, guests=people)
        if wants_hotel else None
    )  # fmt: skip
    return TripRequest(flight=flight, hotel=hotel)


# ----------------------------------------------------------------------------- the AI's tools
# Dory's brain interprets the message and calls these; they validate, search the same catalogue
# and record a card for the platform (web chat cards, Discord components). The model only ever
# talks about what they return, and asks one question when something essential is missing.
TRIP_TTL_S = 2 * 3600.0
CARD_TOOL_NAMES = ("search_flights", "search_hotels")
_find_flights, _find_hotels = search_flights, search_hotels  # the tools below reuse these names


@dataclass
class Trip:
    flight: FlightQuery | None = None
    flight_filters: FlightFilters | None = None
    hotel: HotelQuery | None = None
    hotel_filters: HotelFilters | None = None
    return_flight: FlightQuery | None = None  # the way back (origin and destination swapped)
    return_filters: FlightFilters | None = None
    # booking_refs the person chose in the cards, by slot: flight / return / room (what the card
    # "Book in sandbox" offers to book together)
    picked: dict[str, str] = field(default_factory=dict)
    expires: float = 0.0


class Trips:
    """Each person's last flight and hotel search, so "and a hotel there", "only non-stop" or
    "3 nights" continue the same trip across messages and across the two searches. Owner-keyed,
    process memory, forgotten after `ttl_s` without use."""

    def __init__(self, ttl_s: float = TRIP_TTL_S, clock: Callable[[], float] = time.monotonic):
        self.ttl, self.clock = ttl_s, clock
        self._items: dict[str, Trip] = {}
        self._lock = threading.Lock()

    def get(self, owner: str) -> Trip:
        with self._lock:
            trip = self._items.get(owner)
            return trip if trip is not None and trip.expires > self.clock() else Trip()

    def remember(self, owner: str, **parts) -> None:
        with self._lock:
            now = self.clock()
            for k in [k for k, v in self._items.items() if v.expires <= now]:
                del self._items[k]
            trip = self._items.get(owner) or Trip()
            for k, v in parts.items():
                setattr(trip, k, v)
            trip.expires = now + self.ttl
            self._items[owner] = trip

    def pick(self, owner: str, ref: str, today: date) -> str | None:
        """Remember a booking_ref chosen in a card; returns its slot, or None when the ref does not
        resolve. A flight on the reverse route of the picked flight, leaving after it lands, is the
        way back (`return`); any other flight replaces `flight` and drops a way back that no longer
        fits; a room is `room`."""
        got = by_booking_ref(ref, today)
        if got is None:
            return None
        trip = self.get(owner)
        picked = dict(trip.picked)
        if got["kind"] == "stay":
            slot = "room"
        else:
            f = got["flight"]
            out = by_booking_ref(picked.get("flight", ""), today)
            o = out["flight"] if out else None
            back = o is not None and (f["origin"]["code"], f["destination"]["code"]) == (
                o["destination"]["code"], o["origin"]["code"]) and f["depart"] >= o["arrive"]  # fmt: skip
            slot = "return" if back else "flight"
            if not back:
                ret = by_booking_ref(picked.get("return", ""), today)
                r = ret["flight"] if ret else None
                if r is None or (r["origin"]["code"], r["destination"]["code"]) != (
                        f["destination"]["code"], f["origin"]["code"]) or r["depart"] < f["arrive"]:  # fmt: skip
                    picked.pop("return", None)
        picked[slot] = ref.strip()
        self.remember(owner, picked=picked)
        return slot

    def picked(self, owner: str) -> dict[str, str]:
        return dict(self.get(owner).picked)

    def unpick(self, owner: str, *slots: str) -> None:
        """Forget picks (e.g. the ones just booked)."""
        left = {k: v for k, v in self.get(owner).picked.items() if k not in slots}
        self.remember(owner, picked=left)


@dataclass
class CardCtx:
    owner: str  # "discord:<user id>", "web:<email>"
    today: date
    trips: Trips
    render: bool = True  # False = a voice turn: nothing is drawn, the result is spoken
    home: str = ""  # the person's home airport (profile): the departure when a request names none
    cards: list[dict] = field(default_factory=list)  # what the platform renders after the reply


def place_code(text: str) -> str | None:
    """A city or airport name / IATA code -> the code; None when unknown."""
    v = " ".join((text or "").lower().split())
    if re.fullmatch(r"[a-z]{3}", v):
        return v.upper()
    for code, names in CITY_ALIASES.items():
        if v in names:
            return code
    for code, (city, airport, _) in AIRPORTS.items():
        if v in (city.lower(), airport.lower()):
            return code
    return None


def _day(text: str) -> date | None:
    try:
        return date.fromisoformat((text or "").strip())
    except ValueError:
        return None


def _problem(e: ValueError) -> str:
    errs = getattr(e, "errors", None)
    if callable(errs):
        return "; ".join(f"{'.'.join(map(str, x['loc'])) or 'search'}: {x['msg']}" for x in errs())
    return str(e)


def _csv(text: str) -> list[str]:
    return [x.strip().lower() for x in (text or "").split(",") if x.strip()]


def _need(missing: list[str]) -> dict:
    return {"status": "need_details", "missing": missing,
            "ask": "Ask the person ONE short question for: " + ", ".join(missing)
                   + ". Do not guess these and do not search yet."}  # fmt: skip


def _unknown(place: str) -> dict:
    return {"status": "unknown_place", "place": place,
            "note": "No airport or city of that name in the sample data. Ask for the city or "
                    "IATA code, or offer Bangkok (BKK) -> Singapore (SIN), which has results."}  # fmt: skip


def _card(ctx: CardCtx, kind: str, q, f, leg: str = "out") -> None:
    # the latest search of a kind (and flight leg) wins
    ctx.cards[:] = [c for c in ctx.cards if (c["kind"], c.get("leg", "out")) != (kind, leg)]
    ctx.cards.append({"kind": kind, "leg": leg, "query": q.model_dump(mode="json"),
                      "filters": f.model_dump(mode="json")})  # fmt: skip


def _shown(ctx: CardCtx) -> str:
    if ctx.render:
        return ("The person sees these as interactive cards under your reply (filters, more "
                "results, select). Say in one or two sentences what you searched and the standout "
                "option from `top`; do not list every result.")  # fmt: skip
    return "Nothing is drawn (voice): describe at most two options from `top` in short sentences."


_RULE = ("Sample data: never present a price as live availability; searching books nothing (only "
         "book_trip makes a sandbox booking, with the person's confirmation); never mention a "
         "flight, time or price that is not in this result. To book, pass a booking_ref from this "
         "result to book_trip.")  # fmt: skip


def card_tools(ctx: CardCtx) -> list:
    """`search_flights` and `search_hotels` for the agent, bound to one person and one request.
    Both tool functions share `.cards` (read it with `tool_cards`)."""

    def search_flights(origin: str = "", destination: str = "", depart_date: str = "",
                       travellers: int = 0, cabin: str = "", stops: str = "",
                       departure_time: str = "", airlines: str = "",
                       max_price_per_traveller: int = 0, sort: str = "",
                       clear_filters: bool = False) -> dict:  # fmt: skip
        """THE flight search: find one-way flights, show them to the person and get the
        booking_ref that book_trip books (sample data: real airline names, sample schedules and
        prices; Bangkok BKK <-> Singapore SIN has results both ways). Use it for any request to
        look for, compare, narrow or book flights. A round trip is two calls: out, then back
        (origin and destination swapped, a later date). To refine ("only non-stop", "cheapest
        first", "for 3 people"), call it again with ONLY the changed fields: missing fields
        continue the person's current trip. If it answers need_details or unknown_place, ask the
        person that one question.

        Args:
            origin: departure city or IATA code, e.g. Bangkok or BKK.
            destination: arrival city or IATA code, e.g. Singapore or SIN.
            depart_date: YYYY-MM-DD; work out "next Tuesday" yourself from today's date.
            travellers: adult travellers 1-9; 0 keeps the trip's number (else 1).
            cabin: economy or business; empty keeps the trip's cabin (else economy).
            stops: nonstop and/or 1stop, comma-separated; empty = any.
            departure_time: morning, afternoon and/or evening, comma-separated; empty = any.
            airlines: IATA airline codes, comma-separated, e.g. TG,SQ; empty = any.
            max_price_per_traveller: THB including taxes; 0 = no limit.
            sort: best, cheapest, fastest or earliest; empty keeps the current order.
            clear_filters: true to drop the stops / time / airline / price filters.
        """
        trip = ctx.trips.get(ctx.owner)
        prev, hotel = trip.flight, trip.hotel
        o = place_code(origin) if origin.strip() else (prev.origin if prev else None)
        if origin.strip() and o is None:
            return _unknown(origin)
        d = place_code(destination) if destination.strip() else None
        if destination.strip() and d is None:
            return _unknown(destination)
        d = d or (prev.destination if prev else hotel.city if hotel else None)
        if (
            o is None and ctx.home and ctx.home != d
        ):  # never a flight from X to X: then Dory asks where from
            o = ctx.home
        day = _day(depart_date) if depart_date.strip() else None
        if depart_date.strip() and day is None:
            return {"status": "invalid", "problem": "depart_date must be YYYY-MM-DD"}
        day = day or (prev.depart if prev else hotel.check_in if hotel else None)
        missing = [n for n, v in (("origin", o), ("destination", d), ("depart_date", day)) if not v]
        if missing:
            return _need(missing)
        try:
            q = FlightQuery(
                origin=o, destination=d, depart=day,
                adults=travellers or (prev.adults if prev else hotel.guests if hotel else 1),
                cabin=cabin.strip().lower() or (prev.cabin if prev else "economy"),
            )  # fmt: skip
            # the way back of the current trip is its own leg (its own card, filters, booking)
            back = prev is not None and (q.origin, q.destination, prev.depart <= q.depart) == (
                prev.destination, prev.origin, True)  # fmt: skip
            leg_prev, leg_filters = (
                (trip.return_flight, trip.return_filters) if back else (prev, trip.flight_filters)
            )
            # filters are preferences: they stay while the route does ("only non-stop", then
            # "for 3 people" or "what about Wednesday?")
            same = leg_prev is not None and (leg_prev.origin, leg_prev.destination) == (
                q.origin, q.destination)  # fmt: skip
            base = leg_filters if same and leg_filters and not clear_filters else None
            f = (base or FlightFilters()).model_copy(deep=True)
            changes = {
                "stops": _csv(stops) or None,
                "times": _csv(departure_time) or None,
                "airlines": [a.upper() for a in _csv(airlines)] or None,
                "max_price": max_price_per_traveller or None,
                "sort": sort.strip().lower() or None,
            }
            f = FlightFilters(**{**f.model_dump(), **{k: v for k, v in changes.items() if v}})
        except ValueError as e:
            return {"status": "invalid", "problem": _problem(e)}
        if p := date_problem(ctx.today, q.depart):
            return {"status": "invalid", "problem": p, "today": ctx.today.isoformat()}
        res = _find_flights(q, f, 0, 3)
        if back:
            ctx.trips.remember(ctx.owner, return_flight=q, return_filters=f)
        else:  # a new outbound route starts a new trip: its old way back no longer applies
            keep = prev is not None and (prev.origin, prev.destination) == (q.origin, q.destination)
            ctx.trips.remember(ctx.owner, flight=q, flight_filters=f,
                               **({} if keep else {"return_flight": None, "return_filters": None}))  # fmt: skip
        _card(ctx, "flights", q, f, "return" if back else "out")
        return {
            "status": "ok" if res["total"] else "no_results",
            "empty": res["empty"],
            "query": res["query"],
            "filters": res["filters"],
            "total": res["total"],
            "top": [
                {
                    "id": o["id"],
                    "booking_ref": o["booking_ref"],
                    "airline": o["airline"]["name"],
                    "flights": o["flights"],
                    "depart": o["depart"],
                    "arrive": o["arrive"],
                    "duration_min": o["duration_min"],
                    "stops": o["stops"],
                    "via": [v["code"] for v in o["via"]],
                    "checked_bag_kg": o["baggage"]["checked_kg"],
                    "tags": o["tags"],
                    "price_per_traveller": o["price"]["per_traveller"],
                    "total_for_all_travellers": o["price"]["total"],
                    "currency": CURRENCY,
                }
                for o in res["results"]
            ],  # fmt: skip
            "leg": "return" if back else "out",
            "data": res["data"],
            "shown": _shown(ctx),
            "rule": _RULE,
        }

    def search_hotels(city: str = "", check_in: str = "", check_out: str = "", nights: int = 0,
                      rooms: int = 0, guests: int = 0, free_cancellation: bool = False,
                      breakfast: bool = False, min_stars: int = 0, min_guest_score: float = 0,
                      max_price_per_night: int = 0, sort: str = "", hotel_id: str = "",
                      clear_filters: bool = False) -> dict:  # fmt: skip
        """THE hotel search: find hotels, show them to the person and get the booking_ref that
        book_trip books (sample data: FICTIONAL properties with sample ratings and prices;
        Singapore SIN has results). Use it for any request to look for, compare, narrow or book
        hotels. A hotel "there" / "for the trip" continues the person's flight search (its city,
        date, travellers, and the way back's date as check-out). Each hotel comes with its
        cheapest fitting room; pass hotel_id to list all of that hotel's rooms (each with its own
        booking_ref). To refine, call it again with ONLY the changed fields. If it answers
        need_details or unknown_place, ask the person that one question.

        Args:
            city: city or IATA code, e.g. Singapore or SIN.
            check_in: YYYY-MM-DD.
            check_out: YYYY-MM-DD; or give nights instead.
            nights: number of nights 1-30 (instead of check_out).
            rooms: 1-4; 0 keeps the trip's number (else enough rooms for two per room).
            guests: 1-12; 0 keeps the trip's number (else the flight's travellers, else 1).
            free_cancellation: only rates that can be cancelled for free.
            breakfast: only rates with breakfast.
            min_stars: 1-5; 0 = any.
            min_guest_score: 0-10; 0 = any.
            max_price_per_night: THB per room per night including taxes; 0 = no limit.
            sort: recommended, price or rating; empty keeps the current order.
            hotel_id: a hotel's id from an earlier result, to list its rooms; empty = search.
            clear_filters: true to drop the filters.
        """
        trip = ctx.trips.get(ctx.owner)
        prev, flight = trip.hotel, trip.flight
        c = place_code(city) if city.strip() else None
        if city.strip() and c is None:
            return _unknown(city)
        c = c or (prev.city if prev else flight.destination if flight else None)
        start = _day(check_in) if check_in.strip() else None
        if check_in.strip() and start is None:
            return {"status": "invalid", "problem": "check_in must be YYYY-MM-DD"}
        start = start or (prev.check_in if prev else flight.depart if flight else None)
        end = _day(check_out) if check_out.strip() else None
        if check_out.strip() and end is None:
            return {"status": "invalid", "problem": "check_out must be YYYY-MM-DD"}
        if end is None and start and nights:
            end = start + timedelta(days=nights)
        if end is None and start and prev:
            end = start + timedelta(days=prev.nights)
        back = trip.return_flight
        if end is None and start and back is not None and back.depart > start:
            end = back.depart  # check out the day the way back flies
        missing = [n for n, v in (("city", c), ("check_in", start), ("nights", end)) if not v]
        if missing:
            return _need(missing)
        people = guests or (prev.guests if prev else flight.adults if flight else 1)
        try:
            q = HotelQuery(city=c, check_in=start, check_out=end, guests=people,
                           rooms=rooms or (prev.rooms if prev and not guests else
                                           max(1, math.ceil(people / 2))))  # fmt: skip
            same = prev is not None and prev.city == q.city
            base = trip.hotel_filters if same and trip.hotel_filters and not clear_filters else None
            f = (base or HotelFilters()).model_dump()
            changes = {
                "free_cancellation": free_cancellation or None,
                "breakfast": breakfast or None,
                "min_stars": min_stars or None,
                "min_score": min_guest_score or None,
                "max_nightly": max_price_per_night or None,
                "sort": sort.strip().lower() or None,
            }
            f = HotelFilters(**{**f, **{k: v for k, v in changes.items() if v}})
        except ValueError as e:
            return {"status": "invalid", "problem": _problem(e)}
        if p := date_problem(ctx.today, q.check_in, q.check_out):
            return {"status": "invalid", "problem": p, "today": ctx.today.isoformat()}
        res = _find_hotels(q, f, 0, 3, ctx.today)
        ctx.trips.remember(ctx.owner, hotel=q, hotel_filters=f)
        _card(ctx, "hotels", q, f)
        if hotel_id.strip():
            got = hotel_rooms(q, hotel_id.strip().lower(), ctx.today)
            if got is None or not got["rooms"]:
                return {"status": "no_results", "hotel_id": hotel_id, "data": dict(DATA_STATUS),
                        "note": "no room of that hotel fits this stay (or no such hotel_id)"}  # fmt: skip
            return {
                "status": "ok",
                "hotel": {
                    "id": got["hotel"]["id"],
                    "name": got["hotel"]["name"],
                    "fictional": True,
                },
                "query": res["query"],
                "rooms": [
                    {
                        "booking_ref": r["booking_ref"],
                        "name": r["name"],
                        "beds": r["beds"],
                        "max_guests": r["max_guests"],
                        "breakfast": r["breakfast"],
                        "free_cancellation_until": r["cancellation"]["until"],
                        "price_per_room_per_night": r["price"]["nightly"],
                        "total_for_stay": r["price"]["total"],
                        "currency": CURRENCY,
                    }
                    for r in got["rooms"]
                ],  # fmt: skip
                "data": got["data"],
                "shown": _shown(ctx),
                "rule": _RULE,
            }
        return {
            "status": "ok" if res["total"] else "no_results",
            "empty": res["empty"],
            "query": res["query"],
            "filters": res["filters"],
            "total": res["total"],
            "top": [
                {
                    "id": h["id"],
                    "booking_ref": h["room"]["booking_ref"],
                    "name": h["name"],
                    "fictional": True,
                    "area": h["area"],
                    "stars": h["stars"],
                    "guest_score": h["review"]["score"],
                    "room": h["room"]["name"],
                    "free_cancellation": h["cancellation"]["free"],
                    "price_per_room_per_night": h["price"]["nightly"],
                    "total_for_stay": h["price"]["total"],
                    "currency": CURRENCY,
                    "tags": h["tags"],
                }
                for h in res["results"]
            ],  # fmt: skip
            "data": res["data"],
            "shown": _shown(ctx),
            "rule": _RULE,
        }

    search_flights.cards = search_hotels.cards = ctx.cards
    return [search_flights, search_hotels]


def tool_cards(tools: list) -> list[dict]:
    """The cards the travel tools recorded for this reply (like `qa.tool_files`)."""
    for f in tools:
        box = getattr(f, "cards", None)
        if isinstance(box, list) and getattr(f, "__name__", "") in CARD_TOOL_NAMES:
            return list(box)
    return []


def travel_payload(cards: list[dict]) -> dict | None:
    """The chat reply's `travel`: the queries and filters of the searches to draw."""
    by = {("return_flights" if c.get("leg") == "return" else c["kind"]): c for c in cards}
    if not by:
        return None
    return {
        "flights": by["flights"]["query"] if "flights" in by else None,
        "hotels": by["hotels"]["query"] if "hotels" in by else None,
        "flight_filters": by["flights"]["filters"] if "flights" in by else None,
        "hotel_filters": by["hotels"]["filters"] if "hotels" in by else None,
        "return_flights": by["return_flights"]["query"] if "return_flights" in by else None,
        "return_flight_filters": (
            by["return_flights"]["filters"] if "return_flights" in by else None
        ),
    }


_FLIGHT_REF = re.compile(r"^([A-Z]{3})([A-Z]{3})\.([A-Z0-9-]+-(\d{8})-([EB]))\.(\d)$")
_STAY_REF = re.compile(
    r"^([a-z]{3})\.([a-z0-9-]+)\.([a-z0-9-]+)\.(\d{8})\.(\d{1,2})\.(\d)\.(\d{1,2})$"
)


def by_booking_ref(ref: str, today: date) -> dict | None:
    """A search result's `booking_ref` -> its fare review (`kind` flight) or stay review (`kind`
    stay), priced again from the catalogue, so a model cannot change a price by retyping it.
    None = malformed, unknown, in the past or too far ahead. Case-insensitive (book_trip
    upper-cases what it is given)."""
    raw = (ref or "").strip()
    try:
        if m := _FLIGHT_REF.match(raw.upper()):
            o, d, fid, day, cabin, n = m.groups()
            q = FlightQuery(origin=o, destination=d, depart=datetime.strptime(day, "%Y%m%d").date(),
                            adults=int(n), cabin="economy" if cabin == "E" else "business")  # fmt: skip
            r = None if date_problem(today, q.depart) else fare_review(q, fid)
            return {"kind": "flight", **r} if r else None
        if m := _STAY_REF.match(raw.lower()):
            city, hid, rid, day, nights, rooms, guests = m.groups()
            start = datetime.strptime(day, "%Y%m%d").date()
            q = HotelQuery(city=city, check_in=start, check_out=start + timedelta(days=int(nights)),
                           rooms=int(rooms), guests=int(guests))  # fmt: skip
            if date_problem(today, q.check_in, q.check_out):
                return None
            r = room_review(q, hid, rid, today)
            return {"kind": "stay", "query": q.model_dump(mode="json"), **r} if r else None
    except ValueError:  # an impossible date or a query the models refuse
        return None
    return None
