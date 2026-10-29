"""Static preview of the Discord weather card (offline, no Discord, no network).

Builds the REAL payloads of `dory.weather_bot` from the fake Open-Meteo of the tests (Singapore,
29 Oct 2026): the 3-day card under a chat answer, the 5-day card after the button, the Thai card,
the line when the forecast cannot load and the reply to someone else's click, rendered with the
Discord imitation of `dory_travel_discord_preview.py`. Optionally screenshots each with Playwright.

    uv run python scripts/dory_weather_discord_preview.py --out /tmp/dory-weather-discord [--png]
"""

from __future__ import annotations

import argparse
import base64
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests/dory")]

from dory_travel_discord_preview import AVATAR, CSS, component, message  # noqa: E402
from test_weather_cards import Net  # noqa: E402 - the tests' fake Open-Meteo

from dory.i18n import t  # noqa: E402
from dory.travel_search import Sessions  # noqa: E402
from dory.weather import weather_card  # noqa: E402
from dory.weather_bot import weather_view  # noqa: E402

LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")  # Discord masked links


def steps() -> list[tuple[str, str, object]]:
    """(label, command, LayoutView or plain text)."""
    svc, sessions = Net().service(), Sessions()
    out = []
    for label, lang, days in (
        ("1 · Card under a chat answer (3 days)", "en", 3),
        ("2 · After the 5 days button", "en", 5),
        ("3 · Thai: the condition worded by icon", "th", 3),
    ):
        s = sessions.start("discord:1", "weather", {"place": "Singapore"})
        card = weather_card(svc, "Singapore", 1.2897, 103.8501, lang, days)
        out.append((label, "@Dory what's the weather in Singapore this week?",
                    weather_view(card, s, lang)))  # fmt: skip
    out.append(("4 · The forecast could not load", "@Dory weather in Singapore?",
                t("discord.weather.failed", "en")))  # fmt: skip
    out.append(("5 · Someone else's (or an expired) card's button", "/dory weather",
                t("discord.weather.expired", "en")))  # fmt: skip
    return out


def render() -> str:
    avatar = "data:image/png;base64," + base64.b64encode(AVATAR.read_bytes()).decode()
    parts = []
    for label, command, payload in steps():
        if isinstance(payload, str):
            body = f'<div class="plain">{html.escape(payload)}</div>'
        else:
            stats = f"{payload.total_children_count}/40 components, {payload.content_length()}/4000 chars"
            label = f"{label} — {stats}"
            body = "".join(component(c) for c in payload.to_components())
            body = LINK.sub(r'<a href="\2" style="color:#00a8fc">\1</a>', body)
        parts.append(message(label, command, body, avatar))
    return (
        "<!doctype html><meta charset='utf-8'><title>Dory weather preview</title>"
        f"<style>{CSS}</style><main><h1>Dory · the weather card</h1>"
        "<p class='lead'>Rendered from the real payloads of dory.weather_bot (Components V2) with "
        "the tests' fake Open-Meteo. An imitation of Discord's dark theme, not a screenshot of "
        f"Discord.</p>{''.join(parts)}</main>"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="/tmp/dory-weather-discord")
    ap.add_argument("--png", action="store_true", help="screenshot with Playwright (chromium)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    page = out / "weather-preview.html"
    page.write_text(render(), encoding="utf-8")
    print(page)
    if args.png:
        from playwright.sync_api import sync_playwright

        names = ("card-3-day", "card-5-day", "card-thai", "failed", "expired")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            tab = browser.new_page(viewport={"width": 900, "height": 900}, device_scale_factor=1)
            tab.goto(page.as_uri())
            for name, step in zip(names, tab.query_selector_all("section.step"), strict=True):
                step.screenshot(path=str(out / f"weather-{name}.png"))
                print(out / f"weather-{name}.png")
            browser.close()


if __name__ == "__main__":
    main()
