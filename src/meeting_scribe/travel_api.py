"""Travel search API for the "Talk to Dory" chat cards (`static/center.html`).

A thin layer over `dory.travel_search`: validated bodies in, its JSON-ready dicts out. Sample data
only (THB, taxes included, nothing is booked); every answer, errors included, carries `data` =
`travel_search.DATA_STATUS`. `today` is the Bangkok date.

Public on purpose (anonymous demo; the cards' filters and Edit search must work without the AI).
What protects it: a token bucket per client IP and one for everyone, a cap on searches running at
once, bounded bodies (size, fields, lists, strings, page size) and ONE error shape:
`{"error": {"code", "message", "fields"?}, "data": DATA_STATUS}` with codes `invalid`,
`past_date`, `too_far` (422), `not_found` (404), `too_large` (413), `rate_limited` (429 +
Retry-After), `busy` (503 + Retry-After), `server_error` (500).
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import AsyncIterator
from datetime import date, datetime
from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from dory import travel_search as ts
from dory.coo_store import SQLiteDocStore
from meeting_scribe.config import get_settings
from meeting_scribe.limits import TokenBucket

logger = logging.getLogger(__name__)
BANGKOK = ZoneInfo("Asia/Bangkok")
MAX_BODY = 16_384  # bytes; the largest valid search is under 1 KB

MESSAGES = {
    "invalid": "Some fields are not valid.",
    "past_date": "That date has passed. Pick today or a later date.",
    "too_far": "That date is too far ahead for the sample data. Pick an earlier date.",
    "not_found": "That is not part of this search.",
    "too_large": "The request is too large.",
    "rate_limited": "Too many requests. Try again in a moment.",
    "busy": "The travel demo is busy. Try again in a moment.",
    "server_error": "Something went wrong. Try again in a moment.",
    # booking from the cards (/api/center/orgs/{org}/travel/book, signed in)
    "unauthorized": "Sign in again.",
    "license": "This company's licence is not active.",
    "forbidden": "You are not a member of this company.",
    "needs_discord": "Booking from the cards needs the company's Discord workspace (Dory's ledger).",
    "travel_off": "Travel is turned off for this company.",
}
_BY_STATUS = {401: "unauthorized", 402: "license", 403: "forbidden", 404: "not_found",
              413: "too_large", 422: "invalid", 429: "rate_limited", 503: "busy"}  # fmt: skip


def error(status: int, code: str, fields: list | None = None, headers=None) -> JSONResponse:
    err: dict = {"code": code, "message": MESSAGES[code]}
    if fields:
        err["fields"] = fields
    return JSONResponse({"error": err, "data": dict(ts.DATA_STATUS)}, status, headers=headers)


class _TravelRoute(APIRoute):
    """The one error shape, for this router's routes only (the rest of the app keeps FastAPI's)."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def run(request: Request):
            size = request.headers.get("content-length", "")
            if size.isdigit() and int(size) > MAX_BODY:
                return error(413, "too_large")
            try:
                return await handler(request)
            except RequestValidationError as e:
                fields = [
                    {"field": ".".join(map(str, x["loc"][1:])) or "body", "message": x["msg"]}
                    for x in e.errors()
                ]  # never the input itself
                return error(422, "invalid", fields)
            except HTTPException as e:
                known = isinstance(e.detail, str) and e.detail in MESSAGES
                code = e.detail if known else _BY_STATUS.get(e.status_code)
                return error(e.status_code, code or "server_error", headers=e.headers)
            except Exception:
                logger.exception("travel api failed")
                return error(500, "server_error")

        return run


class Limits:
    """A token bucket per client and one for everyone, plus a cap on searches running at once
    (a busy server says so at once instead of queueing)."""

    def __init__(self, per_min: int, burst: int, global_per_min: int, max_concurrent: int):
        # shortcut: the buckets live in this process (a public route must not write the shared
        # store per client IP); move them to it if the web service ever runs more than one instance
        self.docs = SQLiteDocStore(":memory:")
        self.client = TokenBucket(60 / per_min, burst, name="travel_client")
        everyone = max(1, global_per_min // 6)  # 10 s saved
        self.everyone = TokenBucket(60 / global_per_min, everyone, name="travel_everyone")
        self.slots = threading.BoundedSemaphore(max_concurrent)


@lru_cache
def get_limits() -> Limits:
    """From the web settings (`TRAVEL_*`); tests override it with their own."""
    s = get_settings()
    return Limits(
        s.travel_rate_per_min, s.travel_burst, s.travel_global_rate_per_min, s.travel_max_concurrent
    )


def client_ip(request: Request) -> str:
    """The caller's address. Cloud Run's front end APPENDS the address it saw to X-Forwarded-For,
    so the last entry is the real client; earlier ones are whatever the client sent (forgeable,
    which would dodge the per-client limit). No header (local run): the socket's address."""
    last = request.headers.get("x-forwarded-for", "").rsplit(",", 1)[-1].strip()
    return last or (request.client.host if request.client else "unknown")


async def guard(request: Request, limits: Limits = Depends(get_limits)) -> AsyncIterator[None]:
    for bucket, key in ((limits.client, client_ip(request)), (limits.everyone, "*")):
        if wait := bucket.take(limits.docs, key):
            retry = str(max(1, math.ceil(wait)))
            raise HTTPException(429, "rate_limited", headers={"Retry-After": retry})
    if not limits.slots.acquire(blocking=False):
        raise HTTPException(503, "busy", headers={"Retry-After": "1"})
    try:
        yield
    finally:
        limits.slots.release()


router = APIRouter(
    prefix="/api/travel", tags=["travel"], route_class=_TravelRoute, dependencies=[Depends(guard)]
)


def get_today() -> date:
    """The Bangkok date (overridden in tests)."""
    return datetime.now(BANGKOK).date()


# ----------------------------------------------------------------------------- bodies
# extra fields are refused everywhere, the shared models included
class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FlightQueryIn(ts.FlightQuery):
    model_config = ConfigDict(extra="forbid")


class HotelQueryIn(ts.HotelQuery):
    model_config = ConfigDict(extra="forbid")


class FlightFiltersIn(ts.FlightFilters):
    model_config = ConfigDict(extra="forbid")
    airlines: list[Annotated[str, StringConstraints(max_length=3)]] = Field(
        default_factory=list, max_length=len(ts.AIRLINES)
    )


class HotelFiltersIn(ts.HotelFilters):
    model_config = ConfigDict(extra="forbid")


class FlightSearch(_Body):
    query: FlightQueryIn
    filters: FlightFiltersIn = Field(default_factory=FlightFiltersIn)
    offset: int = Field(0, ge=0, le=1000)
    limit: int = Field(3, ge=1, le=ts.MAX_LIMIT)


class HotelSearch(_Body):
    query: HotelQueryIn
    filters: HotelFiltersIn = Field(default_factory=HotelFiltersIn)
    offset: int = Field(0, ge=0, le=1000)
    limit: int = Field(3, ge=1, le=ts.MAX_LIMIT)


class FareReview(_Body):
    query: FlightQueryIn
    id: str = Field(min_length=1, max_length=80)


class HotelRooms(_Body):
    query: HotelQueryIn
    hotel_id: str = Field(min_length=1, max_length=80)


class RoomReview(HotelRooms):
    room_id: str = Field(min_length=1, max_length=80)


def _dates_ok(today: date, *days: date) -> None:
    if code := ts.date_problem(today, *days):
        raise HTTPException(422, code)


def _found(got: dict | None) -> dict:
    if got is None:
        raise HTTPException(404, "not_found")
    return got


@router.get("/airports")
def airports() -> dict:
    """What the Edit search forms offer, and what the sample data covers."""
    return {
        "airports": [ts.place(c) for c in ts.AIRPORTS],
        "routes": [list(r) for r in sorted(ts.SAMPLE_ROUTES)],
        "hotel_cities": sorted(ts.HOTEL_CITIES),
        "data": dict(ts.DATA_STATUS),
    }


@router.post("/flights")
def flights(body: FlightSearch, today: date = Depends(get_today)) -> dict:
    _dates_ok(today, body.query.depart)
    return ts.search_flights(body.query, body.filters, body.offset, body.limit)


@router.post("/hotels")
def hotels(body: HotelSearch, today: date = Depends(get_today)) -> dict:
    _dates_ok(today, body.query.check_in, body.query.check_out)
    return ts.search_hotels(body.query, body.filters, body.offset, body.limit, today)


@router.post("/flights/review")
def flight_review(body: FareReview, today: date = Depends(get_today)) -> dict:
    _dates_ok(today, body.query.depart)
    return _found(ts.fare_review(body.query, body.id))


@router.post("/hotels/rooms")
def rooms(body: HotelRooms, today: date = Depends(get_today)) -> dict:
    _dates_ok(today, body.query.check_in, body.query.check_out)
    return _found(ts.hotel_rooms(body.query, body.hotel_id, today))


@router.post("/hotels/review")
def room_review(body: RoomReview, today: date = Depends(get_today)) -> dict:
    _dates_ok(today, body.query.check_in, body.query.check_out)
    return _found(ts.room_review(body.query, body.hotel_id, body.room_id, today))


@router.api_route("/{rest:path}", methods=["GET", "POST"], include_in_schema=False)
def unknown(rest: str) -> None:
    """Anything else under /api/travel answers in the same shape (registered last)."""
    raise HTTPException(404, "not_found")


# ----------------------------------------------------------------------------- chat fallback
_TH_MONTHS = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")  # fmt: skip
FALLBACK = {
    "en": "I couldn't interpret this with Dory's AI just now, so this search uses what I could "
    "read from your message: {what}. Use Edit search to change it.",
    "th": "ตอนนี้ดอรี่ใช้ AI ตีความข้อความนี้ไม่ได้ จึงค้นหาจากสิ่งที่อ่านได้ในข้อความของคุณ: {what} "
    "กด “แก้ไขการค้นหา” เพื่อเปลี่ยนได้ค่ะ",
}


def _city(code: str) -> str:
    return f"{ts.place(code)['city']} ({code})"


def fallback_reply(req: ts.TripRequest, lang: str) -> tuple[str, dict]:
    """The chat's answer when Dory's brain failed but `travel_search.parse_request` read a trip
    from the message: one line in the company language (Thai or English) saying the search was
    read without the AI, and the `travel` payload (default filters) the page draws as cards."""
    th = lang == "th"
    what, cards = [], []
    if f := req.flight:
        d = f.depart
        what.append(
            f"เที่ยวบิน {_city(f.origin)} → {_city(f.destination)} วันที่ {d.day} "
            f"{_TH_MONTHS[d.month - 1]} ผู้โดยสาร {f.adults} คน"
            if th
            else f"flights {_city(f.origin)} to {_city(f.destination)} on {d:%a} {d.day} {d:%b}, "
            f"{f.adults} traveller{'s' if f.adults > 1 else ''}"
        )
        cards.append({"kind": "flights", "query": f.model_dump(mode="json"),
                      "filters": ts.FlightFilters().model_dump(mode="json")})  # fmt: skip
    if h := req.hotel:
        d = h.check_in
        what.append(
            f"โรงแรมใน {_city(h.city)} {h.nights} คืน เช็กอิน {d.day} {_TH_MONTHS[d.month - 1]}"
            if th
            else f"a hotel in {_city(h.city)} for {h.nights} night{'s' if h.nights > 1 else ''} "
            f"from {d:%a} {d.day} {d:%b}"
        )
        cards.append({"kind": "hotels", "query": h.model_dump(mode="json"),
                      "filters": ts.HotelFilters().model_dump(mode="json")})  # fmt: skip
    text = FALLBACK["th" if th else "en"].format(what=("; " if not th else " และ").join(what))
    return text, ts.travel_payload(cards)
