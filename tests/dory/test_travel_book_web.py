"""Booking straight from the website's travel cards (`POST /api/center/orgs/{org}/travel/book`):
no AI; the quote is priced from the catalogue without touching book_trip's confirm gate, and the
confirm books (sandbox) only a quote this person was shown, through the headless bot's own
book_trip (trip record, THB receipts in its ledger, a check-in reminder)."""

from datetime import date, datetime
from uuid import uuid4

import pytest
from test_center_api import H, docs, w  # noqa: F401  (the command center fixtures)

from dory import travel_search, trips
from dory.config import Settings as DorySettings
from meeting_scribe import center, travel_api

URL = "/api/center/orgs/org_t/travel/book"
OUT = "BKKSIN.SL106-20261103-E.2"
BACK = "SINBKK.SL107-20261106-E.2"
ROOM = "SIN.harbourlight.deluxe-king.20261103.3.1.2"


@pytest.fixture
def bot(w, monkeypatch):  # noqa: F811
    monkeypatch.setattr(travel_api, "get_today", lambda: date(2026, 10, 27))
    monkeypatch.setattr(
        DorySettings, "now", lambda self: datetime(2026, 10, 27, 9, tzinfo=self.zone)
    )
    monkeypatch.setattr(center, "_card_quotes", {})
    # the headless bot (and its store) outlives the test: a fresh trip kind per test, or book_trip
    # would answer already_booked for a trip an earlier test made
    monkeypatch.setattr(trips, "TRIP_KIND", f"dory_trips_{uuid4().hex[:8]}")
    bot = center.get_bot()  # one headless bot per process: count only this test's trips
    w.trips_before = {t["id"] for t in _all_trips(w, bot)}
    return bot


def book(w, who="mem", status=200, **body):  # noqa: F811
    r = w.client.post(URL, json=body, headers=H[who])
    assert r.status_code == status, r.text
    return r.json()


def _all_trips(w, bot):  # noqa: F811
    ws = center.company_workspace(w.orgs.get(w.org.id))
    return [t for t in bot.docs.find(trips.TRIP_KIND, ws.memory_id) if t.get("references")]


def my_trips(w, bot):  # noqa: F811
    return [t for t in _all_trips(w, bot) if t["id"] not in w.trips_before]


def test_quote_then_confirm_books_one_trip_with_receipts(w, bot):  # noqa: F811
    q = book(w, flight_ref=OUT, return_ref=BACK, room_ref=ROOM, purpose="Lumen kickoff")
    assert q["status"] == "needs_confirmation" and q["data"]["bookable"] is False
    quote = q["quote"]
    assert (
        quote["flight"]["flights"] == ["SL106", "SL107"] and quote["hotel"]["room"] == "Deluxe King"
    )
    assert quote["totals"] == [{"amount": 6380 + 6180 + 25350, "currency": "THB"}]
    again = book(w, flight_ref=OUT, return_ref=BACK, room_ref=ROOM, purpose="Lumen kickoff")
    assert again["status"] == "needs_confirmation" and not my_trips(
        w, bot
    )  # asking twice never books
    done = book(w, flight_ref=OUT, return_ref=BACK, room_ref=ROOM, purpose="Lumen kickoff",
                confirm=True)  # fmt: skip
    assert done["status"] == "booked" and set(done["references"]) == {"flight", "hotel"}
    assert done["totals"] == quote["totals"] and done["checkin_reminder"]
    assert "sandbox booking" in done["text"] and done["references"]["flight"] in done["text"]
    (trip,) = my_trips(w, bot)  # flight out + way back + room = ONE trip
    assert trip["purpose"] == "Lumen kickoff" and trip["return_date"] == "2026-11-06"
    receipts = [bot.store.get(i) for i in trip["receipt_ids"]]
    assert sorted(r.total for r in receipts) == [6380 + 6180, 25350]
    assert all(r.currency == "THB" and r.category == "ค่าเดินทาง" for r in receipts)
    hist = w.client.get("/api/center/orgs/org_t/chat/history", headers=H["mem"]).json()["turns"]
    assert hist[-1]["role"] == "dory" and hist[-1]["text"] == done["text"]  # a reload shows it
    # the quote was used up: confirming it again books nothing more
    assert book(w, flight_ref=OUT, return_ref=BACK, room_ref=ROOM, purpose="Lumen kickoff",
                confirm=True)["status"] == "needs_confirmation"  # fmt: skip
    assert len(my_trips(w, bot)) == 1


def test_confirm_without_a_quote_shown_asks_again(w, bot):  # noqa: F811
    r = book(w, room_ref=ROOM, confirm=True)
    assert r["status"] == "needs_confirmation" and r["quote"]["hotel"]["name"]
    assert not my_trips(w, bot)
    book(w, room_ref=ROOM, purpose="offsite")  # a different purpose is a different quote
    assert book(w, room_ref=ROOM, confirm=True)["status"] == "needs_confirmation"


def test_another_member_cannot_confirm_my_quote(w, bot):  # noqa: F811
    book(w, flight_ref=OUT)
    theirs = book(w, who="adm", flight_ref=OUT, confirm=True)
    assert theirs["status"] == "needs_confirmation" and not my_trips(w, bot)
    assert book(w, flight_ref=OUT, confirm=True)["status"] == "booked"  # mine still is


def test_bad_refs_and_bodies(w, bot):  # noqa: F811
    assert book(w, flight_ref="BKKSIN.XX1-20261103-E.2")["status"] == "expired"
    assert book(w, room_ref="SIN.harbourlight.deluxe-king.20261001.3.1.2")["status"] == "expired"
    err = book(w, status=422)  # nothing picked
    assert err["error"]["code"] == "invalid" and err["data"]["source"] == "sample"
    assert book(w, status=422, return_ref=BACK)["error"]["code"] == "invalid"  # a way back alone
    assert book(w, status=422, flight_ref="x" * 81)["error"]["code"] == "invalid"
    assert book(w, status=422, flight_ref=OUT, extra=1)["error"]["code"] == "invalid"


def test_a_web_only_company_books_from_the_cards_too(w, bot):  # noqa: F811
    """A company with no Discord server (signed up on the website) books a hotel in the sandbox:
    the trip and its receipt go to its web workspace's ledger; no check-in reminder is promised
    (nothing could deliver it to a web-only person)."""
    url = "/api/center/orgs/org_o/travel/book"
    web = w.orgs.get("org_o").web_workspace()
    before = {t["id"] for t in bot.docs.find(trips.TRIP_KIND, web.memory_id)}
    q = w.client.post(url, json={"room_ref": ROOM, "purpose": "web offsite"}, headers=H["other"])
    assert q.status_code == 200, q.text
    assert q.json()["status"] == "needs_confirmation" and q.json()["quote"]["hotel"]["room"]
    done = w.client.post(url, json={"room_ref": ROOM, "purpose": "web offsite", "confirm": True},
                         headers=H["other"]).json()  # fmt: skip
    assert done["status"] == "booked" and done["references"]["hotel"]
    assert "remind" not in done["text"].lower()  # no reminder to promise on the web alone
    (trip,) = [t for t in bot.docs.find(trips.TRIP_KIND, web.memory_id) if t["id"] not in before]
    assert trip["purpose"] == "web offsite" and not trip.get("reminder_id")
    assert [bot.store.get(i).total for i in trip["receipt_ids"]] == [25350]
    flight = w.client.post(
        url, json={"flight_ref": OUT, "confirm": True}, headers=H["other"]
    ).json()
    assert flight["status"] == "needs_confirmation"  # a flight books the same way (quote first)


def test_who_may_book(w, bot, monkeypatch):  # noqa: F811
    r = w.client.post(URL, json={"flight_ref": OUT}, headers=H["stranger"])
    assert r.status_code in (403, 404) and r.json()["error"]["code"] in ("forbidden", "not_found")
    assert w.client.post(URL, json={"flight_ref": OUT}).status_code == 401
    monkeypatch.setattr(center, "get_bot", lambda: None)  # a web-only company: no ledger to book in
    err = book(w, status=409, flight_ref=OUT)
    assert err["error"]["code"] == "booking_unavailable" and err["error"]["message"]


def test_travel_turned_off_is_409(w, bot, monkeypatch):  # noqa: F811
    monkeypatch.setattr(type(bot), "_travel_tools", lambda self, *a, **k: [])
    assert book(w, status=409, flight_ref=OUT)["error"]["code"] == "travel_off"


def test_the_quote_is_book_trips_own_pricing(w, bot):  # noqa: F811
    """card_quote and book_trip agree on the totals (both price from the catalogue)."""
    q = book(w, flight_ref=OUT, room_ref=ROOM)["quote"]
    want = (travel_search.by_booking_ref(OUT, date(2026, 10, 27))["flight"]["price"]["total"]
            + travel_search.by_booking_ref(ROOM, date(2026, 10, 27))["room"]["price"]["total"])  # fmt: skip
    assert q["totals"] == [{"amount": want, "currency": "THB"}]
    done = book(w, flight_ref=OUT, room_ref=ROOM, confirm=True)
    assert done["totals"] == q["totals"]
