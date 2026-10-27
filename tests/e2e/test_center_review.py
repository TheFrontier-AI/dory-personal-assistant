"""Browser checks for the command-center review fixes: a feature's 503 never signs the person out, an org without
Discord gets an empty state, position changes reach the charts, no sideways scroll on a phone, the closed menu and
the page behind an overlaying panel are out of the Tab order, Esc never hangs up a call, My profile never
half-saves, the phone menu closes on its backdrop and the calendar keeps keyboard focus.

Most tests use `?mock=1`. The ones about real HTTP answers (503, 404, a failing save) run the page WITHOUT mock
mode against canned answers from `real_page`, because mock mode never goes through `api()`'s status handling."""

import json
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

ORG = {
    "id": "o1",
    "name": "Acme",
    "role": "owner",
    "license": {"plan": "trial", "status": "active", "seats": 10000, "valid_until": None},
}
ME = {
    "email": "owner@example.com",
    "name": "Olive",
    "first_name": "Olive",
    "last_name": "Owner",
    "orgs": [ORG],
    "identities": [{"platform": "google", "external_id": "owner@example.com", "verified": True}],
    "identity_platforms": ["discord", "slack", "line"],
    "language": "en",
}
DISCORD_ON = {
    "platform": "discord",
    "name": "Discord",
    "enabled": True,
    "configured": True,
    "status": "available",
    "connected": 0,
}


def real_page(page, answers):
    """The page without ?mock=1, signed in through a kept Dory session, against canned answers
    {"METHOD /path": (status, body)}; anything else answers 404. Returns the requests made, in order."""
    calls = []
    table = {"GET /api/center/me": (200, ME), **answers}

    def handle(route):
        req = route.request
        key = req.method + " " + urlparse(req.url).path
        calls.append(key)
        status, body = table.get(key, (404, {"detail": "Not Found"}))
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    page.add_init_script(
        "try { localStorage.setItem('dory_session', 'ss1.e2e.sig'); } catch (e) {}"
    )
    page.route("**/api/**", handle)
    return calls


def test_a_feature_503_shows_a_toast_and_keeps_the_person_signed_in(page):
    real_page(
        page,
        {
            "GET /api/center/orgs/o1/workspaces": (200, []),
            "GET /api/center/orgs/o1/sharing": (200, []),
            "GET /api/center/connectors": (200, [DISCORD_ON]),
            "GET /api/center/connectors/discord/start": (503, {"detail": "not configured"}),
        },
    )
    page.goto("/center#/ws")
    page.get_by_role("button", name="Open invite link").click()
    expect(page.locator("#toast")).to_contain_text("Discord is not switched on yet")
    expect(page.locator("#app")).to_be_visible()
    expect(page.locator("#login")).to_be_hidden()


def test_workspaces_offer_the_invite_only_when_the_discord_connector_is_on(page):
    real_page(
        page,
        {
            "GET /api/center/orgs/o1/workspaces": (200, []),
            "GET /api/center/orgs/o1/sharing": (200, []),
            "GET /api/center/connectors": (
                200,
                [{**DISCORD_ON, "enabled": False, "status": "not_configured"}],
            ),
        },
    )
    page.goto("/center#/ws")
    card = page.locator(".card", has=page.get_by_role("heading", name="Add a Discord server"))
    expect(card.get_by_text("Not enabled yet")).to_be_visible()
    expect(page.get_by_role("button", name="Open invite link")).to_have_count(0)


def test_everyone_on_platforms_without_discord_is_an_empty_state(page):
    real_page(
        page,
        {
            "GET /api/center/orgs/o1/members": (
                200,
                [{"email": "owner@example.com", "role": "owner"}],
            ),
            "GET /api/center/orgs/o1/positions": (200, []),
            "GET /api/center/orgs/o1/people": (404, {"detail": "No connected Discord workspace"}),
        },
    )
    page.goto("/center#/members")
    page.get_by_role("tab", name="Everyone on platforms").click()
    box = page.locator(".card", has=page.get_by_text("No Discord server is connected yet"))
    expect(box).to_be_visible()
    expect(box.get_by_role("link", name="Workspaces")).to_have_attribute("href", "#/ws")
    expect(page.get_by_text("Something went wrong")).to_have_count(0)


def test_a_new_position_reaches_the_positions_chart_and_find_an_expert(page):
    page.goto("/center?mock=1#/members")
    page.get_by_role("tab", name="Org chart").click()
    page.get_by_role("tab", name="Positions chart").click()
    expect(page.locator(".ptree")).to_contain_text("Sales Lead")
    page.get_by_role("tab", name="Find an expert").click()  # loaded once, before the change
    expect(page.locator("#ex-pos")).to_contain_text("Sales Lead")
    page.get_by_role("tab", name="Positions", exact=True).click()
    page.get_by_role("button", name="Create position").click()
    page.locator("#po-title").fill("Ops Lead")
    page.locator("#confirm-ok").click()
    expect(page.locator(".poscard", has_text="Ops Lead")).to_be_visible()
    page.get_by_role("tab", name="Org chart").click()
    expect(page.locator(".ptree")).to_contain_text("Ops Lead")
    page.get_by_role("tab", name="Find an expert").click()
    expect(page.locator("#ex-pos")).to_contain_text("Ops Lead")


@pytest.mark.parametrize(
    "route", ["members", "docs", "mytasks", "mycal", "apps", "account", "monitor"]
)
def test_no_sideways_page_scroll_on_a_phone(page, route):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/center?mock=1#/" + route)
    page.locator("#content [aria-busy]").wait_for(state="detached")
    page.wait_for_timeout(300)
    over = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert over <= 0, f"{route}: {over}px too wide"


def test_the_closed_phone_menu_is_not_a_tab_stop_and_its_backdrop_closes_it(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("/center?mock=1#/overview")
    page.locator("#ov-hero").wait_for()
    page.evaluate("document.activeElement.blur()")
    for _ in range(3):
        page.keyboard.press("Tab")
        assert not page.evaluate("document.getElementById('side').contains(document.activeElement)")
    page.locator("#burger").click()
    expect(page.locator("body")).to_have_class("nav-open")
    expect(page.locator("#side").get_by_role("link", name="Members")).to_be_visible()
    page.mouse.click(375, 600)  # the dimmed page, right of the menu
    expect(page.locator("body")).not_to_have_class("nav-open")
    expect(page.locator("#burger")).to_have_attribute("aria-expanded", "false")


@pytest.mark.parametrize("width", [1024, 390])
def test_the_overlaying_panel_is_modal_and_the_call_hides_the_chat_behind_it(page, width):
    page.set_viewport_size({"width": width, "height": 800})
    page.goto("/center?mock=1#/overview")
    page.locator("#fab").click()
    page.locator("#panel .chat textarea").wait_for()
    expect(page.locator("#panel")).to_have_attribute("aria-modal", "true")
    for _ in range(25):
        page.keyboard.press("Tab")
        assert page.evaluate(
            "(() => { const a = document.activeElement; return !a || a === document.body"
            " || document.getElementById('panel').contains(a); })()"
        )
    page.evaluate("() => doryLive.show('listening')")
    page.locator(".call .rb.end").focus()
    for _ in range(12):
        page.keyboard.press("Shift+Tab")
        assert not page.evaluate("!!document.activeElement.closest('#panel .chat > :not(.call)')")
    page.locator("#panel-x").evaluate("b => b.click()")  # closing hands the page back
    expect(page.locator("#panel")).not_to_have_attribute("aria-modal", "true")
    assert not page.evaluate("document.getElementById('mainwrap').inert")


def test_the_docked_panel_is_not_modal(page):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto("/center?mock=1#/overview")
    page.locator("#fab").click()
    page.locator("#panel .chat textarea").wait_for()
    expect(page.locator("#panel")).not_to_have_attribute("aria-modal", "true")
    assert not page.evaluate("document.getElementById('mainwrap').inert")


def test_escape_does_not_hang_up_a_live_call(page):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto("/center?mock=1#/overview")
    page.locator("#fab").click()
    page.locator("#panel .chat textarea").wait_for()
    page.locator("#panel-live").click()
    page.wait_for_function("doryLive.active()")
    page.keyboard.press("Escape")
    page.wait_for_timeout(1200)
    assert page.evaluate("doryLive.active()")
    expect(page.locator("#panel .call")).not_to_have_class("ended")
    expect(page.get_by_role("button", name="End call").first).to_be_visible()


def test_my_profile_offers_no_own_reports_as_manager(page):
    page.goto("/center?mock=1#/account")
    page.locator("#a-boss").wait_for()
    values = page.locator("#a-boss option").evaluate_all("os => os.map(o => o.value)")
    assert values == ["", "new@example.co.th"], (
        values
    )  # everyone else reports to the owner, directly or not


def test_my_profile_saves_the_manager_first_and_never_half_saves(page):
    calls = real_page(
        page,
        {
            "GET /api/center/orgs/o1/members": (
                200,
                [
                    {"email": "owner@example.com", "role": "owner", "reports_to": None},
                    {
                        "email": "bea@example.com",
                        "role": "member",
                        "name": "Bea",
                        "reports_to": None,
                    },
                ],
            ),
            "PUT /api/center/orgs/o1/members/owner@example.com/structure": (
                400,
                {"detail": "that would make a loop"},
            ),
            "PUT /api/center/me/profile": (200, ME),
        },
    )
    page.goto("/center#/account")
    page.locator("#a-boss").select_option("bea@example.com")
    page.locator("#a-title").fill("CEO")
    page.get_by_role("button", name="Save", exact=True).first.click()
    alert = page.locator("#content").get_by_role("alert")
    expect(alert).to_be_visible()
    expect(alert).not_to_contain_text("(400)")
    expect(alert).not_to_contain_text("[")
    assert "PUT /api/center/me/profile" not in calls, calls


def test_my_profile_requires_first_and_last_name(page):
    page.goto("/center?mock=1#/account")
    first = page.locator("#a-first")
    first.fill("")
    page.get_by_role("button", name="Save", exact=True).first.click()
    expect(first).to_have_attribute("aria-invalid", "true")
    expect(first).to_be_focused()
    expect(page.locator("#toast")).not_to_contain_text("Saved")


def test_the_calendar_keeps_keyboard_focus_on_the_chosen_day(page):
    page.goto("/center?mock=1#/mycal")
    cells = page.locator(".cal-cell:not(.today)")
    cells.first.wait_for()
    cells.nth(3).focus()
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.classList.contains('cal-cell')")
    assert page.evaluate("document.activeElement.classList.contains('sel')")


def test_a_waking_voice_server_shows_a_waking_up_status(page):
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto("/center?mock=1#/overview")
    page.locator("#fab").click()
    page.locator("#panel .chat textarea").wait_for()
    # the GLM voice server says "waking" while its machine boots, then "ready"
    page.evaluate("""() => { const send = MockLiveSocket.prototype.send;
      MockLiveSocket.prototype.send = function (d) { if (!this.hello) { this.emit("waking", ""); setTimeout(() => send.call(this, d), 1500); return; } return send.call(this, d); }; }""")
    page.locator("#panel-live").click()
    status = page.locator(".call .speech .sx")
    expect(status).to_have_text("Waking up Dory's voice server, about two minutes…")
    expect(status).not_to_have_text(
        "Waking up Dory's voice server, about two minutes…", timeout=8000
    )


def test_an_answer_saved_after_stop_waiting_shows_up_in_the_chat(page):
    page.goto("/center?mock=1#/chat")
    box = page.get_by_role("textbox", name="Ask Dory anything…")
    box.fill("slow one")
    page.keyboard.press("Enter")
    page.keyboard.press("Escape")
    expect(page.get_by_text("You stopped waiting.")).to_be_visible()
    # the mock server keeps the answer in the history; the page reads it again and shows it
    expect(page.locator(".chatpage .msg.bot.last .body")).to_contain_text("48,570", timeout=12000)
    expect(page.get_by_text("You stopped waiting.")).to_have_count(0)


def test_live_without_an_organization_says_why(page):
    page.goto("/center?mock=1&orgs=0#/overview")
    page.locator("#fab").click()
    page.locator("#panel-live").click()
    expect(page.locator("#toast")).to_contain_text("Create your organization first")
