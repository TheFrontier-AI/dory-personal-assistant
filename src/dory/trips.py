"""Trips: flight and hotel search plus sandbox booking (pure, no discord import).

The providers are free sandboxes behind the `Provider` protocol (no tickets, no money): Duffel test
mode for flights and the LiteAPI (Nuitee Connect) sandbox for hotels. Amadeus Self-Service, the first
sandbox, was decommissioned on 17 July 2026. `SampleProvider` is deterministic sample data (tests, no
key, sandbox outage); `Fallback` searches the sandbox first and serves the sample on an error, a
timeout or an empty answer, and every result says which (`source`). Tools bound per request:
`search_flights`, `search_hotels`, `book_trip` (two-step confirm through `SecretaryState`; an
approval id, when given, must be APPROVED and the asker's own: checked here, never by the model),
`travel_profile` and `list_trips`. A booking writes a trip record (`dory_trips`), one ledger receipt
per booked item (category ค่าเดินทาง) and a check-in reminder 24 h before departure.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from .i18n import CATALOG, t
from .models import Receipt
from .secretary import CONFIRM_TTL_S, fingerprint
from .secretary_store import new_id

logger = logging.getLogger(__name__)

TRIP_KIND = "dory_trips"
PROFILE_KIND = "dory_travel_profiles"
MAX_RESULTS = 5
PROFILE_MAX = 600
OFFER_TTL_S = 3600.0
SANDBOX_TIMEOUT_S = 25.0
DUFFEL_API = "https://api.duffel.com"
LITEAPI_SEARCH = "https://api.liteapi.travel/v3.0"
LITEAPI_BOOK = "https://book.liteapi.travel/v3.0"
DUFFEL_TEST_PREFIX = "duffel_test_"
CABINS = ("economy", "premium_economy", "business", "first")
PNR_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TRAVEL_CATEGORY = "ค่าเดินทาง"
_IATA = re.compile(r"^[A-Z]{3}$")
_DUR = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:[\d.]+S)?)?$")


class FlightOffer(BaseModel):
    offer_id: str = ""
    provider: str
    carrier: str
    carrier_name: str = ""
    flights: list[str]  # e.g. ["TG403", "TG404"]
    origin: str
    destination: str
    depart: str  # outbound, local ISO from the provider
    arrive: str
    return_depart: str = ""
    return_arrive: str = ""
    duration_min: int
    stops: int = 0
    cabin: str = "economy"
    price: float
    currency: str
    seats: int | None = None
    raw: Any = None  # the provider's own object, needed to book; never shown to the model


class HotelOffer(BaseModel):
    offer_id: str = ""
    provider: str
    hotel_id: str
    name: str
    area: str = ""
    check_in: str
    check_out: str
    nights: int
    room: str = ""
    price_per_night: float
    total: float
    currency: str
    cancellation: str = ""
    raw: Any = None


class Booking(BaseModel):
    reference: str
    status: str = "CONFIRMED"
    provider: str


class Provider(Protocol):
    name: str

    def flights(self, origin: str, destination: str, depart: str, ret: str, adults: int,
                cabin: str) -> list[FlightOffer]: ...  # fmt: skip
    def hotels(self, city: str, check_in: str, check_out: str, adults: int) -> list[HotelOffer]: ...
    def book_flight(self, offer: FlightOffer, traveller: dict) -> Booking: ...
    def book_hotel(self, offer: HotelOffer, traveller: dict) -> Booking: ...


# ----------------------------------------------------------------------------- sample data
CARRIERS = {"TG": "Thai Airways", "SQ": "Singapore Airlines", "CX": "Cathay Pacific",
            "JL": "Japan Airlines"}  # fmt: skip
# route -> (minutes, [(carrier, number, depart HH:MM, arrive HH:MM, one-way THB)]); the return leg
# is the next flight number at the same local times. Illustrative, not live fares.
SAMPLE_FLIGHTS: dict[tuple[str, str], tuple[int, list[tuple[str, str, str, str, int]]]] = {
    ("BKK", "SIN"): (145, [("TG", "403", "08:00", "11:25", 6850), ("SQ", "705", "09:40", "13:05", 7450),
                           ("TG", "409", "14:10", "17:35", 7900), ("SQ", "711", "15:30", "18:55", 8600),
                           ("SQ", "713", "20:10", "23:35", 9200)]),
    ("BKK", "HKG"): (175, [("TG", "600", "08:00", "11:55", 8400), ("CX", "700", "09:05", "12:55", 9100),
                           ("TG", "628", "13:40", "17:35", 9750)]),
    ("BKK", "NRT"): (380, [("TG", "676", "08:00", "15:50", 17200), ("JL", "708", "09:00", "17:05", 18500),
                           ("TG", "640", "23:50", "07:30", 14900)]),
}  # fmt: skip
# city -> (currency, [(hotel id, name, area, room, per night)])
SAMPLE_HOTELS: dict[str, tuple[str, list[tuple[str, str, str, str, int]]]] = {
    "SIN": ("SGD", [
        ("MBSSIN01", "Marina Bay Sands", "Bayfront Avenue, Marina Bay", "Deluxe Room, City View", 689),
        ("FULSIN01", "The Fullerton Hotel Singapore", "Fullerton Square, Marina Bay", "Courtyard Room", 455),
        ("PRCSIN01", "PARKROYAL COLLECTION Marina Bay", "Raffles Boulevard, Marina Bay", "Garden Room", 338),
        ("CCHSIN01", "Carlton City Hotel Singapore", "Tanjong Pagar, 1.5 km from Marina Bay", "Deluxe Room", 210),
        ("HBOSIN01", "Hotel Boss", "Lavender, 3 km from Marina Bay", "Superior Room", 150),
    ]),
    "HKG": ("HKD", [
        ("CORHKG01", "Cordis, Hong Kong", "Mong Kok", "Superior Room", 1450),
        ("HPNHKG01", "Harbour Plaza North Point", "North Point", "Standard Room", 980),
    ]),
    "TYO": ("JPY", [
        ("KPTJPN01", "Keio Plaza Hotel Tokyo", "Shinjuku", "Standard Twin", 28000),
        ("TYIJPN01", "Toyoko Inn Tokyo Station", "Yaesu", "Single", 11000),
    ]),
}  # fmt: skip
SAMPLE_CANCELLATION = "free cancellation until 48 h before check-in"


def pnr(seed: str, n: int = 6) -> str:
    h = hashlib.sha256(seed.encode()).digest()
    return "".join(PNR_ALPHABET[b % len(PNR_ALPHABET)] for b in h[:n])


def _next_number(number: str) -> str:
    return str(int(number) + 1)


class SampleProvider:
    """Deterministic offers so the demo and the tests never depend on the network."""

    name = "sample"

    def flights(self, origin, destination, depart, ret, adults, cabin) -> list[FlightOffer]:
        key, back = (origin, destination), False
        if key not in SAMPLE_FLIGHTS and (destination, origin) in SAMPLE_FLIGHTS:
            key, back = (destination, origin), True
        if key not in SAMPLE_FLIGHTS:
            return []
        minutes, rows = SAMPLE_FLIGHTS[key]
        mult = {"economy": 1, "premium_economy": 1.6, "business": 2.8, "first": 4.5}[cabin]
        out = []
        for carrier, number, dep, arr, thb in rows:
            n = _next_number(number) if back else number
            legs = [f"{carrier}{n}"]
            price = thb * mult * adults
            offer = FlightOffer(
                provider=self.name, carrier=carrier, carrier_name=CARRIERS.get(carrier, carrier),
                flights=legs, origin=origin, destination=destination,
                depart=f"{depart}T{dep}:00", arrive=f"{depart}T{arr}:00", duration_min=minutes,
                cabin=cabin, price=0, currency="THB", seats=9,
            )  # fmt: skip
            if ret:
                offer.flights.append(f"{carrier}{number if back else _next_number(number)}")
                offer.return_depart, offer.return_arrive = f"{ret}T{dep}:00", f"{ret}T{arr}:00"
                price *= 2
            offer.price = round(price)
            out.append(offer)
        return out

    def hotels(self, city, check_in, check_out, adults) -> list[HotelOffer]:
        if city not in SAMPLE_HOTELS:
            return []
        currency, rows = SAMPLE_HOTELS[city]
        nights = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
        return [
            HotelOffer(
                provider=self.name,
                hotel_id=hid,
                name=name,
                area=area,
                check_in=check_in,
                check_out=check_out,
                nights=nights,
                room=room,
                price_per_night=night,
                total=night * nights,
                currency=currency,
                cancellation=SAMPLE_CANCELLATION,
            )  # fmt: skip
            for hid, name, area, room, night in rows
        ]

    def book_flight(self, offer, traveller) -> Booking:
        seed = f"{offer.flights}{offer.depart}{traveller.get('last', '')}"
        return Booking(reference=pnr(seed), provider=self.name)

    def book_hotel(self, offer, traveller) -> Booking:
        seed = f"{offer.hotel_id}{offer.check_in}{traveller.get('last', '')}"
        return Booking(reference=pnr(seed, 8), provider=self.name)


# ----------------------------------------------------------------------------- free sandboxes
# Both are free and cannot spend money: Duffel takes only a test-mode token (`duffel_test_`), and a
# LiteAPI answer that is not marked `sandbox` is refused (a production key would charge the card).
def _minutes(iso_duration: str) -> int:
    m = _DUR.match(iso_duration or "")
    return (int(m[1] or 0) * 1440 + int(m[2] or 0) * 60 + int(m[3] or 0)) if m else 0


class Duffel:
    """Flights in Duffel test mode: free, and its test airline Duffel Airways (ZZ) books on any
    route. Search = one offer request with the offers inline; book = an instant order paid from the
    test balance."""

    name = "duffel"

    def __init__(self, token: str, base: str = DUFFEL_API, *,
                 transport: httpx.BaseTransport | None = None) -> None:  # fmt: skip
        if not token.startswith(DUFFEL_TEST_PREFIX):
            raise ValueError("only a Duffel test-mode token (duffel_test_...) is allowed")
        self.token, self.base, self.transport = token, base, transport

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base, timeout=SANDBOX_TIMEOUT_S, transport=self.transport,
            headers={"Authorization": f"Bearer {self.token}", "Duffel-Version": "v2",
                     "Accept": "application/json"},
        )  # fmt: skip

    def flights(self, origin, destination, depart, ret, adults, cabin) -> list[FlightOffer]:
        slices = [{"origin": origin, "destination": destination, "departure_date": depart}]
        if ret:
            slices.append({"origin": destination, "destination": origin, "departure_date": ret})
        body = {"data": {"slices": slices, "passengers": [{"type": "adult"}] * adults,
                         "cabin_class": cabin}}  # fmt: skip
        with self._client() as c:  # supplier_timeout (ms) stays under our own HTTP timeout
            r = c.post("/air/offer_requests", json=body,
                       params={"return_offers": "true", "supplier_timeout": 20000})  # fmt: skip
        r.raise_for_status()
        data = r.json()["data"]
        if data.get("live_mode"):
            raise RuntimeError("Duffel answered in live mode; only test mode is allowed")
        offers = sorted(data.get("offers") or [], key=lambda o: float(o["total_amount"]))
        return [self._offer(o, cabin) for o in offers[:MAX_RESULTS]]

    def _offer(self, o: dict, cabin: str) -> FlightOffer:
        out = o["slices"][0]["segments"]
        legs = [f"{s['marketing_carrier']['iata_code']}{s['marketing_carrier_flight_number']}"
                for sl in o["slices"] for s in sl["segments"]]  # fmt: skip
        offer = FlightOffer(
            provider=self.name, carrier=o["owner"]["iata_code"], carrier_name=o["owner"].get("name", ""),
            flights=legs, origin=out[0]["origin"]["iata_code"],
            destination=out[-1]["destination"]["iata_code"], depart=out[0]["departing_at"],
            arrive=out[-1]["arriving_at"], duration_min=_minutes(o["slices"][0].get("duration", "")),
            stops=len(out) - 1, cabin=cabin, price=float(o["total_amount"]),
            currency=o["total_currency"],
            raw={"id": o["id"], "amount": o["total_amount"], "currency": o["total_currency"],
                 "passengers": [p["id"] for p in o.get("passengers") or []]},
        )  # fmt: skip
        if len(o["slices"]) > 1:
            back = o["slices"][1]["segments"]
            offer.return_depart, offer.return_arrive = (
                back[0]["departing_at"],
                back[-1]["arriving_at"],
            )
        return offer

    def book_flight(self, offer, traveller) -> Booking:
        raw = offer.raw
        # title, gender and birth date are test-mode placeholders: no ticket is issued
        people = [{"id": pid, "given_name": traveller["first"] if i == 0 else f"GUEST{i + 1}",
                   "family_name": traveller["last"], "title": "mr", "gender": "m",
                   "born_on": "1990-03-14", "email": traveller["email"],
                   "phone_number": traveller["phone"]} for i, pid in enumerate(raw["passengers"])]  # fmt: skip
        body = {"data": {"type": "instant", "selected_offers": [raw["id"]], "passengers": people,
                         "payments": [{"type": "balance", "amount": raw["amount"],
                                       "currency": raw["currency"]}]}}  # fmt: skip
        with self._client() as c:
            r = c.post("/air/orders", json=body)
        r.raise_for_status()
        order = r.json()["data"]
        return Booking(reference=order.get("booking_reference") or order["id"], provider=self.name)


class LiteApi:
    """Hotels in the LiteAPI (Nuitee Connect) sandbox: a free key with no card, real hotel names,
    and a booking paid with ACC_CREDIT_CARD, which the sandbox only simulates. Search = rates by IATA
    city code with the hotel data inline; book = prebook, then book."""

    name = "liteapi"

    def __init__(self, key: str, *, search_base: str = LITEAPI_SEARCH,
                 book_base: str = LITEAPI_BOOK,
                 transport: httpx.BaseTransport | None = None) -> None:  # fmt: skip
        self.key, self.search_base, self.book_base = key, search_base, book_base
        self.transport = transport

    def _client(self, base: str) -> httpx.Client:
        return httpx.Client(
            base_url=base, timeout=SANDBOX_TIMEOUT_S, transport=self.transport,
            headers={"X-API-Key": self.key, "Accept": "application/json"},
        )  # fmt: skip

    def hotels(self, city, check_in, check_out, adults) -> list[HotelOffer]:
        nights = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
        body = {"iataCode": city, "checkin": check_in, "checkout": check_out,
                "occupancies": [{"adults": adults}], "currency": "THB", "guestNationality": "TH",
                "limit": 20, "maxRatesPerHotel": 1, "includeHotelData": True, "timeout": 20}  # fmt: skip
        with self._client(self.search_base) as c:
            r = c.post("/hotels/rates", json=body)
        r.raise_for_status()
        j = r.json()
        if j.get("sandbox") is not True:
            raise RuntimeError("LiteAPI answered outside its sandbox; only the sandbox is allowed")
        info = {h.get("id"): h for h in j.get("hotels") or []}
        out = []
        for h in j.get("data") or []:
            rt = next((x for x in h.get("roomTypes") or [] if x.get("offerId")), None)
            price = (rt or {}).get("offerRetailRate")
            price = (price[0] if price else {}) if isinstance(price, list) else (price or {})
            if rt is None or "amount" not in price:
                continue
            rate = (rt.get("rates") or [{}])[0]
            pol = rate.get("cancellationPolicies") or {}
            until = ((pol.get("cancelPolicyInfos") or [{}])[0]).get("cancelTime", "")
            tag = pol.get("refundableTag", "")
            total = float(price["amount"])
            hotel = info.get(h["hotelId"], {})
            out.append(HotelOffer(
                provider=self.name, hotel_id=h["hotelId"], name=hotel.get("name") or h["hotelId"],
                area=hotel.get("address", ""), check_in=check_in, check_out=check_out, nights=nights,
                room=(rate.get("name") or rt.get("name") or "")[:80],
                price_per_night=round(total / max(nights, 1), 2), total=total,
                currency=price.get("currency", "THB"),
                cancellation=(f"free cancellation until {until}" if tag == "RFN" and until
                              else "non-refundable" if tag == "NRFN" else ""),
                raw={"offerId": rt["offerId"]},
            ))  # fmt: skip
        out.sort(key=lambda o: o.total)
        return out[:MAX_RESULTS]

    def book_hotel(self, offer, traveller) -> Booking:
        who = {"firstName": traveller["first"], "lastName": traveller["last"],
               "email": traveller["email"]}  # fmt: skip
        with self._client(self.book_base) as c:
            r = c.post(
                "/rates/prebook", json={"offerId": offer.raw["offerId"], "usePaymentSdk": False}
            )
            r.raise_for_status()
            r = c.post("/rates/book", json={
                "prebookId": r.json()["data"]["prebookId"], "holder": who,
                "guests": [{"occupancyNumber": 1, **who}], "payment": {"method": "ACC_CREDIT_CARD"},
            })  # fmt: skip
        r.raise_for_status()
        b = r.json()["data"]  # bookingId: the sandbox's hotel confirmation code is the word "test"
        return Booking(reference=b["bookingId"],
                       status=b.get("status") or "CONFIRMED", provider=self.name)  # fmt: skip


class Split:
    """Flights from one sandbox, hotels from another. A half without a key answers nothing, so
    `Fallback` serves the sample for it."""

    def __init__(self, flights: Any = None, hotels: Any = None) -> None:
        self.fl, self.ho = flights, hotels
        self.name = "+".join(p.name for p in (flights, hotels) if p is not None)

    def flights(self, *a) -> list[FlightOffer]:
        return self.fl.flights(*a) if self.fl is not None else []

    def hotels(self, *a) -> list[HotelOffer]:
        return self.ho.hotels(*a) if self.ho is not None else []

    def book_flight(self, offer, traveller) -> Booking:
        return self.fl.book_flight(offer, traveller)

    def book_hotel(self, offer, traveller) -> Booking:
        return self.ho.book_hotel(offer, traveller)


class Fallback:
    """Searches: the sandbox first, the sample on an exception, a timeout or an empty answer.
    Bookings go to whichever provider made the offer, and an error is reported as an error: a sample
    reference for a sandbox offer would be a fake confirmation."""

    def __init__(self, primary: Provider, sample: Provider | None = None) -> None:
        self.primary, self.sample = primary, sample or SampleProvider()
        self.name = primary.name

    def _try(self, what: str, call: Callable[[], Any], fallback: Callable[[], Any]) -> Any:
        try:
            res = call()
            if res:
                return res
            logger.warning("trips: %s %s empty, serving sample", self.primary.name, what)
        except Exception as e:  # noqa: BLE001 - any sandbox failure means "sample"
            logger.warning("trips: %s %s failed (%s), serving sample", self.primary.name, what,
                           type(e).__name__)  # fmt: skip
        return fallback()

    def flights(self, *a) -> list[FlightOffer]:
        return self._try(
            "flights", lambda: self.primary.flights(*a), lambda: self.sample.flights(*a)
        )

    def hotels(self, *a) -> list[HotelOffer]:
        return self._try("hotels", lambda: self.primary.hotels(*a), lambda: self.sample.hotels(*a))

    def book_flight(self, offer, traveller) -> Booking:
        p = self.sample if offer.provider == self.sample.name else self.primary
        return p.book_flight(offer, traveller)

    def book_hotel(self, offer, traveller) -> Booking:
        p = self.sample if offer.provider == self.sample.name else self.primary
        return p.book_hotel(offer, traveller)


def make_provider(settings) -> Provider:
    """Free sandboxes only: Duffel test mode for flights (`DORY_DUFFEL_TOKEN`, a `duffel_test_`
    token) and the LiteAPI sandbox for hotels (`DORY_LITEAPI_KEY`). A missing key or a live Duffel
    token = the sample for that half; `DORY_TRAVEL_PROVIDER=sample` = the sample for both."""
    if settings.travel_provider == "sample":
        return SampleProvider()
    token, key = (settings.duffel_token or "").strip(), (settings.liteapi_key or "").strip()
    if token and not token.startswith(DUFFEL_TEST_PREFIX):
        logger.warning("trips: DORY_DUFFEL_TOKEN is not a test-mode token; flights use the sample")
        token = ""
    if not (token or key):
        return SampleProvider()
    return Fallback(Split(Duffel(token) if token else None, LiteApi(key) if key else None))


# ----------------------------------------------------------------------------- offers across turns
class OfferCache:
    """Offers the model was shown, by short id, so a later message can book one (one process).
    An offer resolves only for the guild and person it was shown to: never across tenants."""

    def __init__(self, ttl_s: float = OFFER_TTL_S, clock: Callable[[], float] = time.monotonic):
        self.ttl, self.clock, self._n = ttl_s, clock, 0
        self._items: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def remember(self, offer: FlightOffer | HotelOffer, guild_id: int, asker_id: int) -> str:
        with self._lock:
            now = self.clock()
            self._items = {k: v for k, v in self._items.items() if v[1] > now}
            self._n += 1
            offer.offer_id = f"{'F' if isinstance(offer, FlightOffer) else 'H'}{self._n}"
            self._items[offer.offer_id] = (offer, now + self.ttl, guild_id, asker_id)
            return offer.offer_id

    def recall(
        self, offer_id: str, guild_id: int, asker_id: int
    ) -> FlightOffer | HotelOffer | None:
        with self._lock:
            hit = self._items.get((offer_id or "").strip().upper())
            if hit and hit[1] > self.clock() and hit[2:] == (guild_id, asker_id):
                return hit[0]
            return None


OFFERS = OfferCache()

# A plain "yes" to a quote: affirmative words plus polite fillers, nothing else.
_YES = re.compile(
    r"\s*(?:(yes|yeah|yep|ok(?:ay)?|sure|confirm(?:ed)?|go ahead|do it|book it|ใช่|ตกลง|ยืนยัน|"
    r"ได้เลย|เอาเลย|จอง|โอเค)|(please|dory|ดอรี่|i|ค่ะ|คะ|ครับ|นะ|เลย|จ้า))[\s,.!]*",
    re.I,
)


def is_confirmation(text: str | None) -> bool:
    """ "Yes, confirm.", "ok book it please", "ยืนยันค่ะ", "ใช่ จองเลย". Anything more ("yes but the
    cheaper hotel") is not: it goes to the model."""
    s, pos, core = (text or "").strip().lower(), 0, False
    if len(s) > 60:
        return False
    while pos < len(s):
        m = _YES.match(s, pos)
        if not m or m.end() == pos:
            return False
        core, pos = core or bool(m.group(1)), m.end()
    return core


# A wordier "go ahead and book both for the kickoff": a booking word, and nothing that makes the
# message a question, a refusal or a change ("what did I book", "not yet", "yes but the cheaper one").
_BOOK_CUE = re.compile(
    r"\b(?:yes|yeah|yep|ok(?:ay)?|sure|confirm(?:ed)?|go ahead|proceed|do it|book(?: it| them| both| "
    r"that| this| those| the)?)\b|ใช่|ตกลง|ยืนยัน|จอง|เอาเลย|ได้เลย|โอเค",
    re.I,
)
_NOT_BOOK = re.compile(
    r"\?|\b(?:no|not|don'?t|never|wait|hold|stop|cancel|but|instead|change|switch|what|which|when|"
    r"where|who|why|how|did|does|was|were|is it|are they)\b|ไม่|ยกเลิก|รอก่อน|แต่|เปลี่ยน|อะไร|ไหม|มั้ย|"
    r"หรือ|ยัง|กี่|เท่าไ|เมื่อไ|ที่ไหน|ใคร|ทำไม|ยังไง|อย่างไร",
    re.I,
)


def asks_to_book(text: str | None) -> bool:
    """The person's message asks to go ahead with the booking: a plain yes, or a booking request
    that is not a question, a refusal or a change. Only such a message may complete a booking."""
    s = (text or "").strip()
    if is_confirmation(s):
        return True
    return 0 < len(s) <= 300 and bool(_BOOK_CUE.search(s)) and not _NOT_BOOK.search(s)


class PendingQuotes:
    """The trip quote each person was shown last, so a plain yes in their very next message books it
    in code (`book_trip.on_confirm`): from text history alone the model once answered "Yes, confirm."
    with "Booked!" and booked nothing. One process; a quote waits as long as the confirm gate."""

    def __init__(self, ttl_s: float = CONFIRM_TTL_S, clock: Callable[[], float] = time.monotonic):
        self.ttl, self.clock = ttl_s, clock
        self._quotes: dict[tuple[int, int], tuple[dict, str, float]] = {}
        self._turns: dict[tuple[int, int], str] = {}
        self._lock = threading.Lock()

    def turn(self, guild_id: int, person_id: int, request_id: str) -> str:
        """Record this person's new request; returns their previous request id ("" = none)."""
        with self._lock:
            prev = self._turns.get((guild_id, person_id), "")
            self._turns[(guild_id, person_id)] = request_id
            return prev

    def put(self, guild_id: int, person_id: int, request_id: str, args: dict) -> None:
        with self._lock:
            self._quotes[(guild_id, person_id)] = (args, request_id, self.clock() + self.ttl)

    def take(self, guild_id: int, person_id: int, request_id: str) -> dict | None:
        """The quote shown in `request_id` (the person's previous request), consumed; else None."""
        with self._lock:
            hit = self._quotes.get((guild_id, person_id))
            if hit is None or hit[1] != request_id or hit[2] <= self.clock():
                return None
            del self._quotes[(guild_id, person_id)]
            return hit[0]


PENDING = PendingQuotes()


# ----------------------------------------------------------------------------- tools
@dataclass
class TripsCtx:
    guild_id: int
    asker_id: int
    asker_name: str
    is_exec: bool
    lang: str
    provider: Any
    docs: Any  # DocStore
    store: Any  # the receipt ledger
    state: Any  # SecretaryState (confirm gate)
    request_id: str
    now: Callable[[], datetime]
    reminders: Any = None  # ReminderBook
    approvals: Any = None  # ApprovalRepo
    offers: OfferCache = OFFERS
    pending: PendingQuotes = PENDING


def _view(offer: FlightOffer | HotelOffer) -> dict:
    return offer.model_dump(exclude={"raw", "provider"}, exclude_defaults=True)


def _item_key(offer: FlightOffer | HotelOffer) -> str:
    """The same flight or hotel whatever search found it: identity only (offer ids restart with the
    process, and a re-search may quote another price or seat count for the same flight)."""
    if isinstance(offer, FlightOffer):
        o = offer
        return fingerprint(
            "flight", o.flights, o.origin, o.destination, o.depart, o.return_depart, o.cabin
        )
    return fingerprint("hotel", offer.hotel_id, offer.check_in, offer.check_out)


def _bad_date(s: str, today: date, *, after: date | None = None) -> str | None:
    try:
        d = date.fromisoformat((s or "").strip())
    except ValueError:
        return "dates must be YYYY-MM-DD"
    if d < today:
        return f"{s} is in the past (today is {today.isoformat()})"
    if after is not None and d <= after:
        return f"{s} must be after {after.isoformat()}"
    return None


def traveller_for(ctx: TripsCtx) -> dict:
    """Name for the booking: the travel profile's `passport name LAST/FIRST` line, else the
    Discord name. Contact fields are placeholders for the sandbox."""
    first, last = (ctx.asker_name.split(" ", 1) + ["DORY"])[:2]
    prof = ctx.docs.get(PROFILE_KIND, ctx.guild_id, str(ctx.asker_id)) or {}
    m = re.search(r"passport name[:\s]+([A-Za-z]+)\s*/\s*([A-Za-z]+)", prof.get("text", ""), re.I)
    if m:
        last, first = m[1], m[2]
    return {"first": first.upper(), "last": last.upper(), "email": "traveller@example.com",
            "phone": "+66812345678"}  # fmt: skip


def trips_tools(ctx: TripsCtx) -> list:
    today = ctx.now().date()
    prev_request = ctx.pending.turn(ctx.guild_id, ctx.asker_id, ctx.request_id)
    # the person's own message this turn, recorded by `on_confirm` (qa.ask_async calls it before
    # the model on every path); None = unknown, which never completes a booking
    heard: dict[str, str | None] = {"text": None}

    def search_flights(origin: str, destination: str, depart_date: str, return_date: str = "",
                       adults: int = 1, cabin: str = "economy") -> dict:  # fmt: skip
        """Bookable flight offers (airline, flight numbers, local times, price). Use this, not
        flight_prices, when the person wants to BOOK or asks for options to choose from. Offers
        carry an offer_id for book_trip. Apply the company travel rules (cabin, caps) from the
        company notes and the person's travel profile; never invent a price or a time.

        Args:
            origin: IATA airport or city code, e.g. BKK.
            destination: IATA airport or city code, e.g. SIN, HKG, NRT.
            depart_date: YYYY-MM-DD.
            return_date: YYYY-MM-DD for a round trip, empty for one way.
            adults: number of adult passengers.
            cabin: economy, premium_economy, business or first.
        """
        o, d = origin.strip().upper(), destination.strip().upper()
        if not (_IATA.match(o) and _IATA.match(d)) or o == d:
            return {
                "status": "error",
                "error": "origin and destination must be different IATA codes",
            }
        cab = (cabin or "economy").strip().lower()
        if cab not in CABINS:
            return {"status": "error", "error": f"cabin must be one of {', '.join(CABINS)}"}
        if err := _bad_date(depart_date, today):
            return {"status": "error", "error": err}
        ret = (return_date or "").strip()
        if ret and (err := _bad_date(ret, today, after=date.fromisoformat(depart_date))):
            return {"status": "error", "error": err}
        try:
            offers = ctx.provider.flights(o, d, depart_date.strip(), ret, max(1, int(adults)), cab)
        except Exception as e:  # noqa: BLE001 - the model must hear "unavailable", not a trace
            logger.warning("trips: flights unavailable (%s)", type(e).__name__)
            return {"status": "unavailable", "reason": "flight search failed, try again later"}
        if not offers:
            return {"status": "none", "reason": f"no offers for {o}-{d} on {depart_date}"}
        for of in offers[:MAX_RESULTS]:
            ctx.offers.remember(of, ctx.guild_id, ctx.asker_id)
        return {"status": "ok", "source": offers[0].provider, "flights": [_view(x) for x in offers[:MAX_RESULTS]],
                "note": "sandbox prices (no real ticket is issued)"}  # fmt: skip

    def search_hotels(city: str, check_in: str, check_out: str, adults: int = 1) -> dict:
        """Hotel offers with an offer_id for book_trip. Compare the nightly price with the company's
        hotel cap for that city (company notes); say the cap and the difference when one is over it
        and offer the nearest in-policy one. Never invent a price.

        Args:
            city: IATA city code, e.g. SIN, HKG, TYO.
            check_in: YYYY-MM-DD.
            check_out: YYYY-MM-DD, after check_in.
            adults: guests in the room.
        """
        c = city.strip().upper()
        if not _IATA.match(c):
            return {"status": "error", "error": "city must be an IATA city code, e.g. SIN"}
        if err := _bad_date(check_in, today):
            return {"status": "error", "error": err}
        if err := _bad_date(check_out, today, after=date.fromisoformat(check_in)):
            return {"status": "error", "error": err}
        try:
            offers = ctx.provider.hotels(
                c, check_in.strip(), check_out.strip(), max(1, int(adults))
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("trips: hotels unavailable (%s)", type(e).__name__)
            return {"status": "unavailable", "reason": "hotel search failed, try again later"}
        if not offers:
            return {"status": "none", "reason": f"no hotel offers in {c} for those dates"}
        for of in offers[:MAX_RESULTS]:
            ctx.offers.remember(of, ctx.guild_id, ctx.asker_id)
        return {
            "status": "ok",
            "source": offers[0].provider,
            "hotels": [_view(x) for x in offers[:MAX_RESULTS]],
            "note": "sandbox prices (no real room is reserved, no money is charged)",
        }

    def book_trip(flight_offer_id: str = "", hotel_offer_id: str = "", purpose: str = "",
                  approval_id: str = "") -> dict:  # fmt: skip
        """Book a flight and/or a hotel from offer_ids shown by search_flights / search_hotels.
        Two steps: the first call returns needs_confirmation with the quote; read it back (items,
        totals, the meeting it is for) and ask the person to confirm; after they confirm in a LATER
        message call again with EXACTLY the same arguments. A choice outside the company rules (cabin,
        hotel cap) needs request_approval first; pass its id as approval_id only once it was approved
        (an unapproved id is refused here). On success the e-receipts are filed in the expense ledger
        under Travel and a check-in reminder is set.

        Args:
            flight_offer_id: offer_id of the chosen flight, or empty.
            hotel_offer_id: offer_id of the chosen hotel, or empty.
            purpose: what the trip is for, e.g. the meeting title.
            approval_id: the approved approval's id when the choice was out of policy.
        """
        fid, hid = (flight_offer_id or "").strip().upper(), (hotel_offer_id or "").strip().upper()
        if not fid and not hid:
            return {"status": "error", "error": "give a flight_offer_id and/or a hotel_offer_id"}
        flight = ctx.offers.recall(fid, ctx.guild_id, ctx.asker_id) if fid else None
        hotel = ctx.offers.recall(hid, ctx.guild_id, ctx.asker_id) if hid else None
        if (fid and not isinstance(flight, FlightOffer)) or (
            hid and not isinstance(hotel, HotelOffer)
        ):
            return {"status": "expired", "reason": "that offer is no longer held; search again"}
        # never the same flight or hotel twice for one person (by content: offer ids restart with the
        # process): a second "yes", a voice retry or a new search of the same offer gets the trip
        items = {k: _item_key(x) for k, x in (("flight", flight), ("hotel", hotel)) if x}
        keys = set(items.values())

        def mine(d: dict) -> bool:
            return d.get("user_id") == ctx.asker_id and bool(
                keys & set(d.get("items", {}).values())
            )

        if done := ctx.docs.find(TRIP_KIND, ctx.guild_id, mine):
            t0 = done[-1]
            booked = [k for k, v in items.items() if v in t0["items"].values()]
            return {"status": "already_booked", "trip_id": t0["id"], "already": booked,
                    "references": t0["references"], "totals": t0["totals"], "purpose": t0["purpose"],
                    "instruction": "Already booked: never book it again; give the references. Book "
                    "only what is new (call again without the already booked item)."}  # fmt: skip
        aid = (approval_id or "").strip()
        if aid:
            a = ctx.approvals.get(aid) if ctx.approvals is not None else None
            if a is None or a.guild_id != ctx.guild_id or a.requester_id != ctx.asker_id:
                return {"status": "refused", "reason": "approval_unknown"}
            if a.status != "approved":
                return {"status": "refused", "reason": f"approval_{a.status}",
                        "instruction": "Do not book. Tell the person the approval is not granted yet."}  # fmt: skip
        why = (purpose or "").strip()[:200]
        totals: dict[str, float] = {}
        for x in (flight, hotel):
            if x is not None:
                amt = x.price if isinstance(x, FlightOffer) else x.total
                totals[x.currency] = round(totals.get(x.currency, 0) + amt, 2)
        quote = {"flight": _view(flight) if flight else None, "hotel": _view(hotel) if hotel else None,
                 "totals": [{"amount": v, "currency": k} for k, v in totals.items()], "purpose": why}  # fmt: skip
        # what is confirmed: the items and the approval; the purpose is a label the model rewords
        # between turns ("Client kickoff" / "client kickoff" made a confirmed quote ask again)
        key = ("trip", ctx.guild_id, ctx.asker_id, fingerprint(fid, hid, aid))
        # Only a message that asks to book completes it: a question asked while a quote waits
        # ("what did I just book?") once made the model call book_trip again with the same args.
        wants = asks_to_book(heard["text"])
        if not wants:
            ctx.state.propose(key, ctx.request_id)
        if not (wants and ctx.state.confirm(key, ctx.request_id)):
            ctx.pending.put(ctx.guild_id, ctx.asker_id, ctx.request_id, {
                "flight_offer_id": fid, "hotel_offer_id": hid, "purpose": why, "approval_id": aid})  # fmt: skip
            return {"status": "needs_confirmation", "quote": quote, "instruction": (
                "Read the quote back (flight, hotel, totals, what it is for) and ask the person to "
                "confirm (English: “Shall I book it?”; Thai: “จองเลยไหมคะ”; in a voice room say it "
                "aloud), and say it is a sandbox quote: no real ticket or room, no money. Do NOT say it is "
                "booked. After they confirm in a later message call "
                "book_trip again with exactly the same arguments.")}  # fmt: skip
        traveller = traveller_for(ctx)
        refs: dict[str, str] = {}
        try:
            if flight is not None:
                refs["flight"] = ctx.provider.book_flight(flight, traveller).reference
            if hotel is not None:
                refs["hotel"] = ctx.provider.book_hotel(hotel, traveller).reference
        except Exception as e:  # noqa: BLE001
            logger.warning("trips: booking failed (%s)", type(e).__name__)
            return {"status": "failed", "error": "the booking service refused", "booked": refs}
        now = ctx.now()
        trip = {
            "id": f"T-{new_id()[:8]}", "guild_id": ctx.guild_id, "user_id": ctx.asker_id, "items": items,
            "user_name": ctx.asker_name, "purpose": why, "references": refs,
            "flight": quote["flight"], "hotel": quote["hotel"], "totals": quote["totals"],
            "provider": (flight or hotel).provider, "approval_id": aid,
            "depart_date": (flight.depart[:10] if flight else hotel.check_in),
            "return_date": (flight.return_depart[:10] if flight and flight.return_depart
                            else (hotel.check_out if hotel else "")),
            "destination": flight.destination if flight else hotel.name,
            "created_at": now.astimezone(UTC).isoformat(timespec="seconds"),
            "receipt_ids": [], "reminder_id": None,
        }  # fmt: skip
        trip["receipt_ids"] = _file_receipts(ctx, trip, flight, hotel, now)
        trip["reminder_id"] = _checkin_reminder(ctx, trip, flight, now)
        ctx.docs.put(TRIP_KIND, ctx.guild_id, trip["id"], trip)
        out = {"status": "booked", "trip_id": trip["id"], "references": refs,
               "totals": trip["totals"], "purpose": why, "filed_receipts": trip["receipt_ids"],
               "provider": trip["provider"]}  # fmt: skip
        if trip["reminder_id"]:
            out["checkin_reminder"] = trip["reminder_id"]
        return out

    def travel_profile(update: str = "", clear: bool = False) -> dict:
        """The person's travel preferences Dory applies without asking again: passport name as
        LAST/FIRST, seat, meal, loyalty programme, hotel wishes, departure times. Call with no
        arguments to read it; with `update` to replace it (keep what the person said, verbatim).

        Args:
            update: the new profile text, up to 600 characters; empty = read only.
            clear: true to delete the profile.
        """
        key = str(ctx.asker_id)
        if clear:
            ctx.docs.delete(PROFILE_KIND, ctx.guild_id, key)
            return {"status": "cleared"}
        text = (update or "").strip()
        if text:
            doc = {
                "text": text[:PROFILE_MAX],
                "updated_at": ctx.now().isoformat(timespec="seconds"),
            }
            ctx.docs.put(PROFILE_KIND, ctx.guild_id, key, doc)
            return {"status": "saved", "profile": doc["text"]}
        doc = ctx.docs.get(PROFILE_KIND, ctx.guild_id, key) or {}
        return {"status": "ok", "profile": doc.get("text", ""), "empty": not doc.get("text")}

    def list_trips(upcoming: bool = True) -> dict:
        """Trips booked through Dory in this company: who travels where, when and for what (so
        "who else is going?" can be answered). Amounts only for the person's own trips, or for
        executives.

        Args:
            upcoming: true = departure today or later; false = everything.
        """
        rows = ctx.docs.find(TRIP_KIND, ctx.guild_id)
        if upcoming:
            rows = [
                r
                for r in rows
                if (r.get("return_date") or r.get("depart_date", "")) >= today.isoformat()
            ]
        rows.sort(key=lambda r: r.get("depart_date", ""))
        out = []
        for r in rows[:20]:
            mine = r.get("user_id") == ctx.asker_id
            item = {k: r.get(k) for k in ("id", "user_name", "purpose", "destination", "depart_date",
                                           "return_date")}  # fmt: skip
            item["flights"] = (r.get("flight") or {}).get("flights")
            item["hotel"] = (r.get("hotel") or {}).get("name")
            if mine or ctx.is_exec:
                item["totals"], item["references"] = r.get("totals"), r.get("references")
            out.append(item)
        return {"status": "ok", "trips": out, "count": len(rows)}

    def on_confirm(question: str) -> str | None:
        """Called by `qa.ask_async` before the model: a plain yes right after a quote books it here
        and is answered from the stored trip. None = the model answers as usual."""
        heard["text"] = question
        if not is_confirmation(question):
            return None
        args = ctx.pending.take(ctx.guild_id, ctx.asker_id, prev_request)
        return _confirm_reply(ctx, book_trip(**args)) if args else None

    book_trip.on_confirm = on_confirm  # type: ignore[attr-defined]
    tools = [search_flights, search_hotels, book_trip, travel_profile, list_trips]
    for fn in tools:
        fn.dory_group = "travel"  # type: ignore[attr-defined]
    return tools


def _file_receipts(ctx: TripsCtx, trip: dict, flight: FlightOffer | None, hotel: HotelOffer | None,
                   now: datetime) -> list[int]:  # fmt: skip
    """One ledger receipt per booked item. A ledger failure never undoes the booking."""
    ids: list[int] = []
    items = (
        [("flight", flight.carrier_name or flight.carrier, flight.price, flight.currency)]
        if flight
        else []
    )
    if hotel:
        items.append(("hotel", hotel.name, hotel.total, hotel.currency))
    for what, vendor, total, currency in items:
        try:
            r = ctx.store.add_receipt(Receipt(
                guild_id=ctx.guild_id, submitter_id=ctx.asker_id, submitter_name=ctx.asker_name,
                sha256=hashlib.sha256(f"trip:{trip['id']}:{what}".encode()).hexdigest(),
                vendor=vendor, receipt_date=now.date().isoformat(),
                effective_date=now.date().isoformat(), currency=currency, total=total,
                category=TRAVEL_CATEGORY, confidence=1.0,
                notes=f"{trip['purpose'] or 'trip'} · ref {trip['references'].get(what, '')}",
                context="booked through Dory (trips)",
                created_at=now.astimezone(UTC).isoformat(timespec="seconds"),
            ))  # fmt: skip
            if r.id is not None:
                ids.append(r.id)
        except Exception as e:  # noqa: BLE001
            logger.warning("trips: receipt not filed (%s)", type(e).__name__)
    return ids


def _confirm_reply(ctx: TripsCtx, res: dict) -> str | None:
    """The answer to a plain yes, built from book_trip's result and the stored trip, never by the
    model. None (the model answers) when the quote could not be confirmed: expired, refused."""
    if res.get("status") == "failed":
        done = ", ".join(f"{k} {v}" for k, v in (res.get("booked") or {}).items())
        extra = t("trip_confirm_partial", ctx.lang, items=done) if done else ""
        return t("trip_confirm_failed", ctx.lang, partial=extra)
    if res.get("status") != "booked":
        return None
    trip = ctx.docs.get(TRIP_KIND, ctx.guild_id, res["trip_id"]) or {}
    refs, items = trip.get("references") or {}, []
    if fl := trip.get("flight"):
        items.append(t("trip_item_flight", ctx.lang, legs=" / ".join(fl.get("flights") or []),
                       carrier=fl.get("carrier_name") or fl.get("carrier", ""), ref=refs.get("flight", "")))  # fmt: skip
    if ho := trip.get("hotel"):
        items.append(
            t("trip_item_hotel", ctx.lang, name=ho.get("name", ""), ref=refs.get("hotel", ""))
        )
    totals = " + ".join(f"{x['amount']:,.2f} {x['currency']}" for x in trip.get("totals") or [])
    when = ""
    rem = ctx.reminders.get(ctx.guild_id, trip["reminder_id"]) if trip.get("reminder_id") else None
    if rem and rem.get("next_at"):
        at = datetime.fromisoformat(rem["next_at"]).astimezone(ctx.now().tzinfo)
        when = t("trip_confirm_reminder", ctx.lang, when=at.strftime("%Y-%m-%d %H:%M"))
    return t("trip_confirm_booked", ctx.lang, trip=res["trip_id"], items="; ".join(items),
             totals=totals, reminder=when)  # fmt: skip


def _checkin_reminder(
    ctx: TripsCtx, trip: dict, flight: FlightOffer | None, now: datetime
) -> str | None:
    """Online check-in reminder 24 h before the outbound departure, in the person's private channel."""
    if flight is None or ctx.reminders is None:
        return None
    try:
        dep = datetime.fromisoformat(flight.depart)
        if dep.tzinfo is None:
            dep = dep.replace(tzinfo=now.tzinfo)
        at = dep - timedelta(hours=24)
        if at <= now:
            return None
        rec = ctx.reminders.create(ctx.guild_id, {
            "user_id": ctx.asker_id, "set_by": ctx.asker_id, "set_by_name": ctx.asker_name,
            "message": t("trip_checkin_reminder", ctx.lang, flight=flight.flights[0],
                         dest=flight.destination, time=dep.strftime("%H:%M")),
            "kind": "once", "next_at": at.astimezone(UTC).isoformat(timespec="seconds"),
            "where": "me", "channel_id": None, "lang": ctx.lang,
            "created_at": now.astimezone(UTC).isoformat(timespec="seconds"),
            "fired": 0, "fails": 0, "active": True,
        })  # fmt: skip
        return rec["id"]
    except Exception as e:  # noqa: BLE001
        logger.warning("trips: reminder not set (%s)", type(e).__name__)
        return None


TRIPS_PROMPT = (
    "\nTrips (booking): when someone wants to book, or asks for flights or hotels to choose from, use "
    "search_flights / search_hotels (bookable sandbox offers with offer_ids), not flight_prices. "
    "Apply what you already know before asking anything: the meeting's date and place from the calendar, "
    "the travel profile (travel_profile: passport name, seat, meal, loyalty) and the company travel rules "
    "in the company notes. Present at most two or three options with the number that matters (price, "
    "time). If a choice breaks a rule (cabin, hotel cap), say the rule and the difference in one sentence, "
    "offer the in-policy option, and offer to ask the approver with request_approval; pass that approval's "
    "id to book_trip only after it was approved (book_trip refuses otherwise). book_trip is two-step: "
    "first read the quote back and ask “Shall I book it?”, book only after a yes in a later message, "
    "then say the references and that the receipts are filed. Never invent prices, times or references. "
    "“Who else is going” = list_trips plus the meeting attendees."
)

STRINGS = {
    "trip_checkin_reminder": {
        "th": "เช็กอินออนไลน์ได้แล้วค่ะ เที่ยวบิน {flight} ไป {dest} ออกพรุ่งนี้ {time}",
        "en": "Online check-in is open: flight {flight} to {dest} departs tomorrow at {time}",
    },
    "trip_confirm_booked": {
        "th": "จองเรียบร้อยแล้วค่ะ ทริป {trip}: {items} รวม {totals} บันทึกใบเสร็จในบัญชีค่าใช้จ่ายหมวด"
        "ค่าเดินทางแล้วค่ะ{reminder} การจองนี้อยู่ในระบบทดสอบ ไม่มีการออกตั๋วและไม่มีการตัดเงินจริงค่ะ",
        "en": "Booked! Trip {trip}: {items}. Total {totals}. The receipts are filed in the expense "
        "ledger under Travel.{reminder} This is a sandbox booking: no ticket is issued and no money "
        "is charged.",
    },
    "trip_confirm_reminder": {
        "th": " ดอรี่จะเตือนให้เช็กอินออนไลน์เวลา {when} ค่ะ",
        "en": " I'll remind you to check in online at {when}.",
    },
    "trip_item_flight": {
        "th": "เที่ยวบิน {legs} ({carrier}) รหัสจอง {ref}",
        "en": "flight {legs} ({carrier}), reference {ref}",
    },
    "trip_item_hotel": {
        "th": "โรงแรม {name} รหัสจอง {ref}",
        "en": "{name}, reference {ref}",
    },
    "trip_confirm_failed": {
        "th": "จองไม่สำเร็จค่ะ ระบบจองปฏิเสธ จึงยังไม่ได้บันทึกทริปหรือใบเสร็จใดๆ{partial}",
        "en": "I couldn't book it: the booking service refused, so no trip or receipt was filed."
        "{partial}",
    },
    "trip_confirm_partial": {
        "th": " ส่วนที่จองไปแล้วก่อนเกิดข้อผิดพลาด: {items}",
        "en": " Booked before the error: {items}.",
    },
}
CATALOG.update(STRINGS)
