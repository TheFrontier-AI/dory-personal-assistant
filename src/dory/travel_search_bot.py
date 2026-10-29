"""Discord half of the "Talk to Dory" flight + hotel search: `/dory flights`, `/dory hotels`, and
the same cards posted under a typed chat answer when Dory's brain searched.

The data and the search, filter and price logic are `travel_search.py` (shared with the web cards);
this module only words its JSON-ready results for Discord and keeps each person's search in
`travel_search.Sessions` (owner `discord:<user id>`, process memory, 30 minutes from the last use).

Chat and voice: `_travel_card_tools` adds `travel_search.card_tools`, THE flight and hotel search
(validated, owner-bound), whose results carry the booking_ref trips.py's `book_trip` books in the
sandbox; after a typed reply `_post_travel_cards` turns the searches the brain ran into one results
message per search, voice speaks them. The slash commands, buttons and menus never need the brain.

Wording: every string is ONE catalog message (`discord.*` keys in `i18n.CATALOG`) with named
placeholders. Counts ("3 nights", `count`) are standalone messages used only as an item of a "·"
list or a factor of a "×" formula; a sentence whose grammar follows a number has its own singular
message. Dates are whole-date messages filled from weekday / month names (`day`).

Layout: Components V2 (`ui.LayoutView`): a heading, one accent-coloured Container per result with
its own action row, then pagination and the filter menus. Every component is a `DynamicItem`
whose custom id is `dory:trv:<act>:<session id>[:<arg>]`, so a click after a restart, after the
TTL or by somebody else gets one friendly line instead of "This interaction failed". Every view is
`LayoutView(timeout=None)`: when a view times out discord.py drops the DynamicItem templates it
registered, which would silence every other search's buttons (`ViewStore.remove_view`).

Discord limits relied on (checked 2026-10-29; https://discord.com/developers/docs/components/reference,
https://discord.com/developers/docs/interactions/receiving-and-responding, discord.py 2.7.1
`LayoutView.content_length`): 40 components per V2 message (nested ones count), 4000 characters of
text displays, 5 buttons or 1 select per action row, 25 select options (max_values <= 25),
custom_id <= 100, button label <= 80, option label / value / description <= 100, placeholder
<= 150, modal title and text input label <= 45, text input placeholder <= 100, at most 5 inputs per
modal, a first response within 3 s (hence the immediate defer), V2 messages carry no `content`.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import math
from datetime import date, datetime, timedelta

import discord
from discord import app_commands, ui
from pydantic import ValidationError

from .i18n import t
from .travel_search import (
    AIRPORTS,
    MAX_DAYS_AHEAD,
    MAX_NIGHTS,
    CardCtx,
    FlightFilters,
    FlightQuery,
    HotelFilters,
    HotelQuery,
    Session,
    Sessions,
    Trips,
    by_booking_ref,
    card_tools,
    date_problem,
    fare_review,
    hotel_rooms,
    next_week_tuesday,
    parse_request,
    room_review,
    search_flights,
    search_hotels,
    tool_cards,
)

logger = logging.getLogger(__name__)

PAGE = 3  # results per message: 3 cards keep the page well under 40 components / 4000 characters
PREFIX = "dory:trv"
ACCENT = discord.Colour(0x4A4FBF)  # Dory indigo: result cards
ACCENT_DEEP = discord.Colour(0x2B2F7A)  # the fare / stay review
PRICE_STEPS = (2000, 2500, 3000, 4000, 5000, 7500, 10000, 15000, 20000, 30000)
TIMES = ("morning", "afternoon", "evening")
HOTEL_ACTS = {"ho", "hf", "hs", "hp", "rm"}
FLIGHT_ACTS = {"fl", "ff", "fa", "fs", "fp"}

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
TAGS = {
    "best_value": "discord.tag.bestValue",
    "cheapest": "discord.tag.cheapest",
    "fastest": "discord.tag.fastest",
    "popular": "discord.tag.popular",
    "top_rated": "discord.tag.topRated",
}
SORTS = {
    "best": "discord.tag.bestValue",
    "cheapest": "discord.tag.cheapest",
    "fastest": "discord.tag.fastest",
    "earliest": "discord.sort.earliest",
    "recommended": "discord.sort.recommended",
    "price": "discord.sort.lowestPrice",
    "rating": "discord.tag.topRated",
}
FLIGHT_FILTERS = {
    "nonstop": "discord.flight.nonstop",
    "1stop": "discord.flight.oneStop",
    "morning": "discord.flight.morning",
    "afternoon": "discord.flight.afternoon",
    "evening": "discord.flight.evening",
}
HOTEL_FILTERS = {
    "free_cancellation": "discord.hotel.freeCancellation",
    "breakfast": "discord.hotel.breakfastIncluded",
    "stars4": "discord.hotel.fourStarsPlus",
    "score8": "discord.hotel.guestScore8Plus",
}
AMENITIES = ("wifi", "pool", "gym", "spa", "restaurant", "breakfast", "terrace", "beach", "shuttle",
             "bar")  # fmt: skip
# query field -> its name in the error messages ("Date" is the existing `pdf_date`, same meaning)
FIELDS = {
    "origin": "discord.field.origin",
    "destination": "discord.field.destination",
    "depart": "pdf_date",
    "adults": "discord.field.travellers",
    "cabin": "discord.field.cabin",
    "city": "discord.field.city",
    "check_in": "discord.field.checkIn",
    "check_out": "discord.field.checkOut",
    "nights": "discord.field.nights",
    "rooms": "discord.field.rooms",
    "guests": "discord.field.guests",
}
FORM = {
    "origin": "discord.form.origin",
    "destination": "discord.form.destination",
    "depart": "discord.form.depart",
    "adults": "discord.form.adults",
    "cabin": "discord.form.cabin",
    "city": "discord.form.city",
    "check_in": "discord.form.checkIn",
    "nights": "discord.form.nights",
    "rooms": "discord.form.rooms",
    "guests": "discord.form.guests",
}


# ----------------------------------------------------------------------------- wording
def num(n: int) -> str:
    return f"{n:,}"


def count(kind: str, n: int, lang: str) -> str:
    """A standalone count phrase ("3 nights"): an item of a "·" list or a factor of a "×"."""
    return t(f"discord.count.{kind}" + ("One" if n == 1 else ""), lang, count=n)


def duration(minutes: int, lang: str) -> str:
    return t("discord.time.duration", lang, hours=minutes // 60, minutes=minutes % 60)


def day(d: date | str, lang: str, year: bool = False) -> str:
    """`Tue 3 Nov` (`Tue 3 Nov 2026`); dates of an ISO date-time are read as local."""
    d = date.fromisoformat(d[:10]) if isinstance(d, str) else d
    return t(
        "discord.date.dayMonthYear" if year else "discord.date.dayMonth",
        lang,
        weekday=t(f"discord.weekday.{WEEKDAYS[d.weekday()]}", lang),
        day=d.day,
        month=t(f"discord.month.{MONTHS[d.month - 1]}", lang),
        year=d.year,
    )


def cabin(code: str, lang: str) -> str:
    return t(f"discord.cabin.{code}", lang)


def place(p: dict) -> str:
    return f"{p['city']} ({p['code']})"


def cancel_text(cancellation: dict, lang: str) -> str:
    if cancellation["free"]:
        return t("discord.hotel.freeCancellationUntil", lang, date=day(cancellation["until"], lang))
    return t("discord.hotel.nonRefundable", lang)


def _tags(tags: list[str], lang: str) -> str:
    return " ".join(f"`{t(TAGS[x], lang)}`" for x in tags if x in TAGS)


def _stay_line(q: dict, lang: str) -> str:
    return " · ".join(
        (
            f"{day(q['check_in'], lang)} → {day(q['check_out'], lang, year=True)}",
            count("nights", q["nights"], lang),
            count("rooms", q["rooms"], lang),
            count("guests", q["guests"], lang),
        )
    )


def _bags(bag: dict, lang: str) -> str:
    if bag["checked_kg"]:
        return t(
            "discord.flight.bags", lang, cabin_kg=bag["cabin_kg"], checked_kg=bag["checked_kg"]
        )
    return t("discord.flight.bagsNoChecked", lang, cabin_kg=bag["cabin_kg"])


def flight_card(o: dict, lang: str) -> str:
    plus = o["arrive_day_offset"]
    times = (
        f"**{o['origin']['code']} {o['depart'][11:16]} → "
        f"{o['destination']['code']} {o['arrive'][11:16]}**"
    )
    if plus:
        times += " " + t("discord.flight.nextDay" + ("One" if plus == 1 else ""), lang, days=plus)
    days = day(o["depart"], lang) + (f" → {day(o['arrive'], lang)}" if plus else "")
    # shortcut: the sample data has at most one stop; a 2-stop offer lists each via the same way
    stops = " · ".join(
        t(
            "discord.flight.oneStopVia",
            lang,
            place=place(v),
            layover=duration(v["layover_min"], lang),
        )
        for v in o["via"]
    ) or t("discord.flight.nonstop", lang)
    p = o["price"]
    if p["travellers"] == 1:
        price = t("discord.flight.priceTotalOne", lang, total=num(p["total"]))
    else:
        price = t(
            "discord.flight.priceTotal",
            lang,
            total=num(p["total"]),
            count=p["travellers"],
            each=num(p["per_traveller"]),
        )
    lines = [
        f"### {o['airline']['name']} · {' + '.join(o['flights'])}",
        _tags(o["tags"], lang),
        times,
        f"{o['origin']['airport']} → {o['destination']['airport']} · {days}",
        f"{duration(o['duration_min'], lang)} · {stops}",
        _bags(o["baggage"], lang),
        price,
        f"-# {t('discord.flight.sampleNote', lang)}",
    ]
    return "\n".join(x for x in lines if x)


def _amenities(codes: list[str], lang: str) -> str:
    return " · ".join(
        t(f"discord.amenity.{c}", lang) if c in AMENITIES else c.title() for c in codes[:4]
    )


def _rating(h: dict, lang: str) -> tuple[str, str]:
    stars = t("discord.hotel.stars", lang, stars="★" * h["stars"], count=h["stars"])
    r = h["review"]
    # shortcut: one plural form; the sample hotels all have hundreds of reviews (a real provider
    # with a 1-review property would need a guestScoreOne message)
    score = t("discord.hotel.guestScore", lang, score=r["score"], count=num(r["count"]))
    return stars, score


def _nightly(p: dict, lang: str) -> str:
    return t("discord.hotel.nightlyPrice", lang, price=num(p["nightly"]))


def _room_price(p: dict, lang: str) -> str:
    total = t(
        "discord.hotel.stayTotal",
        lang,
        total=num(p["total"]),
        nights=count("nights", p["nights"], lang),
        rooms=count("rooms", p["rooms"], lang),
    )
    return f"**{_nightly(p, lang)}**\n{total}"


def hotel_card(h: dict, lang: str) -> str:
    stars, score = _rating(h, lang)
    lines = [
        f"### {h['name']}",
        f"-# {t('discord.hotel.sampleNote', lang)}",
        _tags(h["tags"], lang),
        f"{h['area']}, {h['city']}",
        stars,
        score,
        _amenities(h["amenities"], lang),
        t("discord.hotel.cheapestRoom", lang, room=h["room"]["name"]),
        cancel_text(h["cancellation"], lang),
        _stay_line(h, lang),
        _room_price(h["price"], lang),
        f"-# {t('discord.search.samplePrice', lang)}",
    ]
    return "\n".join(x for x in lines if x)


def _room_details(r: dict, lang: str) -> str:
    return t(
        "discord.hotel.roomDetails", lang, beds=r["beds"], size=r["size_m2"], sleeps=r["max_guests"]
    )


def _meal(r: dict, lang: str) -> str:
    return t(
        "discord.hotel.breakfastIncluded" if r["breakfast"] else "discord.hotel.roomOnly", lang
    )


def room_card(r: dict, lang: str) -> str:
    return "\n".join(
        (
            f"### {r['name']}",
            _room_details(r, lang),
            f"{_meal(r, lang)} · {cancel_text(r['cancellation'], lang)}",
            _room_price(r["price"], lang),
            f"-# {t('discord.search.samplePrice', lang)}",
        )
    )


def _no_rooms(guests: int, rooms: int, lang: str) -> str:
    # no room fits only when more than 4 guests share a room, so `guests` is always plural
    if rooms == 1:
        return t("discord.hotel.noRoomsOneRoom", lang, guests=guests)
    return t("discord.hotel.noRooms", lang, guests=guests, rooms=rooms)


# ----------------------------------------------------------------------------- components
class TravelButton(
    ui.DynamicItem[ui.Button],
    template=PREFIX
    + r":(?P<act>pg|ed|fl|bk|ho|cl|bq|bc|bx):(?P<sid>[0-9a-f]{4,32})(?::(?P<arg>[A-Za-z0-9_-]{1,60}))?",
):
    """Page, edit, select flight, back, view rooms, clear filters, and booking: Book in sandbox (the
    quote), Confirm booking, Cancel. Arg = offset / flight / hotel."""

    def __init__(
        self,
        act: str,
        sid: str,
        arg: str = "",
        label: str = "",
        *,
        style=discord.ButtonStyle.secondary,
        disabled: bool = False,
    ) -> None:
        cid = f"{PREFIX}:{act}:{sid}" + (f":{arg}" if arg else "")
        super().__init__(
            ui.Button(label=(label or act)[:80], style=style, custom_id=cid, disabled=disabled)
        )
        self.act, self.sid, self.arg = act, sid, arg

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(match["act"], match["sid"], match["arg"] or "", getattr(item, "label", "") or "")

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.client.handle_travel_click(interaction, self.act, self.sid, self.arg)


class TravelSelect(
    ui.DynamicItem[ui.Select],
    template=PREFIX
    + r":(?P<act>ff|fa|fs|fp|hf|hs|hp|rm|bw):(?P<sid>[0-9a-f]{4,32})(?::(?P<arg>[A-Za-z0-9_-]{1,60}))?",
):
    """Filter / sort / max price menus, the room menu (arg = hotel id) and "What to book"."""

    def __init__(
        self,
        act: str,
        sid: str,
        options: list[discord.SelectOption],
        placeholder: str,
        *,
        arg: str = "",
        multi: bool = False,
    ) -> None:
        cid = f"{PREFIX}:{act}:{sid}" + (f":{arg}" if arg else "")
        options = options[:25] or [discord.SelectOption(label="-", value="-")]
        # required=False: `required` is for modals and ignored in messages; it keeps min_values=0
        # clear of the "at least 1 when required" rule
        super().__init__(
            ui.Select(
                custom_id=cid,
                placeholder=placeholder[:150],
                options=options,
                required=False,
                min_values=0 if multi else 1,
                max_values=len(options) if multi else 1,
            )
        )
        self.act, self.sid, self.arg = act, sid, arg

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        made = cls(
            match["act"],
            match["sid"],
            list(getattr(item, "options", [])),
            "",
            arg=match["arg"] or "",
        )
        return made

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.client.handle_travel_click(
            interaction, self.act, self.sid, self.arg, list(self.item.values)
        )


def _option(label: str, value: str, default: bool = False, description: str | None = None):
    return discord.SelectOption(
        label=label[:100],
        value=value[:100],
        default=default,
        description=description[:100] if description else None,
    )


def _price_menu(act: str, s: Session, rng: dict | None, current: int | None, kind: str, lang: str):
    """Max price menu; a closed menu shows the chosen option, so every option names the menu."""
    caps = [v for v in PRICE_STEPS if rng and rng["min"] <= v < rng["max"]]
    if current is not None and current not in caps:
        caps = sorted({*caps, current})
    opts = [_option(t(f"discord.{kind}.maxPriceAny", lang), "any", current is None)]
    opts += [
        _option(t(f"discord.{kind}.maxPriceUpTo", lang, price=num(v)), str(v), v == current)
        for v in caps[:24]
    ]
    return ui.ActionRow(TravelSelect(act, s.sid, opts, t(f"discord.{kind}.maxPriceMenu", lang)))


def _sort_menu(act: str, s: Session, sorts: tuple[str, ...], lang: str):
    opts = [
        _option(
            t("discord.search.sortOption", lang, sort=t(SORTS[k], lang)), k, k == s.filters.sort
        )
        for k in sorts
    ]
    return ui.ActionRow(TravelSelect(act, s.sid, opts, t("discord.search.sortMenu", lang)))


def _filtered(s: Session) -> bool:
    """Any filter other than the sort order."""
    default = type(s.filters)().model_dump(exclude={"sort"})
    return s.filters.model_dump(exclude={"sort"}) != default


def _view(*items) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)  # never times out: see the module docstring
    for item in items:
        if item is not None:
            view.add_item(item)
    return view


def _btn(act: str, s: Session, label: str, arg: str = "", **kw) -> TravelButton:
    return TravelButton(act, s.sid, arg, label, **kw)


# ----------------------------------------------------------------------------- views (pure)
def results_view(res: dict, s: Session, lang: str) -> ui.LayoutView:
    """The page of results: heading, one card per result, pages + edit, the filter menus."""
    q, flights = res["query"], res["kind"] == "flights"
    page = t(
        "discord.search.page",
        lang,
        page=res["offset"] // PAGE + 1,
        pages=max(1, math.ceil(res["total"] / PAGE)),
        results=count(res["kind"], res["total"], lang),
        sort=t(SORTS[s.filters.sort], lang),
    )
    if flights:
        route = f"{place(_place(q['origin']))} → {place(_place(q['destination']))}"
        head = [
            f"## {t('discord.flight.heading', lang, route=route)}",
            f"{day(q['depart'], lang, year=True)} · {count('travellers', q['adults'], lang)}"
            f" · {cabin(q['cabin'], lang)}",
        ]
    else:
        route = place(_place(q["city"]))
        head = [f"## {t('discord.hotel.heading', lang, city=route)}", _stay_line(q, lang)]
    head += [f"-# {page}", f"-# {t('discord.search.demoNotice', lang)}"]
    items: list = [ui.TextDisplay("\n".join(head))]
    for r in res["results"]:
        if flights:
            text = flight_card(r, lang)
            label = t("discord.flight.select", lang, flight=" + ".join(r["flights"]))
            action = _btn("fl", s, label, r["id"], style=discord.ButtonStyle.primary)
        else:
            text = hotel_card(r, lang)
            label = t("discord.hotel.viewRooms", lang)
            action = _btn("ho", s, label, r["id"], style=discord.ButtonStyle.primary)
        items.append(ui.Container(ui.TextDisplay(text), ui.ActionRow(action), accent_colour=ACCENT))
    if res["empty"] == "route":
        items.append(ui.TextDisplay(t("discord.search.noSampleData", lang, route=route)))
    elif res["empty"] == "filters":
        items.append(ui.TextDisplay(t("discord.search.noResults", lang)))
    elif res["empty"] and flights:  # nothing in this cabin
        text = t("discord.flight.noCabinFares", lang, cabin=cabin(q["cabin"], lang))
        items.append(ui.TextDisplay(text))
    elif res["empty"]:  # no room fits the guests
        items.append(ui.TextDisplay(_no_rooms(q["guests"], q["rooms"], lang)))
    nav = [
        _btn(
            "pg",
            s,
            "◀ " + t("discord.search.previous", lang),
            str(max(0, res["offset"] - PAGE)),
            disabled=res["offset"] == 0,
        ),
        _btn(
            "pg",
            s,
            t("discord.search.next", lang) + " ▶",
            str(res["offset"] + PAGE),
            disabled=not res["has_more"],
        ),
        _btn("ed", s, t("discord.search.edit", lang)),
    ]
    if _filtered(s):
        nav.append(_btn("cl", s, t("discord.search.clearFilters", lang)))
    items.append(ui.ActionRow(*nav))
    if res["empty"] != "route":
        items += _flight_menus(res, s, lang) if flights else _hotel_menus(res, s, lang)
    return _view(*items)


def _place(code: str) -> dict:
    city, airport, _ = AIRPORTS.get(code, (code, code, 0))
    return {"code": code, "city": city, "airport": airport}


def _flight_menus(res: dict, s: Session, lang: str) -> list:
    f: FlightFilters = s.filters
    picked = {*f.stops, *f.times}
    opts = [_option(t(key, lang), k, k in picked) for k, key in FLIGHT_FILTERS.items()]
    menus = [
        ui.ActionRow(
            TravelSelect("ff", s.sid, opts, t("discord.flight.filtersMenu", lang), multi=True)
        )
    ]
    if res["airlines"]:
        chosen = {a.upper() for a in f.airlines}
        opts = [
            _option(f"{a['name']} ({a['code']})", a["code"], a["code"] in chosen)
            for a in res["airlines"]
        ]
        menus.append(
            ui.ActionRow(
                TravelSelect("fa", s.sid, opts, t("discord.flight.airlinesMenu", lang), multi=True)
            )
        )
    menus.append(_sort_menu("fs", s, ("best", "cheapest", "fastest", "earliest"), lang))
    if res["price_range"]:
        menus.append(_price_menu("fp", s, res["price_range"], f.max_price, "flight", lang))
    return menus


def _hotel_menus(res: dict, s: Session, lang: str) -> list:
    f: HotelFilters = s.filters
    on = {
        "free_cancellation": f.free_cancellation,
        "breakfast": f.breakfast,
        "stars4": (f.min_stars or 0) >= 4,
        "score8": (f.min_score or 0) >= 8,
    }
    opts = [_option(t(HOTEL_FILTERS[k], lang), k, v) for k, v in on.items()]
    return [
        ui.ActionRow(
            TravelSelect("hf", s.sid, opts, t("discord.hotel.filtersMenu", lang), multi=True)
        ),
        _sort_menu("hs", s, ("recommended", "price", "rating"), lang),
        _price_menu("hp", s, res["price_range"], f.max_nightly, "hotel", lang),
    ]


def fare_view(review: dict, s: Session, lang: str) -> ui.LayoutView:
    """The mock itinerary and fare review of one flight (nothing is booked)."""
    o, b, rules = review["flight"], review["breakdown"], review["rules"]
    heading = t(
        "discord.flight.reviewHeading",
        lang,
        airline=o["airline"]["name"],
        flights=" + ".join(o["flights"]),
    )
    lines = [
        f"## {heading}",
        f"{place(o['origin'])} → {place(o['destination'])} · {day(o['depart'], lang, year=True)}"
        f" · {cabin(o['cabin'], lang)} · {count('travellers', o['travellers'], lang)}",
    ]
    segs = []
    for i, g in enumerate(o["segments"]):
        if i:
            v = o["via"][i - 1]
            layover = t(
                "discord.flight.layover",
                lang,
                place=place(v),
                duration=duration(v["layover_min"], lang),
            )
            segs.append(f"-# {layover}")
        plus = "" if g["arrive"][:10] == g["depart"][:10] else f" ({day(g['arrive'], lang)})"
        segs.append(
            f"**{g['flight']}** · {g['depart'][11:16]} {g['from']['airport']} ({g['from']['code']})"
            f" → {g['arrive'][11:16]}{plus} {g['to']['airport']} ({g['to']['code']})"
            f" · {duration(g['minutes'], lang)}"
        )
    change = (
        t("discord.flight.changeFee", lang, fee=num(rules["change_fee"]))
        if rules["change_fee"]
        else t("discord.flight.freeChanges", lang)
    )
    refund = (
        t("discord.flight.refundFee", lang, fee=num(rules["refund_fee"]))
        if rules["refund_fee"] is not None
        else t("discord.flight.notRefundable", lang)
    )
    price = [
        t(
            "discord.flight.fareMath",
            lang,
            base=num(b["base_per_traveller"]),
            taxes=num(b["taxes_per_traveller"]),
            each=num(b["per_traveller"]),
        ),
        t(
            "discord.flight.fareTotal",
            lang,
            each=num(b["per_traveller"]),
            travellers=count("travellers", b["travellers"], lang),
            total=num(b["total"]),
        ),
    ]
    body = "\n".join(
        [
            *segs,
            "",
            f"**{t('discord.flight.baggage', lang)}** · {_bags(o['baggage'], lang)}",
            f"**{t('discord.flight.fareRules', lang)}** · {change} · {refund}",
            f"**{t('discord.search.price', lang)}**",
            *price,
            "",
            f"-# {t('discord.flight.reviewNote', lang)}",
            f"-# {t('discord.search.bookHint', lang, ref=o['booking_ref'])}",
        ]
    )
    return _view(
        ui.Container(
            ui.TextDisplay("\n".join(lines)),
            ui.Separator(),
            ui.TextDisplay(body),
            accent_colour=ACCENT_DEEP,
        ),
        ui.ActionRow(
            _btn("bk", s, "◀ " + t("discord.search.backToResults", lang)),
            _btn("bq", s, t("discord.book.button", lang), style=discord.ButtonStyle.success),
        ),
    )


def _hotel_head(h: dict, lang: str) -> str:
    stars, score = _rating(h, lang)
    note = t("discord.hotel.sampleNote", lang)
    return f"-# {note}\n{h['area']}, {h['city']} · {stars}\n{score}"


def _stay(h: dict) -> dict:
    return {k: h[k] for k in ("check_in", "check_out", "nights", "rooms", "guests")}


def rooms_view(got: dict, s: Session, lang: str) -> ui.LayoutView:
    """Every room of one hotel that fits the guests, with a menu to review one."""
    h, q = got["hotel"], s.query
    back = ui.ActionRow(
        _btn("bk", s, "◀ " + t("discord.hotel.backToHotels", lang)),
        _btn("ed", s, t("discord.search.edit", lang)),
    )
    if h is None:
        return _view(ui.TextDisplay(_no_rooms(q.guests, q.rooms, lang)), back)
    head = [
        f"## {h['name']}",
        _hotel_head(h, lang),
        _stay_line(_stay(h), lang),
        f"-# {t('discord.search.demoNotice', lang)}",
    ]
    items: list = [ui.TextDisplay("\n".join(head))]
    items += [
        ui.Container(ui.TextDisplay(room_card(r, lang)), accent_colour=ACCENT) for r in got["rooms"]
    ]
    opts = [
        _option(
            r["name"],
            r["id"],
            description=f"{_nightly(r['price'], lang)} · {cancel_text(r['cancellation'], lang)}",
        )
        for r in got["rooms"]
    ]
    items.append(
        ui.ActionRow(
            TravelSelect("rm", s.sid, opts, t("discord.hotel.roomMenu", lang), arg=h["id"])
        )
    )
    items.append(back)
    return _view(*items)


def stay_view(review: dict, s: Session, lang: str) -> ui.LayoutView:
    """The stay review of one room (nothing is booked)."""
    h, r = review["hotel"], review["room"]
    p = r["price"]
    head = [
        f"## {t('discord.hotel.reviewHeading', lang, hotel=h['name'])}",
        _hotel_head(h, lang),
    ]
    body = "\n".join(
        (
            f"**{t('discord.hotel.room', lang)}** · {r['name']} · {_room_details(r, lang)}"
            f" · {_meal(r, lang)}",
            f"**{t('discord.hotel.stay', lang)}** · {_stay_line(_stay(h), lang)}",
            f"**{t('discord.hotel.cancellation', lang)}** · {cancel_text(r['cancellation'], lang)}",
            f"**{t('discord.search.price', lang)}**",
            t(
                "discord.hotel.stayMath",
                lang,
                nightly=num(p["nightly"]),
                nights=count("nights", p["nights"], lang),
                rooms=count("rooms", p["rooms"], lang),
            ),
            t(
                "discord.hotel.staySum",
                lang,
                before=num(p["before_taxes"]),
                taxes=num(p["taxes"]),
                total=num(p["total"]),
            ),
            "",
            f"-# {t('discord.hotel.reviewNote', lang)}",
            f"-# {t('discord.search.bookHint', lang, ref=r['booking_ref'])}",
        )
    )
    return _view(
        ui.Container(
            ui.TextDisplay("\n".join(head)),
            ui.Separator(),
            ui.TextDisplay(body),
            accent_colour=ACCENT_DEEP,
        ),
        ui.ActionRow(
            _btn("ho", s, "◀ " + t("discord.hotel.backToRooms", lang), h["id"]),
            _btn("bk", s, t("discord.hotel.backToHotels", lang)),
            _btn("bq", s, t("discord.book.button", lang), style=discord.ButtonStyle.success),
        ),
    )


# ----------------------------------------------------------------------------- booking (pure)
SLOTS = ("flight", "return", "room")  # the order a quote lists the person's picks in


def booking_items(picked: dict[str, str], today: date) -> dict[str, dict]:
    """The picks that still resolve (`travel_search.by_booking_ref`, priced from the catalogue
    exactly as book_trip prices them), by slot."""
    out = {}
    for slot in SLOTS:
        got = by_booking_ref(picked[slot], today) if picked.get(slot) else None
        if got:
            out[slot] = got
    return out


def booking_args(picked: dict[str, str], slots: list[str]) -> dict:
    """book_trip's arguments for the chosen slots; a way back booked without its outbound is
    just a flight."""
    out = picked["flight"] if "flight" in slots else picked["return"] if "return" in slots else ""
    back = picked["return"] if "flight" in slots and "return" in slots else ""
    room = picked["room"] if "room" in slots else ""
    return {"flight_offer_id": out, "hotel_offer_id": room, "purpose": "",
            "return_flight_offer_id": back}  # fmt: skip


def _item(slot: str, got: dict, lang: str) -> tuple[str, int, str]:
    """(quote line, THB total, menu label) of one pick."""
    if got["kind"] == "flight":
        o = got["flight"]
        flights = " + ".join(o["flights"])
        line = t(
            "discord.book.itemReturn" if slot == "return" else "discord.book.itemFlight",
            lang,
            flights=flights,
            route=f"{o['origin']['code']} → {o['destination']['code']}",
            when=f"{day(o['depart'], lang)} {o['depart'][11:16]}",
            total=num(o["price"]["total"]),
        )
        label = t("discord.book.optReturn" if slot == "return" else "discord.book.optFlight",
                  lang, flights=flights)  # fmt: skip
        return line, o["price"]["total"], label
    h, r = got["hotel"], got["room"]
    line = t(
        "discord.book.itemRoom",
        lang,
        hotel=h["name"],
        room=r["name"],
        stay=_stay_line(_stay(h), lang),
        total=num(r["price"]["total"]),
    )
    return line, r["price"]["total"], t("discord.book.optRoom", lang, hotel=h["name"])


def quote_view(s: Session, items: dict, slots: list[str], lang: str) -> ui.LayoutView:
    """The quote for the picks (nothing is booked here), "What to book" when there is a choice,
    Confirm booking / Cancel."""
    lines, total = [f"## {t('discord.book.quoteHeading', lang)}"], 0
    for slot in SLOTS:
        if slot in items and slot in slots:
            line, amount, _ = _item(slot, items[slot], lang)
            lines.append(line)
            total += amount
    lines.append(t("discord.book.total", lang, total=num(total)) if total
                 else t("discord.book.nothing", lang))  # fmt: skip
    lines.append(f"-# {t('discord.book.confirmNote', lang)}")
    parts: list = [ui.Container(ui.TextDisplay("\n".join(lines)), accent_colour=ACCENT_DEEP)]
    if len(items) > 1:
        opts = [
            _option(_item(slot, items[slot], lang)[2], slot, slot in slots)
            for slot in SLOTS
            if slot in items
        ]
        what = TravelSelect("bw", s.sid, opts, t("discord.book.whatMenu", lang), multi=True)
        parts.append(ui.ActionRow(what))
    parts.append(
        ui.ActionRow(
            _btn(
                "bc",
                s,
                t("discord.book.confirm", lang),
                style=discord.ButtonStyle.success,
                disabled=not total,
            ),  # fmt: skip
            _btn("bx", s, t("discord.book.cancel", lang)),
        )
    )
    return _view(*parts)


def _book_problem(res: dict, lang: str) -> str:
    status = res.get("status")
    if status == "expired":
        return t("discord.book.expired", lang)
    if status == "refused":
        return t("discord.book.refused", lang, reason=str(res.get("reason") or "-"))
    return t("discord.book.failed", lang)


def booked_view(res: dict, items: dict, s: Session, lang: str) -> ui.LayoutView:
    """What book_trip did: the sandbox booking (references, total, receipts, check-in reminder)
    or the problem with a way on."""
    if res.get("status") != "booked":
        retry = res.get("status") not in ("expired", "refused")
        row = ui.ActionRow(
            *([_btn("bc", s, t("discord.book.tryAgain", lang))] if retry else []),
            _btn("bx", s, t("discord.book.cancel", lang)),
        )
        return _view(ui.TextDisplay(_book_problem(res, lang)), row)
    refs = res.get("references") or {}
    named = [t(f"discord.book.ref{k.title()}", lang, ref=v) for k, v in refs.items()
             if k in ("flight", "hotel")]  # fmt: skip
    total = sum(int(round(x["amount"])) for x in res.get("totals") or [])
    lines = [
        f"## {t('discord.book.bookedHeading', lang)}",
        t("discord.book.trip", lang, trip=res.get("trip_id", "")),
        t("discord.book.references", lang, refs=" · ".join(named)),
        t("discord.book.total", lang, total=num(total)),
        t("discord.book.receipts", lang, n=len(res.get("filed_receipts") or [])),
    ]
    out = items.get("flight") or items.get("return")
    if res.get("checkin_reminder") and "flight" in refs and out:
        when = datetime.fromisoformat(out["flight"]["depart"]) - timedelta(days=1)
        lines.append(
            t("discord.book.reminder", lang, when=f"{day(when.date(), lang)} {when:%H:%M}")
        )
    lines.append(f"-# {t('discord.book.sandboxNote', lang)}")
    return _view(ui.Container(ui.TextDisplay("\n".join(lines)), accent_colour=ACCENT_DEEP))


# ----------------------------------------------------------------------------- state (pure)
def run_search(s: Session, today: date) -> dict:
    """The session's current page; a page past the end (filters shrank the list) moves back."""
    if s.kind == "flights":
        res = search_flights(s.query, s.filters, s.offset, PAGE)
    else:
        res = search_hotels(s.query, s.filters, s.offset, PAGE, today)
    if not res["results"] and res["total"] and s.offset:
        s.offset = (res["total"] - 1) // PAGE * PAGE
        return run_search(s, today)
    return res


def _new_filters(s: Session, act: str, values: list[str]):
    f = s.filters.model_dump()
    first = values[0] if values else None
    if act == "ff":
        f["stops"] = [v for v in values if v in ("nonstop", "1stop")]
        f["times"] = [v for v in values if v in TIMES]
    elif act == "fa":
        f["airlines"] = list(values)
    elif act in ("fs", "hs"):
        f["sort"] = first or type(s.filters)().sort
    elif act in ("fp", "hp"):
        f["max_price" if act == "fp" else "max_nightly"] = (
            int(first) if (first or "").isdigit() else None
        )
    elif act == "hf":
        f.update(
            free_cancellation="free_cancellation" in values,
            breakfast="breakfast" in values,
            min_stars=4 if "stars4" in values else None,
            min_score=8.0 if "score8" in values else None,
        )
    elif act == "cl":
        f = {**type(s.filters)().model_dump(), "sort": f["sort"]}
    return type(s.filters).model_validate(f)


def travel_click(s: Session, act: str, arg: str, values: list[str], today: date, lang: str):
    """Apply one click to the session and return the view that replaces the message."""
    if (act in HOTEL_ACTS and s.kind != "hotels") or (act in FLIGHT_ACTS and s.kind != "flights"):
        act = "bk"  # a click that does not fit this search: just show its results again
    if act == "fl":
        review = fare_review(s.query, arg)
        if review is not None:
            s.selected, s.extra["ref"] = arg, review["flight"]["booking_ref"]
            return fare_view(review, s, lang)
    elif act == "ho":
        got = hotel_rooms(s.query, arg, today)
        if got is not None:
            s.selected = arg
            return rooms_view(got, s, lang)
    elif act == "rm":
        review = room_review(s.query, arg, values[0] if values else "", today)
        if review is not None:
            s.selected = f"{arg}/{review['room']['id']}"
            s.extra["ref"] = review["room"]["booking_ref"]
            return stay_view(review, s, lang)
        got = hotel_rooms(s.query, arg, today)
        if got is not None:
            return rooms_view(got, s, lang)
    elif act == "pg":
        s.offset = max(0, int(arg)) if arg.isdigit() else 0
    elif act in ("ff", "fa", "fs", "fp", "hf", "hs", "hp", "cl"):
        with contextlib.suppress(ValidationError):  # a value no menu offered: keep the filters
            s.filters, s.offset = _new_filters(s, act, values), 0
    s.selected = None
    return results_view(run_search(s, today), s, lang)


# ----------------------------------------------------------------------------- input (pure)
def _field(name: str, lang: str) -> str | None:
    return t(FIELDS[name], lang) if name in FIELDS else None


def _problem(e: ValidationError, lang: str) -> str:
    """The first validation error in the person's language: `Travellers: must be at most 9`."""
    err = e.errors()[0]
    kind, ctx, msg = err["type"], err.get("ctx") or {}, err["msg"]
    if "must differ" in msg:
        return t("discord.error.sameRoute", lang)
    if "nights after" in msg:
        return t("discord.error.nights", lang, max=MAX_NIGHTS)
    if "at least one guest" in msg:
        return t("discord.error.guestsPerRoom", lang)
    field = _field(str(err["loc"][0]), lang) if err["loc"] else None
    key, extra = None, {}
    if kind == "less_than_equal":
        key, extra = "discord.error.atMost", {"max": ctx.get("le")}
    elif kind == "greater_than_equal":
        key, extra = "discord.error.atLeast", {"min": ctx.get("ge")}
    elif kind.startswith("int_"):
        key = "discord.error.wholeNumber"
    elif kind.startswith("date_"):
        key = "discord.error.dateFormat"
    elif kind == "literal_error":
        key = "discord.error.cabin"
    elif "3-letter" in msg:
        key = "discord.error.airportCode"
    if key is None or field is None:
        return msg  # a validator message no form field owns (English, internal)
    return t(key, lang, field=field, **extra)


def _day(text, field: str, today: date, lang: str) -> tuple[date | None, str | None]:
    text = str(text or "").strip()
    if not text:
        return next_week_tuesday(today), None
    try:
        d = date.fromisoformat(text)
    except ValueError:
        return None, t("discord.error.dateFormat", lang, field=_field(field, lang))
    problem = date_problem(today, d)
    if problem:
        key = {"past_date": "discord.error.pastDate", "too_far": "discord.error.tooFar"}[problem]
        return None, t(key, lang, field=_field(field, lang), days=MAX_DAYS_AHEAD)
    return d, None


def _cabin(text) -> str:
    v = str(text or "").strip().lower()
    if v.startswith("bus") or "ธุรกิจ" in v:
        return "business"
    if v.startswith("eco") or "ประหยัด" in v or not v:
        return "economy"
    return v  # pydantic says "type economy or business"


def flight_query(v: dict, today: date, lang: str) -> tuple[FlightQuery | None, str | None]:
    """Slash options or modal text -> the query, or the problem to show (nothing changes)."""
    depart, problem = _day(v.get("depart"), "depart", today, lang)
    if problem:
        return None, problem
    try:
        return FlightQuery(
            origin=str(v.get("origin") or ""),
            destination=str(v.get("destination") or ""),
            depart=depart,
            adults=str(v.get("adults") or "").strip() or 1,
            cabin=_cabin(v.get("cabin")),
        ), None
    except ValidationError as e:
        return None, _problem(e, lang)


def hotel_query(v: dict, today: date, lang: str) -> tuple[HotelQuery | None, str | None]:
    check_in, problem = _day(v.get("check_in"), "check_in", today, lang)
    if problem:
        return None, problem
    nights = str(v.get("nights") or "3").strip()
    if not nights.isdigit():
        return None, t("discord.error.wholeNumber", lang, field=_field("nights", lang))
    if not 1 <= int(nights) <= MAX_NIGHTS:
        return None, t("discord.error.nights", lang, max=MAX_NIGHTS)
    try:
        return HotelQuery(
            city=str(v.get("city") or ""),
            check_in=check_in,
            check_out=check_in + timedelta(days=int(nights)),
            rooms=str(v.get("rooms") or "").strip() or 1,
            guests=str(v.get("guests") or "").strip() or 2,
        ), None
    except ValidationError as e:
        return None, _problem(e, lang)


def query_values(s: Session) -> dict[str, str]:
    """The current criteria as the edit modal shows them."""
    q = s.query
    if s.kind == "flights":
        return {
            "origin": q.origin,
            "destination": q.destination,
            "depart": q.depart.isoformat(),
            "adults": str(q.adults),
            "cabin": q.cabin,
        }
    return {
        "city": q.city,
        "check_in": q.check_in.isoformat(),
        "nights": str(q.nights),
        "rooms": str(q.rooms),
        "guests": str(q.guests),
    }


class TravelEditModal(ui.Modal):
    """Edit search, prefilled with the current criteria (5 inputs: Discord's maximum)."""

    def __init__(self, s: Session, lang: str) -> None:
        super().__init__(title=t("discord.search.edit", lang)[:45])
        self.sid = s.sid
        self.fields: dict[str, ui.TextInput] = {}
        for name, value in query_values(s).items():
            self.fields[name] = ui.TextInput(default=value, max_length=20)
            self.add_item(ui.Label(text=t(FORM[name], lang)[:45], component=self.fields[name]))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values = {k: str(f.value) for k, f in self.fields.items()}
        await interaction.client.handle_travel_edit(interaction, self.sid, values)


def card_session(sessions: Sessions, owner: str, card: dict) -> Session:
    """A Discord session from a card the AI tools recorded (`travel_search.tool_cards`)."""
    if card["kind"] == "flights":
        query, filters = FlightQuery, FlightFilters
    else:
        query, filters = HotelQuery, HotelFilters
    return sessions.start(
        owner,
        card["kind"],
        query.model_validate(card["query"]),
        filters.model_validate(card["filters"]),
    )


# ----------------------------------------------------------------------------- the mixin
def _owner(interaction) -> str:
    return f"discord:{interaction.user.id}"


class TravelSearchMixin:
    """`/dory flights`, `/dory hotels` and the cards under a chat answer for `SecretaryBot`
    (flag `travel`)."""

    @functools.cached_property
    def travel_sessions(self) -> Sessions:
        return Sessions()

    @functools.cached_property
    def travel_trips(self) -> Trips:
        """Each person's last flight / hotel search across chat messages (the AI tools)."""
        return Trips()

    def _travel_today(self) -> date:
        return self.s.now().date()  # Bangkok: the settings' zone

    # ------------------------------------------------------------------ chat
    def _travel_card_tools(self, guild, asker, tools: list, *, spoken: bool) -> list:
        """The ONE flight search and ONE hotel search (`travel_search.card_tools`) next to
        trips.py's book_trip / travel_profile / list_trips, in typed chat (Discord and the web
        through `dory.headless`) and in voice. Their results carry the booking_ref book_trip
        books; typed chat draws them as cards, voice (`spoken`) speaks them. Only the explicit
        `spoken` decides: the web chat passes a room stand-in without files, which
        `imagegen_bot.looks_spoken` would take for voice."""
        if not self.team.enabled(guild.id, "travel"):
            return tools
        ctx = CardCtx(
            owner=f"discord:{asker.id}",
            today=self._travel_today(),
            trips=self.travel_trips,
            render=not spoken,
        )
        return [*tools, *card_tools(ctx)]

    async def _post_travel_cards(self, message, member, agent: dict, lang: str) -> None:
        """After the reply: one results message per search the brain ran (flights first), each
        an owner-bound session. A failure is logged by type and told in one short line."""
        searches = ("flights", "hotels")  # a weather card rides in the same list (its own poster)
        cards = [c for c in tool_cards(agent.get("extra_tools") or []) if c["kind"] in searches]
        if not cards:
            return  # no search ran (or it asked a question first: need_details)
        today = self._travel_today()
        try:
            for card in sorted(cards, key=lambda c: c["kind"] != "flights"):
                s = card_session(self.travel_sessions, f"discord:{member.id}", card)
                s.extra["lang"] = lang
                await message.channel.send(view=results_view(run_search(s, today), s, lang))
        except Exception as e:  # the answer is already out: never fail the reply for the cards
            logger.warning("travel cards not sent: %s", type(e).__name__)
            with contextlib.suppress(discord.HTTPException):
                await message.channel.send(t("discord.search.cardsFailed", lang))

    def _travel_fail_hint(self, guild_id: int, text: str, lang: str) -> str:
        """The structured-search line for a failed answer to a trip request ("" otherwise)."""
        try:
            if not self.team.enabled(guild_id, "travel"):
                return ""
            if parse_request(text, self._travel_today()) is None:
                return ""
        except Exception:  # e.g. "from Bangkok to Bangkok": not a search we can offer
            return ""
        return t("discord.search.fallbackHint", lang)

    # ------------------------------------------------------------------ slash commands
    def _register_travel_search_commands(self) -> None:
        group = app_commands.Group(name="dory", description=t("cmd_dory"), guild_only=True)
        airports = [
            app_commands.Choice(name=f"{city} ({code})", value=code)
            for code, (city, _, _) in AIRPORTS.items()
        ]
        cabins = [
            app_commands.Choice(name=f"{cabin(c, 'en')} · {cabin(c, 'th')}", value=c)
            for c in ("economy", "business")
        ]

        @group.command(name="flights", description=t("cmd_dory_flights"))
        @app_commands.rename(origin="from", destination="to")
        @app_commands.describe(
            origin=t("cmd_dory_from"),
            destination=t("cmd_dory_to"),
            date=t("cmd_dory_date"),
            travellers=t("cmd_dory_travellers"),
            cabin=t("cmd_dory_cabin"),
        )
        @app_commands.choices(origin=airports, destination=airports, cabin=cabins)
        async def flights(
            interaction: discord.Interaction,
            origin: str,
            destination: str,
            date: str | None = None,
            travellers: app_commands.Range[int, 1, 9] = 1,
            cabin: str = "economy",
        ):
            await self.handle_travel_search(
                interaction,
                "flights",
                {
                    "origin": origin,
                    "destination": destination,
                    "depart": date,
                    "adults": travellers,
                    "cabin": cabin,
                },
            )

        @group.command(name="hotels", description=t("cmd_dory_hotels"))
        @app_commands.describe(
            city=t("cmd_dory_city"),
            check_in=t("cmd_dory_check_in"),
            nights=t("cmd_dory_nights"),
            rooms=t("cmd_dory_rooms"),
            guests=t("cmd_dory_guests"),
        )
        @app_commands.choices(city=airports)
        async def hotels(
            interaction: discord.Interaction,
            city: str,
            check_in: str | None = None,
            nights: app_commands.Range[int, 1, 30] = 3,
            rooms: app_commands.Range[int, 1, 4] = 1,
            guests: app_commands.Range[int, 1, 12] = 2,
        ):
            await self.handle_travel_search(
                interaction,
                "hotels",
                {
                    "city": city,
                    "check_in": check_in,
                    "nights": nights,
                    "rooms": rooms,
                    "guests": guests,
                },
            )

        self.tree.add_command(group)

    async def handle_travel_search(self, interaction, kind: str, values: dict) -> None:
        """The slash commands: defer at once (3 s), then ONE ephemeral results message."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        await asyncio.to_thread(self.team.current, guild.id)
        lang = self._interaction_lang(interaction)
        if not self.team.enabled(guild.id, "travel"):
            await interaction.followup.send(t("discord.search.off", lang), ephemeral=True)
            return
        today = self._travel_today()
        query, problem = (flight_query if kind == "flights" else hotel_query)(values, today, lang)
        if problem:
            await interaction.followup.send(problem, ephemeral=True)
            return
        s = self.travel_sessions.start(_owner(interaction), kind, query)
        s.extra["lang"] = lang
        view = results_view(run_search(s, today), s, lang)
        await interaction.edit_original_response(content=None, view=view)

    async def _travel_expired(self, interaction) -> None:
        lang = self._interaction_lang(interaction)
        await interaction.response.send_message(t("discord.search.expired", lang), ephemeral=True)

    async def handle_travel_click(self, interaction, act, sid, arg="", values=()) -> None:
        """Any button or menu: only the session's owner gets a changed message."""
        s = self.travel_sessions.get(sid, _owner(interaction))
        if s is None:
            await self._travel_expired(interaction)
            return
        lang = s.extra.get("lang", "en")
        if act == "ed":
            await interaction.response.send_modal(TravelEditModal(s, lang))
            return
        if act in ("bq", "bw", "bc", "bx"):
            await self._travel_book(interaction, s, act, list(values))
            return
        today = self._travel_today()
        view = travel_click(s, act, arg, list(values), today, lang)
        if act in ("fl", "rm") and s.selected and s.extra.get("ref"):  # a review shown: a pick
            self.travel_trips.pick(_owner(interaction), s.extra["ref"], today)
        await interaction.response.edit_message(view=view)

    async def _travel_book(self, interaction, s: Session, act: str, values: list[str]) -> None:
        """Book in sandbox (the quote, a NEW ephemeral message: never personal details on a
        public card), What to book, Cancel, Confirm booking (book_trip as the person)."""
        lang, today, owner = s.extra.get("lang", "en"), self._travel_today(), _owner(interaction)
        if not self.team.enabled(interaction.guild.id, "travel"):  # also the licence gate
            await interaction.response.send_message(t("discord.search.off", lang), ephemeral=True)
            return
        if act == "bq":
            if s.extra.get("ref"):
                self.travel_trips.pick(owner, s.extra["ref"], today)
            picked = self.travel_trips.picked(owner)
            items = booking_items(picked, today)
            if not items:
                await interaction.response.send_message(t("discord.book.expired", lang),
                                                        ephemeral=True)  # fmt: skip
                return
            s.extra["book"] = {"picked": {k: picked[k] for k in items}, "slots": list(items)}
            view = quote_view(s, items, list(items), lang)
            await interaction.response.send_message(view=view, ephemeral=True)
            return
        # the quote's own components; pop first, so a double click cannot book twice
        book = s.extra.pop("book", None)
        if book is None:
            await self._travel_expired(interaction)
            return
        items = booking_items(book["picked"], today)
        if act == "bx":
            await interaction.response.edit_message(
                view=_view(ui.TextDisplay(t("discord.book.cancelled", lang)))
            )
            return
        if act == "bw":
            book["slots"] = [v for v in values if v in items]
            s.extra["book"] = book
            await interaction.response.edit_message(view=quote_view(s, items, book["slots"], lang))
            return
        slots = [x for x in book["slots"] if x in items]
        if not slots:
            s.extra["book"] = book
            await interaction.response.edit_message(view=quote_view(s, items, slots, lang))
            return
        await interaction.response.defer()  # the booking writes the ledger: off the 3 s clock
        args = booking_args(book["picked"], slots)
        res = await asyncio.to_thread(self._travel_book_now, interaction.guild,
                                      interaction.user, lang, args)  # fmt: skip
        if res.get("status") == "booked":
            self.travel_trips.unpick(owner, *slots)
        else:
            s.extra["book"] = book  # Try again keeps the same quote
        await interaction.edit_original_response(view=booked_view(res, items, s, lang))

    def _travel_book_now(self, guild, member, lang: str, args: dict) -> dict:
        """book_trip as `member` after Confirm booking: its first call quotes (unless the same
        quote is already waiting, e.g. from the chat), a second, NEW request books; each
        `_travel_tools` call is a new request."""
        res: dict = {"status": "failed"}
        for _ in range(2):
            tools = self._travel_tools(guild, member, lang, self.is_exec_member(member))
            book = next((f for f in tools if getattr(f, "__name__", "") == "book_trip"), None)
            if book is None:
                return {"status": "failed"}
            res = book.clicked(**args)  # the click asks to book (trips.trips_tools)
            if res.get("status") != "needs_confirmation":
                return res
        return res

    async def handle_travel_edit(self, interaction, sid: str, values: dict) -> None:
        """Edit search submitted: a bad value answers privately and keeps the old search."""
        s = self.travel_sessions.get(sid, _owner(interaction))
        if s is None:
            await self._travel_expired(interaction)
            return
        lang, today = s.extra.get("lang", "en"), self._travel_today()
        query, problem = (flight_query if s.kind == "flights" else hotel_query)(values, today, lang)
        if problem:
            await interaction.response.send_message(
                t("discord.search.badInput", lang, problem=problem), ephemeral=True
            )
            return
        s.query, s.offset, s.selected = query, 0, None
        await interaction.response.edit_message(view=results_view(run_search(s, today), s, lang))
