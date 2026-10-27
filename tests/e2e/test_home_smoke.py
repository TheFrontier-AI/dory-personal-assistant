"""Playwright smoke of the homepage (`/`, Dory Descent): the Pause motion control, the scripted live thing
in English and Thai by mouse and keyboard, the header that reads each chapter, the seabed answer, the
sign-up hand-off, no sideways scroll at 320 px, no script errors, and axe WCAG 2.2 AA scans."""

import re

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

WCAG = {
    "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]},
    "resultTypes": ["violations"],
}


def _to(page, section_id: str, offset: int = 10) -> None:
    """Puts a chapter's top under the header (instant, whatever the page's smooth scrolling)."""
    page.evaluate(
        f"window.scrollTo({{top: document.getElementById('{section_id}').offsetTop + {offset},"
        " behavior: 'instant'})"
    )


def test_pause_motion_is_remembered(page):
    page.goto("/")
    pause = page.locator(".hero [data-motion-toggle]")
    expect(pause).to_have_text("Pause motion")
    pause.click()
    expect(page.locator("html")).to_have_class(re.compile(r"\bmotion-off\b"))
    page.reload()
    expect(page.locator("html")).to_have_class(
        re.compile(r"\bmotion-off\b")
    )  # saved in dory-motion
    expect(pause).to_have_text("Play motion")


def test_reduced_motion_starts_still_and_can_be_played(page):
    page.emulate_media(reduced_motion="reduce")
    page.goto("/")
    expect(page.locator("html")).to_have_class(re.compile(r"\bmotion-off\b"))
    play = page.locator(".hero [data-motion-toggle]")
    expect(play).to_have_text("Play motion")
    play.click()
    expect(page.locator("html")).not_to_have_class(re.compile(r"\bmotion-off\b"))


def test_no_script_errors_through_the_whole_dive(page):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("/")
    height = page.evaluate("document.documentElement.scrollHeight")
    for y in range(0, height, 600):
        page.evaluate(f"window.scrollTo({{top: {y}, behavior: 'instant'}})")
    page.wait_for_timeout(300)
    assert errors == []


def test_live_thing_reads_a_message_in_english(page):
    page.goto("/")
    card = page.locator("#card")
    expect(card.locator("[data-f=kind]")).to_have_text("New task for Nok")  # the example on load
    expect(card.locator("[data-f=title]")).to_have_text("Send the Q3 receipts to accounting")
    page.locator("#msg").fill("Arun, please book the venue by tomorrow")
    expect(card.locator("[data-f=kind]")).to_have_text("New task for Arun")
    expect(card.locator("[data-f=title]")).to_have_text("Book the venue")
    expect(card.locator("[data-f=due]")).not_to_contain_text("No date")
    card.get_by_role("button", name="Accept").click()
    expect(card.locator("[data-f=said]")).to_have_text(
        "Accepted. Ben gets one line: Arun accepted it."
    )
    page.locator("#msg").fill("Can someone order more coffee beans?")
    expect(card.locator("[data-f=kind]")).to_have_text("A question for Ben: who takes this?")
    expect(card.get_by_role("button", name="It's mine")).to_be_visible()
    expect(card.locator("[data-f=due]")).to_contain_text("three working days")


def test_live_thing_reads_thai_and_works_by_keyboard(page):
    page.goto("/")
    page.locator("#msg").focus()
    page.keyboard.press("Tab")  # the first example
    expect(page.locator("[data-eg]").first).to_be_focused()
    for _ in range(2):
        page.keyboard.press("Tab")
    expect(page.locator('[data-eg="eg3"]')).to_be_focused()  # "In Thai"
    page.keyboard.press("Enter")
    card = page.locator("#card")
    expect(card.locator("[data-f=kind]")).to_have_text("New task for Arun")
    expect(card.locator("[data-f=title]")).to_have_text("ส่งสรุปยอดขาย")
    page.locator('[data-eg="eg4"]').click()  # Thai, nobody named, Monday
    expect(card.locator("[data-f=kind]")).to_have_text("A question for Ben: who takes this?")
    expect(card.locator("[data-f=title]")).to_have_text("จองห้องประชุม")
    expect(card.locator("[data-f=due]")).to_contain_text("Mon")
    not_a_task = card.get_by_role("button", name="Not a task")
    not_a_task.focus()
    page.keyboard.press("Enter")
    expect(not_a_task).to_have_attribute("aria-pressed", "true")
    expect(card.locator("[data-f=said]")).to_have_text("Closed as not a task. Nothing is assigned.")


def test_the_header_reads_each_chapter(page):
    page.goto("/")
    depth, act = page.locator("#depth"), page.locator(".hd-act")
    expect(depth).to_have_text("0 m")
    _to(page, "midnight")
    expect(depth).to_have_text("1,000 m")
    expect(act).to_have_attribute("data-ink", "light")
    _to(page, "seabed", 400)
    expect(depth).to_have_text("4,000 m")
    expect(act).to_have_attribute("data-ink", "dark")
    _to(page, "twilight")
    expect(depth).to_have_text("200 m")
    expect(act).to_have_attribute("data-ink", "dark")  # the right half is the light field


def test_the_seabed_answer_follows_who_asks_and_the_language(page):
    page.goto("/")
    note = page.locator('#ans [data-ans="note"]')
    expect(note).to_contain_text("#management")  # staff by default: the source is left out
    page.locator('label[for="as-owner"]').click()
    expect(note).to_have_text("Arun can read every source used here.")
    expect(page.locator('#ans [data-ans="x"]')).to_be_visible()
    page.locator('label[for="al-th"]').click()
    expect(page.locator('#ans [data-ans="q"]')).to_have_text("เราตัดสินใจเรื่องงบไตรมาส 3 ไว้ว่ายังไง")
    expect(page.locator("#ans")).to_have_attribute("lang", "th")


def test_the_page_switches_to_thai(page):
    page.goto("/")
    page.locator('.hd [data-lang="th"]').click()
    expect(page.locator("html")).to_have_attribute("lang", "th")
    expect(page.locator("h1")).to_contain_text("ถามครั้งเดียว")
    expect(page.locator("#card [data-f=kind]")).to_have_text("งานใหม่สำหรับนก")


def test_the_sign_up_step_hands_the_name_to_start(page):
    page.goto("/")
    page.locator("#org").fill("Baan Suan Coffee")
    page.get_by_role("button", name="Continue").click()
    page.wait_for_url(re.compile(r"/start\?org=Baan\+Suan\+Coffee$"))


def test_no_sideways_scroll_on_a_small_phone(page):
    page.set_viewport_size({"width": 320, "height": 700})
    page.goto("/")
    assert page.evaluate("document.documentElement.scrollWidth") <= 320


@pytest.mark.parametrize("lang", ["en", "th"])
def test_axe_finds_no_wcag_aa_violations_on_the_homepage(page, lang):
    page.emulate_media(reduced_motion="reduce")  # everything visible at once, nothing mid-animation
    page.add_init_script(
        f"try {{ localStorage.setItem('dory-language', '{lang}'); }} catch (e) {{}}"
    )
    page.goto("/")
    res = Axe().run(page, options=WCAG)
    assert res.violations_count == 0, res.generate_report()
