# ruff: noqa: F811 - the real bot's `bot` fixture is imported next to local `bot` fakes
"""/dory flights and /dory hotels: Components V2 cards built from the shared `travel_search`
results, the clicks, the edit modal and per-person sessions. Offline: fake interactions only."""

from datetime import date, timedelta
from types import SimpleNamespace

import discord
import pytest
from conftest import GUILD as BOT_GUILD
from conftest import FixedClockSettings, fc_resp, scripted, text_resp
from discord import app_commands
from test_coordinator import STAFF, world  # noqa: F401 - the real bot's fixtures
from test_modes import bot  # noqa: F401

from dory import qa, trips
from dory import travel_search as ts
from dory.bot import SecretaryBot
from dory.i18n import EXTRA, t
from dory.travel_search_bot import (
    PAGE,
    TravelButton,
    TravelEditModal,
    TravelSearchMixin,
    TravelSelect,
    booked_view,
    booking_items,
    flight_query,
    hotel_query,
    quote_view,
    results_view,
    run_search,
    travel_click,
)

TODAY = date(2026, 10, 14)  # FixedClockSettings: 2026-10-14 12:00 Bangkok
TUESDAY = ts.next_week_tuesday(TODAY)
GUILD, ME, OTHER = 42, 1001, 2002
TEMPLATES = [
    TravelButton.__discord_ui_compiled_template__,
    TravelSelect.__discord_ui_compiled_template__,
]


# ------------------------------------------------------------------ fakes
class Bot(TravelSearchMixin):
    def __init__(self, travel_on=True, lang="en"):
        self.s, self.lang = FixedClockSettings(), lang
        self.team = SimpleNamespace(current=lambda gid: None, enabled=lambda gid, f: travel_on)

    def _interaction_lang(self, interaction):
        return self.lang


class Click:
    """A slash command, component or modal interaction by user `uid`."""

    def __init__(self, uid=ME, client=None):
        self.user, self.client = SimpleNamespace(id=uid), client
        self.guild, self.channel, self.locale = SimpleNamespace(id=GUILD), SimpleNamespace(id=7), ""
        self.deferred, self.edited, self.sent, self.modals = [], [], [], []
        self.followups, self.original, self.views = [], [], []

        async def defer(**kw):
            self.deferred.append(kw)

        async def edit_message(**kw):
            self.edited.append(kw)

        async def send_message(text=None, ephemeral=False, view=None):
            if view is not None:  # a new message with components (the booking quote)
                self.views.append((view, ephemeral))
            else:
                self.sent.append((text, ephemeral))

        async def send_modal(modal):
            self.modals.append(modal)

        async def followup_send(text, ephemeral=False):
            self.followups.append((text, ephemeral))

        async def edit_original_response(**kw):
            self.original.append(kw)

        self.response = SimpleNamespace(
            defer=defer, edit_message=edit_message, send_message=send_message, send_modal=send_modal
        )
        self.followup = SimpleNamespace(send=followup_send)
        self.edit_original_response = edit_original_response


FLIGHTS = {"origin": "BKK", "destination": "SIN", "depart": None, "adults": 2, "cabin": "economy"}
HOTELS = {"city": "SIN", "check_in": None, "nights": 3, "rooms": 1, "guests": 2}


async def start(bot, kind="flights", values=None, uid=ME):
    click = Click(uid)
    await bot.handle_travel_search(
        click, kind, values or (FLIGHTS if kind == "flights" else HOTELS)
    )
    return click


def session_of(bot, click):
    (sid,) = {m["sid"] for m in map(_match, custom_ids(click.original[-1]["view"]))}
    return bot.travel_sessions.get(sid, f"discord:{click.user.id}")


def _match(custom_id):
    return next(p.fullmatch(custom_id) for p in TEMPLATES if p.fullmatch(custom_id))


def walk(components):
    for c in components:
        yield c
        yield from walk(c.get("components", []))
        if "accessory" in c:
            yield c["accessory"]


def custom_ids(view):
    return [c["custom_id"] for c in walk(view.to_components()) if "custom_id" in c]


def texts(view):
    return "\n".join(c["content"] for c in walk(view.to_components()) if c["type"] == 10)


def buttons(view):
    """Buttons by `act` or `act:arg` (the custom id without the prefix and session id)."""
    out = {}
    for c in walk(view.to_components()):
        if c["type"] == 2:
            m = _match(c["custom_id"])
            out[m["act"] + (f":{m['arg']}" if m["arg"] else "")] = c
    return out


def assert_discord_limits(view):
    """What https://discord.com/developers/docs/components/reference allows a V2 message."""
    assert view.has_components_v2() and view.timeout is None
    assert view.total_children_count <= 40 and view.content_length() <= 4000
    ids = custom_ids(view)
    assert len(ids) == len(set(ids))
    for cid in ids:
        assert len(cid) <= 100 and _match(cid), cid
    for c in walk(view.to_components()):
        if c["type"] == 1:  # action row: up to 5 buttons or exactly one select
            kinds = [x["type"] for x in c["components"]]
            assert (set(kinds) == {2} and len(kinds) <= 5) or kinds == [3], kinds
        if c["type"] == 2:
            assert 1 <= len(c["label"]) <= 80
        if c["type"] == 3:
            opts = c["options"]
            assert 1 <= len(opts) <= 25 and c["max_values"] <= len(opts)
            assert len(c.get("placeholder") or "") <= 150
            for o in opts:
                assert len(o["label"]) <= 100 and len(o["value"]) <= 100
                assert len(o.get("description") or "") <= 100
        if c["type"] == 17:
            assert c["accent_color"] in (0x4A4FBF, 0x2B2F7A)


# ------------------------------------------------------------------ the slash commands
async def test_flights_defer_at_once_then_one_ephemeral_v2_message():
    bot = Bot()
    click = await start(bot)
    assert click.deferred == [{"ephemeral": True, "thinking": True}]
    ((kw),) = click.original
    assert kw["content"] is None and not click.followups
    view = kw["view"]
    assert_discord_limits(view)
    shown = texts(view)
    assert "Flights · Bangkok (BKK) → Singapore (SIN)" in shown
    assert "Page 1 of 4 · 12 flights" in shown
    assert shown.count(t("discord.search.demoNotice", "en")) == 1  # said once per message
    s = session_of(bot, click)
    assert (s.kind, s.query.depart, s.query.adults, s.extra["lang"]) == (
        "flights",
        TUESDAY,
        2,
        "en",
    )


async def test_travel_off_and_bad_input_answer_privately_without_a_search():
    bot = Bot(travel_on=False)
    click = await start(bot)
    assert click.followups == [(t("discord.search.off", "en"), True)] and not click.original
    bot = Bot()
    click = await start(bot, values={**FLIGHTS, "depart": "2026-01-02"})
    assert click.followups == [("Date: that date is in the past", True)] and not click.original
    click = await start(bot, "hotels", {**HOTELS, "check_in": "next friday"})
    assert click.followups == [("Check-in: use a date like 2026-11-03", True)]
    assert not bot.travel_sessions._items


async def test_thai_cards_are_thai():
    bot = Bot(lang="th")
    view = (await start(bot)).original[0]["view"]
    shown = texts(view)
    assert "เที่ยวบิน · " in shown and "ผู้เดินทาง 2 คน" in shown and "รวมภาษีแล้ว" in shown
    assert_discord_limits(view)


def test_commands_are_one_guild_only_group_with_bilingual_short_descriptions():
    bot = Bot()
    bot.tree = app_commands.CommandTree(discord.Client(intents=discord.Intents.none()))
    bot._register_travel_search_commands()
    group = bot.tree.get_command("dory")
    assert isinstance(group, app_commands.Group) and group.guild_only
    subs = {c.name: c for c in group.commands}
    assert set(subs) == {"flights", "hotels"}
    flights = {p.display_name: p for p in subs["flights"].parameters}
    assert list(flights) == ["from", "to", "date", "travellers", "cabin"]
    assert flights["from"].required and flights["to"].required and not flights["date"].required
    assert (flights["travellers"].min_value, flights["travellers"].max_value) == (1, 9)
    hotels = {p.name: p for p in subs["hotels"].parameters}
    assert list(hotels) == ["city", "check_in", "nights", "rooms", "guests"]
    assert hotels["nights"].default == 3 and hotels["guests"].default == 2
    for cmd in (group, *subs.values()):
        assert len(cmd.description) <= 100
    for p in [*flights.values(), *hotels.values()]:
        assert len(p.description) <= 100 and len(p.choices) <= 25


def test_secretary_bot_carries_the_mixin():
    assert issubclass(SecretaryBot, TravelSearchMixin)


# ------------------------------------------------------------------ cards and prices
def test_flight_price_says_total_and_per_traveller_taxes_included():
    s = ts.Sessions().start("discord:1", "flights", flight_query(FLIGHTS, TODAY, "en")[0])
    shown = texts(results_view(run_search(s, TODAY), s, "en"))
    assert "**THB 6,380 total** for 2 travellers (THB 3,190 per traveller), taxes included" in shown
    assert "-# Sample itinerary · Sample price" in shown and "`Best value`" in shown
    one = ts.Sessions().start(
        "discord:1", "flights", flight_query({**FLIGHTS, "adults": 1}, TODAY, "en")[0]
    )
    shown = texts(results_view(run_search(one, TODAY), one, "en"))
    assert "**THB 3,190 total** for 1 traveller, taxes included" in shown
    assert "per traveller)" not in shown


def test_overnight_arrival_shows_plus_one_day_and_both_local_dates():
    s = ts.Sessions().start("discord:1", "flights", flight_query(FLIGHTS, TODAY, "en")[0])
    s.filters = ts.FlightFilters(sort="earliest")
    s.offset = 9  # the last page: 19:45 and 21:30
    shown = texts(results_view(run_search(s, TODAY), s, "en"))
    assert "**BKK 21:30 → SIN 00:55** (+1 day)" in shown
    assert "Tue 20 Oct → Wed 21 Oct" in shown


def test_hotel_card_keeps_stars_score_nightly_and_stay_total_apart():
    s = ts.Sessions().start("discord:1", "hotels", hotel_query(HOTELS, TODAY, "en")[0])
    shown = texts(results_view(run_search(s, TODAY), s, "en"))
    assert "★★★★★ 5-star hotel\nGuest score **9.1**/10 · 4,812 reviews" in shown
    assert "**THB 7,690 per room per night**" in shown
    assert "THB 23,070 total · 3 nights · 1 room · taxes included" in shown
    assert "-# Fictional property · Sample rating and reviews" in shown
    assert "Tue 20 Oct → Fri 23 Oct 2026 · 3 nights · 1 room · 2 guests" in shown
    assert "Non-refundable" in shown and "Free cancellation until" in shown


# ------------------------------------------------------------------ clicks
async def test_a_filter_changes_the_results_and_clear_brings_them_back():
    bot = Bot()
    s = session_of(bot, await start(bot))
    click = Click(client=bot)
    await bot.handle_travel_click(click, "ff", s.sid, "", ["nonstop", "morning"])
    view = click.edited[-1]["view"]
    assert_discord_limits(view)
    shown = texts(view)
    assert "1 stop" not in shown and "Page 1 of 1 · 3 flights" in shown  # FD355, TG403, SQ711
    assert "BKK 06:10" in shown and "BKK 13:30" not in shown
    assert s.filters.stops == ["nonstop"] and s.filters.times == ["morning"]
    await bot.handle_travel_click(click, "fa", s.sid, "", ["SQ"])
    assert "Page 1 of 1 · 1 flight" in texts(click.edited[-1]["view"])
    await bot.handle_travel_click(click, "fp", s.sid, "", ["3000"])
    assert t("discord.search.noResults", "en") in texts(click.edited[-1]["view"])  # empty: filters
    assert "cl" in buttons(click.edited[-1]["view"])
    await bot.handle_travel_click(click, "cl", s.sid)
    assert "12 flights" in texts(click.edited[-1]["view"]) and s.filters == ts.FlightFilters()


async def test_sort_cheapest_puts_the_cheapest_first():
    bot = Bot()
    s = session_of(bot, await start(bot))
    click = Click(client=bot)
    await bot.handle_travel_click(click, "fs", s.sid, "", ["cheapest"])
    first_card = texts(click.edited[-1]["view"]).split("### ")[1]
    assert first_card.startswith("AirAsia · AK 881 + AK 713")


async def test_next_and_previous_page():
    bot = Bot()
    first = await start(bot)
    s = session_of(bot, first)
    page1 = texts(first.original[0]["view"])
    assert buttons(first.original[0]["view"])["pg:0"]["disabled"]  # Previous on page 1
    click = Click(client=bot)
    await bot.handle_travel_click(click, "pg", s.sid, str(PAGE))
    page2 = texts(click.edited[-1]["view"])
    assert "Page 2 of 4" in page2 and page2 != page1 and s.offset == PAGE
    assert not buttons(click.edited[-1]["view"])["pg:0"]["disabled"]
    await bot.handle_travel_click(click, "pg", s.sid, "9")
    assert buttons(click.edited[-1]["view"])["pg:12"]["disabled"]  # Next on the last page
    await bot.handle_travel_click(click, "pg", s.sid, "0")
    assert texts(click.edited[-1]["view"]) == page1


async def test_select_flight_shows_the_fare_review_and_back_restores_page_and_filters():
    bot = Bot()
    s = session_of(bot, await start(bot))
    click = Click(client=bot)
    await bot.handle_travel_click(click, "ff", s.sid, "", ["1stop"])
    results = texts(click.edited[-1]["view"])
    flight_id = next(
        cid.split(":", 4)[4]
        for cid in custom_ids(click.edited[-1]["view"])
        if cid.startswith("dory:trv:fl:") and "AK881" in cid
    )
    await bot.handle_travel_click(click, "fl", s.sid, flight_id)
    review = click.edited[-1]["view"]
    assert_discord_limits(review)
    shown = texts(review)
    assert "Fare review · AirAsia AK 881 + AK 713" in shown
    assert "Layover in Kuala Lumpur (KUL): 2h 15m" in shown
    assert "Checked bag not included" in shown and "Not refundable" in shown
    assert "Base fare THB 1,640 + taxes and fees THB 1,010 = THB 2,650 per traveller" in shown
    assert "THB 2,650 × 2 travellers = **THB 5,300 total**" in shown
    assert t("discord.flight.reviewNote", "en") in shown
    assert ts.fare_review(s.query, flight_id)["booked"] is False and s.selected == flight_id
    await bot.handle_travel_click(click, "bk", s.sid)
    assert texts(click.edited[-1]["view"]) == results and s.filters.stops == ["1stop"]


async def test_hotel_rooms_then_stay_review_then_back_to_rooms_and_hotels():
    bot = Bot()
    s = session_of(bot, await start(bot, "hotels"))
    click = Click(client=bot)
    await bot.handle_travel_click(click, "hf", s.sid, "", ["free_cancellation", "stars4"])
    assert s.filters.free_cancellation and s.filters.min_stars == 4
    hotels = texts(click.edited[-1]["view"])
    assert "Little India Loft" not in hotels and "Non-refundable" not in hotels
    await bot.handle_travel_click(click, "ho", s.sid, "harbourlight")
    rooms = click.edited[-1]["view"]
    assert_discord_limits(rooms)
    assert "### Bay View Suite with breakfast" in texts(rooms) and "sleeps 3" in texts(rooms)
    await bot.handle_travel_click(click, "rm", s.sid, "harbourlight", ["bay-suite"])
    stay = click.edited[-1]["view"]
    assert_discord_limits(stay)
    shown = texts(stay)
    assert "Stay review · Harbourlight Marina Hotel" in shown
    assert "THB 14,900 per room per night × 3 nights × 1 room" in shown
    assert "**THB 44,700 total**" in shown and t("discord.hotel.reviewNote", "en") in shown
    review = ts.room_review(s.query, "harbourlight", "bay-suite", TODAY)
    assert review["booked"] is False and s.selected == "harbourlight/bay-suite"
    await bot.handle_travel_click(click, "ho", s.sid, "harbourlight")
    assert texts(click.edited[-1]["view"]) == texts(rooms)
    await bot.handle_travel_click(click, "bk", s.sid)
    assert texts(click.edited[-1]["view"]) == hotels and s.filters.min_stars == 4


async def test_unknown_route_and_cabin_say_why_without_filters():
    s = ts.Sessions().start(
        "discord:1", "flights", flight_query({**FLIGHTS, "destination": "NRT"}, TODAY, "en")[0]
    )
    view = results_view(run_search(s, TODAY), s, "en")
    assert_discord_limits(view)
    assert "No sample data for Bangkok (BKK) → Tokyo (NRT) yet." in texts(view)
    assert not [c for c in walk(view.to_components()) if c["type"] == 3]  # no filter menus
    big = ts.Sessions().start(
        "discord:1", "hotels", hotel_query({**HOTELS, "guests": 12}, TODAY, "en")[0]
    )
    assert "No room fits 12 guests in 1 room." in texts(
        results_view(run_search(big, TODAY), big, "en")
    )


# ------------------------------------------------------------------ sessions: owner and expiry
async def test_another_person_gets_the_expired_line_and_the_search_is_untouched():
    bot = Bot()
    s = session_of(bot, await start(bot))
    before = (s.offset, s.filters.model_dump(), s.query)
    stranger = Click(OTHER, client=bot)
    for act, arg, values in (
        ("pg", "3", []),
        ("ff", "", ["nonstop"]),
        ("ed", "", []),
        ("fl", "SQ711-20261020-E", []),
    ):
        await bot.handle_travel_click(stranger, act, s.sid, arg, values)
    assert stranger.sent == [(t("discord.search.expired", "en"), True)] * 4
    assert not stranger.edited and not stranger.modals
    await bot.handle_travel_edit(stranger, s.sid, {**{k: str(v) for k, v in FLIGHTS.items()}})
    assert stranger.sent[-1] == (t("discord.search.expired", "en"), True) and not stranger.edited
    assert (s.offset, s.filters.model_dump(), s.query) == before


async def test_an_unknown_or_timed_out_search_answers_gracefully():
    bot = Bot()
    now = [0.0]
    bot.travel_sessions = ts.Sessions(ttl_s=1800, clock=lambda: now[0])
    s = session_of(bot, await start(bot))
    click = Click(client=bot)
    await bot.handle_travel_click(click, "pg", "0123456789", "3")  # never existed (a restart)
    now[0] = 1801.0
    await bot.handle_travel_click(click, "pg", s.sid, "3")
    assert click.sent == [(t("discord.search.expired", "en"), True)] * 2 and not click.edited


async def test_dynamic_items_rebuild_from_their_custom_ids_and_reach_the_bot():
    bot = Bot()
    view = (await start(bot)).original[0]["view"]
    ids = custom_ids(view)
    nxt = next(c for c in ids if c.startswith("dory:trv:pg:") and c.endswith(":3"))
    click = Click(client=bot)
    m = TravelButton.__discord_ui_compiled_template__.fullmatch(nxt)
    button = await TravelButton.from_custom_id(click, SimpleNamespace(label="Next"), m)
    await button.callback(click)
    assert "Page 2 of 4" in texts(click.edited[-1]["view"])
    ff = next(c for c in ids if c.startswith("dory:trv:ff:"))
    m = TravelSelect.__discord_ui_compiled_template__.fullmatch(ff)
    menu = await TravelSelect.from_custom_id(click, SimpleNamespace(options=[]), m)
    menu._refresh_state(click, {"values": ["nonstop"]})  # what discord.py does on dispatch
    await menu.callback(click)
    assert "Page 1 of 3 · 9 flights" in texts(click.edited[-1]["view"])


# ------------------------------------------------------------------ edit search
async def test_edit_opens_a_prefilled_modal_and_bad_input_keeps_the_search():
    bot = Bot()
    s = session_of(bot, await start(bot))
    s.offset = 3
    click = Click(client=bot)
    await bot.handle_travel_click(click, "ed", s.sid)
    (modal,) = click.modals
    assert isinstance(modal, TravelEditModal) and len(modal.children) == 5
    assert {k: f.default for k, f in modal.fields.items()} == {
        "origin": "BKK",
        "destination": "SIN",
        "depart": TUESDAY.isoformat(),
        "adults": "2",
        "cabin": "economy",
    }
    assert all(len(lbl.text) <= 45 for lbl in modal.children) and len(modal.title) <= 45
    assert len(modal.to_dict()["components"]) == 5  # Discord's maximum per modal
    before = s.query
    for bad, problem in (
        ({"adults": "12"}, "Travellers: must be at most 9"),
        ({"destination": "BKK"}, "From and To must be different airports"),
        ({"depart": "3/11/2026"}, "Date: use a date like 2026-11-03"),
        ({"cabin": "first"}, "Cabin: type economy or business"),
        ({"origin": "Bangkok"}, "From: use a 3-letter airport code such as BKK"),
    ):
        await bot.handle_travel_edit(click, s.sid, {**modal_values(modal), **bad})
        assert click.sent[-1] == (t("discord.search.badInput", "en", problem=problem), True)
    assert s.query is before and s.offset == 3 and not click.edited
    await bot.handle_travel_edit(
        click, s.sid, {**modal_values(modal), "adults": "3", "cabin": "Business"}
    )
    assert (s.query.adults, s.query.cabin, s.offset) == (3, "business", 0)
    assert "3 travellers · Business" in texts(click.edited[-1]["view"])


async def test_hotel_modal_submit_reaches_the_bot_with_its_values():
    bot = Bot()
    s = session_of(bot, await start(bot, "hotels"))
    opener = Click(client=bot)
    await bot.handle_travel_click(opener, "ed", s.sid)
    (modal,) = opener.modals
    assert list(modal.fields) == ["city", "check_in", "nights", "rooms", "guests"]
    modal.fields["nights"]._value = "31"
    submit = Click(client=bot)
    await modal.on_submit(submit)
    assert submit.sent == [
        (t("discord.search.badInput", "en", problem="Nights: stay 1 to 30 nights"), True)
    ]
    modal.fields["nights"]._value, modal.fields["guests"]._value = "2", "4"
    await modal.on_submit(submit)
    assert (s.query.nights, s.query.guests) == (2, 4)
    assert "2 nights · 1 room · 4 guests" in texts(submit.edited[-1]["view"])


def modal_values(modal):
    return {k: f.value for k, f in modal.fields.items()}


# ------------------------------------------------------------------ every view of the journey
@pytest.mark.parametrize("lang", ["en", "th", *EXTRA])  # translations must fit too
def test_every_view_of_the_journey_fits_discord(lang):
    sessions = ts.Sessions()
    s = sessions.start("discord:1", "flights", flight_query(FLIGHTS, TODAY, lang)[0])
    views = [results_view(run_search(s, TODAY), s, lang)]
    for act, arg, values in (
        ("ff", "", ["nonstop", "1stop", "morning", "afternoon", "evening"]),
        ("fa", "", ["TG", "SQ", "MH", "VN"]),
        ("fp", "", ["7500"]),
        ("pg", "3", []),
        ("fl", "MH783-MH603-20261020-E", []),
        ("bk", "", []),
    ):
        views.append(travel_click(s, act, arg, values, TODAY, lang))
    h = sessions.start(
        "discord:1", "hotels", hotel_query({**HOTELS, "guests": 4, "rooms": 2}, TODAY, lang)[0]
    )
    views.append(results_view(run_search(h, TODAY), h, lang))
    for act, arg, values in (
        ("hf", "", ["free_cancellation", "breakfast", "stars4", "score8"]),
        ("cl", "", []),
        ("hp", "", ["5000"]),
        ("ho", "orchard-lantern", []),
        ("rm", "orchard-lantern", ["family"]),
    ):
        views.append(travel_click(h, act, arg, values, TODAY, lang))
    for view in views:
        assert_discord_limits(view)
    assert "Family Room with breakfast" in texts(views[-1])
    for session in (s, h):  # the Edit search form: title and labels <= 45, at most 5 inputs
        modal = TravelEditModal(session, lang)
        rows = modal.to_components()
        assert 1 <= len(modal.title) <= 45 and 1 <= len(rows) <= 5
        assert all(1 <= len(r["label"]) <= 45 for r in rows), [r["label"] for r in rows]


# ------------------------------------------------------------------ the chat path (brain -> tool -> cards)
def _named(name):
    def f():
        return {}

    f.__name__ = name
    return f


TRIPS_TOOLS = [_named(n) for n in ("book_trip", "travel_profile", "list_trips")]


@pytest.mark.parametrize("spoken", [False, True])
def test_chat_and_voice_get_the_one_search_next_to_book_trip(spoken):
    bot, guild, me = Bot(), SimpleNamespace(id=GUILD), SimpleNamespace(id=ME)
    tools = bot._travel_card_tools(guild, me, TRIPS_TOOLS, spoken=spoken)
    names = [f.__name__ for f in tools]
    assert len(names) == len(set(names))  # no tool name twice
    assert names == ["book_trip", "travel_profile", "list_trips", "search_flights", "search_hotels"]
    flights = tools[3]
    assert flights.cards is tools[4].cards  # the card tools share one outbox
    res = flights(origin="BKK", destination="SIN", depart_date=TUESDAY.isoformat())
    assert res["top"][0]["booking_ref"].startswith("BKKSIN.")
    assert ("cards" in res["shown"]) is (not spoken) and ("voice" in res["shown"]) is spoken
    off = Bot(travel_on=False)._travel_card_tools(guild, me, TRIPS_TOOLS, spoken=spoken)
    assert off == TRIPS_TOOLS


class Channel:
    def __init__(self, fail=False):
        self.views, self.texts, self.fail = [], [], fail

    async def send(self, text=None, view=None):
        if view is not None and self.fail:
            raise discord.HTTPException(SimpleNamespace(status=400, reason="bad"), "nope")
        (self.views if view is not None else self.texts).append(view or text)


def _chat(bot, uid=ME, **search):
    """What `_agent_kwargs` hands the brain, after the brain called the flight tool."""
    tools = bot._travel_card_tools(SimpleNamespace(id=GUILD), SimpleNamespace(id=uid), [],
                                   spoken=False)  # fmt: skip
    if search:
        assert tools[0](**search)["status"] in ("ok", "need_details")
    return {"extra_tools": tools}, SimpleNamespace(channel=Channel())


ASK = {"origin": "Bangkok", "destination": "Singapore", "depart_date": TUESDAY.isoformat(),
       "travellers": 2, "stops": "nonstop"}  # fmt: skip


async def test_cards_the_brain_searched_follow_the_answer_and_stay_owner_bound():
    bot = Bot()
    agent, message = _chat(bot, **ASK)
    await bot._post_travel_cards(message, SimpleNamespace(id=ME), agent, "en")
    (view,) = message.channel.views
    assert_discord_limits(view)
    body = texts(view)
    assert "Showing" not in body and "9 flights" in body  # the non-stop filter the brain chose
    assert t("discord.search.demoNotice", "en") in body
    assert t("discord.flight.sampleNote", "en") in body
    sid = _match(custom_ids(view)[0])["sid"]
    other = Click(OTHER)
    await bot.handle_travel_click(other, "nx", sid)
    assert other.sent == [(t("discord.search.expired", "en"), True)] and not other.edited
    mine = Click(ME)
    await bot.handle_travel_click(mine, "nx", sid)
    assert mine.edited  # the asker's own buttons work


async def test_a_weather_card_next_to_a_search_is_not_a_travel_search():
    """The weather tool's card shares the reply's card list (`tool_cards`); the travel poster
    leaves it alone (no error line), the weather poster draws it."""
    bot = Bot()
    agent, message = _chat(bot, **ASK)
    weather = SimpleNamespace(__name__="weather", cards=[{"kind": "weather", "place": "Singapore",
                              "lat": 1.29, "lng": 103.85, "days": 3}])  # fmt: skip
    agent["extra_tools"].append(weather)
    await bot._post_travel_cards(message, SimpleNamespace(id=ME), agent, "en")
    assert len(message.channel.views) == 1 and message.channel.texts == []


async def test_a_trip_request_answered_without_a_search_still_posts_cards():
    bot = Bot()
    agent, message = _chat(bot)  # the card tools were offered, the brain called none
    message.content = "<@1> any hotel and flight suggestions for Singapore next Tuesday?"
    await bot._post_travel_cards(message, SimpleNamespace(id=ME), agent, "en")
    assert len(message.channel.views) == 2 and message.channel.texts == []  # flights, then hotels


async def test_a_question_instead_of_a_search_posts_no_cards():
    bot = Bot()
    agent, message = _chat(bot, destination="Singapore")  # need_details: origin and date
    await bot._post_travel_cards(message, SimpleNamespace(id=ME), agent, "en")
    assert message.channel.views == [] and message.channel.texts == []


async def test_a_card_that_cannot_be_sent_becomes_one_short_line():
    bot = Bot()
    agent, message = _chat(bot, **ASK)
    message.channel.fail = True
    await bot._post_travel_cards(message, SimpleNamespace(id=ME), agent, "en")
    assert message.channel.texts == [t("discord.search.cardsFailed", "en")]


async def test_a_failed_answer_to_a_trip_request_offers_the_structured_search():
    bot = Bot()
    trip = "Find a flight from Bangkok to Singapore next week"
    assert bot._travel_fail_hint(GUILD, trip, "en") == t("discord.search.fallbackHint", "en")
    assert bot._travel_fail_hint(GUILD, "What did I miss?", "en") == ""
    assert Bot(travel_on=False)._travel_fail_hint(GUILD, trip, "en") == ""
    edits = []

    async def finish():
        pass

    async def edit(content):
        edits.append(content)

    ack = SimpleNamespace(finish=finish, sent=SimpleNamespace(edit=edit), message=None)
    await SecretaryBot._ack_failed(None, ack, "en", bot._travel_fail_hint(GUILD, trip, "en"))
    assert edits == [t("qa_failed", "en") + "\n" + t("discord.search.fallbackHint", "en")]


def test_results_say_demo_fictional_and_sample():
    bot = Bot()
    s = bot.travel_sessions.start(f"discord:{ME}", "hotels", hotel_query(HOTELS, TODAY, "en")[0])
    body = texts(results_view(run_search(s, TODAY), s, "en"))
    assert t("discord.search.demoNotice", "en") == (
        "Demo results—not live availability or a confirmed booking."
    )
    assert t("discord.search.demoNotice", "en") in body
    assert body.count(t("discord.hotel.sampleNote", "en")) == PAGE
    assert t("discord.hotel.sampleNote", "en") == "Fictional property · Sample rating and reviews"
    assert t("discord.flight.sampleNote", "en") == "Sample itinerary · Sample price"


# ------------------------------------------------------------------ booking: chat and voice, the real bot
def _real(bot, world, spoken):
    """One message's agent kwargs from the real `SecretaryBot._agent_kwargs` (a new request)."""
    member = world.g.members[STAFF]
    msg = bot.room_message(world.g, member, world.pub)
    kw = bot._agent_kwargs(
        msg, world.g, member, False, setting="en", lang="en", question="q", memory=None,
        profile=None, spoken=spoken,
    )  # fmt: skip
    return kw, kw.pop("user_id", STAFF)


def _result(req, name):
    """The last result of tool `name` in the scripted brain's request."""
    for content in reversed(req.contents):
        for part in content.parts or []:
            fr = part.function_response
            if fr is not None and fr.name == name:
                return fr.response


async def _ask(bot, kw, uid, text, model):
    return await qa.ask_async(
        bot.s, bot.store, text, guild_id=BOT_GUILD, is_exec=False, user_id=uid, model=model, **kw
    )


async def test_discord_chat_books_from_the_one_search_then_a_plain_yes(bot, world):
    depart = TUESDAY.isoformat()
    seen = {}

    def answer(name, line):
        def step(req):
            seen[name] = _result(req, name)
            return text_resp(line)

        return step

    # 1. "flights to Singapore": the brain calls THE flight search; the cards follow the answer
    kw, uid = _real(bot, world, spoken=False)
    search = {"origin": "BKK", "destination": "SIN", "depart_date": depart}
    await _ask(bot, kw, uid, "Flights Bangkok to Singapore next Tuesday", scripted(
        fc_resp(("search_flights", search)), answer("search_flights", "SL 106 is the best value.")))  # fmt: skip
    channel = Channel()
    await bot._post_travel_cards(SimpleNamespace(channel=channel), world.g.members[STAFF], kw, "en")
    (view,) = channel.views
    sid = _match(custom_ids(view)[0])["sid"]
    assert bot.travel_sessions.get(sid, f"discord:{STAFF}") is not None  # owner-bound
    assert bot.travel_sessions.get(sid, f"discord:{OTHER}") is None
    ref = seen["search_flights"]["top"][0]["booking_ref"]
    # 2. a later message, "book it": book_trip with the result's booking_ref -> the quote
    kw, uid = _real(bot, world, spoken=False)
    await _ask(bot, kw, uid, f"book {ref}", scripted(
        fc_resp(("book_trip", {"flight_offer_id": ref, "purpose": "Lumen kickoff"})),
        answer("book_trip", "Thai Lion Air SL 106, THB 3,190. Shall I book it?")))  # fmt: skip
    assert seen["book_trip"]["status"] == "needs_confirmation"
    # 3. the person's plain yes is booked by code, never by the model
    kw, uid = _real(bot, world, spoken=False)
    ans = await _ask(bot, kw, uid, "yes", object())
    assert ans.rounds == 0 and ans.tool_calls == [("book_trip", {})]
    assert ans.text.startswith("Booked!") and "sandbox booking" in ans.text
    listed = {f.__name__: f for f in _real(bot, world, False)[0]["extra_tools"]}["list_trips"]()
    booked = listed["trips"][0]
    assert booked["references"]["flight"] in ans.text and booked["flights"] == ["SL106"]
    record = bot.docs.get(trips.TRIP_KIND, BOT_GUILD, booked["id"])
    (receipt,) = [bot.store.get(i) for i in record["receipt_ids"]]
    assert receipt.category == "ค่าเดินทาง" and receipt.vendor == "Thai Lion Air"
    assert receipt.total == seen["search_flights"]["top"][0]["total_for_all_travellers"]


async def test_voice_books_with_the_same_search_spoken_not_drawn(bot, world):
    kw, _ = _real(bot, world, spoken=True)
    tools = {f.__name__: f for f in kw["extra_tools"]}
    res = tools["search_flights"](origin="BKK", destination="SIN", depart_date=TUESDAY.isoformat())
    assert "voice" in res["shown"] and "cards" not in res["shown"]  # spoken, not drawn
    ref = res["top"][0]["booking_ref"]
    assert tools["book_trip"](ref, purpose="client visit")["status"] == "needs_confirmation"
    later = {f.__name__: f for f in _real(bot, world, spoken=True)[0]["extra_tools"]}
    assert later["book_trip"].on_confirm("Go ahead and book it for the visit") is None  # heard
    done = later["book_trip"](ref, purpose="client visit")  # the next message: confirmed
    assert done["status"] == "booked" and done["provider"] == "sample"
    assert done["totals"] == [
        {"amount": res["top"][0]["total_for_all_travellers"], "currency": "THB"}
    ]


def test_fare_and_stay_reviews_say_how_to_book_in_the_sandbox():
    s = Bot().travel_sessions.start(
        f"discord:{ME}", "flights", flight_query(FLIGHTS, TODAY, "en")[0]
    )
    first = run_search(s, TODAY)["results"][0]
    fare = texts(travel_click(s, "fl", first["id"], [], TODAY, "en"))
    assert t("discord.search.bookHint", "en", ref=first["booking_ref"]) in fare
    h = Bot().travel_sessions.start(f"discord:{ME}", "hotels", hotel_query(HOTELS, TODAY, "en")[0])
    stay = texts(travel_click(h, "rm", "orchard-lantern", ["superior-twin-bb"], TODAY, "en"))
    assert "SIN.orchard-lantern.superior-twin-bb." in stay and "`book SIN." in stay


# ------------------------------------------------------------------ booking straight from the cards
FRIDAY = TUESDAY + timedelta(days=3)


def _as(world, member):  # noqa: F811
    """A component click by a real member of the real bot's server."""
    c = Click(member.id)
    c.user, c.guild = member, world.g
    return c


def _searches(bot, owner):
    """The person's three cards: the way out, the way back, Singapore hotels."""
    out = bot.travel_sessions.start(owner, "flights", ts.FlightQuery(depart=TUESDAY, adults=2))
    back = bot.travel_sessions.start(owner, "flights", ts.FlightQuery(
        origin="SIN", destination="BKK", depart=FRIDAY, adults=2))  # fmt: skip
    stay = bot.travel_sessions.start(owner, "hotels", ts.HotelQuery(
        check_in=TUESDAY, check_out=FRIDAY, guests=2))  # fmt: skip
    for x in (out, back, stay):
        x.extra["lang"] = "en"
    return out, back, stay


def _trips_of(bot, world):  # noqa: F811
    return {f.__name__: f for f in _real(bot, world, False)[0]["extra_tools"]}["list_trips"]()


async def test_book_straight_from_the_cards_one_trip_for_the_picks(bot, world):  # noqa: F811
    me, owner = world.g.members[STAFF], f"discord:{STAFF}"
    out, back, stay = _searches(bot, owner)
    first_out = run_search(out, TODAY)["results"][0]
    first_back = run_search(back, TODAY)["results"][0]
    for x, act, arg, values in ((out, "fl", first_out["id"], []), (back, "fl", first_back["id"], []),
                                (stay, "ho", "harbourlight", []),
                                (stay, "rm", "harbourlight", ["deluxe-king"])):  # fmt: skip
        await bot.handle_travel_click(_as(world, me), act, x.sid, arg, values)
    picked = bot.travel_trips.picked(owner)
    assert picked == {"flight": first_out["booking_ref"], "return": first_back["booking_ref"],
                      "room": picked["room"]} and ".deluxe-king." in picked["room"]  # fmt: skip
    # Book in sandbox on the stay review: a NEW ephemeral message quoting all three picks
    c = _as(world, me)
    await bot.handle_travel_click(c, "bq", stay.sid)
    ((quote, ephemeral),) = c.views
    assert ephemeral and not c.edited  # the card itself is not touched
    assert_discord_limits(quote)
    assert any(":bw:" in cid for cid in custom_ids(quote))  # "What to book": three picks
    room = ts.by_booking_ref(picked["room"], TODAY)["room"]["price"]["total"]
    legs = first_out["price"]["total"] + first_back["price"]["total"]
    plain = texts(quote).replace("**", "")
    assert first_out["flights"][0] in plain and "Way back" in plain and "Harbourlight" in plain
    assert f"Total THB {legs + room:,}" in plain and "Nothing is booked until you confirm" in plain
    # drop the room: the quote is redone, nothing booked yet
    c = _as(world, me)
    await bot.handle_travel_click(c, "bw", stay.sid, "", ["flight", "return"])
    plain = texts(c.edited[-1]["view"]).replace("**", "")
    assert f"Total THB {legs:,}" in plain and "Harbourlight" not in plain
    assert not _trips_of(bot, world)["trips"]
    # Confirm booking: book_trip as the person -> ONE trip, out and back merged
    c = _as(world, me)
    await bot.handle_travel_click(c, "bc", stay.sid)
    assert c.deferred == [{}]
    plain = texts(c.original[-1]["view"]).replace("**", "")
    assert "Booked in the sandbox" in plain and "no money is charged" in plain
    assert f"Total THB {legs:,}" in plain and "Online check-in reminder" in plain
    assert "Receipts filed in the expense ledger under Travel: 1" in plain
    (trip,) = _trips_of(bot, world)["trips"]
    legs_booked = [x.replace(" ", "") for x in first_out["flights"] + first_back["flights"]]
    assert trip["flights"] == legs_booked and trip["references"]["flight"] in plain
    record = bot.docs.get(trips.TRIP_KIND, world.g.id, trip["id"])
    assert record["return_date"] == FRIDAY.isoformat() and record["reminder_id"]
    (receipt,) = [bot.store.get(i) for i in record["receipt_ids"]]
    assert receipt.total == legs and receipt.category == "ค่าเดินทาง"
    assert bot.travel_trips.picked(owner) == {"room": picked["room"]}  # booked picks cleared
    # the same Confirm again: nothing waits any more -> the expired line, no second booking
    c = _as(world, me)
    await bot.handle_travel_click(c, "bc", stay.sid)
    assert c.sent == [(t("discord.search.expired", bot._interaction_lang(c)), True)]
    assert len(_trips_of(bot, world)["trips"]) == 1


async def test_nobody_else_can_quote_or_confirm_my_booking(bot, world):  # noqa: F811
    me = world.g.members[STAFF]
    other = next(m for uid, m in world.g.members.items() if uid != STAFF)
    out, _, _ = _searches(bot, f"discord:{STAFF}")
    first = run_search(out, TODAY)["results"][0]
    await bot.handle_travel_click(_as(world, me), "fl", out.sid, first["id"])
    await bot.handle_travel_click(_as(world, me), "bq", out.sid)
    for act in ("bq", "bw", "bc", "bx"):
        c = _as(world, other)
        await bot.handle_travel_click(c, act, out.sid, "", ["flight"])
        assert c.sent == [(t("discord.search.expired", bot._interaction_lang(c)), True)]
        assert not (c.views or c.edited or c.original or c.deferred)
    c = _as(world, me)
    await bot.handle_travel_click(c, "bq", "deadbeef")  # unknown, or the bot restarted
    assert c.sent == [(t("discord.search.expired", bot._interaction_lang(c)), True)]
    c = _as(world, me)
    await bot.handle_travel_click(c, "bx", out.sid)  # Cancel: nothing booked, the pick kept
    assert texts(c.edited[-1]["view"]) == t("discord.book.cancelled", "en")
    assert bot.travel_trips.picked(f"discord:{STAFF}") == {"flight": first["booking_ref"]}
    assert not _trips_of(bot, world)["trips"]


@pytest.mark.parametrize("lang", ["en", "th", *EXTRA])
def test_the_booking_views_fit_discord(lang):
    sessions = ts.Sessions()
    s = sessions.start("discord:1", "flights", ts.FlightQuery(depart=TUESDAY, adults=2))
    out = ts.search_flights(
        ts.FlightQuery(depart=TUESDAY, adults=2), ts.FlightFilters(sort="fastest")
    )
    back = ts.search_flights(
        ts.FlightQuery(origin="SIN", destination="BKK", depart=FRIDAY, adults=2)
    )
    stay = ts.HotelQuery(check_in=TUESDAY, check_out=FRIDAY, rooms=2, guests=4)
    room = ts.hotel_rooms(stay, "orchard-lantern", TODAY)["rooms"][-1]
    picked = {"flight": out["results"][0]["booking_ref"], "return": back["results"][-1]["booking_ref"],
              "room": room["booking_ref"]}  # fmt: skip
    items = booking_items(picked, TODAY)
    assert set(items) == {"flight", "return", "room"}
    assert_discord_limits(quote_view(s, items, list(items), lang))
    assert_discord_limits(quote_view(s, items, [], lang))  # nothing chosen: Confirm disabled
    done = {"status": "booked", "trip_id": "T-1234abcd", "filed_receipts": [1, 2],
            "references": {"flight": "ABC234", "hotel": "XYZ98765"}, "checkin_reminder": "R-0001",
            "totals": [{"amount": 37910.0, "currency": "THB"}]}  # fmt: skip
    assert_discord_limits(booked_view(done, items, s, lang))
    for problem in ("expired", "refused", "failed"):
        assert_discord_limits(booked_view({"status": problem, "reason": "approval_pending"},
                                          items, s, lang))  # fmt: skip


async def test_a_chat_yes_after_a_card_quote_or_booking_books_nothing(bot, world):  # noqa: F811
    """The card quote never calls book_trip, and the card's Confirm uses up its own quote: a plain
    "yes" typed in chat afterwards must not book anything (reported as a possible quirk)."""
    me, owner = world.g.members[STAFF], f"discord:{STAFF}"
    out, _, _ = _searches(bot, owner)
    first = run_search(out, TODAY)["results"][0]
    await bot.handle_travel_click(_as(world, me), "fl", out.sid, first["id"], [])
    await bot.handle_travel_click(_as(world, me), "bq", out.sid)  # the card's quote
    kw, uid = _real(bot, world, spoken=False)
    ans = await _ask(bot, kw, uid, "yes", scripted(text_resp("Nothing to confirm.")))
    assert ans.text == "Nothing to confirm." and not _trips_of(bot, world)["trips"]
    await bot.handle_travel_click(_as(world, me), "bc", out.sid)  # Confirm on the card
    assert len(_trips_of(bot, world)["trips"]) == 1
    kw, uid = _real(bot, world, spoken=False)
    ans = await _ask(bot, kw, uid, "yes", scripted(text_resp("Nothing to confirm.")))
    assert ans.text == "Nothing to confirm." and len(_trips_of(bot, world)["trips"]) == 1
