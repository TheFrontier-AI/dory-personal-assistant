"""Weather cards: the Open-Meteo forecast source (fake HTTP only), WMO conditions, the travel tip,
the card the web and Discord draw, the card the weather tool records next to the answer, and which
source a deployment uses."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest

from dory import travel_search
from dory.gmaps import MapsError
from dory.weather import (
    OPEN_METEO_CREDIT,
    OpenMeteoService,
    WeatherCtx,
    WeatherService,
    build_weather_tools,
    make_weather_service,
    tip_for,
    weather_card,
    wmo,
)

ZONE = ZoneInfo("Asia/Bangkok")
NOW = datetime(2026, 10, 29, 15, 0, tzinfo=ZONE)
DAYS = ["2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02"]
SIN = {"name": "Singapore", "latitude": 1.28967, "longitude": 103.85007,
       "timezone": "Asia/Singapore", "country": "Singapore", "admin1": "Singapore"}  # fmt: skip


def forecast(params: dict) -> dict:
    """An Open-Meteo /v1/forecast answer for what was asked (current / daily / hourly)."""
    n = int(params.get("forecast_days", 7))
    out = {"latitude": 1.29, "longitude": 103.85, "timezone": "Asia/Singapore",
           "utc_offset_seconds": 28800}  # fmt: skip
    if "current" in params:
        out["current"] = {"time": "2026-10-29T16:00", "temperature_2m": 31.2,
                          "apparent_temperature": 36.4, "weather_code": 80, "precipitation": 0.4,
                          "wind_speed_10m": 9.7, "relative_humidity_2m": 74}  # fmt: skip
    daily = {"time": DAYS[:n], "weather_code": [80, 3, 95, 1, 61][:n],
             "temperature_2m_max": [32.1, 31.0, 30.4, 31.8, 30.9][:n],
             "temperature_2m_min": [25.9, 26.1, 25.4, 25.8, 25.6][:n],
             "apparent_temperature_max": [37.0, 35.2, 34.8, 36.0, 35.1][:n],
             "precipitation_probability_max": [55, 20, 80, 10, 70][:n],
             "precipitation_sum": [3.1, 0.0, 14.2, 0.0, 6.0][:n],
             "wind_speed_10m_max": [14.0, 12.2, 18.9, 10.1, 13.3][:n],
             "uv_index_max": [7.5, 9.1, 4.0, 10.2, 6.6][:n]}  # fmt: skip
    if "daily" in params:
        out["daily"] = {k: v for k, v in daily.items()
                        if k == "time" or k in params["daily"].split(",")}  # fmt: skip
    return out


class Net:
    """Fake Open-Meteo: records every request; `down` = connection error, `status` = HTTP status."""

    def __init__(self, down=False, status=200, places=(SIN,)):
        self.calls: list[httpx.Request] = []
        self.down, self.status, self.places = down, status, list(places)

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        if self.down:
            raise httpx.ConnectError("down", request=req)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": True, "reason": "x"})
        params = dict(req.url.params)
        if req.url.path == "/v1/search":
            return httpx.Response(200, json={"results": self.places} if self.places else {})
        return httpx.Response(200, json=forecast(params))

    def service(self, key=""):
        return OpenMeteoService(key, httpx.Client(transport=httpx.MockTransport(self.handler)))


def test_current_and_days_are_parsed_into_the_shared_shape():
    net = Net()
    svc = net.service()
    cur = svc.current(1.28967, 103.85007, "en")
    assert cur["condition"] == "Slight rain showers" and cur["icon"] == "showers"
    assert (cur["temp_c"], cur["feels_c"], cur["humidity"], cur["wind_kmh"]) == (
        31.2,
        36.4,
        74,
        9.7,
    )
    assert cur["rain_pct"] == 55 and cur["uv"] == 7.5  # today's max from the daily block
    assert cur["time"] == "2026-10-29T16:00" and cur["timezone"] == "Asia/Singapore"
    days = svc.days(1.28967, 103.85007, "en", 5)
    assert [d["date"] for d in days] == DAYS
    assert days[2]["icon"] == "storm" and days[2]["storm_pct"] == 100
    assert days[1]["storm_pct"] is None and (days[1]["temp_c"], days[1]["min_c"]) == (31.0, 26.1)
    q = dict(net.calls[-1].url.params)
    assert net.calls[-1].url.host == "api.open-meteo.com" and "apikey" not in q
    assert q["timezone"] == "auto" and q["forecast_days"] == "5" and q["latitude"] == "1.2897"


def test_answers_are_cached_and_a_key_uses_the_customer_host():
    net = Net()
    svc = net.service()
    svc.days(1.3, 103.8, "en", 3)
    svc.days(1.3, 103.8, "en", 3)
    assert len(net.calls) == 1  # ten-minute cache
    paid = Net()
    paid.service("k-123").current(1.3, 103.8, "en")
    assert paid.calls[0].url.host == "customer-api.open-meteo.com"
    assert paid.calls[0].url.params["apikey"] == "k-123"


@pytest.mark.parametrize("net", [Net(down=True), Net(status=500), Net(status=429)])
def test_a_failing_service_raises_maps_unavailable(net):
    with pytest.raises(MapsError) as e:
        net.service().current(1.3, 103.8, "en")
    assert e.value.code == "maps_unavailable"


def test_geocoding_finds_a_city_and_says_when_nothing_matches():
    net = Net()
    svc = net.service()
    got = svc.geo.find("Singapore", "en")
    assert got["label"] == "Singapore, Singapore" and got["timezone"] == "Asia/Singapore"
    assert svc.geo.locate("singapore ", "en") == (1.28967, 103.85007)
    assert len(net.calls) == 1  # same name, cached
    assert net.calls[0].url.host == "geocoding-api.open-meteo.com"
    assert Net(places=()).service().geo.locate("Atlantis", "en") is None


def test_wmo_codes():
    assert wmo(0) == ("Clear sky", "sun") and wmo(95)[1] == "storm" and wmo(45)[1] == "fog"
    assert wmo(None) == ("", "cloud") and wmo(42) == ("", "cloud") and wmo("x") == ("", "cloud")


@pytest.mark.parametrize(
    "cur, days, want",
    [
        (
            {},
            [{"date": "d1", "storm_pct": None}, {"date": "d2", "storm_pct": 100}],
            ("storm", "d2"),
        ),
        ({}, [{"date": "d1", "rain_pct": 20}, {"date": "d2", "rain_pct": 70}], ("umbrella", "d2")),
        ({}, [{"date": "d1", "rain_pct": 10, "rain_mm": 6}], ("umbrella", "d1")),
        ({"temp_c": 35}, [{"date": "d1", "temp_c": 30}], ("heat", None)),
        ({}, [{"date": "d1", "temp_c": 34.5}], ("heat", None)),  # no current temperature
        ({"temp_c": 30}, [{"date": "d1", "temp_c": 31, "uv": 9}], ("sun", None)),
        ({"temp_c": 14}, [{"date": "d1", "temp_c": 16, "min_c": 9}], ("jacket", None)),
        ({"temp_c": 24}, [{"date": "d1", "temp_c": 26, "min_c": 18, "uv": 5}], ("pleasant", None)),
    ],
)
def test_one_travel_tip(cur, days, want):
    tip = tip_for(cur, days)
    assert (tip["key"], tip["day"]) == want


@pytest.mark.parametrize("asked, n", [(3, 3), (5, 5), (4, 3), (9, 5)])
def test_the_card_carries_now_three_or_five_days_a_tip_and_the_credit(asked, n):
    card = weather_card(Net().service(), "Singapore", 1.28967, 103.85007, "en", days=asked)
    assert card["kind"] == "weather" and card["place"] == "Singapore" and card["estimate"] is True
    assert len(card["days"]) == n and card["days"][0]["date"] == DAYS[0]
    assert card["current"]["icon"] == "showers" and card["current"]["temp_c"] == 31.2
    assert card["local_time"] == "2026-10-29T16:00" and card["timezone"] == "Asia/Singapore"
    assert card["source"] == "Open-Meteo" and card["credit"] == OPEN_METEO_CREDIT
    assert card["tip"] == {"key": "storm", "day": "2026-10-31"}  # day 3 has a thunderstorm
    assert set(card["days"][0]) <= {"date", "condition", "icon", "temp_c", "min_c", "rain_pct",
                                    "rain_mm", "storm_pct"}  # fmt: skip


def test_the_card_fails_loudly_so_the_page_can_show_its_fallback():
    with pytest.raises(MapsError):
        weather_card(Net(down=True).service(), "Singapore", 1.3, 103.8, "en")


def tool(net=None):
    ctx = WeatherCtx((net or Net()).service(), None, "en", ZONE, lambda: NOW)
    (weather,) = build_weather_tools(ctx)
    return weather, ctx


def test_the_weather_tool_records_one_card_for_the_place_it_answered():
    weather, ctx = tool()
    res = weather("Singapore")
    assert res["place"] == "Singapore" and res["source"] == "Open-Meteo" and "shown" in res
    assert ctx.cards == [{"kind": "weather", "place": "Singapore", "lat": 1.2897,
                          "lng": 103.8501, "days": 3}]  # fmt: skip
    weather("Singapore", when="2026-11-02")  # four days out: only the 5-day card shows it
    assert len(ctx.cards) == 1 and ctx.cards[0]["days"] == 5
    weather("Singapore", when="tomorrow")
    assert ctx.cards[0]["days"] == 3


def test_no_card_when_the_tool_fails():
    weather, ctx = tool(Net(places=()))
    assert weather("Atlantis")["error"] == "place_not_found" and ctx.cards == []
    weather, ctx = tool(Net(down=True))
    assert weather("")["error"] == "maps_unavailable" and ctx.cards == []


def test_weather_cards_ride_with_the_travel_cards_in_the_reply():
    weather, _ = tool()
    flights, hotels = travel_search.card_tools(
        travel_search.CardCtx("web:a@x.co", NOW.date(), travel_search.Trips())
    )
    weather("Singapore")
    flights.cards.append({"kind": "flights", "query": {"origin": "BKK"}, "filters": {}})
    cards = travel_search.tool_cards([flights, hotels, weather])
    assert [c["kind"] for c in cards] == ["flights", "weather"]  # the shared list counts once
    payload = travel_search.travel_payload(cards)
    assert payload["flights"] == {"origin": "BKK"} and payload["hotels"] is None
    assert payload["weather"]["place"] == "Singapore" and payload["weather"]["days"] == 3
    assert travel_search.travel_payload(travel_search.tool_cards([weather]))["flights"] is None


def test_which_forecast_source_a_deployment_uses():
    def s(**kw):
        base = {"weather_provider": "auto", "maps_enabled": False, "openmeteo_api_key": "",
                "gcp_project": "p", "maps_api_key": ""}  # fmt: skip
        return SimpleNamespace(**{**base, **kw})

    google = WeatherService(None, None)
    assert isinstance(make_weather_service(s()), OpenMeteoService)  # no Google Maps: Open-Meteo
    assert make_weather_service(s(maps_enabled=True), google) is google
    assert make_weather_service(s(weather_provider="google"), google) is google
    assert isinstance(make_weather_service(s(maps_enabled=True, weather_provider="open-meteo")),
                      OpenMeteoService)  # fmt: skip
    assert make_weather_service(s(weather_provider="off", maps_enabled=True), google) is None
    assert make_weather_service(s(openmeteo_api_key="k")).key == "k"


def test_settings_default_and_the_key_is_never_shown():
    from dory.config import Settings

    st = Settings(_env_file=None, openmeteo_api_key="secret-k")
    assert Settings(_env_file=None).weather_provider == "auto"
    assert "secret-k" not in repr(st)
