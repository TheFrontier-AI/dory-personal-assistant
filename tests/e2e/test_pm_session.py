"""/pm signs in with the same saved Dory session as /center and /start, and forgets one the server rejects."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_pm_sends_the_saved_session_and_forgets_it_when_rejected(page):
    seen = []

    def me(route):
        seen.append(route.request.headers.get("authorization"))
        route.fulfill(status=401, json={"detail": "expired"})

    page.route("**/api/center/me", me)
    page.add_init_script(
        "try { localStorage.setItem('dory_session', 'ss1.saved.sig'); } catch (e) {}"
    )
    page.goto("/pm")
    expect(page.locator("#login")).to_be_visible()
    assert seen == ["Bearer ss1.saved.sig"]
    # the init script puts it back on every navigation, so read it before any reload
    assert page.evaluate("localStorage.getItem('dory_session')") is None
