"""Weather for Dory: Google Maps Platform Weather API (WeatherNext models), plus an optional
WeatherNext 2 ensemble read from BigQuery, or, where Google Maps is off, Open-Meteo (`OpenMeteoService`,
no key; its free API is for NON-commercial use, so `DORY_OPENMETEO_API_KEY` switches to the paid
customer hosts before a commercial launch). Locations come from remembered places (visibility rules
in `geo.py`) or the geocoder of the service. Answers carry a place NAME, never an address. A
successful `weather` call records a card (`WeatherCtx.cards`) that the web chat and Discord draw
from `weather_card`."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx

from .geo import parse_when
from .gmaps import Geocoder, GoogleHttp, MapsError
from .i18n import map_language_code
from .places import PlacesCtx

logger = logging.getLogger(__name__)

BASE = "https://weather.googleapis.com/v1"
SOURCE = "Google Weather (WeatherNext)"
BANGKOK = (13.7563, 100.5018)
CACHE_SECONDS = 600
MAX_HOURS = 240
RAIN_NOTE_PCT = 60
_DAY_WORDS = {"today": 0, "วันนี้": 0, "tomorrow": 1, "พรุ่งนี้": 1, "มะรืนนี้": 2, "มะรืน": 2}


# ---------------------------------------------------------------------------- parsing
def _g(d, *path, default=None):
    for k in path:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
    return default if d is None else d


def norm_conditions(d: dict) -> dict:
    """One current / hourly / day-part block -> flat numbers (None when absent)."""
    prob = _g(d, "precipitation", "probability", "percent")
    qpf = _g(d, "precipitation", "qpf", "quantity")
    return {
        "condition": _g(d, "weatherCondition", "description", "text", default=""),
        "temp_c": _g(d, "temperature", "degrees"),
        "feels_c": _g(d, "feelsLikeTemperature", "degrees"),
        "rain_pct": prob,
        "rain_mm": qpf,
        "storm_pct": d.get("thunderstormProbability"),
        "wind_kmh": _g(d, "wind", "speed", "value"),
        "uv": d.get("uvIndex"),
    }


def norm_day(d: dict) -> dict:
    day, night = d.get("daytimeForecast") or {}, d.get("nighttimeForecast") or {}
    a, b = norm_conditions(day), norm_conditions(night)

    def worst(k, fn=max):
        vals = [x[k] for x in (a, b) if x[k] is not None]
        return fn(vals) if vals else None

    out = dict(a)
    out["rain_pct"] = worst("rain_pct")
    out["storm_pct"] = worst("storm_pct")
    out["rain_mm"] = round(sum(x["rain_mm"] for x in (a, b) if x["rain_mm"] is not None), 1) if (
        a["rain_mm"] is not None or b["rain_mm"] is not None
    ) else None  # fmt: skip
    out["wind_kmh"] = worst("wind_kmh")
    out["temp_c"] = _g(d, "maxTemperature", "degrees", default=a["temp_c"])
    out["min_c"] = _g(d, "minTemperature", "degrees")
    out["feels_c"] = _g(d, "feelsLikeMaxTemperature", "degrees", default=a["feels_c"])
    dd = d.get("displayDate") or {}
    out["date"] = f"{dd.get('year', 0):04d}-{dd.get('month', 0):02d}-{dd.get('day', 0):02d}"
    return out


def summarize(c: dict, lang: str) -> str:
    """One natural line from normalised conditions."""
    th = lang == "th"
    bits = [c.get("condition") or ("อากาศ" if th else "Weather")]
    t, f = c.get("temp_c"), c.get("feels_c")
    if t is not None:
        lo = c.get("min_c")
        rng = f"{round(lo)}-{round(t)}°C" if lo is not None else f"{round(t)}°C"
        bits.append(("อุณหภูมิ " if th else "") + rng)
        if f is not None and abs(f - t) >= 3 and lo is None:
            bits.append(f"รู้สึกเหมือน {round(f)}°C" if th else f"feels like {round(f)}°C")
    p = c.get("rain_pct")
    if p is not None:
        bits.append(f"โอกาสฝน {round(p)}%" if th else f"{round(p)}% chance of rain")
    if (c.get("storm_pct") or 0) >= 30:
        bits.append(f"พายุฝนฟ้าคะนอง {round(c['storm_pct'])}%" if th else "thunderstorms likely")
    if (c.get("uv") or 0) >= 8:
        bits.append(f"UV สูง ({c['uv']})" if th else f"high UV ({c['uv']})")
    line = ", ".join(str(b) for b in bits)
    if (p or 0) >= 50:
        line += " ควรพกร่มค่ะ" if th else " - bring an umbrella"
    return line


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------- BigQuery ensemble
ENSEMBLE_SQL = """
SELECT t.ensemble_member AS member, f.total_precipitation_6hr AS precip_m
FROM `{table}` AS t, UNNEST(t.forecast) AS f
WHERE t.init_time = (SELECT MAX(init_time) FROM `{table}`)
  AND ST_DWITHIN(t.geography, ST_GEOGPOINT(@lng, @lat), @radius_m)
  AND f.time > @t0 AND f.time <= @t1
"""  # assumed WeatherNext layout: one row per member and grid point, `forecast` array of steps


class WeatherNextBigQuerySource:
    """WeatherNext 2 ensemble (64 members): share of members above a rain threshold. Disabled with
    an empty dataset. `run(sql, params) -> rows` is injectable (tests use fake rows)."""

    def __init__(self, dataset: str, table: str = "weathernext_2_0_0", run: Callable | None = None):
        self.table = f"{dataset}.{table}"
        self.enabled = bool(dataset)
        self._run = run

    def _runner(self):
        if self._run:
            return self._run

        def run(sql, params):
            from google.cloud import bigquery  # optional dependency

            client = bigquery.Client()
            cfg = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter(
                        k, "TIMESTAMP" if isinstance(v, datetime) else
                        "FLOAT64" if isinstance(v, float) else "INT64", v)
                    for k, v in params.items()
                ]
            )  # fmt: skip
            return [dict(r) for r in client.query(sql, job_config=cfg).result()]

        return run

    def ensemble(self, lat: float, lng: float, start: datetime, hours: int = 6, mm: float = 1.0):
        if not self.enabled:
            raise MapsError("ensemble_unavailable", "not_configured")
        params = {
            "lat": float(lat), "lng": float(lng), "radius_m": 30000,
            "t0": start.astimezone(UTC), "t1": start.astimezone(UTC) + timedelta(hours=hours),
        }  # fmt: skip
        try:
            rows = self._runner()(ENSEMBLE_SQL.format(table=self.table), params)
        except MapsError:
            raise
        except Exception as e:
            logger.warning("weathernext bigquery failed: %s", type(e).__name__)
            raise MapsError("ensemble_unavailable", type(e).__name__) from e
        return parse_ensemble(rows, mm)


def parse_ensemble(rows: list[dict], mm: float = 1.0) -> dict:
    """Rows of {member, precip_m (metres)} -> per-member total (mm) and the share above `mm`."""
    total: dict = {}
    for r in rows:
        if r.get("precip_m") is None:
            continue
        total[r["member"]] = total.get(r["member"], 0.0) + float(r["precip_m"]) * 1000.0
    if not total:
        raise MapsError("ensemble_unavailable", "no_rows")
    vals = sorted(total.values())
    n = len(vals)
    return {
        "members": n,
        "rain_probability_pct": round(100 * sum(v > mm for v in vals) / n),
        "threshold_mm": mm,
        "median_mm": round(vals[n // 2], 1),
        "p90_mm": round(vals[min(n - 1, math.ceil(0.9 * n) - 1)], 1),
        "max_mm": round(vals[-1], 1),
    }


# ---------------------------------------------------------------------------- service
class WeatherService:
    """Long-lived: Weather API calls with a 10-minute cache."""

    def __init__(
        self, http: GoogleHttp, geo: Geocoder, bq: WeatherNextBigQuerySource | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):  # fmt: skip
        self.http, self.geo, self.bq, self.clock = http, geo, bq, clock
        self._cache: dict = {}

    def _cached(self, key, fn):
        hit = self._cache.get(key)
        if hit and hit[0] > self.clock():
            return hit[1]
        val = fn()
        self._cache[key] = (self.clock() + CACHE_SECONDS, val)
        return val

    @staticmethod
    def _loc(lat, lng, lang, **extra) -> dict:
        return {
            "location.latitude": round(lat, 4), "location.longitude": round(lng, 4),
            "languageCode": map_language_code(lang), "unitsSystem": "METRIC", **extra,
        }  # fmt: skip

    def current(self, lat, lng, lang) -> dict:
        p = self._loc(lat, lng, lang)
        return norm_conditions(
            self._cached(("cur", *p.values()), lambda: self.http.get(f"{BASE}/currentConditions:lookup", p))
        )  # fmt: skip

    def hours(self, lat, lng, lang, ahead: int) -> list[dict]:
        """Hourly entries from now through `ahead` hours (<= 240), each with its start time."""
        ahead = max(1, min(MAX_HOURS, ahead))

        def fetch():
            out, token = [], None
            for _ in range(11):
                p = self._loc(lat, lng, lang, hours=ahead, pageSize=24)
                if token:
                    p["pageToken"] = token
                d = self.http.get(f"{BASE}/forecast/hours:lookup", p)
                out += d.get("forecastHours") or []
                token = d.get("nextPageToken")
                if not token:
                    break
            return out

        rows = self._cached(("hrs", round(lat, 3), round(lng, 3), lang, ahead), fetch)
        return [
            {**norm_conditions(r), "start": _parse_ts(_g(r, "interval", "startTime", default=""))}
            for r in rows
            if _g(r, "interval", "startTime")
        ]

    def days(self, lat, lng, lang, count: int = 10) -> list[dict]:
        p = self._loc(lat, lng, lang, days=count, pageSize=10)
        d = self._cached(
            ("day", *p.values()), lambda: self.http.get(f"{BASE}/forecast/days:lookup", p)
        )
        return [norm_day(x) for x in d.get("forecastDays") or []]

    def rain_at(self, lat, lng, when: datetime | None, now: datetime) -> float | None:
        """Rain probability (%) at `when` (None = now), or None when unknown. Never raises."""
        try:
            if when is None or when <= now + timedelta(minutes=30):
                return self.current(lat, lng, "th").get("rain_pct")
            ahead = math.ceil((when - now).total_seconds() / 3600) + 1
            if ahead > MAX_HOURS:
                return None
            rows = self.hours(lat, lng, "th", ahead)
            best = min(rows, key=lambda r: abs((r["start"] - when).total_seconds()), default=None)
            return best["rain_pct"] if best else None
        except (MapsError, ValueError, KeyError):
            return None


# ---------------------------------------------------------------------------- Open-Meteo
OPEN_METEO = "https://{host}api.open-meteo.com/v1/forecast"
OPEN_METEO_GEO = "https://{host}geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_SOURCE = "Open-Meteo"
OPEN_METEO_CREDIT = "Weather data by Open-Meteo.com (CC BY 4.0)"
# WMO weather interpretation codes (Open-Meteo docs) -> (condition, icon key the cards draw)
WMO = {
    0: ("Clear sky", "sun"), 1: ("Mainly clear", "sun"), 2: ("Partly cloudy", "cloud-sun"),
    3: ("Overcast", "cloud"), 45: ("Fog", "fog"), 48: ("Depositing rime fog", "fog"),
    51: ("Light drizzle", "drizzle"), 53: ("Moderate drizzle", "drizzle"),
    55: ("Dense drizzle", "drizzle"), 56: ("Light freezing drizzle", "drizzle"),
    57: ("Dense freezing drizzle", "drizzle"), 61: ("Slight rain", "rain"),
    63: ("Moderate rain", "rain"), 65: ("Heavy rain", "rain"), 66: ("Light freezing rain", "rain"),
    67: ("Heavy freezing rain", "rain"), 71: ("Slight snowfall", "snow"),
    73: ("Moderate snowfall", "snow"), 75: ("Heavy snowfall", "snow"), 77: ("Snow grains", "snow"),
    80: ("Slight rain showers", "showers"), 81: ("Moderate rain showers", "showers"),
    82: ("Violent rain showers", "showers"), 85: ("Slight snow showers", "snow"),
    86: ("Heavy snow showers", "snow"), 95: ("Thunderstorm", "storm"),
    96: ("Thunderstorm with slight hail", "storm"), 97: ("Heavy thunderstorm", "storm"),
    99: ("Thunderstorm with heavy hail", "storm"),
}  # fmt: skip
STORM_CODES = {95, 96, 97, 99}


def wmo(code) -> tuple[str, str]:
    try:
        return WMO.get(int(code), ("", "cloud"))
    except (TypeError, ValueError):
        return "", "cloud"


class OpenMeteoGeo:
    """Place name -> coordinates through Open-Meteo's geocoding API (10-minute cache)."""

    def __init__(
        self, get: Callable[[str, dict], dict], clock: Callable[[], float] = time.monotonic
    ):
        self.get, self.clock = get, clock
        self._cache: dict = {}

    def find(self, text: str, lang: str = "en") -> dict | None:
        """The best match: {name, label, lat, lng, timezone, country}; None when nothing matches."""
        key = (text.strip().casefold(), lang)
        hit = self._cache.get(key)
        if hit and hit[0] > self.clock():
            return hit[1]
        d = self.get("geo", {"name": text.strip(), "count": 1, "language": lang, "format": "json"})
        r = (d.get("results") or [None])[0]
        out = None
        if r and r.get("latitude") is not None and r.get("longitude") is not None:
            parts = [r.get("name") or text.strip(), r.get("country") or ""]
            out = {"name": r.get("name") or text.strip(), "label": ", ".join(p for p in parts if p),
                   "lat": float(r["latitude"]), "lng": float(r["longitude"]),
                   "timezone": r.get("timezone") or "", "country": r.get("country") or ""}  # fmt: skip
        self._cache[key] = (self.clock() + CACHE_SECONDS, out)
        return out

    def locate(self, text: str, lang: str = "en") -> tuple[float, float] | None:
        got = self.find(text, lang)
        return (got["lat"], got["lng"]) if got else None


class OpenMeteoService(WeatherService):
    """`WeatherService`'s interface (current / hours / days / rain_at / .geo) on Open-Meteo. Free and
    keyless for NON-commercial use only (https://open-meteo.com/en/terms); `api_key` uses the paid
    customer hosts. Network or API failures raise `MapsError("maps_unavailable")` like Google's."""

    source, credit = OPEN_METEO_SOURCE, OPEN_METEO_CREDIT

    def __init__(self, api_key: str = "", http: httpx.Client | None = None,
                 clock: Callable[[], float] = time.monotonic):  # fmt: skip
        self.key, self.client = api_key.strip(), http or httpx.Client(timeout=10.0)
        self.http, self.bq, self.clock = None, None, clock
        self._cache: dict = {}
        self.geo = OpenMeteoGeo(self._get, clock)

    def _get(self, which: str, params: dict) -> dict:
        host = "customer-" if self.key else ""
        url = (OPEN_METEO_GEO if which == "geo" else OPEN_METEO).format(host=host)
        q = {**params, **({"apikey": self.key} if self.key else {})}
        try:
            r = self.client.get(url, params=q)
        except httpx.HTTPError as e:
            raise MapsError("maps_unavailable", type(e).__name__) from None
        if r.status_code != 200:
            raise MapsError("maps_unavailable", f"open-meteo {r.status_code}")
        return r.json()

    def _forecast(self, lat, lng, **params) -> dict:
        p = {"latitude": round(lat, 4), "longitude": round(lng, 4), "timezone": "auto", **params}
        return self._cached(("om", tuple(sorted(p.items()))), lambda: self._get("forecast", p))

    def current(self, lat, lng, lang) -> dict:
        d = self._forecast(lat, lng, current="temperature_2m,apparent_temperature,weather_code,"
                           "precipitation,wind_speed_10m,relative_humidity_2m",
                           daily="precipitation_probability_max,uv_index_max", forecast_days=1)  # fmt: skip
        c, day = d.get("current") or {}, d.get("daily") or {}
        text, icon = wmo(c.get("weather_code"))
        return {"condition": text, "icon": icon, "code": c.get("weather_code"),
                "temp_c": c.get("temperature_2m"), "feels_c": c.get("apparent_temperature"),
                "rain_pct": (day.get("precipitation_probability_max") or [None])[0],
                "rain_mm": c.get("precipitation"), "storm_pct": None,
                "wind_kmh": c.get("wind_speed_10m"), "uv": (day.get("uv_index_max") or [None])[0],
                "humidity": c.get("relative_humidity_2m"), "time": c.get("time") or "",
                "timezone": d.get("timezone") or ""}  # fmt: skip

    def days(self, lat, lng, lang, count: int = 10) -> list[dict]:
        d = self._forecast(lat, lng, daily="weather_code,temperature_2m_max,temperature_2m_min,"
                           "apparent_temperature_max,precipitation_probability_max,precipitation_sum,"
                           "wind_speed_10m_max,uv_index_max", forecast_days=max(1, min(count, 16)))  # fmt: skip
        day = d.get("daily") or {}

        def col(k, i):
            v = day.get(k) or []
            return v[i] if i < len(v) else None

        out = []
        for i, date_s in enumerate(day.get("time") or []):
            text, icon = wmo(col("weather_code", i))
            out.append({"date": date_s, "condition": text, "icon": icon, "code": col("weather_code", i),
                        "temp_c": col("temperature_2m_max", i), "min_c": col("temperature_2m_min", i),
                        "feels_c": col("apparent_temperature_max", i),
                        "rain_pct": col("precipitation_probability_max", i),
                        "rain_mm": col("precipitation_sum", i),
                        "storm_pct": 100 if col("weather_code", i) in STORM_CODES else None,
                        "wind_kmh": col("wind_speed_10m_max", i), "uv": col("uv_index_max", i)})  # fmt: skip
        return out

    def hours(self, lat, lng, lang, ahead: int) -> list[dict]:
        ahead = max(1, min(MAX_HOURS, ahead))
        d = self._forecast(lat, lng, hourly="temperature_2m,apparent_temperature,weather_code,"
                           "precipitation_probability,precipitation,wind_speed_10m",
                           forecast_days=max(1, min(16, math.ceil(ahead / 24) + 1)))  # fmt: skip
        h, off = d.get("hourly") or {}, timedelta(seconds=d.get("utc_offset_seconds") or 0)
        rows = []
        for i, ts in enumerate(h.get("time") or []):

            def col(k, i=i):
                v = h.get(k) or []
                return v[i] if i < len(v) else None

            text, icon = wmo(col("weather_code"))
            start = (datetime.fromisoformat(ts) - off).replace(tzinfo=UTC)
            rows.append({"condition": text, "icon": icon, "temp_c": col("temperature_2m"),
                         "feels_c": col("apparent_temperature"),
                         "rain_pct": col("precipitation_probability"), "rain_mm": col("precipitation"),
                         "storm_pct": None, "wind_kmh": col("wind_speed_10m"), "uv": None,
                         "start": start})  # fmt: skip
        now = datetime.now(UTC) - timedelta(hours=1)
        return [r for r in rows if r["start"] >= now][:ahead]


def make_weather_service(settings, google: WeatherService | None = None) -> WeatherService | None:
    """The forecast source for the weather tool and cards (`DORY_WEATHER_PROVIDER`): Google Weather
    (`google`, or `auto` with maps_enabled; pass the bot's own to share its cache), Open-Meteo
    (`open-meteo`, or `auto` without maps), None when `off`."""
    mode = (getattr(settings, "weather_provider", "auto") or "auto").strip().lower()
    if mode == "off":
        return None
    if mode == "google" or (mode == "auto" and getattr(settings, "maps_enabled", False)):
        if google is not None:
            return google
        http = GoogleHttp(settings.gcp_project, api_key=settings.maps_api_key)
        return WeatherService(http, Geocoder(http))
    return OpenMeteoService(getattr(settings, "openmeteo_api_key", ""))


def tip_for(current: dict, days: list[dict]) -> dict:
    """One travel tip from the forecast, as a key the platforms word: storm / umbrella (with the
    first wet day) / heat / sun / jacket / pleasant."""
    for d in days:
        if d.get("storm_pct"):
            return {"key": "storm", "day": d.get("date")}
    for d in days:
        if (d.get("rain_pct") or 0) >= RAIN_NOTE_PCT or (d.get("rain_mm") or 0) >= 5:
            return {"key": "umbrella", "day": d.get("date")}
    highs = [x.get("temp_c") for x in (current, *days) if x.get("temp_c") is not None]
    lows = [d["min_c"] for d in days if d.get("min_c") is not None]
    if highs and max(highs) >= 34:
        return {"key": "heat", "day": None}
    if max([d.get("uv") or 0 for d in days] + [current.get("uv") or 0]) >= 8:
        return {"key": "sun", "day": None}
    if lows and min(lows) <= 12:
        return {"key": "jacket", "day": None}
    return {"key": "pleasant", "day": None}


def weather_card(service, label: str, lat: float, lng: float, lang: str, days: int = 3) -> dict:
    """What a weather card draws: the place, its local time, now, the next `days` days (3 or 5)
    and one tip. Raises MapsError when the service is down (the card shows its fallback)."""
    days = 5 if days >= 5 else 3
    cur = service.current(lat, lng, lang)
    rows = service.days(lat, lng, lang, days)[:days]
    keep = ("date", "condition", "icon", "temp_c", "min_c", "rain_pct", "rain_mm", "storm_pct")
    now_keys = ("condition", "icon", "temp_c", "feels_c", "rain_pct", "wind_kmh", "uv", "humidity")
    return {
        "kind": "weather",
        "place": label,
        "lat": round(lat, 4),
        "lng": round(lng, 4),
        "local_time": cur.get("time") or "",
        "timezone": cur.get("timezone") or "",
        "current": {k: cur.get(k) for k in now_keys if cur.get(k) is not None},
        "days": [{k: d.get(k) for k in keep if d.get(k) is not None} for d in rows],
        "tip": tip_for(cur, rows),
        "source": getattr(service, "source", SOURCE),
        "credit": getattr(service, "credit", ""),
        "estimate": True,
    }


# ---------------------------------------------------------------------------- tools
@dataclass
class WeatherCtx:
    service: WeatherService
    places: PlacesCtx | None
    lang: str
    zone: object
    now: Callable[[], datetime]
    cards: list[dict] = field(default_factory=list)  # the weather cards to draw after the reply
    render: bool = True  # False = a voice turn: no card is drawn, the answer is spoken


class WeatherTools:
    def __init__(self, ctx: WeatherCtx):
        self.c = ctx
        self.located: tuple[str, float, float] | None = None  # the last place `weather` looked up

    def locate(self, place: str):
        """(label, lat, lng) for a place name / address; the office, else Bangkok, when empty."""
        from .geo import find_place

        c = self.c
        pc = c.places
        p = find_place(pc, place if place.strip() else "office")
        if p is not None:
            if p.lat is None or p.lng is None:
                got = c.service.geo.locate(p.address or p.name, c.lang)
                if got is None:
                    raise MapsError("place_not_found", "geocode")
                p.lat, p.lng = got
                try:
                    pc.repo.put(p)
                except Exception:  # best effort cache of the coordinates
                    logger.info("could not store coordinates", exc_info=True)
            return p.name, p.lat, p.lng
        if not place.strip():
            return ("กรุงเทพฯ" if c.lang == "th" else "Bangkok"), *BANGKOK
        got = c.service.geo.locate(place.strip(), c.lang)
        if got is None:
            raise MapsError("place_not_found", "geocode")
        return place.strip(), *got

    def weather(self, place: str = "", when: str = "now", detail: str = "summary") -> dict:
        """Weather and forecast for a place (Google Weather API / WeatherNext, or Open-Meteo).

        Args:
            place: a remembered place ("สาขาบางนา", "ออฟฟิศ") or any address / area name. Empty =
                the asker's office, else Bangkok.
            when: "now", "today", "tomorrow", a date YYYY-MM-DD, a time ("17:00", "พรุ่งนี้ 8 โมง")
                or ISO 8601; forecasts reach 10 days (hourly 240 h).
            detail: "summary" (default), "hourly" (next hours), or "ensemble" (rain probability from
                the 64-member WeatherNext 2 ensemble, only if configured).
        """
        c = self.c
        now = c.now()
        try:
            label, lat, lng = self.locate(place or "")
            self.located = (label, lat, lng)
            w = (when or "now").strip()
            key = w.casefold()
            base = {
                "place": label,
                "source": getattr(c.service, "source", SOURCE),
                "estimate": True,
            }
            day_off = _DAY_WORDS.get(key)
            if day_off is None and len(w) == 10 and w[4] == "-":
                try:
                    day_off = (datetime.fromisoformat(w).date() - now.date()).days
                except ValueError:
                    day_off = None
            at = (
                None
                if day_off is not None or key in ("", "now", "ตอนนี้")
                else parse_when(w, now, c.zone)
            )
            if day_off is not None:
                if not 0 <= day_off <= 9:
                    return {"error": "out_of_range", "detail": "forecast covers the next 10 days"}
                at = (now + timedelta(days=day_off)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                at = max(at, now)
            if detail == "ensemble":
                return self._ensemble(base, lat, lng, at or now)
            if detail == "hourly":
                start = at or now
                ahead = math.ceil((start - now).total_seconds() / 3600) + 12
                if ahead > MAX_HOURS:
                    return {"error": "out_of_range", "detail": "hourly forecast covers 240 hours"}
                rows = [r for r in c.service.hours(lat, lng, c.lang, ahead)
                        if r["start"] >= start - timedelta(minutes=59)][:12]  # fmt: skip
                return {**base, "hours": [
                    {"time": f"{r['start'].astimezone(c.zone):%a %H:%M}", **_brief(r)} for r in rows
                ]}  # fmt: skip
            if at is None:
                cur = c.service.current(lat, lng, c.lang)
                return {**base, "when": "now", **_brief(cur), "summary": summarize(cur, c.lang)}
            if day_off is not None:
                days = c.service.days(lat, lng, c.lang)
                want = (now + timedelta(days=day_off)).date().isoformat()
                row = next((d for d in days if d["date"] == want), None)
                if row is None:
                    return {"error": "no_forecast", "detail": want}
                return {**base, "when": want, **_brief(row), "summary": summarize(row, c.lang)}
            ahead = math.ceil((at - now).total_seconds() / 3600) + 1
            if ahead > MAX_HOURS:
                return {"error": "out_of_range", "detail": "hourly forecast covers 240 hours"}
            rows = c.service.hours(lat, lng, c.lang, max(ahead, 1))
            row = min(rows, key=lambda r: abs((r["start"] - at).total_seconds()), default=None)
            if row is None:
                return {"error": "no_forecast"}
            return {**base, "when": f"{at.astimezone(c.zone):%Y-%m-%d %H:%M}", **_brief(row),
                    "summary": summarize(row, c.lang)}  # fmt: skip
        except MapsError as e:
            return _error(e)
        except ValueError as e:
            return {"error": "bad_time", "detail": str(e)}

    def _ensemble(self, base, lat, lng, start) -> dict:
        bq = self.c.service.bq
        if bq is None or not bq.enabled:
            return {"error": "ensemble_unavailable",
                    "detail": "the WeatherNext ensemble is not configured; use detail=summary"}  # fmt: skip
        res = bq.ensemble(lat, lng, start)
        return {**base, "when": f"{start.astimezone(self.c.zone):%Y-%m-%d %H:%M}", "ensemble": res,
                "source": "WeatherNext 2 ensemble (BigQuery)"}  # fmt: skip


def _brief(c: dict) -> dict:
    keys = (
        "condition",
        "temp_c",
        "min_c",
        "feels_c",
        "rain_pct",
        "rain_mm",
        "storm_pct",
        "wind_kmh",
        "uv",
    )
    return {k: c[k] for k in keys if c.get(k) not in (None, "")}


def _error(e: MapsError) -> dict:
    if e.code == "maps_unavailable":
        return {"error": "maps_unavailable", "detail": "the weather service is not available "
                f"right now ({e.reason}); say so briefly and do not guess the weather"}  # fmt: skip
    return {"error": e.code, "detail": e.reason}


def build_weather_tools(ctx: WeatherCtx) -> list:
    tools = WeatherTools(ctx)

    def weather(place: str = "", when: str = "now", detail: str = "summary") -> dict:
        tools.located = None
        res = tools.weather(place, when, detail)
        if ctx.render and "error" not in res and tools.located:  # a card next to the answer
            label, lat, lng = tools.located
            day = str(res.get("when", ""))[:10]  # "now", or YYYY-MM-DD[ HH:MM]
            far = day[:1].isdigit() and day > (ctx.now() + timedelta(days=2)).date().isoformat()
            ahead = 5 if far else 3  # a day 3+ days out is only on the 5-day card
            ctx.cards[:] = [c for c in ctx.cards if c.get("kind") != "weather"]
            ctx.cards.append({"kind": "weather", "place": label, "lat": round(lat, 4),
                              "lng": round(lng, 4), "days": ahead})  # fmt: skip
            res = {**res, "shown": "A weather card for this place is drawn under your reply; "
                   "say the essentials in one or two sentences."}  # fmt: skip
        return res

    weather.__doc__ = WeatherTools.weather.__doc__
    weather.cards = ctx.cards  # type: ignore[attr-defined]  (read with travel_search.tool_cards)
    return [weather]
