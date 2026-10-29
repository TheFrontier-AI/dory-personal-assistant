"""Discord glue for travel time and weather (logic in `travel.py`, `weather.py`, `gmaps.py`).

`MapsMixin` gives `SecretaryBot` the agent tools (`_maps_tools`, appended to `extra_tools` by
`_agent_kwargs`, so voice has them too) and two lines for the private morning brief. Everything is
off unless `DORY_MAPS_ENABLED` is true and the guild's `maps` flag is on."""

from __future__ import annotations

import logging
from datetime import datetime

from .geo import find_place
from .gmaps import Geocoder, GoogleHttp
from .i18n import t
from .travel import RouteService, TravelCtx, TravelTools, build_travel_tools, leave_line
from .weather import (
    WeatherCtx,
    WeatherNextBigQuerySource,
    WeatherService,
    WeatherTools,
    build_weather_tools,
    make_weather_service,
)

logger = logging.getLogger(__name__)


class MapsMixin:
    _maps_svc: tuple[RouteService, WeatherService] | None = None
    _weather_svc: tuple[tuple, WeatherService | None] | None = None  # (settings key, service)

    def _maps_on(self, guild_id: int) -> bool:
        return bool(self.s.maps_enabled) and self.team.enabled(guild_id, "maps")

    def _weather_service(self) -> WeatherService | None:
        """The forecast source of the weather tool and its cards (`weather.make_weather_service`:
        Google Weather where maps is on, else Open-Meteo, None when off), built once per setting."""
        key = (bool(self.s.maps_enabled), self.s.weather_provider)
        if self._weather_svc is None or self._weather_svc[0] != key:
            google = self._maps_services()[1] if key[0] else None
            self._weather_svc = (key, make_weather_service(self.s, google))
        return self._weather_svc[1]

    def _maps_services(self) -> tuple[RouteService, WeatherService]:
        if self._maps_svc is None:
            http = GoogleHttp(self.s.gcp_project, api_key=self.s.maps_api_key)
            bq = WeatherNextBigQuerySource(
                self.s.weathernext_bq_dataset, self.s.weathernext_bq_table
            )
            self._maps_svc = (RouteService(http), WeatherService(http, Geocoder(http), bq))
        return self._maps_svc

    def _maps_places(self, guild, asker, is_exec, message=None):
        """The places access context for this request (None when places are off)."""
        if not self._places_on(guild.id):
            return None
        if message is None:  # a private DM: the asker alone hears
            return self._places_ctx(guild, asker, is_exec, channel=None, in_guild=False)
        return self._places_ctx(
            guild, asker, is_exec, channel=message.channel,
            room=getattr(message, "room", None), in_guild=message.guild is not None,
        )  # fmt: skip

    def _maps_tools(
        self, message, guild, asker, is_exec: bool, lang: str, *, spoken: bool = False
    ) -> list:
        """travel_time (Google Maps on) + weather (Google or Open-Meteo, `_weather_service`) for one
        request. Never raises."""
        try:
            if not self.team.enabled(guild.id, "maps"):
                return []
            forecast = self._weather_service()
            zone, now = self.s.zone, self.s.now
            pc = self._maps_places(guild, asker, is_exec, message)
            wctx = WeatherCtx(forecast, pc, lang, zone, now, render=not spoken)
            weather = build_weather_tools(wctx) if forecast else []
            if not self._maps_on(guild.id):
                return weather  # no Google Maps: the weather tool alone (Open-Meteo)
            routes, google = self._maps_services()
            return [*build_travel_tools(TravelCtx(routes, pc, lang, zone, now, google)), *weather]
        except Exception:
            logger.warning("maps tools unavailable", exc_info=True)
            return []

    # ------------------------------------------------------------- morning brief (private DM)
    def _maps_brief_notes(self, guild, member, meetings: list[dict], now: datetime, lang: str):
        """Deterministic lines for the member's own morning brief: when to leave for an in-person
        meeting today, and the weather at the office. Blocking; never raises."""
        notes: list[str] = []
        try:
            if not self._maps_on(guild.id):
                return notes
            routes, weather = self._maps_services()
            pc = self._maps_places(guild, member, False)  # DM: only the member hears
            if pc is None:
                return notes
            zone = self.s.zone
            tools = TravelTools(TravelCtx(routes, pc, lang, zone, lambda: now, weather))
            origin = (
                find_place(pc, "บ้าน")
                or find_place(pc, "home")
                or find_place(pc, "ออฟฟิศ")
                or find_place(pc, "office")
            )
            for m in meetings:
                place = (
                    pc.repo.get(guild.id, m.get("place_id") or "") if m.get("place_id") else None
                )
                start = datetime.fromisoformat(m["start_utc"]).astimezone(zone)
                if place is None or origin is None or place.id == origin.id or start <= now:
                    continue
                if not pc.can_see(place):
                    continue
                r = tools.travel_time(origin.name, place.name, "drive", arrive_by=start.isoformat())
                line = leave_line(r, origin.name, m["title"], place.name, lang)
                if line:
                    notes.append(line)
            office = find_place(pc, "ออฟฟิศ") or find_place(pc, "office")
            if office is not None:
                w = WeatherTools(WeatherCtx(weather, pc, lang, zone, lambda: now)).weather(
                    office.name, "today"
                )
                if w.get("summary"):
                    notes.append(t("bf_weather_line", lang, place=w["place"], summary=w["summary"]))
        except Exception:
            logger.warning("maps brief notes failed", exc_info=True)
        return notes
