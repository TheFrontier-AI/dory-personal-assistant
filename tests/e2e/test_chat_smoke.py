"""Playwright smoke of the chat page (`/center?mock=1#/chat`): send with Enter, the thinking state,
Stop waiting with Escape, an error with Retry, the empty state's asks, the top bar's search, the docked panel, the
voice call (Speaker, Expand, Escape), the first-run page, and axe WCAG 2.2 AA scans."""

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
    box = page.get_by_role("textbox", name="Ask Dory anything…")
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


def test_empty_state_offers_three_asks_that_send_their_words(page):
    page.goto(CHAT)
    page.locator(".chatpage .msgs article").first.wait_for()
    page.evaluate("""() => { const w = chatWidget({ turns: [] }, 'e', { page: true });
      document.querySelector('.chatpage .convo .chat').replaceWith(w.wrap); }""")
    asks = page.get_by_role("group", name="Try asking").get_by_role("button")
    expect(asks).to_have_count(3)
    asks.filter(has_text="Show upcoming meetings").click()
    expect(page.locator(".chatpage .msg.me .body").last).to_have_text("Show upcoming meetings")


def test_axe_finds_no_wcag_aa_violations_in_the_chat(page):
    page.goto(CHAT)
    page.locator(".chatpage .msgs article").first.wait_for()
    res = Axe().run(page, context=".chatpage", options=WCAG)
    assert res.violations_count == 0, res.generate_report()


def test_chat_has_a_title_svg_icons_and_english_samples(page):
    page.goto(CHAT)
    page.locator(".chatpage .msgs article").first.wait_for()
    expect(page.get_by_role("heading", level=1, name="Chat with Dory")).to_be_visible()
    expect(page.locator(".chatpage .msgs")).to_contain_text("Ask me anything")
    assert not page.evaluate(
        "/[\\u0e00-\\u0e7f]/.test(document.querySelector('.chatpage').innerText)"
    )
    assert not page.evaluate(
        "/[\\u{1F300}-\\u{1FAFF}\\u{2600}-\\u{27BF}]/u.test(document.body.innerText)"
    )
    assert page.locator("#nav a svg.ic").count() >= 10
    assert (
        page.evaluate("getComputedStyle(document.getElementById('chat-live')).backgroundImage")
        == "none"
    )


def test_search_box_asks_dory_in_the_docked_panel(page):
    page.goto("/center?mock=1#/overview")
    search = page.get_by_role("searchbox", name="Search anything with Dory")
    expect(search).to_be_visible()
    page.keyboard.press("ControlOrMeta+k")
    expect(search).to_be_focused()
    search.fill("office lease")
    page.keyboard.press("Enter")
    panel = page.get_by_role("dialog", name="Talk to Dory")
    expect(panel).to_be_visible()
    expect(panel.locator(".msg.me").last).to_contain_text('Search everything for "office lease"')
    expect(panel.locator(".msg.bot.last .body")).not_to_be_empty()
    assert (
        page.evaluate("getComputedStyle(document.getElementById('mainwrap')).paddingRight")
        == "400px"
    )  # docked


def test_voice_call_speaker_expand_and_escape(page):
    page.goto("/center?mock=1#/overview")
    page.locator("#fab").click()
    page.locator("#panel .chat textarea").wait_for()
    page.evaluate("() => doryLive.show('listening', { lvl: .5 })")
    call = page.get_by_role("region", name="Live call with Dory")
    expect(call).to_be_visible()
    expect(call.get_by_role("status").first).to_have_text("I'm listening…")
    spk = call.get_by_role("button", name="Mute Dory's voice on this device")
    spk.click()
    expect(call.get_by_role("button", name="Turn Dory's voice back on")).to_have_attribute(
        "aria-pressed", "true"
    )
    call.get_by_role("button", name="Expand").click()
    expect(page.locator(".call.max")).to_have_count(1)
    page.keyboard.press("Escape")
    expect(page.locator(".call.max")).to_have_count(0)
    expect(call).to_be_visible()  # Escape restored the size; the panel stays open
    res = Axe().run(page, context="#panel", options=WCAG)
    assert res.violations_count == 0, res.generate_report()


def test_axe_finds_no_wcag_aa_violations_on_the_company_profile(page):
    page.goto("/center?mock=1#/overview")
    page.locator("#ov-hero").wait_for()
    page.locator("#fab").click()
    page.locator("#panel .chat textarea").wait_for()
    res = Axe().run(page, options=WCAG)
    assert res.violations_count == 0, res.generate_report()


def test_first_run_page_and_its_help_ask_dory(page):
    page.goto("/center?mock=1&orgs=0#/overview")
    expect(page.get_by_role("heading", level=2, name="No organization yet")).to_be_visible()
    expect(page.get_by_role("heading", name="What you can do with an organization")).to_be_visible()
    res = Axe().run(page, options=WCAG)
    assert res.violations_count == 0, res.generate_report()
    page.get_by_role("button", name="Ask Dory").click()
    panel = page.get_by_role("dialog", name="Talk to Dory")
    expect(panel).to_contain_text("Dory answers “How do I get started?”")
