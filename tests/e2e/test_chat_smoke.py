"""Playwright smoke of the chat page (`/center?mock=1#/chat`): send with Enter, the thinking state,
Stop waiting with Escape, an error with Retry, the empty state's chips, and an axe WCAG 2.2 AA scan."""

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

CHAT = "/center?mock=1#/chat"
WCAG = {
    "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]},
    "resultTypes": ["violations"],
}


def test_send_think_stop_and_retry(page):
    page.goto(CHAT)
    log = page.locator(".chatpage .msgs")
    expect(log).to_have_attribute("role", "log")
    box = page.get_by_role("textbox", name="Message Dory…")
    expect(box).to_be_focused()
    box.fill("What did I miss?")
    page.keyboard.press("Enter")
    expect(page.locator(".chatpage .msg.wait")).to_be_visible()
    expect(page.get_by_role("button", name="Stop waiting")).to_be_visible()
    expect(page.locator(".chatpage .msg.bot.last .body")).to_contain_text("48,570")
    expect(page.get_by_role("button", name="Send")).to_be_disabled()  # empty composer
    box.fill("slow one")
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    expect(page.get_by_text("You stopped waiting.")).to_be_visible()
    box.fill("please make an error")
    page.keyboard.press("Enter")
    alert = page.get_by_role("alert").filter(has_text="Dory couldn't answer")
    expect(alert).to_be_visible()
    expect(alert.get_by_role("button", name="Try again")).to_be_visible()


def test_empty_state_offers_four_asks(page):
    page.goto(CHAT)
    page.locator(".chatpage .msgs article").first.wait_for()
    page.evaluate("""() => { const w = chatWidget({ turns: [] }, 'e', { page: true });
      document.querySelector('.chatpage .convo .chat').replaceWith(w.wrap); }""")
    chips = page.get_by_role("group", name="Try asking").get_by_role("button")
    expect(chips).to_have_count(4)  # the mock user is an admin: spending is offered


def test_axe_finds_no_wcag_aa_violations_in_the_chat(page):
    page.goto(CHAT)
    page.locator(".chatpage .msgs article").first.wait_for()
    res = Axe().run(page, context=".chatpage", options=WCAG)
    assert res.violations_count == 0, res.generate_report()
