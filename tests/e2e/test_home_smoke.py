"""Playwright smoke of the homepage (`/`): the Pause motion control, the header links and the phone menu,
the film dialog, the scripted live demo in English and Thai by mouse and keyboard, the For Teams answer,
the sign-up hand-off, no sideways scroll at 320 px, no script errors, and axe WCAG 2.2 AA scans."""

import re

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

WCAG = {
    "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]},
    "resultTypes": ["violations"],
}


def _scroll_through(page) -> None:
    """Scrolls the whole page once (instant) so every entrance has played, then back to the top."""
    height = page.evaluate("document.documentElement.scrollHeight")
    for y in range(0, height, 500):
        page.evaluate(f"window.scrollTo({{top: {y}, behavior: 'instant'}})")
        page.wait_for_timeout(40)
    page.wait_for_timeout(900)
    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")


def test_pause_motion_is_remembered(page):
    page.goto("/")
    pause = page.locator(".hero [data-motion-toggle]")
    expect(pause).to_have_text("Pause motion")
    pause.click()
    expect(page.locator("html")).to_have_class(re.compile(r"\bmotion-off\b"))
    expect(page.locator(".hero-dory img")).to_have_css("animation-name", "none")
    page.reload()
    expect(page.locator("html")).to_have_class(
        re.compile(r"\bmotion-off\b")
    )  # saved in dory-motion
    expect(pause).to_have_text("Play motion")
    expect(page.locator("footer [data-motion-toggle]")).to_have_text("Play motion")


def test_reduced_motion_starts_still_and_can_be_played(page):
    page.emulate_media(reduced_motion="reduce")
    page.goto("/")
    expect(page.locator("html")).to_have_class(re.compile(r"\bmotion-off\b"))
    expect(page.locator(".bubbles span").first).to_have_css("animation-name", "none")
    play = page.locator(".hero [data-motion-toggle]")
    expect(play).to_have_text("Play motion")
    play.click()
    expect(page.locator("html")).not_to_have_class(re.compile(r"\bmotion-off\b"))


def test_no_script_errors_through_the_whole_page(page):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("/")
    _scroll_through(page)
    page.wait_for_timeout(300)
    assert errors == []


def test_every_header_link_lands_on_its_section(page):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.emulate_media(reduced_motion="reduce")  # instant jumps
    page.goto("/")
    for name, sid in (
        ("Features", "features"),
        ("How it works", "how"),
        ("For Teams", "teams"),
        ("Trust", "trust"),
        ("Pricing", "pricing"),
        ("FAQ", "faq"),
    ):
        page.locator(".hd-nav").get_by_role("link", name=name, exact=True).click()
        expect(page.locator(f"#{sid} h2")).to_be_in_viewport()
    expect(page.locator(".hd")).to_have_class(re.compile(r"\bsolid\b"))  # frosted once scrolled
    expect(page.locator(".hd").get_by_role("link", name="Log in")).to_have_attribute(
        "href", "/center"
    )


def test_the_phone_menu_opens_and_closes(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/")
    menu = page.locator(".menu-btn")
    expect(page.locator(".hd-nav")).to_be_hidden()
    menu.click()
    expect(menu).to_have_attribute("aria-expanded", "true")
    expect(page.locator(".hd-nav").get_by_role("link", name="Pricing")).to_be_visible()
    page.keyboard.press("Escape")
    expect(menu).to_have_attribute("aria-expanded", "false")
    expect(menu).to_be_focused()
    menu.click()
    page.locator(".hd-nav").get_by_role("link", name="FAQ").click()
    expect(menu).to_have_attribute("aria-expanded", "false")
    expect(page.locator("#faq h2")).to_be_in_viewport()


def test_see_dory_at_work_opens_the_film_in_a_dialog(page):
    page.goto("/")
    film = page.locator("#film")
    expect(film).to_be_hidden()
    assert (
        page.evaluate("document.getElementById('intro').poster") == ""
    )  # nothing loads before it opens
    page.get_by_role("link", name="See Dory at work").click()
    expect(page.get_by_role("dialog", name="Meet Dory")).to_be_visible()
    expect(film.locator("video")).to_have_attribute("preload", "none")
    expect(film.locator("video")).to_have_attribute("poster", "/static/dory/meet-dory.webp")
    expect(film.get_by_role("button", name="Close")).to_be_focused()  # the first control in it
    page.keyboard.press("Escape")
    expect(film).to_be_hidden()
    # the dialog's close event (queued after it hides) stops the film
    page.wait_for_function("document.getElementById('intro').paused", timeout=5000)


def test_the_film_starts_from_the_top_every_time_it_opens(page):
    page.goto("/")
    see = page.get_by_role("link", name="See Dory at work")
    see.click()
    page.keyboard.press("Escape")
    page.wait_for_function("document.getElementById('intro').paused", timeout=5000)
    page.evaluate("document.getElementById('intro').currentTime = 9")  # closed mid-film
    see.click()
    assert page.evaluate("document.getElementById('intro').currentTime") < 1


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


def test_the_empty_card_names_no_channel(page):
    page.goto("/")
    card = page.locator("#card")
    page.locator("#msg").fill("")
    expect(card.locator("[data-f=kind]")).to_have_text("Nothing caught yet")
    expect(card.locator("[data-f=where]")).to_be_hidden()
    page.locator("#msg").fill("Arun, please book the venue by tomorrow")
    expect(card.locator("[data-f=where]")).to_have_text("in Arun's private Dory channel")


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


def test_the_team_answer_follows_who_asks_and_the_language(page):
    page.goto("/")
    note = page.locator('#ans [data-ans="note"]')
    expect(note).to_contain_text("#management")  # staff by default: the source is left out
    page.locator('label[for="as-owner"]').click()
    expect(note).to_have_text("Arun can read every source used here.")
    expect(page.locator('#ans [data-ans="x"]')).to_be_visible()
    page.locator('label[for="al-th"]').click()
    expect(page.locator('#ans [data-ans="q"]')).to_have_text("เราตัดสินใจเรื่องงบไตรมาส 3 ไว้ว่ายังไง")
    expect(page.locator("#ans")).to_have_attribute("lang", "th")


def test_the_page_switches_to_thai_and_back(page):
    page.goto("/")
    page.locator('.hd [data-lang="th"]').click()
    expect(page.locator("html")).to_have_attribute("lang", "th")
    expect(page.locator("h1")).to_contain_text("ถามครั้งเดียว")
    expect(page.locator(".hd-nav a").first).to_have_text("ความสามารถ")
    expect(page.locator("#card [data-f=kind]")).to_have_text("งานใหม่สำหรับนก")
    page.locator("#lang-other").click()
    expect(page.locator("html")).to_have_attribute("lang", "en")
    expect(page.locator("h1")).to_contain_text("Ask once.")


JOINED = (
    "ด\u2060อ\u2060รี่"  # ดอรี่ with word joiners: the browser's Thai dictionary does not know the name
)
# every rendered ดอรี่ on the page whose letters land on more than one line
BROKEN_NAMES = r"""() => {
  const bad = [], walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let seen = 0;
  for (let n; (n = walk.nextNode()); ) {
    for (const m of n.data.matchAll(/ด\u2060?อ\u2060?รี่/g)) {
      const r = document.createRange();
      r.setStart(n, m.index);
      r.setEnd(n, m.index + m[0].length);
      const rs = [...r.getClientRects()].filter((x) => x.width > 0);
      if (!rs.length) continue; // not rendered (a closed dialog, a hidden state)
      seen++;
      if (rs.some((x) => x.top >= rs[0].bottom - 2)) bad.push(n.parentElement.dataset.i18n || n.data);
    }
  }
  return { seen, bad };
}"""


def test_thai_never_breaks_inside_dorys_name(page):
    page.emulate_media(reduced_motion="reduce")
    page.add_init_script("try { localStorage.setItem('dory-language', 'th'); } catch (e) {}")
    page.goto("/")
    names = page.evaluate(
        r"Object.values(I18N).flatMap((e) => e.th.match(/ด\u2060?อ\u2060?รี่/g) || [])"
    )
    assert len(names) > 20 and set(names) == {JOINED}  # every Thai string the page can render
    page.evaluate("for (const d of document.querySelectorAll('details')) d.open = true")
    for width in (360, 390):
        page.set_viewport_size({"width": width, "height": 800})
        for eg in ("eg1", "eg4"):  # a task for someone, then the question to Ben
            page.locator(f'[data-eg="{eg}"]').click()
            result = page.evaluate(BROKEN_NAMES)
            assert result["seen"] > 20 and result["bad"] == [], (width, eg, result)


def test_the_sign_up_step_hands_the_name_to_start(page):
    page.goto("/")
    page.locator("#org").fill("Baan Suan Coffee")
    page.get_by_role("button", name="Continue").click()
    page.wait_for_url(re.compile(r"/start\?org=Baan\+Suan\+Coffee$"))


@pytest.mark.parametrize("width", [320, 390])
def test_no_sideways_scroll_on_a_phone(page, width):
    page.set_viewport_size({"width": width, "height": 700})
    page.goto("/")
    _scroll_through(page)
    assert page.evaluate("document.documentElement.scrollWidth") <= width


@pytest.mark.parametrize(("lang", "motion"), [("en", "reduce"), ("th", "reduce"), ("en", "on")])
def test_axe_finds_no_wcag_aa_violations_on_the_homepage(page, lang, motion):
    if motion == "reduce":
        page.emulate_media(reduced_motion="reduce")  # everything visible at once, nothing moving
    page.add_init_script(
        f"try {{ localStorage.setItem('dory-language', '{lang}'); }} catch (e) {{}}"
    )
    page.goto("/")
    if motion == "on":
        _scroll_through(page)  # every entrance has finished before the scan
    res = Axe().run(page, options=WCAG)
    assert res.violations_count == 0, res.generate_report()
