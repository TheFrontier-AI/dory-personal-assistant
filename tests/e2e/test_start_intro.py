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


def settled(only_intro=True):
    """True once every one-off animation has played: the intro's own, or the whole page's (step 4 rising underneath)."""
    keep = f"!({OWN}) || " if only_intro else ""
    return f"""() => document.getAnimations().every((a) => {keep}a.playState !== 'running'
  || a.effect.getTiming().iterations === Infinity)"""


SETTLED = settled()
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
    # the dots are a list assistive technology reaches (role=list: Safari drops it with the bullets off), named after
    # the story and numbered, so "current step" means something
    expect(intro(page).get_by_role("list", name="Meet Dory").get_by_role("listitem")).to_have_count(
        9
    )
    expect(page.locator("#intro-dots")).to_have_attribute("role", "list")
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
@pytest.mark.parametrize(
    "size",
    [(320, 900), (1280, 900), (320, 480), (568, 320)],
    ids=[
        "phone",
        "desktop",
        "small phone",
        "landscape phone",
    ],  # the last two scroll: scrollable-region-focusable
)
def test_axe_finds_no_wcag_aa_violations_in_the_intro(page, size, chapter):
    page.set_viewport_size(dict(zip(("width", "height"), size, strict=True)))
    page.goto(PREVIEW)
    next_times(page, chapter)
    expect(intro(page)).to_have_attribute("data-chapter", str(chapter))
    settle(page)  # every fragment in, none caught half faded
    control(page, "Pause").click()  # the story holds still for the scan...
    page.clock.resume()  # ...while axe-core's own timers run (on the held clock the scan would never end)
    res = Axe().run(page, options=WCAG)
    assert res.violations_count == 0, res.generate_report()


@pytest.mark.parametrize(
    ("reduce", "saved"),
    [(True, None), (False, "off"), (True, "on")],
    ids=["reduced motion", "homepage pause", "reduced motion beats the homepage's motion on"],
)
def test_stills_mode_has_no_movement(page, reduce, saved):
    """The homepage's Pause is the case that matters most: without the OS setting the theme does not shorten
    anything, so the 240 ms cross-fades really run and a stray slide would show."""
    if reduce:
        page.emulate_media(reduced_motion="reduce")
    if saved:
        page.add_init_script(f"localStorage.setItem('dory-motion', '{saved}');")
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


# where the chapter on screen sits in the stage, whether it is taller than the stage, and the stage's tabindex
STAGE_FIT = """() => { const s = document.getElementById('intro-stage'),
  c = s.children[+document.getElementById('intro').dataset.chapter], b = c.getBoundingClientRect();
  return [b.top - s.getBoundingClientRect().top, b.height > s.clientHeight, s.getAttribute('tabindex')]; }"""


@pytest.mark.parametrize(
    "size", [(568, 320), (320, 480), (1280, 900)], ids=["landscape phone", "small phone", "desktop"]
)
def test_a_chapter_keeps_its_place_and_the_stage_is_a_tab_stop_only_when_it_scrolls(page, size):
    page.set_viewport_size(dict(zip(("width", "height"), size, strict=True)))
    page.goto(PREVIEW)
    tall = []
    for chapter in range(1, 9):
        arrived = page.evaluate(
            f"() => {{ document.getElementById('intro-next').click(); return ({STAGE_FIT})(); }}"
        )
        page.wait_for_function("() => !document.querySelector('#intro-stage > [data-leaving]')")
        now = page.evaluate(STAGE_FIT)
        # the chapter does not jump when the one before it hides (on a short screen the taller one set the row)
        assert abs(arrived[0] - now[0]) <= 1, (chapter, arrived, now)
        assert now[0] >= 0, (chapter, now)  # a taller chapter scrolls from its top
        # the keyboard can reach the stage only when there is something to scroll
        assert now[2] == ("0" if now[1] else None), (chapter, now)
        tall.append(now[1])
    assert any(tall) == (size[1] < 900), tall


def test_a_leaving_chapter_hides_even_when_its_fade_never_ends(page):
    page.goto(PREVIEW)
    page.add_style_tag(content="#intro [data-id][data-leaving] { animation: none !important; }")
    control(page, "Next").click()
    shown = stage(page).locator(":scope > :not([hidden])")
    expect(shown).to_have_count(2)  # no fade, so no animationend
    page.clock.run_for(1000)  # the fail-safe
    expect(shown).to_have_count(1)
    expect(intro(page)).to_have_attribute("data-chapter", "1")


def test_the_layer_closes_when_its_own_fade_ends(page):
    """intro.css is the hand-off's only clock: the layer goes when its fade has played, not on a second timer."""
    page.goto(PREVIEW)
    next_times(page, 8)
    page.clock.run_for(900)  # the hand-off beat
    expect(intro(page)).to_have_attribute("data-handoff", "fade")
    ms = page.evaluate(
        "document.getElementById('intro').getAnimations().find((a) => a.animationName === 'intro-gone'"
        " && !a.effect.pseudoElement).effect.getComputedTiming().endTime"
    )
    assert 0 < ms < 1300, ms
    page.clock.run_for(round(ms) - 50)
    expect(page.locator("#intro")).to_have_count(1)
    page.clock.run_for(100)
    expect(page.locator("#intro")).to_have_count(0)


def _luminance(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(int(v)) for v in rgb.split("(")[1].split(")")[0].split(",")[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_the_current_dot_reads_on_the_surface_ground(page):
    page.goto(PREVIEW)
    next_times(page, 8)
    dot, opacity = page.locator("#intro-dots [aria-current]").evaluate(
        "(e) => [getComputedStyle(e).backgroundColor, getComputedStyle(e).opacity]"
    )
    ground = page.locator("#intro").evaluate(
        "(e) => getComputedStyle(e, '::before').backgroundColor"
    )
    hi, lo = sorted((_luminance(dot), _luminance(ground)), reverse=True)
    assert opacity == "1" and (hi + 0.05) / (lo + 0.05) >= 3, (dot, ground)  # WCAG 1.4.11


@pytest.mark.parametrize("size", [(1280, 900), (390, 844)], ids=["desktop", "phone"])
def test_the_last_chip_lands_on_the_first_example(page, logged, size):
    page.set_viewport_size(dict(zip(("width", "height"), size, strict=True)))
    to_the_intro(page)
    next_times(page, 8)
    expect(intro(page)).to_have_attribute("data-chapter", "8")
    # step 4 has risen into place underneath (in a real run it had the whole story to do so)
    page.wait_for_function(settled(only_intro=False))
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


# ------------------------------------------------------------------ the sound
# The synth is Web Audio, which cannot be heard here, so the page's AudioContext is wrapped: it counts constructions
# and suspend / resume calls, and records every sound source (what it plays at, when it starts on the audio clock,
# how often it was told to stop) and every gain target (what the music is set to).
AUDIO_SPY = """(() => {
  const Real = window.AudioContext || window.webkitAudioContext;
  const spy = window.spy = { contexts: 0, suspend: 0, resume: 0, sources: [], targets: [] };
  const watch = (ctx, node, kind) => {
    const rec = { kind, freq: node.frequency ? node.frequency.value : 0, delay: null, stops: 0, last: null };
    spy.sources.push(rec);
    const start = node.start.bind(node), stop = node.stop.bind(node);
    node.start = (at = 0) => { rec.freq = node.frequency ? node.frequency.value : 0; rec.delay = at - ctx.currentTime; return start(at); };
    node.stop = (at) => { rec.stops += 1; rec.last = at - ctx.currentTime; return stop(at); };
    return node;
  };
  window.AudioContext = class extends Real {
    constructor(...a) { super(...a); spy.contexts += 1; window.audioContext = this; }
    suspend() { spy.suspend += 1; return super.suspend(); }
    resume() { spy.resume += 1; return super.resume(); }
    createOscillator() { return watch(this, super.createOscillator(), 'tone'); }
    createBufferSource() { return watch(this, super.createBufferSource(), 'noise'); }
    createGain() {
      const g = super.createGain(), set = g.gain.setTargetAtTime.bind(g.gain);
      g.gain.setTargetAtTime = (v, t, c) => { spy.targets.push(v); return set(v, t, c); };
      return g;
    }
  };
  delete window.webkitAudioContext;
})();"""
# the tab goes hidden (true) or comes back (false), as the browser tells the page
HIDE_TAB = """(h) => {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => h });
  document.dispatchEvent(new Event('visibilitychange'));
}"""
HZ = {"D5": 587.33, "F#5": 739.99, "A5": 880.0, "D6": 1174.66, "A6": 1760.0}


@pytest.fixture
def spy(page):
    page.add_init_script(AUDIO_SPY)
    return lambda: page.evaluate("JSON.parse(JSON.stringify(window.spy))")


def tones(spy_now, *notes):
    """How many sound sources play at these notes (half a hertz either way)."""
    return sum(
        1
        for s in spy_now["sources"]
        if s["kind"] == "tone" and any(abs(s["freq"] - HZ[n]) < 0.5 for n in notes)
    )


def sound_on(page):
    control(page, "Sound").click()
    expect(control(page, "Sound")).to_have_attribute("aria-pressed", "true")


def test_sound_starts_off_and_no_audio_context_exists(page, spy):
    page.goto(PREVIEW)
    expect(control(page, "Sound")).to_have_attribute("aria-pressed", "false")
    page.clock.run_for(10_000)  # past the ping, the pops and the tick
    now = spy()
    assert now["contexts"] == 0 and now["sources"] == [], now


def test_sound_toggle_creates_one_context_and_mutes(page, spy, errors, logged):
    page.goto(PREVIEW)
    sound_on(page)
    # the name stays "Sound": the state is aria-pressed (ruling 3)
    page.wait_for_function("window.spy.sources.length >= 2")
    now = spy()
    assert now["contexts"] == 1
    pad = [k for k, s in enumerate(now["sources"]) if s["stops"] == 0]
    assert len(pad) == 2, (
        now
    )  # a two-sine pad, running until it is muted (every other sound has an end of its own)
    control(page, "Sound").click()
    expect(control(page, "Sound")).to_have_attribute("aria-pressed", "false")
    now = spy()
    assert now["contexts"] == 1 and now["targets"][-1] == 0, (
        now
    )  # the mix fades to silence at once...
    assert all(now["sources"][k]["stops"] >= 1 for k in pad), now  # ...and the pad is stopped
    sound_on(page)  # and on again: the same context, a new pad
    now = spy()
    assert now["contexts"] == 1
    assert len([s for s in now["sources"] if s["stops"] == 0]) == 2, now
    assert errors == [] and logged == []


def test_sound_suspends_when_the_tab_is_hidden(page, spy):
    page.goto(PREVIEW)
    sound_on(page)
    before = spy()
    page.evaluate(HIDE_TAB, True)
    after = spy()
    assert after["suspend"] == before["suspend"] + 1, (before, after)
    page.evaluate(HIDE_TAB, False)
    assert spy()["resume"] == after["resume"] + 1


def context_is(page, state):
    page.wait_for_function(f"window.audioContext && window.audioContext.state === '{state}'")


def test_sound_follows_pause_and_a_hidden_tab_does_not_override_it(page, spy):
    page.goto(PREVIEW)
    sound_on(page)
    context_is(page, "running")  # the real context, started from the click
    base = spy()
    page.locator("#intro-pause").click()
    context_is(page, "suspended")
    held = spy()
    assert held["suspend"] == base["suspend"] + 1
    page.evaluate(HIDE_TAB, True)
    page.evaluate(HIDE_TAB, False)  # the tab is back, but the person paused: still held
    assert spy()["resume"] == held["resume"]
    context_is(page, "suspended")
    page.locator("#intro-pause").click()
    assert spy()["resume"] == held["resume"] + 1
    context_is(page, "running")


def test_sound_switched_on_while_paused_starts_held(page, spy):
    page.goto(PREVIEW)
    page.locator("#intro-pause").click()
    sound_on(page)
    context_is(page, "suspended")  # the story is paused: so is the sound
    page.locator("#intro-pause").click()
    context_is(page, "running")


def test_skip_stops_every_voice_at_once(page, spy):
    page.goto(PREVIEW)
    sound_on(page)
    next_times(page, 2)  # the ping is queued
    pad = [k for k, s in enumerate(spy()["sources"]) if s["stops"] == 0]
    assert len(pad) == 2  # only the pad has no end of its own
    control(page, "Skip").click()
    expect(page.locator("#intro")).to_have_count(0)
    now = spy()
    assert now["targets"][-1] == 0, now  # the mix fades to silence at once
    assert all(now["sources"][k]["stops"] >= 1 for k in pad), now
    page.clock.run_for(200)  # after the fade the context itself goes
    context_is(page, "closed")
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    assert spy()["suspend"] == now["suspend"]  # nothing listens any more


def test_cues_fire_only_while_sound_is_on_and_only_from_then_on(page, spy):
    page.goto(PREVIEW)
    next_times(page, 2)  # the answer chapter: its ping and tick pass with the sound off
    page.clock.run_for(1000)
    assert spy()["sources"] == []
    sound_on(
        page
    )  # on mid-chapter (ruling 13): the pad starts, this chapter's cues still to come are dropped...
    now = spy()
    assert len(now["sources"]) == 2 and tones(now, "D6", "A6") == 0, now
    page.clock.run_for(1500)  # past the tick due 2 s into the chapter
    assert [s for s in spy()["sources"] if s["kind"] == "noise"] == []
    next_times(
        page, 3
    )  # ...and the next chapters' cues play: receipts, voice: "I'm listening…" lights Dory
    now = spy()
    assert tones(now, "D6") == 1 and tones(now, "A6") == 1, now


def test_the_ping_and_the_tick_land_on_the_story_beats(page, spy):
    page.goto(PREVIEW)
    sound_on(page)
    next_times(page, 2)
    now = spy()
    ping = sorted(s["delay"] for s in now["sources"] if abs(s["freq"] - HZ["D6"]) < 0.5)
    assert len(ping) == 1 and 0.8 <= ping[0] <= 0.9, now  # Dory's light, 0.8 s into the chapter
    low = [s["delay"] for s in now["sources"] if abs(s["freq"] - HZ["A6"]) < 0.5]
    assert len(low) == 1 and low[0] > ping[0], now  # the second note of the two
    noise = [s["delay"] for s in now["sources"] if s["kind"] == "noise"]
    assert len(noise) == 1 and 2.0 <= noise[0] <= 2.1, now  # the label swaps to "found it"


def test_the_things_said_pop_in_with_the_sound_on(page, spy):
    page.goto(PREVIEW)
    sound_on(page)
    page.clock.run_for(1400)  # the brand frame ends: the promise's three chips rise 70 ms apart
    expect(intro(page)).to_have_attribute("data-chapter", "1")
    now = spy()
    pops = sorted(
        (s["delay"], s["freq"])
        for s in now["sources"]
        if s["kind"] == "tone" and 400 < s["freq"] < 700
    )
    assert [round(f) for _, f in pops] == [480, 550, 620], (
        now
    )  # three soft pops, each a little higher
    assert [d - pops[0][0] for d, _ in pops] == pytest.approx([0, 0.07, 0.14], abs=0.006), pops


def test_in_stills_the_sound_keeps_the_story_beats(page, spy):
    """Ruling 14: stills keep the motion timeline, so a cue lands on its still's cross-fade."""
    page.emulate_media(reduced_motion="reduce")
    page.goto(PREVIEW)
    expect(intro(page)).to_have_attribute("data-mode", "stills")
    sound_on(page)
    next_times(page, 2)
    now = spy()
    ping = [s["delay"] for s in now["sources"] if abs(s["freq"] - HZ["D6"]) < 0.5]
    assert len(ping) == 1 and 0.8 <= ping[0] <= 0.9, now  # the same beat as in motion
    noise = [s["delay"] for s in now["sources"] if s["kind"] == "noise"]
    assert len(noise) == 1 and 2.0 <= noise[0] <= 2.1, now


def test_a_skipped_chapters_cues_do_not_sound_in_the_next(page, spy):
    page.goto(PREVIEW)
    sound_on(page)
    next_times(page, 2)
    tick = [s for s in spy()["sources"] if s["kind"] == "noise"]
    assert len(tick) == 1 and tick[0]["last"] > 2, tick  # due 2 s into the answer chapter
    next_times(page, 1)  # Next leaves that chapter first
    tick = [s for s in spy()["sources"] if s["kind"] == "noise"]
    assert len(tick) == 1 and tick[0]["last"] < 0.05, (
        tick
    )  # so its tick is called off, not left for the next one


def test_the_music_dips_for_the_decision_and_the_chime_follows_accept(page, spy):
    page.goto(PREVIEW)
    sound_on(page)
    pad_level = spy()["targets"][0]
    next_times(page, 3)  # the card waits
    assert spy()["targets"][-1] == pytest.approx(pad_level * 10 ** (-9 / 20))  # nine decibels down
    assert tones(spy(), "D5", "F#5", "A5") == 0  # no chime before the answer
    page.clock.run_for(4100)  # Dory presses Accept herself
    now = spy()
    assert tones(now, "D5") == 1 and tones(now, "F#5") == 1 and tones(now, "A5") == 1, now
    assert now["targets"][-1] == pytest.approx(pad_level)  # and the music comes back


def test_declining_brings_the_music_back_with_no_chime(page, spy):
    page.goto(PREVIEW)
    sound_on(page)
    pad_level = spy()["targets"][0]
    next_times(page, 3)
    control(page, "Decline").click()
    assert tones(spy(), "D5", "F#5", "A5") == 0
    page.clock.run_for(2300)  # the next chapter
    expect(intro(page)).to_have_attribute("data-chapter", "4")
    assert spy()["targets"][-1] == pytest.approx(pad_level)


def test_turning_sound_on_during_the_decision_starts_the_pad_dipped(page, spy):
    page.goto(PREVIEW)
    next_times(page, 3)
    sound_on(page)
    pad_level = spy()["targets"][0]
    assert spy()["targets"][-1] == pytest.approx(pad_level * 10 ** (-9 / 20))


def test_the_swell_sounds_at_the_surface(page, spy, errors, logged):
    page.goto(PREVIEW)
    sound_on(page)
    pad = [k for k, s in enumerate(spy()["sources"]) if s["stops"] == 0]
    next_times(page, 8)
    now = spy()
    swell = [s for s in now["sources"] if s["kind"] == "tone" and 250 < s["freq"] < 750]
    assert len(swell) >= 3, now  # a chord, not a note
    page.clock.run_for(2300)
    expect(page.locator("#intro")).to_have_count(
        0
    )  # and it ends with the story, nothing left playing
    now = spy()
    assert len(pad) == 2 and all(now["sources"][k]["stops"] >= 1 for k in pad), (
        now
    )  # the pad stops with it
    context_is(page, "closed")  # and the context goes (150 ms after the end, inside the run above)
    assert errors == [] and logged == []


def test_without_web_audio_the_intro_plays_silently(page, errors, logged):
    page.add_init_script("delete window.AudioContext; delete window.webkitAudioContext;")
    page.goto(PREVIEW)
    expect(intro(page)).to_be_visible()
    expect(page.locator("#intro-sound")).to_be_hidden()  # nothing to switch on
    expect(control(page, "Skip")).to_be_visible()
    page.clock.run_for(STORY_MS)
    expect(page.locator("#intro")).to_have_count(0)  # it still plays to the end
    assert errors == [] and logged == []


# Sound is optional: whatever goes wrong on the audio path is logged, the audio is closed and its control goes, and the
# story plays on. The context is wrapped so that one call fails: (what fails, the error, the chapter it shows up in and
# how long that chapter plays; the noise tick is first asked for in the answer chapter).
BREAK_AUDIO = """(() => {
  const Real = window.AudioContext;
  window.AudioContext = class extends Real {
    %s
  };
})();"""
BROKEN = [
    ("resume() { return Promise.reject(new Error('resume blocked')); }", "resume blocked", 0, 1500),
    ("createOscillator() { throw new Error('no oscillators'); }", "no oscillators", 0, 1500),
    ("createBufferSource() { throw new Error('no noise'); }", "no noise", 2, 5100),
]


@pytest.mark.parametrize(
    ("fault", "text", "chapter", "ms"), BROKEN, ids=["resume", "oscillator", "noise tick"]
)
def test_an_audio_failure_never_ends_the_intro(page, errors, logged, fault, text, chapter, ms):
    page.add_init_script(BREAK_AUDIO % fault)
    page.goto(PREVIEW)
    control(page, "Sound").click()
    next_times(page, chapter)
    sound = page.locator("#intro-sound")
    expect(sound).to_be_hidden()  # as with no Web Audio
    expect(sound).to_have_attribute("aria-pressed", "false")
    expect(intro(page)).to_have_attribute("data-chapter", str(chapter))  # still open...
    page.clock.run_for(ms)
    expect(intro(page)).to_have_attribute("data-chapter", str(chapter + 1))  # ...and advancing
    control(page, "Next").click()
    expect(intro(page)).to_have_attribute("data-chapter", str(chapter + 2))
    assert errors == []
    assert len(logged) == 1 and text in logged[0], logged
    page.clock.run_for(STORY_MS)
    expect(page.locator("#intro")).to_have_count(0)  # to the end, silently


def test_a_refused_pause_hold_drops_the_sound_and_keeps_the_pause(page, errors, logged):
    page.add_init_script(
        BREAK_AUDIO % "suspend() { return Promise.reject(new Error('suspend blocked')); }"
    )
    page.goto(PREVIEW)
    control(page, "Sound").click()
    page.locator("#intro-pause").click()
    expect(page.locator("#intro-sound")).to_be_hidden()
    expect(page.locator("#intro-pause")).to_have_text("Play")  # the story is paused all the same
    page.clock.run_for(5000)
    expect(intro(page)).to_have_attribute("data-chapter", "0")
    page.locator("#intro-pause").click()
    page.clock.run_for(1500)
    expect(intro(page)).to_have_attribute("data-chapter", "1")
    assert errors == []
    assert len(logged) == 1 and "suspend blocked" in logged[0], logged


def test_what_an_ended_run_leaves_behind_never_touches_the_next_one(page, errors, logged):
    """A run's queued dialog close event and an audio error that arrives after it ended are its own: the next run plays
    on with its Sound button (the error is logged)."""
    page.add_init_script(
        BREAK_AUDIO
        % "resume() { return new Promise((_, no) => setTimeout(() => no(new Error('late resume')), 1000)); }"
    )
    page.goto(PREVIEW)
    control(page, "Sound").click()  # its resume answers a second later
    control(page, "Skip").click()
    expect(page.locator("#intro")).to_have_count(0)
    page.evaluate(
        "() => { DoryIntro.play({ t, preview: true, onDone: () => {} }); }"
    )  # the next run
    expect(control(page, "Sound")).to_be_visible()
    page.clock.run_for(1000)  # the first run's audio fails now
    expect(control(page, "Sound")).to_be_visible()
    expect(intro(page)).to_have_attribute("data-chapter", "0")
    assert errors == []
    assert len(logged) == 1 and "late resume" in logged[0], logged
