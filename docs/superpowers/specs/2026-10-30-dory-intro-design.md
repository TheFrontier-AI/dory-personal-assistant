# Dory intro: "from the deep to the surface" (design)

30 Oct 2026. Owner request (30 Oct, 00:30 Bangkok): use Meta's "Introducing Muse" film as inspiration for a
premium, art-directed introduction to Dory, built into the existing app. Reference analysis:
`motion/dory-launch-film/research/08-muse-intro-reference.md` (untracked, on the owner's disk). Owner picked
the placement on 30 Oct ("OK" to the recommendation below).

## Intent

A new person has just created their organization in `/start`. In about 15 seconds the intro should make them
feel what Dory is for (you ask once, she remembers, finds and follows up, you stay in charge) and then hand
them into the product at the moment of first success: the examples that open the chat. It should look and
sound like a carefully directed launch moment, in Dory's own world, not a generic slideshow.

**Idea (design-taste pass):** in this intro, *the things a team says once in chat* become *objects sinking
into the deep that Dory's light lifts back to the surface*, where the last one turns into the person's first
question. (Competitor test: a generic assistant has no deep, no light and no "said once" objects.)

**The one live thing:** at the decision beat the person presses Accept, Edit or Decline themselves on a copy
of Dory's real task card; any choice continues the story (Accept → chime; Edit / Decline → a one-line
"You decide, every time."), and with no input for 4 seconds it continues on its own. It never blocks.

## Goals, non-goals, anti-goals

- Goals: one rehearsed focal sequence; the brand's deep-to-surface story; a visible "Dory is working" state
  and a moment where the person decides; a seamless hand-off into step 4; optional sound that adds to it;
  fast on phones; accessible; skippable at any moment.
- Non-goals: a product tour of the command center, video files, new server routes, new dependencies,
  changing what step 4 does.
- Anti-goals (failure even if it works): delaying a person who wants to start (no forced wait, no
  blocking clicks after skip), sound that surprises anyone, a fake answer presented as real, Meta's
  look (white + 3D objects + confetti) instead of Dory's, motion that makes anyone dizzy.

## Approaches considered

1. **Right after sign-up, flowing into the chat (chosen).** Plays once between Preferences (step 3) and
   Start (step 4) and resolves into step 4's examples. Most "into the app"; touches the sign-up flow.
2. Homepage hero. Everyone sees it, no auth risk; overlaps the existing film and "See Dory at work".
3. First visit to `/center`. In-app, but the largest page and the highest regression risk.

## The experience (about 15 s; every state also reachable as a still for reduced motion)

The intro is a full-viewport layer over step 4, which is already rendered (and focused at the end)
underneath. Times are targets; motion tokens from `theme.css` (`--ease`, `--ease-buoy`, durations).

| t (s) | Beat | Picture | Sound (only if on) |
| --- | --- | --- | --- |
| 0.0–1.4 | Brand frame | Deep scope (Abyss → Deep), sparse marine snow. The round painted mark `dory-mark.webp` rises 24 px into the centre: frame 0 is already composed | low pad fades in |
| 1.4–4.6 | Headline | "Ask once." then "Dory remembers." (Anuphan 700), word by word (480 ms entrances, 80 ms stagger). Small glass chips rise behind it: a chat bubble, a receipt, a task card (product icons, no 3D, no reef plate) | soft bubble pops on the chips |
| 4.6–9.6 | Ask | Example label "Example · fictional names". A question bubble ("What did we agree with ABC?") lands; Dory's light turns on beside the label "Dory is working" and the label's second half cycles: "searching your chat" → "found it"; her answer bubble: "42,000 THB for the Q4 package" with a source chip "Ploy · #sales" | two-note ping on the light; tick on each label change |
| 9.6–12.8 (+ up to 4 s waiting) | You decide | A task card slides up: "Send the ABC deck · Ploy · due Fri" with Accept / Edit / Decline, built as a fragment of the product's real card. The music dips and the card waits for the person (the live thing above); after 4 s it presses Accept itself (140 ms press) and turns "Accepted" | quiet dip, then a warm chime |
| 12.8–15.0 | Surface | The deep gradient lifts upward like water draining off glass: the layer's background crossfades to the light Surface ground, the chips float to the top and the last one settles exactly on the first example in step 4's list; the layer fades and step 4's heading takes focus | swell that resolves and fades |

Copy: only lines already approved for the film (`motion/dory-launch-film/02-screenplay.md` sign-off list:
"Ask once. Dory remembers.", fictional names Nok and Ploy, the example data) plus UI words ("Skip",
"Sound on/off", "Example · fictional names"). Every new string goes into start.html's dictionary in
English and Thai.

## Full version (owner, 30 Oct: "present all of the content completely"; "use English use cases only")

The table above is the short cut. The owner asked for every capability, so the intro runs the Muse-like
rhythm (example → line) through all of them, about 40 s, at the person's own pace (chapter dots, Next,
Pause, Skip). Chapters 0–1 are the brand frame and the promise above; chapter 8 is the surface.

| # | Chapter | Example (product fragment, `data-ui`) | Line |
| --- | --- | --- | --- |
| 2 | Answers | the ask beat above, with the source chip | She answers with the source. |
| 3 | Tasks | the decision beat above (the live thing) | Say it once, and it becomes a task with an owner. |
| 4 | Receipts | a drawn receipt photo → "Filed" → the month's travel total | Snap a receipt. She files it. |
| 5 | Voice | the call stage: "I'm listening…" → her spoken answer as captions | Or ask out loud. |
| 6 | Travel | one sentence → a flight card and a hotel card with the product's sample labels → "Booked in the sandbox" | Plan a trip in one sentence. |
| 7 | Roles | the same spending question from Nok (owner) and Ploy (member): Nok gets the company total, Ploy gets her own receipts and a plain "company totals are for managers" | She only shares what your role allows. (owner approved 30 Oct) |
| 8 | Surface | everything resolves and drains up into the light theme; the last bubble becomes step 4's first example | — |

**English use cases only (owner, 30 Oct):** every example, headline and chapter line is English in both
page languages, like the film; there is no Thai-language chapter. Only the controls and the region label
follow the page language (the page's dictionary rule: every interface string in Thai and English). The
example content lives in one English data block in the script, not in the dictionary.

Truth notes: every example sits under "Example with fictional names"; the source chip shows what
`chat_search` attaches when it finds the message (an example, not a live claim); voice is English only;
travel shows the product's own "Sample" / "Fictional property" / "Booked in the sandbox" strings
(English); meeting minutes are left out (not live). Builder-check calls (30 Oct): a client-only preview
`/start?intro=1` replays the intro without touching any account (review and tests); every run starts
silent (no remembered sound setting).

## Copy deck (English only, except the controls)

| Key | Text |
| --- | --- |
| example notice | Example with fictional names |
| headline | Ask once. / Dory remembers. |
| rising bubbles | I'll send the deck Friday. · ABC confirmed 42,000 THB for Q4. · Who's going to Singapore next week? |
| ch2 question (Nok) | What price did we agree with ABC? |
| ch2 status | Dory is working · searching your chat → found it |
| ch2 answer | 42,000 THB for the Q4 package. Ploy confirmed it in #sales. |
| ch2 source chip | Ploy · #sales |
| ch2 line | She answers with the source. |
| ch3 card | Send the ABC deck · Ploy · due Fri |
| ch3 buttons / result | Accept · Edit · Decline / Accepted / You decide, every time. |
| ch3 line | Say it once, and it becomes a task with an owner. |
| ch4 result / total | Filed: Taxi · 240 THB · Travel / Travel this month: 3,180 THB |
| ch4 line | Snap a receipt. She files it. |
| ch5 captions (quotation marks are notation, not shown) | Remind me to send the ABC deck on Friday at 4 pm. / Done. I'll remind you on Friday at 4 pm. |
| ch5 line | Or ask out loud. |
| ch6 request | Find a flight for two from Bangkok to Singapore next Tuesday, and a hotel for two nights. |
| ch6 labels | the product's own English `tv_*` strings (Sample itinerary · Sample price; Fictional property; Booked in the sandbox) |
| ch6 line | Plan a trip in one sentence. |
| ch7 exchange | Nok: How much did we spend this month? → 48,200 THB across 31 receipts. / Ploy: same question → Your receipts this month: 3,180 THB. Company totals are for managers. |
| ch7 line | She only shares what your role allows. |

Controls (dictionary, both languages): region label Meet Dory / รู้จักดอรี่ · Skip / ข้าม · Next / ถัดไป ·
Pause / หยุดชั่วคราว · Play / เล่นต่อ · Sound / เสียง (one constant label with `aria-pressed`; ruling 3 of the build ledger).

All numbers and names are fictional sample data inside the labelled example; no claim beyond the film's
sign-off list (chapter 7 approved by the owner on 30 Oct).

## Controls and states

- **Skip** (top right, first in focus order, also Esc) ends the intro at once: the layer is removed and the
  existing `show("step4")` focus rule applies. No click on step 4 is blocked after skip or after the end.
- **Sound** toggle (aria-pressed, off at the start of every run; no remembered setting). Audio
  starts only from that click (browser autoplay rules); turning it off stops every voice at once.
- Plays **once per browser** (localStorage `dory-intro` = `seen`), only when step 4 is reached from step 3
  in this tab (a new organization). Returning members and the "existing" path never see it.
- If storage is blocked: it plays, and nothing breaks.

## Look, motion, sound

- Look: the brand's deep scope (`[data-theme="deep"]` tokens) turning into the Surface theme; Foam / Mist
  type; Glow `#5FF2E0` only as Dory's working light beside its label; no Lantern accent (step 4's button
  keeps the one call to action); round painted mark; product stroke icons.
- House rules (design-taste skill): chips and bubbles are flat fills one tone step above the ground (no
  glass, no blur, no shadows at rest); no eyebrow, pill badge or tiny uppercase label: the example notice
  is a sentence-case line at 16 px or more ("Example with fictional names"); the headline is one face, one
  colour, no styled accent word, two lines at most at 390 px; Anuphan display + IBM Plex Sans Thai only.
  The task card and chat bubbles are product fragments (`data-ui`) and keep the product's own look.
- Declared brand exceptions (passed to the inspector with `--allow`): the deep scope's Abyss → Deep
  gradient and Dory's Glow are the brand's own devices (`theme.css`, CLAUDE.md), not decoration.
- Motion: transforms and opacity only (GPU-friendly), Web Animations API driven by one small timeline
  (skip = finish/cancel all), one camera-like move per beat, no flashes, nothing over 3 Hz. Numbers
  (taste skill's tested recipes, mapped onto the brand's `--ease`): headline lines rise 28 px over 800 ms,
  expo out, 90 ms between lines; chips 600 ms ease-out, 70 ms apart; status label swap 240 ms; press
  140 ms; the surfacing 1,200 ms in-out; anything leaving takes about 70 % of its entrance.
- Sound: synthesized in the browser with the Web Audio API (no files, no licences): a filtered two-sine pad,
  the two-note ping (D6 → A6, the film's motif), short sine "pops", a filtered-noise tick, a three-note
  chime, a final swell. Master level well under speech level; context suspended when the tab is hidden.

## Accessibility and fallbacks

- `prefers-reduced-motion: reduce` or the homepage's saved Pause (`dory-motion`): no movement; the same
  four beats appear as still cards that cross-fade, then the layer closes (or Skip).
- The layer is a labelled region (`role="dialog"`, `aria-modal`, `aria-labelledby`), focus stays inside it
  until it closes; a polite live region reads the beats ("Ask once. Dory remembers.", the example
  question and answer, "Accepted"); contrast from the theme's tested token pairs; works at 320 px wide.
- No Web Audio, no Web Animations API or an error: skip straight to step 4 (never a blank layer).

## Integration

- `src/meeting_scribe/static/start.html`: the layer markup (hidden), its CSS (page-specific, after
  `theme.css`), the timeline and sound code in the page's script; `show("step4")` starts it when the
  conditions above hold. Assets: `static/dory/dory-mark.webp` (exists). No new route, no server change.
- Tests: `tests/test_dory_page.py` (dictionary stays bilingual; still only existing `/api/center` routes; no
  audio files; reduced-motion rules present; sound off by default), a new `tests/e2e/test_start_intro.py`
  (plays after step 3 and lands focused on step 4; Skip and Esc; reduced motion shows stills; plays once;
  sound toggle state; axe WCAG 2.2 AA on the layer at 320 px and desktop), and the existing e2e conftest
  marks the intro seen for tests that are not about it.
- Taste gate: the design-taste skill's `lint.mjs` on the changed source and `inspect.mjs` on `/start` with
  the intro's reduced-motion stills at 1440, 768 and 390 px (`--allow` for the two brand exceptions only),
  then screenshots looked at and critiqued before review.

## Rollout

Branch `feat/dory-intro` from `origin/main`, pull request, owner review. Deploy only with the owner's
approval (web traffic is pinned; a deploy is 0 % until traffic is moved). The hackathon film records
`/center`, so it is not affected.

## Left to the builder

Exact curves within the tokens, icon choice per chip, the pad's voicing, and the final pixel hand-off
between the last chip and the first example.
