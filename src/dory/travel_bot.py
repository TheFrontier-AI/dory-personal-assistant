"""Discord glue for currency conversion and flights (logic: `currency.py`, `flights.py`).

`TravelMixin` gives `SecretaryBot` the agent tools (`_travel_tools`, appended to `extra_tools` by
`_agent_kwargs`, so voice has them too) and the flight-tracking poll (`_travel_due`, from `tick`),
which DMs only the person who asked for the tracking.
"""

from __future__ import annotations

import asyncio
import logging
import time

from . import trips
from .currency import Converter, currency_tools
from .dm import send_dm
from .flights import (
    FlightService,
    FlightTracker,
    flight_tools,
    select_provider,
)
from .i18n import resolve_lang, t
from .secretary_store import new_id

logger = logging.getLogger(__name__)
TRAVEL_TICK_SECONDS = 60.0  # how often tracks are looked at (each is polled every 15 minutes)


class TravelMixin:
    def _travel_init(self) -> None:
        provider = select_provider(self.s.aerodatabox_key, self.s.aviationstack_key)
        self.converter = Converter()
        self.flight_service = FlightService(
            self.llm, self.s.gemini_model, provider, today=lambda: self.s.now().date()
        )
        self.flight_tracker = FlightTracker(self.docs, provider)
        # free sandboxes: sample unless DORY_DUFFEL_TOKEN / DORY_LITEAPI_KEY
        self.trips_provider = trips.make_provider(self.s)
        self._travel_last = 0.0

    def _travel_on(self, guild_id: int) -> bool:
        return self.team.enabled(guild_id, "travel")

    def _travel_tools(
        self, guild, asker, lang: str, is_exec: bool = False, *, reminders: bool = True
    ) -> list:
        """convert_currency, flight_status, flight_prices, track_flight and the trips tools
        (book_trip, travel_profile, list_trips; the searches are travel_search's card tools).
        `reminders` False: no check-in reminder (nothing delivers one to a web-only person).
        Never raises: without them Dory just cannot do these."""
        try:
            if not self._travel_on(guild.id):
                return []
            return [
                *currency_tools(self.converter, lang),
                *flight_tools(
                    self.flight_service,
                    self.flight_tracker,
                    guild.id,
                    asker.id,
                    today=lambda: self.s.now().date(),
                    lang=lang,
                ),
                *trips.trips_tools(
                    trips.TripsCtx(
                        guild_id=guild.id,
                        asker_id=asker.id,
                        asker_name=asker.display_name,
                        is_exec=is_exec,
                        lang=lang,
                        provider=self.trips_provider,
                        docs=self.docs,
                        store=self.store,
                        state=self.secretary_state,
                        request_id=new_id(),
                        now=self.s.now,
                        reminders=getattr(self, "reminder_book", None) if reminders else None,
                        approvals=getattr(self, "approvals", None),
                    )
                ),  # fmt: skip
            ]
        except Exception:
            logger.warning("travel tools unavailable", exc_info=True)
            return []

    async def _travel_due(self) -> None:
        """Poll the due flight tracks (only with a provider key) and DM the requester."""
        if self.flight_tracker.provider is None or not self.guilds:
            return
        now = time.monotonic()
        if now - self._travel_last < TRAVEL_TICK_SECONDS:
            return
        self._travel_last = now
        for guild in list(self.guilds):
            if not self._travel_on(guild.id):
                continue
            for doc in await asyncio.to_thread(self.flight_tracker.due, guild.id):
                events = await asyncio.to_thread(self.flight_tracker.poll, doc)
                member = guild.get_member(doc["user_id"])
                if member is None or not events:
                    continue
                lang = resolve_lang(self.team.current(guild.id).language_setting)
                for ev in events:
                    text = t(
                        f"flight_{ev.kind}_dm",
                        lang,
                        flight=doc["display"],
                        date=doc["date"],
                        minutes=ev.minutes,
                        time=ev.time or "-",
                        gate=ev.gate,
                    )
                    await send_dm(member, text)
