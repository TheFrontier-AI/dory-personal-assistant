"""A command center left open: coming back to the tab (or Dory changing something) reloads the page's data in
place. The page on screen stays until the fresh one is drawn: no loading skeleton flashes, the page never
collapses to one screen, the scroll position stays, and the new data really replaces the old."""

import pytest

pytestmark = pytest.mark.e2e

# hidden for 11 s (the refresh threshold is 10 s), then visible again
RETURN_AFTER_11_S = """() => {
  const set = (h) => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => h });
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => (h ? "hidden" : "visible") });
    document.dispatchEvent(new Event("visibilitychange"));
  };
  set(true);
  const real = Date.now; Date.now = () => real() + 11000;
  set(false);
}"""

# every frame for 2 s: is a skeleton in the page, how tall is it, where is it scrolled
WATCH = """() => new Promise((done) => {
  const f = [], t0 = performance.now();
  const step = () => {
    const shown = [...document.querySelectorAll("#content .skeleton")].some((s) => s.checkVisibility({ visibilityProperty: true }));
    f.push({ skel: shown, h: document.documentElement.scrollHeight, y: scrollY,
             old: !!document.querySelector("#content [data-old]") });
    if (performance.now() - t0 < 2000) requestAnimationFrame(step); else done(f);
  };
  requestAnimationFrame(step);
})"""


@pytest.mark.parametrize("trigger", ["tab_return", "dory_changed_something"])
@pytest.mark.parametrize(
    "view", ["overview", "docs", "ws", "apps", "members", "license", "account", "mytasks", "mycal"]
)
def test_a_refresh_keeps_the_page_until_the_new_one_is_drawn(page, view, trigger):
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # the fixtures block web fonts and Google sign-in on purpose; those loads failing are not page errors
    page.on(
        "console",
        lambda m: (
            errors.append(m.text)
            if m.type == "error" and not m.text.startswith("Failed to load resource")
            else None
        ),
    )
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"/center?mock=1#/{view}")
    page.locator("#content > h1").wait_for()
    page.wait_for_timeout(800)  # the view has drawn
    page.evaluate("document.querySelector('#content > :last-child').setAttribute('data-old', '')")
    page.mouse.wheel(0, 700)
    page.wait_for_timeout(300)
    y0, h0 = page.evaluate("[scrollY, document.documentElement.scrollHeight]")
    assert y0 > 0  # the page is long enough to scroll
    if trigger == "tab_return":
        page.evaluate(RETURN_AFTER_11_S)
    else:
        page.evaluate("refreshView()")  # what a chat answer or a Live turn that used a tool calls
    frames = page.evaluate(WATCH)
    assert not any(f["skel"] for f in frames), "a loading skeleton flashed"
    assert min(f["h"] for f in frames) >= h0 * 0.9, "the page collapsed while reloading"
    assert abs(page.evaluate("scrollY") - y0) <= 4, "the scroll position jumped"
    assert not frames[-1]["old"], "the page was not refreshed"
    assert page.locator("#content .stage").count() == 0
    assert errors == []


def test_moving_to_another_page_still_shows_it_loading(page):
    """Only a refresh of the page on screen is quiet: a new page still shows its loading state at once."""
    page.goto("/center?mock=1#/overview")
    page.locator("#content > h1").wait_for()
    seen = page.evaluate(
        """() => new Promise((done) => {
          new MutationObserver((ms, o) => { if (document.querySelector("#content .skeleton")) { o.disconnect(); done(true); } })
            .observe(document.getElementById("content"), { childList: true, subtree: true });
          location.hash = "#/members";
          setTimeout(() => done(false), 1500);
        })"""
    )
    assert seen


def test_an_idle_overview_does_not_redraw_what_has_not_changed(page):
    """The overview's Discord actions card checks a pending action every 5 s; an unchanged list is not drawn
    again (a redraw drops the focus and selection in it), and a hidden tab does not ask at all."""
    page.goto("/center?mock=1#/overview")
    page.locator("#ov-actions .tbl").wait_for(state="attached")  # folded away until opened
    assert (
        page.locator("#ov-actions .badge.warn").count() > 0
    )  # a pending action keeps the 5 s check alive
    changes = page.evaluate(
        """() => new Promise((done) => {
          let n = 0;
          new MutationObserver((ms) => { n += ms.length; }).observe(document.getElementById("ov-actions"), { childList: true, subtree: true });
          setTimeout(() => done(n), 11500);
        })"""
    )
    assert changes == 0
