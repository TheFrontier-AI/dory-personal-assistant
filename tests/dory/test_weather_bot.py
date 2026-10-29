# ruff: noqa: F811, F402 - the real bot's `bot` fixture is imported next to local `bot` fakes
"""The Discord weather card: posted under a chat answer when the brain called `weather`, and
`/dory weather`; 3 / 5 days and Refresh for the owner only. Offline: the fake Open-Meteo of
test_weather_cards and fake interactions."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import discord
from conftest import FixedClockSettings
from discord import app_commands
from test_coordinator import STAFF, world  # noqa: F401 - the real bot's fixtures
from test_modes import bot  # noqa: F401
from test_weather_cards import Net

from dory.bot import SecretaryBot
from dory.i18n import t
from dory.travel_search_bot import TravelSearchMixin
from dory.weather import WeatherCtx, build_weather_tools
from dory.weather_bot import WeatherButton, WeatherCardMixin, card_blocks, find_place

ZONE = ZoneInfo("Asia/Bangkok")
NOW = datetime(2026, 10, 29, 15, 0, tzinfo=ZONE)
GUILD, ME, OTHER = 42, 1001, 2002
TEMPLATE = WeatherButton.__discord_ui_compiled_template__
CREDIT = "[Weather data by Open-Meteo.com (CC BY 4.0)](https://open-meteo.com/)"


# ------------------------------------------------------------------ fakes
class Bot(TravelSearchMixin, WeatherCardMixin):
    def __init__(self, net=None, maps_on=True, lang="en"):
        self.s, self.lang, self.dynamic = FixedClockSettings(), lang, []
        self.svc = (net or Net()).service()
        self.team = SimpleNamespace(current=lambda gid: None, enabled=lambda gid, f: maps_on)

    def _weather_service(self):
        return self.svc

    def _interaction_lang(self, interaction):
        return self.lang

    def add_dynamic_items(self, *items):
        self.dynamic += items


class Channel:
    def __init__(self, fail=False):
        self.views, self.texts, self.fail, self.mentions = [], [], fail, []

    async def send(self, text=None, view=None, allowed_mentions=None):
        if view is not None and self.fail:
            raise discord.HTTPException(SimpleNamespace(status=400, reason="bad"), "nope")
        (self.views if view is not None else self.texts).append(view or text)
        self.mentions.append(allowed_mentions)


class Click:
    """A slash command or button interaction by user `uid`."""

    def __init__(self, uid=ME, client=None):
        self.user, self.client = SimpleNamespace(id=uid), client
        self.guild, self.channel, self.locale = SimpleNamespace(id=GUILD), SimpleNamespace(id=7), ""
        self.deferred, self.sent, self.followups, self.original = [], [], [], []

        async def defer(**kw):
            self.deferred.append(kw)

        async def send_message(text=None, ephemeral=False):
            self.sent.append((text, ephemeral))

        async def followup_send(text, ephemeral=False):
            self.followups.append((text, ephemeral))

        async def edit_original_response(**kw):
            self.original.append(kw)

        self.response = SimpleNamespace(defer=defer, send_message=send_message)
        self.followup = SimpleNamespace(send=followup_send)
        self.edit_original_response = edit_original_response


def weather_tool(net=None, lang="en"):
    (weather,) = build_weather_tools(
        WeatherCtx((net or Net()).service(), None, lang, ZONE, lambda: NOW)
    )
    return weather


async def chat_card(bot, lang="en", when="now"):
    """What follows a typed answer whose brain asked for the weather in Singapore."""
    weather = weather_tool(lang=lang)
    assert "shown" in weather("Singapore", when=when)
    channel = Channel()
    await bot._post_weather_card(
        SimpleNamespace(channel=channel), SimpleNamespace(id=ME), {"extra_tools": [weather]}, lang
    )
    return channel


def walk(components):
    for c in components:
        yield c
        yield from walk(c.get("components", []))


def texts(view):
    return "\n".join(c["content"] for c in walk(view.to_components()) if c["type"] == 10)


def buttons(view):
    """Buttons by act: {act: component}."""
    return {
        TEMPLATE.fullmatch(c["custom_id"])["act"]: c
        for c in walk(view.to_components())
        if c["type"] == 2
    }


def sid_of(view):
    (sid,) = {TEMPLATE.fullmatch(c["custom_id"])["sid"] for c in walk(view.to_components())
              if "custom_id" in c}  # fmt: skip
    return sid


def assert_discord_limits(view):
    """What https://discord.com/developers/docs/components/reference allows a V2 message."""
    assert view.has_components_v2() and view.timeout is None
    assert view.total_children_count <= 40 and view.content_length() <= 4000
    ids = [c["custom_id"] for c in walk(view.to_components()) if "custom_id" in c]
    assert len(ids) == len(set(ids)) == 3
    for cid in ids:
        assert len(cid) <= 100 and TEMPLATE.fullmatch(cid), cid
    for c in walk(view.to_components()):
        if c["type"] == 1:
            kinds = [x["type"] for x in c["components"]]
            assert set(kinds) == {2} and len(kinds) <= 5, kinds
        if c["type"] == 2:
            assert 1 <= len(c["label"]) <= 80
        if c["type"] == 17:
            assert c["accent_color"] == 0x4A4FBF


# ------------------------------------------------------------------ the card under a chat answer
async def test_a_chat_answer_that_asked_for_the_weather_gets_one_card():
    bot = Bot()
    channel = await chat_card(bot)
    (view,) = channel.views
    assert channel.texts == []
    assert_discord_limits(view)
    shown = texts(view)
    assert shown.startswith("## Weather · Singapore\n")  # the place the brain asked about
    assert "Local time Thu 29 Oct · 16:00" in shown
    assert "🌦️ 31°C · Slight rain showers" in shown  # the emoji never stands alone
    assert "Feels like 36°C · Humidity 74% · Wind 10 km/h · Rain 55%" in shown
    assert "**Thu 29 Oct** 🌦️ Slight rain showers · 32° / 26°C · Rain 55%" in shown
    assert "**Sat 31 Oct** ⛈️ Thunderstorm · 30° / 25°C · Rain 80%" in shown
    assert "Sun 1 Nov" not in shown  # 3 days
    assert t("discord.weather.tip.storm", "en", day="Sat 31 Oct") in shown
    assert t("discord.weather.estimate", "en") in shown
    assert CREDIT in shown  # the licence's attribution, linked
    (allowed,) = channel.mentions  # the place is the brain's words: never a ping
    assert not (allowed.everyone or allowed.users or allowed.roles)
    b = buttons(view)
    assert b["d3"]["disabled"] and not b["d5"].get("disabled") and not b["rf"].get("disabled")
    s = bot.weather_sessions.get(sid_of(view), f"discord:{ME}")
    assert (s.query["place"], s.query["lat"], s.query["lng"]) == ("Singapore", 1.2897, 103.8501)
    assert s.extra == {"days": 3, "lang": "en"}
    assert bot.weather_sessions.get(sid_of(view), f"discord:{OTHER}") is None  # owner-bound


async def test_a_day_four_days_out_opens_on_the_five_day_card():
    channel = await chat_card(Bot(), when="2026-11-02")
    (view,) = channel.views
    assert "Mon 2 Nov" in texts(view) and buttons(view)["d5"]["disabled"]


async def test_no_card_when_no_weather_tool_ran_or_it_failed():
    bot = Bot()
    channel = Channel()
    message, me = SimpleNamespace(channel=channel), SimpleNamespace(id=ME)
    await bot._post_weather_card(message, me, {"extra_tools": []}, "en")
    await bot._post_weather_card(message, me, {}, "en")
    failed = weather_tool(Net(places=()))
    assert failed("Atlantis")["error"] == "place_not_found"
    await bot._post_weather_card(message, me, {"extra_tools": [failed]}, "en")
    assert channel.views == [] and channel.texts == []
    assert not bot.weather_sessions._items


async def test_a_forecast_that_cannot_load_is_one_short_line_never_a_failed_reply():
    channel = await chat_card(Bot(Net(down=True)))
    assert channel.views == [] and channel.texts == [t("discord.weather.failed", "en")]
    assert "/dory weather" in t("discord.weather.failed", "en")
    bot, weather, channel = Bot(), weather_tool(), Channel(fail=True)  # Discord refuses the card
    weather("Singapore")
    await bot._post_weather_card(SimpleNamespace(channel=channel), SimpleNamespace(id=ME),
                                 {"extra_tools": [weather]}, "en")  # fmt: skip
    assert channel.texts == [t("discord.weather.failed", "en")]


async def test_thai_card_words_the_condition_in_thai():
    channel = await chat_card(Bot(lang="th"), lang="th")
    (view,) = channel.views
    assert_discord_limits(view)
    shown = texts(view)
    assert "Slight rain showers" not in shown and "Thunderstorm" not in shown
    assert f"🌦️ 31°C · {t('discord.weather.sky.showers', 'th')}" in shown
    assert f"⛈️ {t('discord.weather.sky.storm', 'th')}" in shown
    assert "**พฤ. 29 ต.ค.**" in shown and "รู้สึกเหมือน 36°C" in shown
    assert t("discord.weather.tip.storm", "th", day="ส. 31 ต.ค.") in shown
    assert CREDIT in shown  # the attribution stays as the licence words it
    assert buttons(view)["d5"]["label"] == t("discord.weather.days", "th", count=5)


def test_a_card_from_google_weather_has_no_icons_local_time_or_credit():
    card = {"kind": "weather", "place": "Office", "local_time": "", "timezone": "",
            "current": {"condition": "Cloudy", "temp_c": 30.4},
            "days": [{"date": "2026-10-29", "condition": "Rain", "temp_c": 31, "rain_pct": 70}],
            "tip": {"key": "umbrella", "day": "2026-10-29"},
            "source": "Google Weather (WeatherNext)", "credit": "", "estimate": True}  # fmt: skip
    shown = "\n".join(card_blocks(card, "th"))
    assert "### 30°C · Cloudy" in shown  # no icon key: no emoji, the service's own words
    assert "**พฤ. 29 ต.ค.** Rain · 31°C · โอกาสฝน 70%" in shown
    assert "เวลาท้องถิ่น" not in shown and "open-meteo" not in shown
    assert "-# Google Weather (WeatherNext)" in shown


def test_a_typed_place_is_found_by_either_geocoder():
    svc = Net().service()
    assert find_place(svc, "Singapore", "en") == {
        "label": "Singapore, Singapore", "lat": 1.28967, "lng": 103.85007,
    }  # fmt: skip
    google = SimpleNamespace(geo=SimpleNamespace(locate=lambda text, lang: (13.7, 100.5)))
    assert find_place(google, " Bangkok ", "en") == {"label": "Bangkok", "lat": 13.7, "lng": 100.5}
    nowhere = SimpleNamespace(geo=SimpleNamespace(locate=lambda text, lang: None))
    assert find_place(nowhere, "Atlantis", "en") is None
    assert find_place(Net(places=()).service(), "Atlantis", "en") is None


# ------------------------------------------------------------------ the buttons
async def test_five_days_then_three_then_refresh_edit_the_owners_card():
    bot = Bot()
    sid = sid_of((await chat_card(bot)).views[0])
    mine = Click(ME)
    await bot.handle_weather_click(mine, "d5", sid)
    assert mine.deferred == [{}] and not mine.followups
    view = mine.original[-1]["view"]
    assert_discord_limits(view)
    assert "Mon 2 Nov" in texts(view) and buttons(view)["d5"]["disabled"]
    assert not buttons(view)["d3"].get("disabled") and sid_of(view) == sid
    await bot.handle_weather_click(mine, "d3", sid)
    assert "Sun 1 Nov" not in texts(mine.original[-1]["view"])
    await bot.handle_weather_click(mine, "rf", sid)
    view = mine.original[-1]["view"]
    assert len(mine.original) == 3 and buttons(view)["d3"]["disabled"]  # refresh keeps 3 days


async def test_another_person_or_an_old_card_gets_one_private_line():
    bot = Bot()
    sid = sid_of((await chat_card(bot)).views[0])
    other = Click(OTHER)
    await bot.handle_weather_click(other, "d5", sid)
    assert other.sent == [(t("discord.weather.expired", "en"), True)]
    assert not other.deferred and not other.original
    assert bot.weather_sessions.get(sid, f"discord:{ME}").extra["days"] == 3  # untouched
    gone = Click(ME)
    await bot.handle_weather_click(gone, "rf", "deadbeef00")
    assert gone.sent == [(t("discord.weather.expired", "en"), True)]


async def test_a_refresh_that_fails_says_so_privately_and_the_card_stays():
    bot = Bot()
    sid = sid_of((await chat_card(bot)).views[0])
    bot.svc = Net(down=True).service()
    mine = Click(ME)
    await bot.handle_weather_click(mine, "d5", sid)
    assert mine.followups == [(t("discord.weather.refreshFailed", "en"), True)]
    assert mine.original == []  # the old card is not edited
    assert bot.weather_sessions.get(sid, f"discord:{ME}").extra["days"] == 3


async def test_buttons_rebuild_from_their_custom_ids_and_reach_the_bot():
    bot = Bot()
    view = (await chat_card(bot)).views[0]
    cid = buttons(view)["d5"]["custom_id"]
    click = Click(ME, client=bot)
    item = SimpleNamespace(label="5 days")
    button = await WeatherButton.from_custom_id(click, item, TEMPLATE.fullmatch(cid))
    assert (button.act, button.sid, button.item.custom_id) == ("d5", sid_of(view), cid)
    await button.callback(click)
    assert "Mon 2 Nov" in texts(click.original[-1]["view"])


# ------------------------------------------------------------------ /dory weather
async def test_slash_weather_defers_then_one_private_card():
    bot = Bot()
    click = Click(ME)
    await bot.handle_weather_command(click, "Singapore", 5)
    assert click.deferred == [{"ephemeral": True, "thinking": True}] and not click.followups
    ((kw),) = click.original
    assert kw["content"] is None
    assert_discord_limits(kw["view"])
    shown = texts(kw["view"])
    assert "Weather · Singapore, Singapore" in shown and "Mon 2 Nov" in shown
    s = bot.weather_sessions.get(sid_of(kw["view"]), f"discord:{ME}")
    assert s.extra == {"days": 5, "lang": "en"}


async def test_slash_weather_place_not_found_off_or_down_is_one_private_line():
    click = Click(ME)
    await Bot(Net(places=())).handle_weather_command(click, "Atlantis", 3)
    assert click.followups == [(t("discord.weather.notFound", "en", place="Atlantis"), True)]
    for bot in (Bot(maps_on=False), Bot()):
        if bot.team.enabled(GUILD, "maps"):
            bot.svc = None  # DORY_WEATHER_PROVIDER=off
        click = Click(ME)
        await bot.handle_weather_command(click, "Singapore", 3)
        assert click.followups == [(t("discord.weather.off", "en"), True)] and not click.original
    click = Click(ME)
    await Bot(Net(down=True)).handle_weather_command(click, "Singapore", 3)
    assert click.followups == [(t("discord.weather.failed", "en"), True)] and not click.original


def test_weather_joins_the_dory_group_with_short_bilingual_descriptions():
    bot = Bot()
    bot.tree = app_commands.CommandTree(discord.Client(intents=discord.Intents.none()))
    bot._register_travel_search_commands()
    group = bot.tree.get_command("dory")
    subs = {c.name: c for c in group.commands}
    assert set(subs) == {"flights", "hotels", "weather"} and group.guild_only
    params = {p.name: p for p in subs["weather"].parameters}
    assert list(params) == ["place", "days"]
    assert params["place"].required and params["days"].default == 3
    assert [c.value for c in params["days"].choices] == [3, 5]
    for x in (group, subs["weather"], *params.values()):
        assert 1 <= len(x.description) <= 100
    assert bot.dynamic == [WeatherButton]  # old cards' buttons answer after a restart


def test_secretary_bot_carries_the_mixin():
    assert issubclass(SecretaryBot, WeatherCardMixin)


async def test_the_real_bots_weather_tool_feeds_its_card(bot, world):
    svc = Net().service()
    bot._weather_service = lambda: svc  # the fake Open-Meteo instead of the network
    member = world.g.members[STAFF]
    kw = bot._agent_kwargs(
        bot.room_message(world.g, member, world.pub), world.g, member, False, setting="en",
        lang="en", question="q", memory=None, profile=None, spoken=False,
    )  # fmt: skip
    (weather,) = [f for f in kw["extra_tools"] if f.__name__ == "weather"]
    assert "shown" in weather("Singapore")
    channel = Channel()
    await bot._post_weather_card(SimpleNamespace(channel=channel), member, kw, "en")
    (view,) = channel.views
    assert_discord_limits(view)
    assert bot.weather_sessions.get(sid_of(view), f"discord:{STAFF}") is not None
