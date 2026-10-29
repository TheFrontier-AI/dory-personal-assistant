"""Discord half of the weather card: the card under a typed chat answer when Dory's brain called
the `weather` tool, and `/dory weather place:<text> days:<3|5>` (ephemeral, like flights/hotels).

The forecast is `weather.weather_card` (shared with the web card) from the bot's one forecast
source, `MapsMixin._weather_service`; this module only words it for Discord (`card_blocks`, pure)
and keeps each card's place in a `travel_search.Sessions` of its own (owner `discord:<user id>`,
process memory, 30 minutes from the last use), so 3 days / 5 days / Refresh work for the owner and
everybody else (or a click after a restart or the TTL) gets one private line.

Same look and rules as the travel cards (`travel_search_bot`): Components V2 `LayoutView(timeout=
None)` in Dory's accent, `DynamicItem` buttons with custom ids `dory:wx:<act>:<session id>`. A
forecast that cannot load never fails the reply: one short catalog line instead, and a refresh
that fails says so privately while the old card stays. The Open-Meteo credit (CC BY 4.0) is always
shown, linked: it is the licence's condition.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging

import discord
from discord import app_commands, ui

from .gmaps import MapsError
from .i18n import t
from .travel_search import Session, Sessions, tool_cards
from .travel_search_bot import ACCENT, _view, day
from .weather import weather_card

logger = logging.getLogger(__name__)

PREFIX = "dory:wx"
CREDIT_URL = "https://open-meteo.com/"  # only Open-Meteo's cards carry a credit
ICONS = {"sun": "☀️", "cloud-sun": "⛅", "cloud": "☁️", "fog": "🌫️", "drizzle": "🌦️",
         "rain": "🌧️", "showers": "🌦️", "snow": "🌨️", "storm": "⛈️"}  # fmt: skip
DAYS = {"d3": 3, "d5": 5}


# ----------------------------------------------------------------------------- wording (pure)
def _deg(v) -> str:
    return str(round(v))


def _join(sep: str, *parts: str) -> str:
    return sep.join(x for x in parts if x)


def sky(row: dict, lang: str) -> tuple[str, str]:
    """(emoji, condition words); the emoji is never shown without the words. English keeps the
    forecast's own words; any other language words it by icon key from the catalog (`t` falls
    back to English, never Thai). No icon key (Google Weather) = the service's words, no emoji."""
    icon = row.get("icon")
    words = row.get("condition") or ""
    if icon in ICONS and (lang != "en" or not words):
        words = t(f"discord.weather.sky.{icon}", lang)
    return ICONS.get(icon, ""), words


def card_blocks(card: dict, lang: str) -> tuple[str, str, str]:
    """`weather.weather_card` as three text blocks: the place and now, the day rows, the tip with
    the estimate label and the source credit. A missing value just drops its item."""
    cur = card.get("current") or {}
    head = [f"## {t('discord.weather.heading', lang, place=card['place'])}"]
    local = card.get("local_time") or ""
    if len(local) >= 16:  # "2026-10-29T16:00", the place's own clock
        when = t("discord.weather.localTime", lang, day=day(local, lang), time=local[11:16])
        head.append(f"-# {when}")
    emoji, words = sky(cur, lang)
    temp = f"{_deg(cur['temp_c'])}°C" if cur.get("temp_c") is not None else ""
    head.append(f"### {_join(' ', emoji, _join(' · ', temp, words))}")
    readings = [
        ("feels_c", "feelsLike", "temp"),
        ("humidity", "humidity", "pct"),
        ("wind_kmh", "wind", "speed"),
        ("rain_pct", "rainChance", "pct"),
    ]
    got = [t(f"discord.weather.{key}", lang, **{arg: _deg(cur[k])}) for k, key, arg in readings
           if cur.get(k) is not None]  # fmt: skip
    if got:
        head.append(_join(" · ", *got))
    rows = []
    for d in card.get("days") or []:
        high, low = d.get("temp_c"), d.get("min_c")
        temps = f"{_deg(high)}° / {_deg(low)}°C" if None not in (high, low) else (
            f"{_deg(high)}°C" if high is not None else ""
        )  # fmt: skip
        rain = (
            t("discord.weather.rainChance", lang, pct=_deg(d["rain_pct"]))
            if d.get("rain_pct") is not None
            else ""
        )
        rows.append(_join(" · ", _join(" ", f"**{day(d['date'], lang)}**", *sky(d, lang)), temps,
                          rain))  # fmt: skip
    tip = card.get("tip") or {}
    foot = []
    if tip.get("key"):
        when = day(tip["day"], lang) if tip.get("day") else ""
        foot.append("💡 " + t(f"discord.weather.tip.{tip['key']}", lang, day=when))
    foot.append(f"-# {t('discord.weather.estimate', lang)}")
    if card.get("credit"):
        foot.append(f"-# [{card['credit']}]({CREDIT_URL})")
    elif card.get("source"):
        foot.append(f"-# {card['source']}")
    return "\n".join(head), "\n".join(rows), "\n".join(foot)


def find_place(service, text: str, lang: str) -> dict | None:
    """{label, lat, lng} for typed text. Open-Meteo's geocoder names the place it found; Google's
    (`gmaps.Geocoder`) only locates, so the typed text is the label. None = nothing matched."""
    geo = service.geo
    if hasattr(geo, "find"):
        got = geo.find(text, lang)
        return {"label": got["label"], "lat": got["lat"], "lng": got["lng"]} if got else None
    at = geo.locate(text, lang)
    return {"label": text.strip(), "lat": at[0], "lng": at[1]} if at else None


# ----------------------------------------------------------------------------- components
class WeatherButton(
    ui.DynamicItem[ui.Button], template=PREFIX + r":(?P<act>d3|d5|rf):(?P<sid>[0-9a-f]{4,32})"
):
    """3 days, 5 days, Refresh."""

    def __init__(self, act: str, sid: str, label: str = "", *, disabled: bool = False) -> None:
        super().__init__(
            ui.Button(
                label=(label or act)[:80],
                style=discord.ButtonStyle.secondary,
                custom_id=f"{PREFIX}:{act}:{sid}",
                disabled=disabled,
            )
        )
        self.act, self.sid = act, sid

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(match["act"], match["sid"], getattr(item, "label", "") or "")

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.client.handle_weather_click(interaction, self.act, self.sid)


def weather_view(card: dict, s: Session, lang: str) -> ui.LayoutView:
    """One card: place and now, the day rows, the tip and credit, then the buttons."""
    head, rows, foot = card_blocks(card, lang)
    shown = len(card.get("days") or [])
    buttons = [
        WeatherButton(act, s.sid, t("discord.weather.days", lang, count=n), disabled=shown == n)
        for act, n in DAYS.items()
    ]
    buttons.append(WeatherButton("rf", s.sid, "↻ " + t("discord.weather.refresh", lang)))
    parts = [ui.TextDisplay(head), ui.Separator()]
    if rows:
        parts += [ui.TextDisplay(rows), ui.Separator()]
    parts += [ui.TextDisplay(foot), ui.ActionRow(*buttons)]
    return _view(ui.Container(*parts, accent_colour=ACCENT))


# ----------------------------------------------------------------------------- the mixin
class WeatherCardMixin:
    """The weather card under a chat answer and `/dory weather` for `SecretaryBot` (needs
    `MapsMixin._weather_service`; the guild's `maps` flag, like the weather tool)."""

    @functools.cached_property
    def weather_sessions(self) -> Sessions:
        return Sessions()  # its own store: a weather id never reaches the travel clicks

    def _weather_session(self, owner: str, place: str, lat, lng, days: int, lang: str) -> Session:
        # kind "weather" + a dict query; the default filters Sessions adds are never read
        s = self.weather_sessions.start(owner, "weather", {"place": place, "lat": lat, "lng": lng})
        s.extra.update(days=5 if days >= 5 else 3, lang=lang)
        return s

    async def _weather_card_view(self, s: Session, days: int) -> ui.LayoutView:
        """The card for the session's place, read off the event loop. Raises when it cannot load
        (MapsError from the service, or the forecast turned off since)."""
        service = self._weather_service()
        if service is None:
            raise MapsError("maps_unavailable", "weather off")
        q, lang = s.query, s.extra["lang"]
        card = await asyncio.to_thread(
            weather_card, service, q["place"], q["lat"], q["lng"], lang, days
        )
        return weather_view(card, s, lang)

    # ------------------------------------------------------------------ chat
    async def _post_weather_card(self, message, member, agent: dict, lang: str) -> None:
        """After the reply: one card for the place the brain's `weather` call answered (typed chat
        only: voice records none). A failure is logged by type and told in one short line."""
        cards = [c for c in tool_cards(agent.get("extra_tools") or []) if c["kind"] == "weather"]
        if not cards:
            return
        c = cards[-1]
        try:
            s = self._weather_session(f"discord:{member.id}", c["place"], c["lat"], c["lng"],
                                      c["days"], lang)  # fmt: skip
            view = await self._weather_card_view(s, s.extra["days"])
            # the place label is the brain's (or a remembered place's) words: never a ping
            await message.channel.send(view=view, allowed_mentions=discord.AllowedMentions.none())
        except Exception as e:  # the answer is already out: never fail the reply for the card
            logger.warning("weather card not sent: %s", type(e).__name__)
            with contextlib.suppress(discord.HTTPException):
                await message.channel.send(t("discord.weather.failed", lang))

    # ------------------------------------------------------------------ /dory weather
    def _register_weather_command(self, group: app_commands.Group) -> None:
        """`/dory weather` on the travel commands' `/dory` group, and the buttons' templates, so a
        card's buttons answer after a restart (`_register_travel_search_commands` calls this)."""
        both = [
            app_commands.Choice(
                name=f"{t('discord.weather.days', 'en', count=n)} · "
                f"{t('discord.weather.days', 'th', count=n)}",
                value=n,
            )
            for n in DAYS.values()
        ]

        @group.command(name="weather", description=t("cmd_dory_weather"))
        @app_commands.describe(place=t("cmd_dory_place"), days=t("cmd_dory_days"))
        @app_commands.choices(days=both)
        async def weather(
            interaction: discord.Interaction,
            place: app_commands.Range[str, 1, 100],
            days: int = 3,
        ):
            await self.handle_weather_command(interaction, place, days)

        self.add_dynamic_items(WeatherButton)

    async def handle_weather_command(self, interaction, place: str, days: int = 3) -> None:
        """Defer at once (3 s), then ONE ephemeral card, or one private line: off / not found /
        could not load."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        gid = interaction.guild.id
        await asyncio.to_thread(self.team.current, gid)
        lang = self._interaction_lang(interaction)
        try:
            service = self._weather_service() if self.team.enabled(gid, "maps") else None
            if service is None:
                await interaction.followup.send(t("discord.weather.off", lang), ephemeral=True)
                return
            found = await asyncio.to_thread(find_place, service, place, lang)
            if found is None:
                line = t("discord.weather.notFound", lang, place=place.strip())
                await interaction.followup.send(line, ephemeral=True)
                return
            owner = f"discord:{interaction.user.id}"
            s = self._weather_session(owner, found["label"], found["lat"], found["lng"], days,
                                      lang)  # fmt: skip
            view = await self._weather_card_view(s, s.extra["days"])
        except Exception as e:
            logger.warning("weather command failed: %s", type(e).__name__)
            await interaction.followup.send(t("discord.weather.failed", lang), ephemeral=True)
            return
        await interaction.edit_original_response(content=None, view=view)

    async def handle_weather_click(self, interaction, act: str, sid: str) -> None:
        """3 days / 5 days / Refresh: only the card's owner gets a changed card."""
        s = self.weather_sessions.get(sid, f"discord:{interaction.user.id}")
        if s is None:
            line = t("discord.weather.expired", self._interaction_lang(interaction))
            await interaction.response.send_message(line, ephemeral=True)
            return
        await interaction.response.defer()  # the forecast may take seconds: off the 3 s clock
        days = DAYS.get(act, s.extra["days"])
        try:
            view = await self._weather_card_view(s, days)
        except Exception as e:  # the old card stays as it was
            logger.warning("weather refresh failed: %s", type(e).__name__)
            line = t("discord.weather.refreshFailed", s.extra["lang"])
            await interaction.followup.send(line, ephemeral=True)
            return
        s.extra["days"] = days
        await interaction.edit_original_response(view=view)
