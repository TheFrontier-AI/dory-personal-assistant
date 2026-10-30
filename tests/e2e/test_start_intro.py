"""Browser checks for the first-time intro over /start's last step (static/dory/intro/intro.js).

It plays once per browser over step 4, right after the travel step, and gives the focus to step 4's heading when it
ends; /start?intro=1 replays it with no account and remembers nothing. Skip and Esc end it at once, the decision beat
waits at most four seconds, stills (reduced motion or the homepage's saved Pause) keep the same timeline without
movement, and only the controls follow the page language: the story is English. Its beats are timeouts, so every test
holds the page's clock and moves it by hand."""

import datetime

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import expect

from .test_start_signup import CREATED, WCAG, create_org, person, signup

pytestmark = [pytest.mark.e2e, pytest.mark.intro]

T0 = datetime.datetime(2026, 10, 30, 9, 0, tzinfo=datetime.UTC)
PREVIEW = "/start?intro=1"
STORY_MS = 40_000  # every chapter with the full decision wait is about 36 s
# The intro's own animations (the theme and the page run their own, reduced ones). They run on the browser's real
# clock, not the page's held one: a test that needs them finished waits for them (settle).
OWN = "a.effect && a.effect.target && a.effect.target.closest('#intro')"
# what each running animation inside the intro changes: a transition by its property, an animation by its keyframes
MOVING = f"""() => document.getAnimations().filter((a) => {OWN}).map((a) => a.transitionProperty
  ? [a.transitionProperty]
  : a.effect.getKeyframes().flatMap((k) => Object.keys(k).filter((p) => !['offset', 'computedOffset', 'easing',
    'composite'].includes(p))))"""
SETTLED = f"""() => document.getAnimations().every((a) => !({OWN}) || a.playState !== 'running'
  || a.effect.getTiming().iterations === Infinity)"""
# Next pressed in the page itself, so the cross-fade it starts is measured before the browser's clock moves on
NEXT_THEN_MOVING = (
    f"() => {{ document.getElementById('intro-next').click(); return ({MOVING})(); }}"
)
# every chapter's line on screen, and what the live region reads (chapter 8 has neither: it hands over to step 4)
COPY = {
    1: ("Ask once. Dory remembers.", "Ask once. Dory remembers."),
    2: ("She answers with the source.", "Ploy confirmed it in #sales."),
    3: ("Say it once, and it becomes a task with an owner.", "Send the ABC deck · Ploy · due Fri."),
    4: ("Snap a receipt. She files it.", "Travel this month: 3,180 THB."),
    5: ("Or ask out loud.", "Done. I'll remind you on Friday at 4 pm."),
    6: (
        "Plan a trip in one sentence.",
        "Fictional property · Sample rating and reviews. Booked in the sandbox.",
    ),
    7: ("She only shares what your role allows.", "Company totals are for managers."),
    8: ("Who's going to Singapore next week?", ""),
}
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


@pytest.fixture
def logged(page):
    """Errors the intro caught and logged: it ends itself on one, so a test would not notice it otherwise."""
    seen = []
    page.on(
        "console",
        lambda m: (
            m.type == "error" and "/intro/" in m.location.get("url", "") and seen.append(m.text)
        ),
    )
    return seen


def settle(page):
    """Waits until every one-off animation inside the intro has played (the snow and Dory's light loop on)."""
    page.wait_for_function(SETTLED)


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
    # the dots are a list assistive technology reaches, numbered, so "current step" means something
    expect(intro(page).get_by_role("list").get_by_role("listitem")).to_have_count(9)
    expect(dots.nth(4)).to_have_text("5")
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


@pytest.mark.parametrize("chapter", sorted(COPY))
def test_every_chapter_shows_its_line_and_reads_its_example(page, chapter):
    line, said = COPY[chapter]
    page.goto(PREVIEW)
    next_times(page, chapter)
    expect(intro(page)).to_have_attribute("data-chapter", str(chapter))
    expect(
        stage(page).locator(f":scope > :nth-child({chapter + 1})").get_by_text(line)
    ).to_be_visible()
    if said:
        expect(live(page)).to_contain_text(said)
    else:
        expect(live(page)).to_have_text("")


def test_pause_holds_what_moves_and_next_still_brings_the_next_chapter(page):
    page.goto(PREVIEW)
    next_times(page, 2)  # the answer chapter builds itself over about four seconds
    expect(stage(page).locator(":scope > :not([hidden])")).to_have_count(
        1
    )  # the chapter before has faded out
    page.locator("#intro-pause").click()
    held = f"document.getAnimations().filter((a) => {OWN}).map((a) => a.playState)"
    states = page.evaluate(held)
    # the marine snow, Dory's light and the beats all hold
    assert states and "running" not in states, states
    control(page, "Next").click()  # the next chapter still comes in while the story waits
    expect(intro(page)).to_have_attribute("data-chapter", "3")
    settle(page)
    expect(page.locator("#intro-accept")).to_be_visible()
    page.locator("#intro-pause").click()
    assert "running" in page.evaluate(held)  # and Play lets everything move again


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


@pytest.mark.parametrize(
    ("reduce", "saved"),
    [(True, None), (False, "off"), (True, "on")],
    ids=["reduced motion", "homepage pause", "reduced motion beats the homepage's motion on"],
)
def test_stills_keep_the_timeline_and_close_at_the_end(page, reduce, saved):
    if reduce:
        page.emulate_media(reduced_motion="reduce")
    if saved:
        page.add_init_script(f"localStorage.setItem('dory-motion', '{saved}');")
    to_the_intro(page)
    expect(intro(page)).to_have_attribute("data-mode", "stills")
    # stills play on their own too, so they can pause
    expect(control(page, "Pause")).to_be_visible()
    page.clock.run_for(2000)
    expect(intro(page)).to_have_attribute("data-chapter", "1")  # the same timeline as motion
    next_times(page, 2)  # Next still steps: on to the decision
    page.clock.run_for(3900)
    expect(stage(page).get_by_text("Accepted", exact=True)).to_have_count(0)
    page.clock.run_for(200)  # it waits at most four seconds here too
    expect(stage(page).get_by_text("Accepted", exact=True)).to_be_visible()
    # nothing moves: whatever still animates only fades (Ruling 8: stills cross-fade, opacity only)
    assert all(set(props) <= {"opacity"} for props in page.evaluate(MOVING))
    page.clock.run_for(STORY_MS)
    expect(page.locator("#intro")).to_have_count(0)  # it closes by itself
    expect(step4_heading(page)).to_be_focused()  # and hands over to step 4
    assert seen_flag(page) == "seen"


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


def test_the_api_never_throws_or_rejects(page, errors, logged):
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
    assert len(logged) == 1  # but what went wrong is in the console, not swallowed


def test_a_missing_intro_script_never_breaks_step_4(page, errors):
    page.route("**/static/dory/intro/intro.js", lambda route: route.abort())
    signup(page, CREATED)
    create_org(page)
    page.get_by_role("button", name="Save and continue").click()
    expect(page.locator("#step4 h2")).to_be_visible()
    page.get_by_role("button", name="ไทย").click()
    expect(page.locator("#step4 h2")).to_have_text("พร้อมแล้ว")
    assert errors == []


# ------------------------------------------------------------------ the look and the motion
@pytest.mark.parametrize("chapter", [0, 3, 7])
@pytest.mark.parametrize("width", [320, 1280])
def test_axe_finds_no_wcag_aa_violations_in_the_intro(page, width, chapter):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(PREVIEW)
    next_times(page, chapter)
    expect(intro(page)).to_have_attribute("data-chapter", str(chapter))
    settle(page)  # every fragment in, none caught half faded
    control(page, "Pause").click()  # the story holds still for the scan...
    page.clock.resume()  # ...while axe-core's own timers run (on the held clock the scan would never end)
    res = Axe().run(page, options=WCAG)
    assert res.violations_count == 0, res.generate_report()


def test_stills_mode_has_no_movement(page):
    page.emulate_media(reduced_motion="reduce")
    page.goto(PREVIEW)
    expect(intro(page)).to_have_attribute("data-mode", "stills")
    for chapter in range(1, 9):
        moving = page.evaluate(NEXT_THEN_MOVING)
        assert moving, f"chapter {chapter} cross-fades in"
        assert all(set(props) <= {"opacity"} for props in moving), (chapter, moving)
    page.clock.run_for(1000)  # chapter 8's hand-off: in stills the layer only fades away
    expect(intro(page)).to_have_attribute("data-handoff", "fade")
    expect(page.locator("#intro [data-fly]")).to_have_count(0)
    assert all(set(props) <= {"opacity"} for props in page.evaluate(MOVING))


def test_small_landscape_fits_and_closes(page, logged):
    page.set_viewport_size({"width": 568, "height": 320})
    to_the_intro(page)
    for chapter in range(9):
        if chapter:
            control(page, "Next").click()
        expect(intro(page)).to_have_attribute("data-chapter", str(chapter))
        sideways = page.evaluate(
            "[document.documentElement.scrollWidth, ...['intro-stage', 'intro'].map((id) => {"
            " const e = document.getElementById(id); return e.scrollWidth - e.clientWidth; })]"
        )
        assert sideways[0] <= 568 and sideways[1:] == [0, 0], (chapter, sideways)
        expect(control(page, "Skip")).to_be_in_viewport()
    page.clock.run_for(
        1000
    )  # step 4's first example is below the fold: no chip flies, the layer fades
    expect(intro(page)).to_have_attribute("data-handoff", "fade")
    page.clock.run_for(2000)
    expect(page.locator("#intro")).to_have_count(0)
    expect(step4_heading(page)).to_be_focused()
    assert logged == []


@pytest.mark.parametrize("size", [(1280, 900), (390, 844)], ids=["desktop", "phone"])
def test_the_last_chip_lands_on_the_first_example(page, logged, size):
    page.set_viewport_size(dict(zip(("width", "height"), size, strict=True)))
    to_the_intro(page)
    next_times(page, 8)
    expect(intro(page)).to_have_attribute("data-chapter", "8")
    # step 4 has risen into place underneath (in a real run it had the whole story to do so)
    page.wait_for_function(SETTLED.replace(f"!({OWN}) || ", ""))
    page.clock.run_for(1000)  # the hand-off beat
    expect(intro(page)).to_have_attribute("data-handoff", "land")
    fly = page.locator("#intro [data-fly]")
    # the last thing said, lifted out of the stage
    expect(fly).to_have_text("Who's going to Singapore next week?")
    settle(page)
    # its words now sit on the first example's first line, starting where the example's words start
    words = "(e) => { const r = document.createRange(); r.selectNodeContents(e); const b = r.getClientRects()[0];"
    words += " return [b.left, b.top + b.height / 2]; }"
    landed, example = fly.evaluate(words), page.locator("#tries a").first.evaluate(words)
    assert abs(landed[0] - example[0]) <= 1.5 and abs(landed[1] - example[1]) <= 1.5, (
        landed,
        example,
    )
    page.clock.run_for(1500)
    expect(page.locator("#intro")).to_have_count(0)
    expect(step4_heading(page)).to_be_focused()
    page.locator("#tries a").first.click(trial=True)
    assert logged == []


def test_example_notice_is_readable(page):
    page.goto(PREVIEW)
    next_times(page, 1)
    for chapter in range(2, 8):
        control(page, "Next").click()
        notice = stage(page).locator(f":scope > :nth-child({chapter + 1}) [data-ui=notice]")
        expect(notice).to_have_text("Example with fictional names")
        expect(notice).to_be_visible()
        size, case = notice.evaluate(
            "(e) => [parseFloat(getComputedStyle(e).fontSize), getComputedStyle(e).textTransform]"
        )
        assert size >= 16 and case == "none", (chapter, size, case)
