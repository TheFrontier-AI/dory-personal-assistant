"""The /center side of sign-up (mock mode): an example picked on /start fills the chat box and is never sent
for the person, and My account lets the person change the travel preferences the sign-up asked for."""

import json
import time

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

CHAT = "/center?mock=1#/chat"
ACCOUNT = "/center?mock=1#/account"
ASK = "Show me hotels in Singapore for two nights"
WCAG = {
    "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]},
    "resultTypes": ["violations"],
}


def prefill(page, q=ASK, age_ms=0):
    value = json.dumps({"q": q, "at": int(time.time() * 1000) - age_ms})
    page.add_init_script(
        f"try {{ if (!sessionStorage.getItem('seeded')) {{ sessionStorage.setItem('seeded', '1');"
        f" sessionStorage.setItem('dory_chat_prefill', {json.dumps(value)}); }} }} catch (e) {{}}"
    )


def test_the_example_fills_the_chat_box_focuses_it_and_sends_nothing(page):
    prefill(page)
    page.goto(CHAT)
    page.locator(".chatpage .msgs article").first.wait_for()
    box = page.get_by_role("textbox", name="Ask Dory anything…")
    expect(box).to_have_value(ASK)
    expect(box).to_be_focused()
    expect(page.get_by_role("button", name="Send")).to_be_enabled()  # ready, not sent
    assert page.locator(".chatpage .msg.me .body", has_text=ASK).count() == 0
    assert page.evaluate("sessionStorage.getItem('dory_chat_prefill')") is None  # read once


def test_an_example_is_used_once(page):
    prefill(page)
    page.goto(CHAT)
    page.locator(".chatpage .msgs article").first.wait_for()
    page.reload()
    page.locator(".chatpage .msgs article").first.wait_for()
    expect(page.get_by_role("textbox", name="Ask Dory anything…")).to_have_value(
        ""
    )  # gone after the first use


def test_an_old_example_does_not_surprise_the_person_later(page):
    prefill(page, age_ms=11 * 60 * 1000)
    page.goto(CHAT)
    page.locator(".chatpage .msgs article").first.wait_for()
    expect(page.get_by_role("textbox", name="Ask Dory anything…")).to_have_value("")


def test_my_account_changes_the_travel_preferences_and_keeps_them(page):
    page.goto(ACCOUNT)
    card = page.locator(".card", has=page.get_by_role("heading", name="Travel preferences"))
    expect(card).to_be_visible()
    airport, currency = card.get_by_label("Home airport"), card.get_by_label("Preferred currency")
    expect(airport).to_have_value("")
    airport.select_option("BKK")
    currency.select_option("USD")
    card.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Saved").first).to_be_visible()
    page.goto("/center?mock=1#/overview")  # away and back: the page reads what the server returned
    page.goto(ACCOUNT)
    expect(page.get_by_label("Home airport")).to_have_value("BKK")
    expect(page.get_by_label("Preferred currency")).to_have_value("USD")


@pytest.mark.parametrize("width", [320, 1440])
def test_axe_finds_no_wcag_aa_violations_in_the_travel_card(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(ACCOUNT)
    card = page.locator(".card", has=page.get_by_role("heading", name="Travel preferences"))
    expect(card).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    res = Axe().run(page, context=".card:has(#a-airport)", options=WCAG)
    assert res.violations_count == 0, res.generate_report()
