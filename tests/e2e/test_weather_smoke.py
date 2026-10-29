"""Playwright smoke of the weather card in the "Talk to Dory" chat (`/center?mock=1`): the mock chat
plays Dory's weather tool and the card's own fetch answers a canned forecast (no network). The card
says it is an estimate and credits Open-Meteo, 3 days -> 5 days, Refresh shows the skeleton at the
card's size, a failed forecast says so with Try again (the answer stays), flights + weather in one
reply, the chat page redraws it from the history, axe WCAG 2.2 AA, nothing scrolls sideways at 320 px.

`WEATHER_SHOTS=<dir>` also saves screenshots there (off by default)."""

import os
from pathlib import Path

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

ASK = "What's the weather in Singapore?"
WCAG = {
    "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]},
    "resultTypes": ["violations"],
}
OVERFLOW = """() => { const p = document.querySelector('#panel').getBoundingClientRect(), bad = [];
  for (const n of document.querySelectorAll('#panel *')) {
    if (n.closest('.sr')) continue;
    const r = n.getBoundingClientRect();
    if (r.width && (r.right > p.right + 0.5 || r.left < p.left - 0.5)) bad.push(n.className || n.tagName);
  }
  return { scroll: document.documentElement.scrollWidth, inner: innerWidth, bad }; }"""


def shot(target, name):
    if d := os.environ.get("WEATHER_SHOTS"):
        Path(d).mkdir(parents=True, exist_ok=True)
        target.screenshot(path=str(Path(d) / f"{name}.png"))


def say(page, text=ASK):
    page.goto("/center?mock=1")
    page.locator("#fab").click()
    page.locator("#p-in").fill(text)
    page.keyboard.press("Enter")
    return page.locator("#panel")


def ask(page, text=ASK):
    panel = say(page, text)
    card = panel.locator(".tv-wx")
    expect(card.locator(".tv-wday")).to_have_count(3)
    return panel, card


def test_a_weather_reply_draws_the_forecast_card(page):
    page.set_viewport_size({"width": 1280, "height": 900})
    panel, card = ask(page)
    expect(card.get_by_role("heading", name="Weather: Singapore")).to_be_visible()
    expect(card).to_contain_text("Forecast · estimate")
    expect(card).to_contain_text("Local time")
    expect(card.locator(".tv-wtemp")).to_have_text("31°C")
    expect(card.locator(".tv-wnow")).to_contain_text("Slight rain showers")
    for words in ("Feels like", "36°C", "Humidity", "74%", "Wind", "10 km/h", "Rain chance"):
        expect(card.locator(".tv-wstats")).to_contain_text(words)
    expect(card.locator(".tv-wday").first).to_contain_text("Today")
    expect(card.locator(".tv-wday").first).to_contain_text("High 32° / Low 26°")  # sr words
    expect(card.locator(".tv-wday").first).to_contain_text("Rain 55%")
    expect(card.locator(".tv-wtip")).to_contain_text("Thunderstorms are possible on ")
    credit = card.get_by_role("link", name="Weather data by Open-Meteo.com (CC BY 4.0)")
    expect(credit).to_have_attribute("href", "https://open-meteo.com/")
    for icon in card.locator(".tv-wic").all():  # decorative: the condition is always in words
        expect(icon).to_have_attribute("aria-hidden", "true")
    expect(card.get_by_role("button", name="3 days")).to_have_attribute("aria-pressed", "true")
    # a weather-only reply: no sample-travel note and no searches
    expect(panel.locator(".tv-note")).to_have_count(0)
    expect(panel.locator(".tv-flight, .tv-hotel")).to_have_count(0)
    shot(panel, "weather-panel-1280")


def test_the_toggle_switches_three_days_to_five(page):
    _, card = ask(page)
    five = card.get_by_role("button", name="5 days")
    five.click()
    expect(five).to_have_attribute("aria-pressed", "true")
    expect(card.get_by_role("button", name="3 days")).to_have_attribute("aria-pressed", "false")
    expect(card.locator(".tv-wday")).to_have_count(5)
    expect(card.get_by_role("status")).to_have_text("5-day forecast for Singapore updated.")
    card.get_by_role("button", name="3 days").click()
    expect(card.locator(".tv-wday")).to_have_count(3)


def test_refresh_shows_the_skeleton_at_the_cards_size_then_the_card(page):
    _, card = ask(page)
    before = card.bounding_box()["height"]
    card.get_by_role("button", name="Refresh").click()
    expect(card.locator(".skeleton").first).to_be_visible()
    expect(card.locator(".tv-wbody")).to_have_attribute("aria-busy", "true")
    assert card.bounding_box()["height"] >= before - 1  # the chat does not jump
    expect(card.locator(".tv-wday")).to_have_count(3)
    expect(card.locator(".skeleton")).to_have_count(0)
    expect(card.get_by_role("button", name="Refresh")).to_be_focused()


def test_a_failed_forecast_says_so_and_try_again_recovers(page):
    page.set_viewport_size({"width": 1280, "height": 900})
    panel = say(page, "weather in Singapore error")
    expect(panel.locator(".msg.bot.last .body")).to_contain_text("Singapore is warm")  # stays
    alert = panel.locator(".tv-wx").get_by_role("alert")
    expect(alert).to_have_text(
        "Couldn't load the forecast: The forecast service isn't answering right now.Try again"
    )
    shot(panel, "weather-error")
    alert.get_by_role("button", name="Try again").click()
    expect(panel.locator(".tv-wx .tv-wday")).to_have_count(3)
    expect(panel.locator(".tv-wx").get_by_role("alert")).to_have_count(0)


def test_flights_and_weather_in_one_reply(page):
    panel = say(page, "Find a flight from Bangkok to Singapore next week and the weather there")
    expect(panel.locator(".tv-flight")).to_have_count(1)
    expect(panel.locator(".tv-wx .tv-wday")).to_have_count(3)
    expect(panel.locator(".tv-note")).to_have_count(1)  # the flight search keeps its sample note


def test_the_chat_page_redraws_the_card_from_the_history(page):
    page.set_viewport_size({"width": 1280, "height": 900})
    ask(page)
    page.evaluate("location.hash = '#/chat'")  # same document: the mock history keeps the turn
    card = page.locator(".chatpage .tv-wx")
    expect(card.locator(".tv-wday")).to_have_count(3)  # fetched again, fresh
    expect(card).to_contain_text("Forecast · estimate")
    shot(page, "weather-chat-page")


def test_axe_finds_no_wcag_aa_violations_in_the_weather_card(page):
    page.emulate_media(reduced_motion="reduce")
    panel = say(page, "Find a flight from Bangkok to Singapore next week and the weather there")
    card = panel.locator(".tv-wx")
    card.get_by_role("button", name="5 days").click()
    expect(card.locator(".tv-wday")).to_have_count(5)
    res = Axe().run(page, context="#panel", options=WCAG)
    assert res.violations_count == 0, res.generate_report()
    panel.locator("#p-in").fill("weather error")  # and the error state
    page.keyboard.press("Enter")
    expect(panel.locator(".tv-wx").nth(1).get_by_role("alert")).to_have_count(1)
    res = Axe().run(page, context="#panel", options=WCAG)
    assert res.violations_count == 0, res.generate_report()


def test_nothing_overflows_a_320_px_panel(page):
    page.set_viewport_size({"width": 320, "height": 1500})  # tall: the screenshot holds the card
    panel, card = ask(page)
    card.get_by_role("button", name="5 days").click()
    expect(card.locator(".tv-wday")).to_have_count(5)
    got = page.evaluate(OVERFLOW)
    assert got["scroll"] <= got["inner"] and got["bad"] == [], got
    for b in card.get_by_role("button").all():  # 44 px targets
        box = b.bounding_box()
        assert box["height"] >= 44 and box["width"] >= 44, b.text_content()
    card.scroll_into_view_if_needed()
    shot(page, "weather-320")


def test_a_thai_page_words_the_card_in_thai(page):
    page.add_init_script("try { localStorage.setItem('dory-language', 'th'); } catch (e) {}")
    page.set_viewport_size({"width": 1280, "height": 900})
    _, card = ask(page)
    expect(card).to_contain_text("พยากรณ์อากาศ · ค่าประมาณ")
    # Open-Meteo's conditions are English: a Thai page shows the icon's Thai name instead
    expect(card.locator(".tv-wnow")).to_contain_text("ฝนตกเป็นช่วงๆ")
    expect(card.locator(".tv-wday").first).to_contain_text("วันนี้")
    expect(card.locator(".tv-wtip")).to_contain_text("อาจมีพายุฝนฟ้าคะนอง")
    expect(card.get_by_role("button", name="5 วัน")).to_have_attribute("aria-pressed", "false")
    shot(card, "weather-thai")


def test_offline_says_so_and_the_card_comes_back_on_reconnect(page):
    _, card = ask(page)
    page.context.set_offline(True)
    card.get_by_role("button", name="Refresh").click()
    expect(card.locator(".tv-alert")).to_contain_text("You're offline.")
    expect(card.locator(".tv-alert").get_by_role("button", name="Try again")).to_be_visible()
    page.context.set_offline(False)  # the "online" event loads it again
    expect(card.locator(".tv-wday")).to_have_count(3)
    expect(card.locator(".tv-alert")).to_have_count(0)
