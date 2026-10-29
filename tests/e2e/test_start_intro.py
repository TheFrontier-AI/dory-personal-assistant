"""Browser checks for the first-time intro over /start's last step (static/dory/intro/intro.js).

It plays once per browser over step 4, right after the travel step, and gives the focus to step 4's heading when it
ends; /start?intro=1 replays it with no account and remembers nothing. Skip and Esc end it at once, the decision beat
waits at most four seconds, stills (reduced motion or the homepage's saved Pause) wait for Next, and only the controls
follow the page language: the story is English. Its beats are timeouts, so every test holds the page's clock and
moves it by hand."""

import datetime

import pytest
from playwright.sync_api import expect

from .test_start_signup import CREATED, create_org, person, signup

pytestmark = [pytest.mark.e2e, pytest.mark.intro]

T0 = datetime.datetime(2026, 10, 30, 9, 0, tzinfo=datetime.UTC)
PREVIEW = "/start?intro=1"
STORY_MS = 40_000  # every chapter with the full decision wait is about 36 s
# Sign-in keeps its session in storage, so storage is blocked from the moment step 4 is drawn: every read and write
# the intro makes then throws, as in a browser that blocks site data.
BLOCK_STORAGE_AT_STEP_4 = """(() => {
  const real = Object.getOwnPropertyDescriptor(window, 'localStorage')
    || Object.getOwnPropertyDescriptor(Window.prototype, 'localStorage');
  Object.defineProperty(window, 'localStorage', { configurable: true, get() {
    const step4 = document.getElementById('step4');
    if (step4 && !step4.hidden) throw new DOMException('The operation is insecure.', 'SecurityError');
    return real.get.call(window);
  } });
})();"""


@pytest.fixture(autouse=True)
def held_clock(page):
    """Timers fire only when the test runs the clock (installed before the first load; it stays paused on reload)."""
    page.clock.install(time=T0)
    page.clock.pause_at(T0 + datetime.timedelta(seconds=1))


@pytest.fixture
def errors(page):
    seen = []
    page.on("pageerror", lambda e: seen.append(str(e)))
    return seen


def intro(page, name="Meet Dory"):
    return page.get_by_role("dialog", name=name)


def control(page, name):
    return page.locator("#intro").get_by_role("button", name=name, exact=True)


def stage(page):
    return page.locator("#intro-stage")


def live(page):
    return page.locator("#intro-live")


def step4_heading(page):
    return page.get_by_role("heading", name="You're all set")


def seen_flag(page):
    return page.evaluate("localStorage.getItem('dory-intro')")


def to_the_intro(page, button="Skip for now"):
    """Signs up and ends the travel step: step 4 is drawn and the intro opens over it."""
    signup(page, CREATED)
    create_org(page)
    page.get_by_role("button", name=button).click()
    expect(page.locator("#step4")).to_be_visible()


def next_times(page, n):
    for _ in range(n):
        control(page, "Next").click()


# ------------------------------------------------------------------ playing and handing over
def test_preview_plays_from_the_brand_frame_and_closes_without_writing_seen(page, errors):
    calls = []
    page.on("request", lambda r: "/api/" in r.url and calls.append(r.url))
    page.goto(PREVIEW)
    expect(intro(page)).to_be_visible()
    expect(intro(page)).to_have_attribute("data-chapter", "0")
    expect(intro(page)).to_have_attribute("data-mode", "motion")
    expect(page.locator("#intro-skip")).to_be_focused()  # first in the focus order
    for name in ("Skip", "Next", "Pause", "Sound"):
        expect(control(page, name)).to_be_visible()
    sound = control(page, "Sound")
    expect(sound).to_have_attribute("aria-pressed", "false")  # every run starts silent
    sound.click()
    expect(sound).to_have_attribute("aria-pressed", "true")
    page.clock.run_for(2000)
    expect(live(page)).to_contain_text("Ask once. Dory remembers.")
    expect(intro(page)).to_have_attribute("data-chapter", "1")
    control(page, "Skip").click()
    expect(page.locator("#intro")).to_have_count(0)
    assert seen_flag(page) is None  # a preview remembers nothing
    assert calls == [] and errors == []  # and touches no account


def test_after_preferences_it_plays_once_then_lands_on_step_4(page, errors):
    to_the_intro(page)
    expect(intro(page)).to_be_visible()  # over step 4, already drawn underneath
    control(page, "Skip").click()
    expect(page.locator("#intro")).to_have_count(0)
    expect(step4_heading(page)).to_be_focused()
    page.locator("#tries a").first.click(trial=True)  # nothing covers the examples any more
    assert seen_flag(page) == "seen"
    # once per browser: the same flow again goes straight to the examples
    page.reload()
    expect(page.locator("#step2")).to_be_visible()
    create_org(page)
    page.get_by_role("button", name="Skip for now").click()
    expect(step4_heading(page)).to_be_focused()
    expect(page.locator("#intro")).to_have_count(0)
    assert errors == []


def test_left_alone_it_ends_on_its_own_and_lands_on_step_4(page):
    to_the_intro(page, button="Save and continue")
    page.clock.run_for(STORY_MS)
    expect(page.locator("#intro")).to_have_count(0)
    expect(step4_heading(page)).to_be_focused()
    assert seen_flag(page) == "seen"


def test_escape_skips(page):
    to_the_intro(page)
    page.clock.run_for(6000)  # mid-story
    page.keyboard.press("Escape")
    expect(page.locator("#intro")).to_have_count(0)
    expect(step4_heading(page)).to_be_focused()
    assert seen_flag(page) == "seen"


# ------------------------------------------------------------------ the story and its controls
def test_next_steps_chapters_and_dots_follow(page):
    page.goto(PREVIEW)
    dots = page.locator("#intro-dots > li")
    expect(dots).to_have_count(9)
    expect(dots.first).to_have_attribute("aria-current", "step")
    next_times(page, 2)
    expect(intro(page)).to_have_attribute("data-chapter", "2")
    expect(dots.nth(2)).to_have_attribute("aria-current", "step")
    expect(page.locator("#intro-dots [aria-current]")).to_have_count(1)
    shown = stage(page).locator(":scope > :not([hidden])")
    expect(shown).to_have_count(1)  # one chapter at a time
    # the example is labelled, told on screen and read to screen readers
    expect(shown.get_by_text("Example with fictional names")).to_be_visible()
    expect(shown.get_by_text("What price did we agree with ABC?")).to_be_visible()
    expect(shown.get_by_text("She answers with the source.")).to_be_visible()
    expect(live(page)).to_contain_text("42,000 THB for the Q4 package.")


def test_pause_holds_the_story_and_play_goes_on(page):
    page.goto(PREVIEW)
    pause = page.locator("#intro-pause")
    page.clock.run_for(1000)  # most of the brand frame's 1.4 s
    pause.click()
    expect(pause).to_have_text("Play")
    page.clock.run_for(10_000)
    expect(intro(page)).to_have_attribute("data-chapter", "0")
    pause.click()
    expect(pause).to_have_text("Pause")
    page.clock.run_for(500)  # it goes on from where it was, not from the start of the chapter
    expect(intro(page)).to_have_attribute("data-chapter", "1")


def test_the_decision_waits_four_seconds_then_accepts(page):
    page.goto(PREVIEW)
    next_times(page, 3)
    expect(intro(page)).to_have_attribute("data-chapter", "3")
    expect(stage(page).get_by_text("Send the ABC deck · Ploy · due Fri")).to_be_visible()
    expect(page.locator("#intro-accept")).to_be_visible()
    page.clock.run_for(3900)
    expect(intro(page)).to_have_attribute("data-chapter", "3")
    expect(stage(page).get_by_text("Accepted", exact=True)).to_have_count(0)
    page.clock.run_for(200)
    expect(stage(page).get_by_text("Accepted", exact=True)).to_be_visible()
    expect(live(page)).to_have_text("Accepted")
    expect(intro(page)).to_have_attribute("data-decision", "accept")
    page.clock.run_for(2000)
    expect(intro(page)).to_have_attribute("data-chapter", "4")


@pytest.mark.parametrize("choice", ["Edit", "Decline"])
def test_pressing_decline_says_you_decide(page, choice):
    page.goto(PREVIEW)
    next_times(page, 3)
    control(page, choice).click()
    expect(stage(page).get_by_text("You decide, every time.")).to_be_visible()
    expect(live(page)).to_have_text("You decide, every time.")
    # the story goes on, and Dory never presses Accept over the person's choice
    page.clock.run_for(4000)
    expect(intro(page)).to_have_attribute("data-chapter", "4")
    expect(stage(page).get_by_text("Accepted", exact=True)).to_have_count(0)
    expect(control(page, "Next")).to_be_focused()  # the pressed button left with its chapter


@pytest.mark.parametrize("still", ["reduced motion", "homepage pause"])
def test_stills_wait_for_next_and_close_after_the_last(page, still):
    if still == "reduced motion":
        page.emulate_media(reduced_motion="reduce")
    else:
        page.add_init_script("try { localStorage.setItem('dory-motion', 'off'); } catch (e) {}")
    page.goto(PREVIEW)
    expect(intro(page)).to_have_attribute("data-mode", "stills")
    expect(page.locator("#intro-pause")).to_be_hidden()  # nothing plays, so nothing to pause
    page.clock.run_for(STORY_MS)
    expect(intro(page)).to_have_attribute("data-chapter", "0")
    next_times(page, 3)
    page.clock.run_for(STORY_MS)  # the decision waits for the person too
    expect(intro(page)).to_have_attribute("data-chapter", "3")
    next_times(page, 5)
    expect(intro(page)).to_have_attribute("data-chapter", "8")
    control(page, "Next").click()
    expect(page.locator("#intro")).to_have_count(0)


# ------------------------------------------------------------------ the review focus
def test_blocked_storage_still_plays_and_skips(page, errors):
    page.add_init_script(BLOCK_STORAGE_AT_STEP_4)
    to_the_intro(page)
    expect(intro(page)).to_be_visible()
    page.clock.run_for(2000)
    expect(live(page)).to_contain_text("Ask once. Dory remembers.")
    control(page, "Skip").click()
    expect(page.locator("#intro")).to_have_count(0)
    expect(step4_heading(page)).to_be_focused()
    assert errors == []


def test_rapid_next_and_skip_mid_decision(page, errors):
    page.goto(PREVIEW)
    next_times(page, 5)
    expect(intro(page)).to_have_attribute("data-chapter", "5")  # one chapter per press
    next_times(page, 3)
    expect(intro(page)).to_have_attribute("data-chapter", "8")
    control(page, "Next").click()  # past the last chapter it ends: never a chapter 9
    expect(page.locator("#intro")).to_have_count(0)
    page.reload()
    next_times(page, 3)
    expect(page.locator("#intro-accept")).to_be_visible()
    control(page, "Skip").click()  # mid-decision
    expect(page.locator("#intro")).to_have_count(0)
    page.clock.run_for(STORY_MS)  # nothing it had scheduled comes back
    expect(page.locator("#intro")).to_have_count(0)
    assert errors == []


def test_language_switch_relabels_controls_only(page):
    page.goto(PREVIEW)
    expect(intro(page)).to_be_visible()
    # the page's own language switch, behind the layer (as when a signed-in account's language arrives)
    page.locator("[data-lang=th]").dispatch_event("click")
    expect(intro(page, name="รู้จักดอรี่")).to_be_visible()
    for sel, text in (
        ("#intro-skip", "ข้าม"),
        ("#intro-next", "ถัดไป"),
        ("#intro-pause", "หยุดชั่วคราว"),
        ("#intro-sound", "เสียง"),
    ):
        expect(page.locator(sel)).to_have_text(text)
    page.clock.run_for(2000)
    expect(live(page)).to_contain_text("Ask once. Dory remembers.")  # the story stays English
    # ...and screen readers voice it as English on the Thai page
    for story in (stage(page), live(page)):
        expect(story).to_have_attribute("lang", "en")
    page.locator("#intro-pause").click()
    expect(page.locator("#intro-pause")).to_have_text("เล่นต่อ")


def test_focus_stays_inside_the_dialog(page):
    # signed in: once the account arrives the page moves to step 2 behind the intro and focuses that step's heading
    held = []
    page.add_init_script("try { localStorage.setItem('dory_session', 'ss1.e2e'); } catch (e) {}")
    page.route("**/api/center/me", lambda route: held.append(route))
    page.goto(PREVIEW)
    expect(intro(page)).to_be_visible()
    for _ in range(100):
        if held:
            break
        page.wait_for_timeout(20)
    held[0].fulfill(json=person())
    expect(page.locator("#step2")).to_be_visible()
    expect(page.locator("#intro-skip")).to_be_focused()
    next_times(page, 3)  # the decision adds its three buttons
    inside = "document.activeElement.closest('#intro') !== null"
    for key in ["Tab"] * 12 + ["Shift+Tab"] * 4:
        page.keyboard.press(key)
        assert page.evaluate(inside), key


def test_without_web_animations_it_goes_straight_to_step_4(page, errors):
    page.add_init_script("delete Element.prototype.animate;")
    to_the_intro(page)
    expect(step4_heading(page)).to_be_focused()
    expect(page.locator("#intro")).to_have_count(0)
    page.goto(PREVIEW)  # waits for the load event, after the preview call at DOMContentLoaded
    expect(page.locator("#intro")).to_have_count(0)
    assert errors == []


def test_the_api_never_throws_or_rejects(page, errors):
    """start.html calls these inside its own handlers: a throw there would show the travel step's offline note."""
    page.goto("/start")
    got = page.evaluate(
        """async () => {
          const asked = [DoryIntro.shouldPlay(null), DoryIntro.shouldPlay(), DoryIntro.relabel()];
          let done = 0;
          await DoryIntro.play({ t: null, onDone: () => { done += 1; } }); // a broken call still ends cleanly
          return [...asked, done, !!document.getElementById('intro')];
        }"""
    )
    assert got == [True, True, None, 1, False]
    assert errors == []


def test_a_missing_intro_script_never_breaks_step_4(page, errors):
    page.route("**/static/dory/intro/intro.js", lambda route: route.abort())
    signup(page, CREATED)
    create_org(page)
    page.get_by_role("button", name="Save and continue").click()
    expect(page.locator("#step4 h2")).to_be_visible()
    page.get_by_role("button", name="ไทย").click()
    expect(page.locator("#step4 h2")).to_have_text("พร้อมแล้ว")
    assert errors == []
