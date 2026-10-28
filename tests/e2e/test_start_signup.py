"""Browser checks for the sign-up page (/start): the pending state and one request per press, the name check,
a lost connection, 429 / 422 answers, focus on each new step, the keyboard-only flow, no sideways scroll on a
phone, 44 px buttons, and an axe WCAG 2.2 AA scan of the organization step.

/start has no mock mode: the REAL page runs against canned answers. A kept Dory session skips the Google step
and `GET /api/center/me` answers a person with no organization, so the page opens on step 2."""

import json
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


def signup(page, *replies):
    """Opens /start signed in. Each `POST /api/center/orgs` takes the next reply (the last one repeats):
    (status, body[, headers]), "abort" (no connection) or "hold" (kept open; answer it through the
    returned `held` list). Returns (posted bodies, held routes)."""
    posts, held = [], []

    def handle(route):
        req = route.request
        key = req.method + " " + urlparse(req.url).path
        if key == "GET /api/center/me":
            return route.fulfill(json=ME)
        if key != "POST /api/center/orgs":
            return route.fulfill(status=404, json={"detail": "Not Found"})
        reply = replies[min(len(posts), len(replies) - 1)]
        posts.append(json.loads(req.post_data))
        if reply == "abort":
            return route.abort()
        if reply == "hold":
            return held.append(route)
        status, body, *headers = reply
        route.fulfill(status=status, json=body, headers=headers[0] if headers else None)

    page.add_init_script(
        "try { localStorage.setItem('dory_session', 'ss1.e2e.sig'); } catch (e) {}"
    )
    page.route("**/api/**", handle)
    page.goto("/start")
    expect(page.locator("#step2")).to_be_visible()
    return posts, held


def to_step3(page):
    page.get_by_role("button", name="Next").click()
    expect(page.locator("#step3")).to_be_visible()


def name_field(page):
    return page.get_by_role("textbox", name="Organization name")


def create_button(page):
    return page.locator("#create")


def test_the_happy_path_lands_on_each_step_heading_and_names_the_new_organization(page):
    posts, _ = signup(page, CREATED)
    expect(page.locator("#step2 h2")).to_be_focused()
    to_step3(page)
    expect(page.locator("#step3 h2")).to_be_focused()
    name_field(page).fill(f"  {NAME} ")
    page.get_by_role("button", name="Create organization").click()
    expect(page.locator("#step4")).to_be_visible()
    expect(page.locator("#step4 h2")).to_be_focused()
    expect(page.locator("#created-note")).to_contain_text(f'"{NAME}" is ready')
    assert posts == [{"name": NAME}]


def test_a_double_click_or_enter_while_creating_sends_one_request(page):
    posts, held = signup(page, "hold", CREATED)
    to_step3(page)
    name_field(page).fill(NAME)
    button = create_button(page)
    button.dblclick()
    expect(button).to_have_text("Creating…")
    expect(button).to_have_attribute("aria-busy", "true")
    expect(button).to_have_attribute("aria-disabled", "true")
    name_field(page).press("Enter")
    name_field(page).press("Enter")
    page.wait_for_timeout(300)
    assert len(posts) == 1
    held[0].fulfill(json=ORG)
    expect(page.locator("#step4")).to_be_visible()
    assert len(posts) == 1


def test_a_lost_connection_keeps_the_name_and_the_same_button_retries(page):
    posts, _ = signup(page, "abort", CREATED)
    to_step3(page)
    name_field(page).fill(NAME)
    create_button(page).click()
    error = page.locator("#org-error")
    expect(error).to_have_text("Couldn't reach Dory. Check your connection and try again.")
    expect(name_field(page)).to_have_value(NAME)
    expect(create_button(page)).to_have_text("Create organization")
    expect(create_button(page)).not_to_have_attribute("aria-busy", "true")
    expect(name_field(page)).not_to_have_attribute("aria-invalid", "true")  # the name was fine
    create_button(page).click()
    expect(page.locator("#step4")).to_be_visible()
    assert posts == [{"name": NAME}, {"name": NAME}]  # the server dedupes the repeat


def test_too_many_attempts_names_the_seconds_from_retry_after(page):
    signup(page, (429, {"detail": "Too many attempts"}, {"Retry-After": "42"}))
    to_step3(page)
    name_field(page).fill(NAME)
    create_button(page).click()
    expect(page.locator("#org-error")).to_have_text("Too many attempts. Try again in 42 seconds.")


def test_a_server_error_shows_its_status(page):
    signup(page, (502, {"detail": "Bad Gateway"}))
    to_step3(page)
    name_field(page).fill(NAME)
    create_button(page).click()
    expect(page.locator("#org-error")).to_contain_text("502")


def test_a_blank_name_or_a_422_marks_the_field_and_puts_focus_back(page):
    posts, _ = signup(page, (422, {"detail": "Organization name is required"}))
    to_step3(page)
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
    assert posts == []

    field.fill(NAME)
    create_button(page).focus()
    page.keyboard.press("Enter")  # the server says no
    expect(error).to_contain_text("Check the organization name")
    expect(field).to_have_attribute("aria-invalid", "true")
    expect(field).to_be_focused()
    expect(field).to_have_value(NAME)
    assert posts == [{"name": NAME}]


def test_the_whole_sign_up_works_by_keyboard_alone(page):
    posts, _ = signup(page, CREATED)
    expect(page.locator("#step2 h2")).to_be_focused()
    page.keyboard.press("Tab")  # the plan
    page.keyboard.press("Tab")
    expect(page.get_by_role("button", name="Next")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("#step3 h2")).to_be_focused()
    page.keyboard.press("Tab")
    expect(name_field(page)).to_be_focused()
    page.keyboard.type(NAME)
    page.keyboard.press("Enter")
    expect(page.locator("#step4 h2")).to_be_focused()
    assert posts == [{"name": NAME}]


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


@pytest.mark.parametrize("width", [390, 1440])
def test_axe_finds_no_wcag_aa_violations_on_the_organization_step(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(reduced_motion="reduce")  # everything visible at once
    signup(page, CREATED)
    to_step3(page)
    create_button(page).click()  # blank: the error and aria-invalid are part of the scan
    expect(page.locator("#org-error")).to_be_visible()
    res = Axe().run(page, options=WCAG)
    assert res.violations_count == 0, res.generate_report()


@pytest.mark.parametrize("width", [360, 390])
def test_no_sideways_scroll_and_44px_buttons_on_a_phone(page, width):
    page.set_viewport_size({"width": width, "height": 740})
    page.emulate_media(reduced_motion="reduce")
    signup(page, CREATED)

    def check(step):
        assert page.evaluate("document.documentElement.scrollWidth") <= width, step
        for box in page.locator(f"#{step} .btn:visible").all():
            assert box.bounding_box()["height"] >= 44, (step, box.text_content())

    check("step2")
    to_step3(page)
    create_button(page).click()
    expect(page.locator("#org-error")).to_be_visible()
    check("step3")
    name_field(page).fill(NAME)
    create_button(page).click()
    expect(page.locator("#step4")).to_be_visible()
    check("step4")


def test_a_sign_in_that_expired_before_create_goes_back_to_sign_in_and_keeps_the_name(page):
    """A 401 on create (the session died after sign-in): back to the sign-in step with a plain line, the
    saved session forgotten, and the typed name kept for the next pass (sessionStorage: survives Discord)."""
    signup(page, (401, {"detail": "Sign-in required"}))
    to_step3(page)
    name_field(page).fill(NAME)
    create_button(page).click()
    expect(page.locator("#step1")).to_be_visible()
    expect(page.locator("#login-error")).to_contain_text("Your sign-in expired")
    assert page.evaluate("localStorage.getItem('dory_session')") is None
    assert page.evaluate("sessionStorage.getItem('dory_signup_org')") == NAME


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


def test_a_one_second_wait_reads_one_second(page):
    signup(page, (429, {"detail": "Too many attempts, try again shortly"}, {"Retry-After": "1"}))
    to_step3(page)
    name_field(page).fill(NAME)
    create_button(page).click()
    expect(page.locator("#org-error")).to_have_text("Too many attempts. Try again in 1 second.")
