"""Browser checks for the sign-up and onboarding flow (/start): account -> organization -> welcome + optional
travel preferences -> start chatting. The pending state and one request per press, the name check, a lost
connection, 429 / 422 / 5xx answers, focus on each new step, the keyboard-only flow, skipping, resuming and
returning users, no sideways scroll from 320 px, 44 px targets, Thai, and axe WCAG 2.2 AA scans of every screen.

/start has no mock mode: the REAL page runs against canned answers. A kept Dory session skips the Google step;
`GET /api/center/me` answers the person and `PUT /api/center/me/travel` the optional step."""

import json
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import expect

from meeting_scribe import center

pytestmark = pytest.mark.e2e

WCAG = {
    "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]},
    "resultTypes": ["violations"],
}
ME = {"email": "nina@example.com", "name": "Nina", "orgs": [], "language": "en"}
NAME = "Baan Suan Coffee"
ORG = {"id": "o9", "name": NAME, "role": "owner", "license": {"plan": "trial", "status": "active"}}
CREATED = (200, ORG)
AIRPORTS = {
    "airports": [
        {"code": "BKK", "city": "Bangkok", "airport": "Suvarnabhumi Airport"},
        {"code": "SIN", "city": "Singapore", "airport": "Singapore Changi Airport"},
    ]
}


def person(*, orgs=False, onboarded=False, airport="", currency=""):
    """What GET /api/center/me answers: a new person, or one who already has an organization."""
    return {
        **ME,
        "orgs": [{**ORG, "pending": False}] if orgs else [],
        "onboarded": onboarded,
        "home_airport": airport,
        "currency": currency,
    }


def signup(page, *replies, me=None, travel=None, airports=(200, AIRPORTS), init=""):
    """Opens /start signed in. Each `POST /api/center/orgs` takes the next reply (the last one repeats):
    (status, body[, headers]), "abort" (no connection) or "hold" (kept open; answer it through `held`).
    `travel` does the same for `PUT /api/center/me/travel` (default: echo the saved values).
    Returns a namespace of what was sent: .posts (organizations), .puts (travel bodies), .held."""
    flow = SimpleNamespace(posts=[], puts=[], held=[])
    me = me if me is not None else person()
    travel_replies = list(travel or [])

    def handle(route):
        req = route.request
        key = req.method + " " + urlparse(req.url).path
        if key == "GET /api/center/me":
            return route.fulfill(json=me)
        if key == "GET /api/travel/airports":
            status, body = airports
            return route.fulfill(status=status, json=body)
        if key == "PUT /api/center/me/travel":
            body = json.loads(req.post_data)
            flow.puts.append(body)
            reply = (
                travel_replies[min(len(flow.puts), len(travel_replies)) - 1]
                if travel_replies
                else None
            )
            if reply == "abort":
                return route.abort()
            if reply == "hold":
                return flow.held.append(route)
            if reply:
                status, payload = reply
                return route.fulfill(status=status, json=payload)
            saved = {"onboarded": True, "orgs": me["orgs"]}
            if not body.get("skip"):
                saved |= {
                    "home_airport": body.get("home_airport", ""),
                    "currency": body.get("currency", ""),
                }
            return route.fulfill(json={**me, **saved})
        if key != "POST /api/center/orgs":
            return route.fulfill(status=404, json={"detail": "Not Found"})
        reply = replies[min(len(flow.posts), len(replies) - 1)]
        flow.posts.append(json.loads(req.post_data))
        if reply == "abort":
            return route.abort()
        if reply == "hold":
            return flow.held.append(route)
        status, body, *headers = reply
        route.fulfill(status=status, json=body, headers=headers[0] if headers else None)

    page.add_init_script(
        "try { localStorage.setItem('dory_session', 'ss1.e2e.sig'); } catch (e) {}" + init
    )
    page.route("**/api/**", handle)
    page.goto("/start")
    expect(page.locator("#step2" if not me["orgs"] else "section.card:visible")).to_be_visible()
    return flow


def name_field(page):
    return page.get_by_role("textbox", name="Organization name")


def create_button(page):
    return page.locator("#create")


def create_org(page, name=NAME):
    name_field(page).fill(name)
    create_button(page).click()
    expect(page.locator("#step3")).to_be_visible()


def airport(page):
    return page.get_by_label("Home airport (optional)")


def currency(page):
    return page.get_by_label("Preferred currency (optional)")


# ------------------------------------------------------------------ account
def test_the_first_screen_explains_the_value_and_links_terms_privacy_and_sign_in(page):
    page.goto("/start")
    expect(page.get_by_role("heading", level=1)).to_have_text("Bring Dory to your team")
    # both open a new tab, and a screen reader is told so
    terms = page.locator("#step1").get_by_role("link", name="Terms (opens in a new tab)")
    privacy = page.locator("#step1").get_by_role("link", name="Privacy Policy (opens in a new tab)")
    expect(terms).to_have_attribute("href", "/terms")
    expect(privacy).to_have_attribute("href", "/privacy")
    expect(page.locator("#step1").get_by_role("link", name="Sign in")).to_have_attribute(
        "href", "/center"
    )
    assert (
        page.locator("input[type=password], input[type=checkbox]").count() == 0
    )  # nothing to consent to


def test_a_lost_connection_while_signing_in_is_said_plainly(page):
    page.add_init_script(
        "try { localStorage.setItem('dory_session', 'ss1.e2e.sig'); } catch (e) {}"
    )
    page.route("**/api/center/me", lambda route: route.abort())
    page.goto("/start")
    expect(page.locator("#login-error")).to_have_text(
        "Couldn't reach Dory. Check your connection and try again."
    )
    expect(page.locator("#login-error")).to_have_attribute("role", "alert")


# ------------------------------------------------------------------ organization
def test_the_happy_path_lands_on_each_step_heading_and_names_the_new_organization(page):
    flow = signup(page, CREATED)
    expect(page.locator("#step2 h2")).to_be_focused()
    expect(
        page.get_by_text("Nothing is charged")
    ).to_be_visible()  # the trust line sits on the form
    name_field(page).fill(f"  {NAME} ")
    page.get_by_role("button", name="Create organization").click()
    expect(page.locator("#step3")).to_be_visible()
    expect(page.locator("#step3 h2")).to_be_focused()
    expect(page.locator("#created-note")).to_contain_text(f'"{NAME}" is ready')
    assert flow.posts == [{"name": NAME}]


def test_progress_is_a_named_list_and_the_current_step_is_announced(page):
    """The step bar was aria-hidden: a screen-reader user had no idea there were four steps."""
    signup(page, CREATED)
    steps = page.get_by_role("list", name="Sign-up progress")
    expect(steps.get_by_role("listitem")).to_have_count(4)
    expect(steps.locator('[aria-current="step"]')).to_have_count(1)
    expect(steps.locator('[aria-current="step"]')).to_contain_text("Organization")
    create_org(page)
    expect(steps.locator('[aria-current="step"]')).to_contain_text("Preferences")


def test_a_double_click_or_enter_while_creating_sends_one_request(page):
    flow = signup(page, "hold", CREATED)
    name_field(page).fill(NAME)
    button = create_button(page)
    button.dblclick()
    expect(button).to_have_text("Creating…")
    expect(button).to_have_attribute("aria-busy", "true")
    expect(button).to_have_attribute("aria-disabled", "true")
    name_field(page).press("Enter")
    name_field(page).press("Enter")
    page.wait_for_timeout(300)
    assert len(flow.posts) == 1
    flow.held[0].fulfill(json=ORG)
    expect(page.locator("#step3")).to_be_visible()
    assert len(flow.posts) == 1


def test_a_lost_connection_keeps_the_name_and_the_same_button_retries(page):
    flow = signup(page, "abort", CREATED)
    name_field(page).fill(NAME)
    create_button(page).click()
    error = page.locator("#org-error")
    expect(error).to_have_text("Couldn't reach Dory. Check your connection and try again.")
    expect(name_field(page)).to_have_value(NAME)
    expect(create_button(page)).to_have_text("Create organization")
    expect(create_button(page)).not_to_have_attribute("aria-busy", "true")
    expect(name_field(page)).not_to_have_attribute("aria-invalid", "true")  # the name was fine
    create_button(page).click()
    expect(page.locator("#step3")).to_be_visible()
    assert flow.posts == [{"name": NAME}, {"name": NAME}]  # the server dedupes the repeat


def test_too_many_attempts_names_the_seconds_from_retry_after(page):
    signup(page, (429, {"detail": "Too many attempts"}, {"Retry-After": "42"}))
    name_field(page).fill(NAME)
    create_button(page).click()
    expect(page.locator("#org-error")).to_have_text("Too many attempts. Try again in 42 seconds.")


def test_a_server_error_shows_its_status(page):
    signup(page, (502, {"detail": "Bad Gateway"}))
    name_field(page).fill(NAME)
    create_button(page).click()
    expect(page.locator("#org-error")).to_contain_text("502")


def test_a_blank_name_or_a_422_marks_the_field_and_puts_focus_back(page):
    flow = signup(page, (422, {"detail": "Organization name is required"}))
    field, error = name_field(page), page.locator("#org-error")
    expect(error).to_have_attribute("role", "alert")
    expect(field).to_have_attribute("aria-describedby", "org-error")
    expect(field).to_have_attribute("required", "")
    expect(field).to_have_attribute("autocomplete", "organization")
    expect(field).to_have_attribute("maxlength", "120")

    field.fill("   ")
    create_button(page).click()  # caught on the page: nothing is sent
    expect(error).to_contain_text("Check the organization name")
    expect(field).to_have_attribute("aria-invalid", "true")
    expect(field).to_be_focused()
    assert flow.posts == []

    field.fill(NAME)
    create_button(page).focus()
    page.keyboard.press("Enter")  # the server says no
    expect(error).to_contain_text("Check the organization name")
    expect(field).to_have_attribute("aria-invalid", "true")
    expect(field).to_be_focused()
    expect(field).to_have_value(NAME)
    assert flow.posts == [{"name": NAME}]


def test_a_sign_in_that_expired_before_create_goes_back_to_sign_in_and_keeps_the_name(page):
    """A 401 on create (the session died after sign-in): back to the sign-in step with a plain line, the
    saved session forgotten, and the typed name kept for the next pass (sessionStorage: survives Discord)."""
    signup(page, (401, {"detail": "Sign-in required"}))
    name_field(page).fill(NAME)
    create_button(page).click()
    expect(page.locator("#step1")).to_be_visible()
    expect(page.locator("#login-error")).to_contain_text("Your sign-in expired")
    assert page.evaluate("localStorage.getItem('dory_session')") is None
    assert page.evaluate("sessionStorage.getItem('dory_signup_org')") == NAME


def test_a_one_second_wait_reads_one_second(page):
    signup(page, (429, {"detail": "Too many attempts, try again shortly"}, {"Retry-After": "1"}))
    name_field(page).fill(NAME)
    create_button(page).click()
    expect(page.locator("#org-error")).to_have_text("Too many attempts. Try again in 1 second.")


# ------------------------------------------------------------------ welcome + preferences
def test_saving_the_preferences_sends_both_and_leads_to_the_examples(page):
    flow = signup(page, CREATED)
    create_org(page)
    expect(page.get_by_role("heading", name="Welcome to Dory")).to_be_focused()
    expect(airport(page)).to_have_value("")  # nothing is preselected for the person
    expect(currency(page)).to_have_value("")
    airport(page).select_option("BKK")
    currency(page).select_option("USD")
    page.get_by_role("button", name="Save and continue").click()
    expect(page.locator("#step4")).to_be_visible()
    expect(page.get_by_role("heading", name="You're all set")).to_be_focused()
    assert flow.puts == [{"currency": "USD", "home_airport": "BKK"}]
    # the home airport makes the first example a complete request
    links = page.locator("#tries a")
    expect(links).to_have_count(3)
    expect(links.first).to_have_text("Find me a flight from Bangkok to Singapore next Friday")
    expect(page.get_by_role("link", name="Start chatting with Dory")).to_have_attribute(
        "href", "/center#/chat"
    )


def test_skipping_goes_on_at_once_and_only_stamps_the_step(page):
    flow = signup(page, CREATED, travel=["hold"])
    create_org(page)
    page.get_by_role("button", name="Skip for now").click()
    expect(page.locator("#step4")).to_be_visible()  # does not wait for the answer
    expect(page.locator("#tries a").first).to_have_text("Find me a flight to Singapore next Friday")
    assert flow.puts == [{"skip": True}]


def test_a_failed_save_stays_on_the_step_keeps_the_choices_and_retries(page):
    flow = signup(
        page, CREATED, travel=[(500, {"detail": "boom"}), "abort", (429, {"detail": "x"})]
    )
    create_org(page)
    airport(page).select_option("SIN")
    currency(page).select_option("JPY")
    save = page.locator("#pref-save")
    error = page.locator("#pref-error")
    save.click()
    expect(error).to_contain_text("error 500")
    expect(error).to_have_attribute("role", "alert")
    expect(page.locator("#step3")).to_be_visible()
    expect(airport(page)).to_have_value("SIN")  # nothing was lost
    expect(currency(page)).to_have_value("JPY")
    expect(save).not_to_have_attribute("aria-busy", "true")
    save.click()
    expect(error).to_have_text("Couldn't reach Dory. Check your connection and try again.")
    save.click()
    expect(error).to_contain_text("Too many attempts")
    assert (
        flow.puts == [{"currency": "JPY", "home_airport": "SIN"}] * 3
    )  # the same choices every time


def test_a_double_press_on_save_sends_one_request(page):
    flow = signup(page, CREATED, travel=["hold"])
    create_org(page)
    save = page.locator("#pref-save")
    save.dblclick()
    expect(save).to_have_text("Saving…")
    expect(save).to_have_attribute("aria-busy", "true")
    page.wait_for_timeout(300)
    assert len(flow.puts) == 1
    flow.held[0].fulfill(json={**person(orgs=True), "onboarded": True})
    expect(page.locator("#step4")).to_be_visible()
    assert len(flow.puts) == 1


def test_without_the_airport_list_the_field_is_off_and_only_the_currency_is_sent(page):
    flow = signup(page, CREATED, airports=(500, {"detail": "down"}))
    create_org(page)
    expect(airport(page)).to_be_disabled()
    expect(page.get_by_text("Couldn't load the airports")).to_be_visible()
    currency(page).select_option("EUR")
    page.get_by_role("button", name="Save and continue").click()
    expect(page.locator("#step4")).to_be_visible()
    assert flow.puts == [{"currency": "EUR"}]


def test_the_travel_step_speaks_thai_with_thai_city_names(page):
    # the language saved with the account wins over the browser's: this person chose Thai
    signup(page, CREATED, me={**person(), "language": "th"})
    expect(page.get_by_role("textbox", name="ชื่อองค์กร")).to_be_visible()  # the label is Thai too
    page.locator("#org-name").fill(NAME)
    page.locator("#create").click()
    expect(page.locator("#step3 h2")).to_have_text("ยินดีต้อนรับสู่ดอรี่")
    expect(page.locator("#pref-airport option[value=BKK]")).to_have_text("กรุงเทพฯ (BKK)")
    page.locator("#pref-airport").select_option("SIN")
    page.get_by_role("button", name="บันทึกและไปต่อ").click()
    expect(page.locator("#tries a").first).to_have_text("หาเที่ยวบินจากสิงคโปร์ไปกรุงเทพฯวันศุกร์หน้า")


def test_the_whole_sign_up_works_by_keyboard_alone(page):
    flow = signup(page, CREATED)
    expect(page.locator("#step2 h2")).to_be_focused()
    page.keyboard.press("Tab")
    expect(name_field(page)).to_be_focused()
    page.keyboard.type(NAME)
    page.keyboard.press("Enter")
    expect(page.locator("#step3 h2")).to_be_focused()
    for expected in (
        airport(page),
        currency(page),
        page.locator("#pref-save"),
        page.locator("#pref-skip"),
    ):
        page.keyboard.press("Tab")
        expect(expected).to_be_focused()
    page.keyboard.press("Enter")  # Skip for now
    expect(page.locator("#step4 h2")).to_be_focused()
    page.keyboard.press("Tab")  # the examples come before the primary action, in reading order
    expect(page.locator("#tries a").first).to_be_focused()
    assert flow.posts == [{"name": NAME}] and flow.puts == [{"skip": True}]


def test_back_from_the_examples_returns_to_the_preferences_with_the_choices(page):
    signup(page, CREATED)
    create_org(page)
    airport(page).select_option("SIN")
    page.get_by_role("button", name="Save and continue").click()
    expect(page.locator("#step4")).to_be_visible()
    page.get_by_role("button", name="Back").click()
    expect(page.locator("#step3 h2")).to_be_focused()
    expect(airport(page)).to_have_value("SIN")


def test_an_example_travels_to_the_chat_as_text_and_the_session_comes_along(page):
    signup(page, CREATED)
    create_org(page)
    page.get_by_role("button", name="Skip for now").click()
    page.route(
        "**/center",
        lambda route: route.fulfill(content_type="text/html", body="<title>Center</title>"),
    )
    page.locator("#tries a", has_text="hotels in Singapore").click()
    page.wait_for_url("**/center#/chat")
    stored = json.loads(page.evaluate("sessionStorage.getItem('dory_chat_prefill')"))
    assert stored["q"] == "Show me hotels in Singapore for two nights"


# ------------------------------------------------------------------ the first-time intro's hand-over
# A stand-in for intro.js that records how this page calls the intro (the intro itself: test_start_intro.py).
INTRO_SPY = """
window.__intro = [];
window.DoryIntro = {
  shouldPlay: (o) => { __intro.push(['should', o.preview]); return true; },
  play: (o) => {
    __intro.push(['play', o.preview, typeof o.t, !document.getElementById('step4').hidden]);
    window.__done = o.onDone;
    return Promise.resolve();
  },
  relabel: () => __intro.push(['relabel']),
};
"""


def spy_on_the_intro(page):
    page.route(
        "**/static/dory/intro/intro.js",
        lambda route: route.fulfill(body=INTRO_SPY, content_type="text/javascript"),
    )


@pytest.mark.parametrize("button", ["Save and continue", "Skip for now"])
def test_both_ends_of_the_travel_step_play_the_intro_over_step_4_already_shown(page, button):
    spy_on_the_intro(page)
    signup(page, CREATED)
    create_org(page)
    page.get_by_role("button", name=button).click()
    expect(page.locator("#step4")).to_be_visible()
    assert page.evaluate("__intro") == [["should", False], ["play", False, "function", True]]
    page.evaluate("document.activeElement.blur(); __done()")  # closing the intro gives focus back
    expect(page.locator("#step4 h2")).to_be_focused()


def test_the_preview_link_plays_the_intro_once_the_page_has_loaded(page):
    spy_on_the_intro(page)
    page.goto("/start?intro=1")
    assert page.evaluate("__intro") == [["should", True], ["play", True, "function", False]]


def test_a_language_switch_lets_the_intro_relabel_its_controls(page):
    spy_on_the_intro(page)
    page.goto("/start")
    page.get_by_role("button", name="ไทย").click()
    assert ["relabel"] in page.evaluate("__intro")


# ------------------------------------------------------------------ returning users
def test_a_member_who_finished_is_welcomed_back_without_being_asked_again(page):
    flow = signup(page, me=person(orgs=True, onboarded=True, airport="SIN", currency="THB"))
    expect(page.locator("#existing")).to_be_visible()
    expect(page.locator("#existing h2")).to_be_focused()
    expect(page.locator("#step3")).to_be_hidden()
    assert flow.puts == [] and flow.posts == []
    # ...and may still change the choices: the saved values are what the form shows
    page.get_by_role("button", name="Travel preferences").click()
    expect(page.locator("#step3")).to_be_visible()
    expect(airport(page)).to_have_value("SIN")
    expect(currency(page)).to_have_value("THB")
    expect(page.locator("#created-note")).to_be_hidden()  # not a brand new organization


def test_an_existing_member_is_not_forced_through_onboarding(page):
    """Created before the travel step existed (or invited): no stamp and no unfinished sign-up in this tab."""
    signup(page, me=person(orgs=True, onboarded=False))
    expect(page.locator("#existing")).to_be_visible()
    expect(page.locator("#step3")).to_be_hidden()


def test_a_reload_in_the_same_tab_resumes_at_the_unfinished_step(page):
    """The organization was created in this tab and the travel step never ended: back to that step."""
    flow = signup(
        page,
        me=person(orgs=True, onboarded=False),
        init=" try { sessionStorage.setItem('dory_signup_prefs', '1'); } catch (e) {}",
    )
    expect(page.locator("#step3")).to_be_visible()
    expect(page.get_by_role("heading", name="Welcome to Dory")).to_be_focused()
    page.get_by_role("button", name="Skip for now").click()
    expect(page.locator("#step4")).to_be_visible()
    assert flow.puts == [{"skip": True}]
    assert page.evaluate("sessionStorage.getItem('dory_signup_prefs')") is None  # not resumed twice


def test_another_organization_can_be_created_from_the_returning_screen(page):
    flow = signup(page, CREATED, me=person(orgs=True, onboarded=True))
    page.get_by_role("button", name="Create another organization").click()
    expect(page.locator("#step2 h2")).to_be_focused()
    name_field(page).fill(NAME)
    create_button(page).click()
    expect(page.locator("#step3")).to_be_visible()
    assert flow.posts == [{"name": NAME}]


# ------------------------------------------------------------------ Discord
def test_the_discord_button_shows_it_is_on_its_way(page, monkeypatch):
    monkeypatch.setattr(center, "discord_login_enabled", lambda: True)
    # The redirect replaces the page, and Playwright cannot read a page while it navigates, so the
    # button's state is written down as the page unloads and read on the stand-in Discord page.
    page.add_init_script(
        """addEventListener('beforeunload', () => { const b = document.getElementById('discord-signup');
        if (b) sessionStorage.setItem('discord_btn', JSON.stringify([b.textContent, b.getAttribute('aria-busy')])); });"""
    )
    page.route(
        "**/api/center/auth/discord/start**",
        lambda route: route.fulfill(content_type="text/html", body="<title>Discord</title>"),
    )
    page.goto("/start")
    page.locator("#discord-signup").click()
    page.wait_for_url("**/api/center/auth/discord/start?next=start")
    seen = page.evaluate("JSON.parse(sessionStorage.getItem('discord_btn'))")
    assert seen == ["Opening Discord…", "true"]


def test_adding_dory_to_discord_is_optional_and_tucked_under_the_chat_button(page):
    signup(page, CREATED)
    create_org(page)
    page.get_by_role("button", name="Skip for now").click()
    summary = page.get_by_text("Also add Dory to your team's Discord (optional)")
    expect(summary).to_be_visible()
    expect(page.get_by_role("link", name="Start chatting with Dory")).to_be_visible()
    expect(page.locator("details.more .how")).to_be_hidden()  # closed until asked for
    summary.click()
    expect(page.locator("details.more .how")).to_be_visible()


# ------------------------------------------------------------------ accessibility and layout
def reach(page, screen):
    """Walks to one screen of the flow."""
    if screen == "step1":
        page.goto("/start")
        return
    signup(page, CREATED)
    if screen == "step2":
        create_button(page).click()  # blank: the error and aria-invalid are part of the scan
        expect(page.locator("#org-error")).to_be_visible()
        return
    create_org(page)
    expect(page.locator("#pref-airport option[value=BKK]")).to_have_count(1)
    if screen == "step4":
        page.get_by_role("button", name="Skip for now").click()
        expect(page.locator("#step4")).to_be_visible()


@pytest.mark.parametrize("width", [320, 390, 1440])
@pytest.mark.parametrize("screen", ["step1", "step2", "step3", "step4"])
def test_axe_finds_no_wcag_aa_violations_on_every_screen(page, width, screen):
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(reduced_motion="reduce")  # everything visible at once
    reach(page, screen)
    res = Axe().run(page, options=WCAG)
    assert res.violations_count == 0, res.generate_report()


@pytest.mark.parametrize("width", [320, 360, 390])
def test_no_sideways_scroll_and_44px_targets_on_a_phone(page, width):
    page.set_viewport_size({"width": width, "height": 740})
    page.emulate_media(reduced_motion="reduce")

    def check(step):
        assert page.evaluate("document.documentElement.scrollWidth") <= width, step
        for box in page.locator(
            f"#{step} .btn:visible, #{step} a.try:visible, #{step} select:visible, #{step} summary:visible"
        ).all():
            assert box.bounding_box()["height"] >= 44, (step, box.text_content()[:30])

    page.goto("/start")
    check("step1")
    signup(page, CREATED)
    check("step2")
    create_button(page).click()
    expect(page.locator("#org-error")).to_be_visible()
    check("step2")
    create_org(page)
    expect(page.locator("#pref-airport option[value=BKK]")).to_have_count(1)
    check("step3")
    page.get_by_role("button", name="Skip for now").click()
    expect(page.locator("#step4")).to_be_visible()
    check("step4")
    page.get_by_text("Also add Dory to your team's Discord (optional)").click()
    check("step4")


def test_the_header_keeps_the_brand_and_the_email_on_one_line_on_a_small_phone(page):
    """At 360 px Thai, the brand ดอรี่ broke as "ด / อรี่" and the email mid-word: one line each,
    the email shortened with an ellipsis (its full text in the title)."""
    page.add_init_script("try { localStorage.setItem('dory-language', 'th'); } catch (e) {}")
    page.set_viewport_size({"width": 360, "height": 800})
    signup(page, CREATED)
    lines = page.evaluate(
        """() => [".logo [data-i18n=brand]", "#who"].map((s) => {
          const el = document.querySelector(s), lh = parseFloat(getComputedStyle(el).lineHeight) || 20;
          return Math.round(el.getBoundingClientRect().height / lh);
        })"""
    )
    assert lines == [1, 1], lines
    assert page.locator("#who").get_attribute("title") == ME["email"]
