# Dory intro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a ~40 s, once-per-browser, skippable "from the deep to the surface" intro that plays between `/start`'s Preferences (step 3) and Start (step 4) and hands the person into step 4's examples.

**Architecture:** three new static files under `src/meeting_scribe/static/dory/intro/` (served at `/static/dory/intro/`, the existing `/static/dory` mount): `intro.js` (chapters, timeline, controls, hand-off), `intro-audio.js` (Web Audio synth), `intro.css`. `start.html` only links them, adds seven dictionary keys and calls `DoryIntro.play()` where it already calls `show("step4")` after step 3. No server change, no new dependency.

**Tech Stack:** vanilla JS (Web Animations API for visuals, `setTimeout` for beats so Playwright's `page.clock` can drive them), Web Audio API, CSS with `theme.css` tokens; pytest (`tests/test_dory_page.py`) and Playwright + axe (`tests/e2e/`).

**Spec:** `docs/superpowers/specs/2026-10-30-dory-intro-design.md` (approved by the owner 30 Oct).

## Global Constraints

- English use cases only: every example, headline and chapter line is the spec's copy deck text, in both page languages; only the controls and the region label are translated (dictionary keys below, Thai and English).
- No Thai characters in `start.html` markup or in `intro.js` (the dictionary carries Thai); no `localStorage` in `start.html` after `dory_center_handoff` (existing test).
- Tokens from `theme.css` only; Glow `#5FF2E0` only as Dory's working light beside its label; no Lantern; fonts Anuphan + IBM Plex Sans Thai; chips flat (no blur, glass or resting shadow); example notice "Example with fictional names" at ≥ 16 px, sentence case.
- Motion: headline lines rise 28 px over 800 ms `cubic-bezier(.16,1,.3,1)`, 90 ms apart; chips 600 ms `var(--ease)`, 70 ms apart; status swap 240 ms; press 140 ms; surfacing 1,200 ms `var(--ease-in-out)`; exits ≈ 70 % of entrances; transforms and opacity only; nothing over 3 Hz.
- Sound off at the start of every run; the `AudioContext` is created only inside the Sound toggle's click; no audio files; suspended while the tab is hidden.
- Plays once per browser (`localStorage["dory-intro"] = "seen"`), only when step 4 is reached from step 3 in this tab; `/start?intro=1` replays it without touching any account and without writing `seen`.
- Stills (no movement) when `prefers-reduced-motion: reduce` or `localStorage["dory-motion"] === "off"`; no Web Animations API → no intro, straight to step 4.
- Skip and Esc end it at once; nothing on step 4 is blocked afterwards; the decision beat waits at most 4 s.

## Review Focus

1. Storage blocked (every `localStorage` call throws): the intro plays, skips and ends normally. → Task 2 test `test_blocked_storage_still_plays_and_skips`.
2. Rapid input (Next pressed five times fast, Skip during the decision beat): one chapter per press within bounds, the layer always closes. → Task 2 `test_rapid_next_and_skip_mid_decision`.
3. Language switch while it plays: controls relabel to Thai, the story stays English. → Task 2 `test_language_switch_relabels_controls_only`.
4. Landscape phone 568×320: no sideways scroll, controls reachable, hand-off falls back to a fade when the first example is off screen. → Task 3 `test_small_landscape_fits_and_closes`.
5. Tab hidden mid-run with sound on: audio suspends, resumes on return. → Task 4 `test_sound_suspends_when_the_tab_is_hidden`.

---

### Task 1: Wire the intro into `/start` (no behaviour yet)

**Files:**
- Create: `src/meeting_scribe/static/dory/intro/intro.js`, `intro-audio.js`, `intro.css` (stubs)
- Modify: `src/meeting_scribe/static/start.html` (head links, dictionary, two step-3 → step-4 call sites at the `pref-form` submit success and `pref-skip` click, `?intro=1` on load)
- Modify: `tests/e2e/conftest.py` (`english_ui` also sets `dory-intro` to `seen`)
- Test: `tests/test_dory_page.py`

**Interfaces:**
- Produces: `window.DoryIntro = { shouldPlay({ preview }): boolean, play({ t, preview, onDone }): Promise<void> }` (stub: `shouldPlay` returns false, `play` calls `onDone()`); dictionary keys `intro_label` Meet Dory / รู้จักดอรี่, `intro_skip` Skip / ข้าม, `intro_next` Next / ถัดไป, `intro_pause` Pause / หยุดชั่วคราว, `intro_play` Play / เล่นต่อ, `intro_sound_on` Sound on / เปิดเสียง, `intro_sound_off` Sound off / ปิดเสียง; `start.html` passes `t` and calls `show("step4")` inside `onDone` for the real trigger.

- [ ] **Step 1: Write the failing tests** `test_start_loads_the_intro_assets` (asserts `<link rel="stylesheet" href="/static/dory/intro/intro.css">` after the theme link, `<script src="/static/dory/intro/intro-audio.js" defer>` and `<script src="/static/dory/intro/intro.js" defer>`, all seven keys in the dictionary with `th` and `en`, `t("intro_skip")` used in the script) and `test_intro_assets_are_served_english_only_and_file_free(client)` (GET each of the three files → 200 with a JS/CSS content type; no `[฀-๿]` in `intro.js`; no `.mp3/.wav/.ogg/.m4a` file in the folder).
- [ ] **Step 2: Run** `env -u HUB_GOOGLE_CLIENT_ID -u DORY_DISCORD_CLIENT_SECRET -u DORY_DISCORD_TOKEN -u DORY_HUB_ADMIN_EMAILS -u DORY_HUB_URL -u DORY_NEBIUS_API_KEY -u GOOGLE_APPLICATION_CREDENTIALS -u GOOGLE_OAUTH_CLIENT_SECRET uv run pytest tests/test_dory_page.py -q -k "intro or start"` → the two new tests FAIL, the existing start tests pass.
- [ ] **Step 3: Implement** the stubs, the links, the keys and the two call sites (`onDone` → `show("step4")`; when `shouldPlay` is false, call `show("step4")` directly, unchanged behaviour).
- [ ] **Step 4: Run** the same command plus `uvx --from 'uv>=0.10' uv run --no-sync pytest -m e2e tests/e2e/test_start_signup.py tests/e2e/test_onboarding_handoff.py -q` (same `env -u` prefix) → all PASS.
- [ ] **Step 5: Commit** "Start: load the intro assets and its seven control strings (no behaviour yet)".

### Task 2: The intro's story, controls and hand-off

**Files:**
- Modify: `src/meeting_scribe/static/dory/intro/intro.js`
- Test: `tests/e2e/test_start_intro.py` (new; reuse `signup`, `create_org` from `tests/e2e/test_start_signup.py`; clear the seen flag with `page.add_init_script("try{localStorage.removeItem('dory-intro')}catch(e){}")`; drive beats with `page.clock.install()` / `page.clock.run_for(ms)`)

**Interfaces:**
- Consumes: Task 1's API and keys.
- Produces (DOM contract used by Tasks 3–5): overlay `#intro` (`role="dialog"`, `aria-modal="true"`, `aria-labelledby="intro-title"`, `data-mode="motion"|"stills"`, `data-chapter="0".."8"`), `#intro-title` (visually hidden, text `t("intro_label")`), controls `#intro-skip`, `#intro-next`, `#intro-pause` (label swaps Pause/Play), `#intro-sound` (`aria-pressed`), chapter dots `#intro-dots` (9 items, current one `aria-current="step"`), live region `#intro-live` (`aria-live="polite"`), stage `#intro-stage`; decision buttons `#intro-accept`, `#intro-edit`, `#intro-decline`; module constant `CHAPTERS` (array of 9 `{ id, ms, line, live }` with the spec's English copy) and `DECISION_WAIT_MS = 4000`.

- [ ] **Step 1: Write the failing e2e tests:**
  - `test_preview_plays_from_the_brand_frame_and_closes_without_writing_seen` (`/start?intro=1` → dialog named "Meet Dory", `data-chapter="0"`; after `run_for(2000)` the live region contains "Ask once. Dory remembers."; Skip → dialog gone; `localStorage['dory-intro']` is null).
  - `test_after_preferences_it_plays_once_then_lands_on_step_4` (signup, create org, "Skip for now" → dialog visible over `#step4`; Skip → dialog gone, step 4 heading "You're all set" focused, `#tries a` clickable; reload the same flow → no dialog).
  - `test_escape_skips` · `test_next_steps_chapters_and_dots_follow` (Next ×2 → `data-chapter="2"`, third dot `aria-current="step"`) · `test_the_decision_waits_four_seconds_then_accepts` (reach chapter 3; `run_for(3900)` still chapter 3; `run_for(200)` → text "Accepted", then chapter 4) · `test_pressing_decline_says_you_decide` ("You decide, every time.").
  - `test_blocked_storage_still_plays_and_skips` (init script makes `localStorage` getters throw) · `test_rapid_next_and_skip_mid_decision` · `test_language_switch_relabels_controls_only` (switch to Thai mid-run → Skip reads "ข้าม", live region still English) · `test_focus_stays_inside_the_dialog` (Tab ×12 never leaves `#intro`) · `test_without_web_animations_it_goes_straight_to_step_4` (init script deletes `Element.prototype.animate` → no dialog, step 4 heading focused).
- [ ] **Step 2: Run** `uvx --from 'uv>=0.10' uv run --no-sync pytest -m e2e tests/e2e/test_start_intro.py -q` (with the `env -u` prefix) → FAIL.
- [ ] **Step 3: Implement** `shouldPlay` (seen flag via a try/catch helper; preview always true), `play` (build the overlay once, focus Skip, trap focus, beat scheduler on `setTimeout` from `CHAPTERS[i].ms`, Pause/Next/Skip/Esc, the decision wait and the three outcomes, the live region text per chapter = its line, write `seen` on close unless preview, remove the layer, call `onDone`). Copy only from the spec's copy deck. Reduced motion and `dory-motion === "off"` set `data-mode="stills"` (no auto-advance in stills: Next steps through; Skip closes).
- [ ] **Step 4: Run** the e2e file and Task 1's commands → PASS.
- [ ] **Step 5: Commit** "Intro: chapters, controls, decision beat and hand-off to step 4".

### Task 3: The look and the motion

**Files:**
- Modify: `src/meeting_scribe/static/dory/intro/intro.css`, `intro.js` (animations only)
- Test: `tests/e2e/test_start_intro.py`

**Interfaces:**
- Consumes: Task 2's DOM contract (ids, `data-mode`, `data-chapter`).
- Produces: CSS custom properties local to `#intro` (`--intro-rise: 28px`, `--intro-line: 800ms`, `--intro-chip: 600ms`, `--intro-surface: 1200ms`); the hand-off `handoff(targetEl)` inside `intro.js` that moves the last chip onto `#tries a:first-child` (or fades when it is off screen).

- [ ] **Step 1: Write the failing tests** `test_axe_finds_no_wcag_aa_violations_in_the_intro` (parametrized widths 320 and 1280, chapters 0, 3, 7 reached with Next; `Axe().run(page, options=WCAG)` from `test_start_signup`), `test_stills_mode_has_no_movement` (`page.emulate_media(reduced_motion="reduce")` → `data-mode="stills"`, `document.getAnimations().length == 0` after Next), `test_small_landscape_fits_and_closes` (viewport 568×320: `document.documentElement.scrollWidth <= 568`, Skip visible, chapter 8 ends with the dialog removed), `test_example_notice_is_readable` (computed font-size of the notice ≥ 16 px; text "Example with fictional names").
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the deep scope ground (Abyss → Deep), flat chips one tone step above it, the product-fragment cards (`data-ui`) for the bubbles, task card, receipt, call stage, travel cards and the two role replies, the headline and chip entrances with the constraint numbers, the status label with Dory's glow beside "Dory is working", the 1,200 ms surfacing into the Surface ground, and `handoff()`. Respect `data-mode="stills"` (no animations; cross-fades only).
- [ ] **Step 4: Run** the e2e file → PASS; open `/start?intro=1` locally at 390 and 1440 px and look at every chapter.
- [ ] **Step 5: Commit** "Intro: deep-to-surface look, motion and stills".

### Task 4: Sound

**Files:**
- Modify: `src/meeting_scribe/static/dory/intro/intro-audio.js`, `intro.js` (cues)
- Test: `tests/e2e/test_start_intro.py`

**Interfaces:**
- Produces: `window.DoryIntroAudio.create(): { setOn(on: boolean): Promise<void>, cue(name: "ping"|"pop"|"tick"|"dip"|"chime"|"swell"): void, suspend(): void, resume(): void }`; `intro.js` calls `create()` only inside the first `#intro-sound` click and `cue()` at the spec's beats.

- [ ] **Step 1: Write the failing tests** (init script wraps `window.AudioContext` to count constructions and calls to `suspend`/`resume`): `test_sound_starts_off_and_no_audio_context_exists` (`aria-pressed="false"`, 0 contexts after 10 s of intro), `test_sound_toggle_creates_one_context_and_mutes` (click → 1 context, `aria-pressed="true"`, label "Sound off"; click again → muted, still 1 context), `test_sound_suspends_when_the_tab_is_hidden` (sound on; dispatch `visibilitychange` with `document.hidden` true → `suspend` called; back → `resume`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** the synth: a filtered two-sine pad, the ping D6 → A6 (1174.66 Hz → 1760 Hz, soft bell envelope), sine pops, a filtered-noise tick, the dip (pad −9 dB over 400 ms), a three-note chime, the final swell; master gain about −18 dBFS; `visibilitychange` suspend/resume.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** "Intro: optional synthesized sound, off by default".

### Task 5: Taste gate, full checks, pull request

**Files:**
- Modify: whatever the gate finds (intro files only)

- [ ] **Step 1: Run** the design-taste gate: `node ~/.claude/skills/design-taste-frontend/scripts/lint.mjs src/meeting_scribe/static/dory/intro` and, with the app served locally (`env -u … STORE=memory uv run uvicorn meeting_scribe.app:app --port 8092`), `node ~/.claude/skills/design-taste-frontend/scripts/inspect.mjs "http://localhost:8092/start?intro=1" --allow gradient,glow`; fix every FAIL, defend or fix every WARN.
- [ ] **Step 2: Look:** screenshots of every chapter in stills mode at 1440, 768, 390 px; critique with the skill's `references/critique.md`; fix the top three; look again (three rounds at most).
- [ ] **Step 3: Run** the whole offline suite and the e2e suite with the `env -u` prefix (`uv run pytest -q`, `uvx --from 'uv>=0.10' uv run --no-sync pytest -m e2e tests/e2e -q`), `uvx ruff check . && uvx ruff format --check .` → all green.
- [ ] **Step 4: Push** `feat/dory-intro` and open a pull request against `main` (body: what, why, the spec link, screenshots, how to preview with `/start?intro=1`, tests run). No merge, no deploy.
