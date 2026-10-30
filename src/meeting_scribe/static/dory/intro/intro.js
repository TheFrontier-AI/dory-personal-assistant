/* Dory intro: the first-time story over /start's last step (about 40 s, once per browser, skippable). start.html draws
   step 4, then calls play(): the layer is a modal <dialog>, so the page behind it is inert, and onDone hands the focus
   back when it closes. Chapters run on setTimeout (the tests drive them with a fake clock). This file says WHEN (each
   fragment's beat, as --at) and lands the last chip on step 4's first example; how things look and move is intro.css's
   (CSS animations, which play on the browser's own clock and stop with Pause). */
(() => {
  "use strict";
  // the controls' dictionary keys in start.html (Thai + English); the story itself is English only
  const KEYS = { title: "intro_label", skip: "intro_skip", next: "intro_next", pause: "intro_pause", play: "intro_play", sound: "intro_sound" };
  const SEEN_KEY = "dory-intro";
  const DECISION_WAIT_MS = 4000; // the live decision never blocks: with no answer, Dory accepts
  const LEAVE_MS = 1000; // longer than any chapter's exit fade (intro.css): a fail-safe if its animationend never comes
  const NOTE = ["notice", "Example with fictional names"];
  const SAID = [["said", "I'll send the deck Friday."], ["said", "ABC confirmed 42,000 THB for Q4."], ["said", "Who's going to Singapore next week?"]];
  // The spec's copy deck, English in both page languages. ms: how long a chapter plays on its own (the decision chapter:
  // after the decision); line: its line on screen, rising at lineAt ms; live: the example in words, read by the polite
  // live region before the line; parts: the example's fragments [data-ui, text, enters at ms] (no time: its place in
  // the list times the chip stagger; no text: a drawing, hidden from screen readers); handoff: the chapter ends with the
  // hand-off (the last chip leaves for step 4's first example at ms, and the layer closes when its fade, intro.css, has
  // played); cues: [ms, sound] pairs, the beat each sound lands on (intro-audio.js; only with the sound on).
  const CHAPTERS = [
    { id: "brand", ms: 1400, line: "", live: "", parts: [["mark", ""]] },
    { id: "promise", ms: 3200, line: "Ask once. Dory remembers.", lineAt: 600, live: "", parts: SAID, cues: [[0, "pop"], [70, "pop"], [140, "pop"]] },
    { id: "answers", ms: 5000, line: "She answers with the source.", lineAt: 3100, cues: [[800, "ping"], [2000, "tick"]],
      live: "Example with fictional names. What price did we agree with ABC? 42,000 THB for the Q4 package. Ploy confirmed it in #sales.",
      parts: [NOTE, ["ask", "What price did we agree with ABC?", 200], ["status", "Dory is working · searching your chat", 800], ["found", "found it", 2000],
        ["answer", "42,000 THB for the Q4 package. Ploy confirmed it in #sales.", 2400], ["source", "Ploy · #sales", 2700]] },
    { id: "tasks", ms: 1600, line: "Say it once, and it becomes a task with an owner.", lineAt: 900, live: "Send the ABC deck · Ploy · due Fri.",
      parts: [NOTE, ["task", "Send the ABC deck · Ploy · due Fri", 200]] },
    { id: "receipts", ms: 4400, line: "Snap a receipt. She files it.", lineAt: 2100, live: "Filed: Taxi · 240 THB · Travel. Travel this month: 3,180 THB.",
      parts: [NOTE, ["receipt", "", 200], ["filed", "Filed: Taxi · 240 THB · Travel", 1100], ["total", "Travel this month: 3,180 THB", 1600]] },
    { id: "voice", ms: 4400, line: "Or ask out loud.", lineAt: 2200, cues: [[200, "ping"]],
      live: "Remind me to send the ABC deck on Friday at 4 pm. Done. I'll remind you on Friday at 4 pm.",
      parts: [NOTE, ["call", "I'm listening…", 200], ["ask", "Remind me to send the ABC deck on Friday at 4 pm.", 900], ["answer", "Done. I'll remind you on Friday at 4 pm.", 1600]] },
    { id: "travel", ms: 5000, line: "Plan a trip in one sentence.", lineAt: 2700,
      live: "Find a flight for two from Bangkok to Singapore next Tuesday, and a hotel for two nights. Sample itinerary · Sample price. Fictional property · Sample rating and reviews. Booked in the sandbox.",
      parts: [NOTE, ["ask", "Find a flight for two from Bangkok to Singapore next Tuesday, and a hotel for two nights.", 200],
        ["flight", "Sample itinerary · Sample price", 1100], ["hotel", "Fictional property · Sample rating and reviews", 1170], ["booked", "Booked in the sandbox", 2100]] },
    { id: "roles", ms: 5000, line: "She only shares what your role allows.", lineAt: 2500,
      live: "Nok: How much did we spend this month? 48,200 THB across 31 receipts. Ploy: How much did we spend this month? Your receipts this month: 3,180 THB. Company totals are for managers.",
      parts: [NOTE, ["ask", "Nok: How much did we spend this month?", 200], ["answer", "48,200 THB across 31 receipts.", 800],
        ["ask", "Ploy: How much did we spend this month?", 1300], ["answer", "Your receipts this month: 3,180 THB. Company totals are for managers.", 1900]] },
    { id: "surface", ms: 900, handoff: true, line: "", live: "", parts: SAID, cues: [[0, "swell"]] },
  ];
  const DECIDE = CHAPTERS.findIndex((c) => c.id === "tasks");
  const RESULT = { accept: "Accepted", edit: "You decide, every time.", decline: "You decide, every time." };

  const $ = (id) => document.getElementById(id);
  function el(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
    e.append(...kids);
    return e;
  }
  // storage may be blocked: then nothing is remembered and nothing breaks
  function stored(key, value) {
    try { if (value) localStorage.setItem(key, value); return localStorage.getItem(key); } catch { return null; }
  }
  const animates = () => typeof Element.prototype.animate === "function"; // no Web Animations API: straight to step 4

  let run = null; // the open intro: { t, preview, done, mode, exact (zoomedRects), i, paused, decided, timer, due, left, after, audio (made by the first Sound press) }
  // an error ends the intro, never a stuck layer, and says what went wrong in the console
  const guard = (fn) => (...a) => { try { fn(...a); } catch (e) { console.error(e); finish(); } };
  // Sound is optional, so a sound error never ends the story: it is logged, the audio is closed and its control goes
  // (as when there is no Web Audio), and the intro plays on silently.
  // r is the run whose audio failed: an error that arrives after its run ended leaves the next run alone.
  function noSound(e, r = run) {
    console.error(e);
    if (!r || r !== run) return;
    const { audio } = run, b = $("intro-sound");
    run.audio = null;
    try { audio?.close(); } catch (err) { console.error(err); }
    if (document.activeElement === b) $("intro-next").focus(); // a hidden button would drop the focus
    b.setAttribute("aria-pressed", "false");
    b.hidden = true;
  }
  const sound = (fn) => { try { if (run.audio) fn(run.audio); } catch (e) { noSound(e); } };
  const beat = (at, k = 0) => `--k:${k}` + (at === undefined ? "" : `;--at:${at}ms`); // intro.css starts each fragment on it

  // One example fragment. Dory's light (theme.css .lantern) sits beside the working label and the call; the working
  // label's second half and the fragment after it ("found it") share one cell, so the one gives way to the other.
  function fragment(box, [ui, text, at], k) {
    const style = beat(at, k), light = () => el("span", { class: "lantern pulse", "aria-hidden": "true" });
    if (!text) return box.append(el("div", { "data-ui": ui, "aria-hidden": "true", style }));
    if (ui === "found") {
      const swap = box.querySelector("[data-ui=swap]");
      swap.setAttribute("style", style);
      return swap.append(el("span", { "data-ui": ui }, text));
    }
    const [label, doing] = text.split(" · ");
    const kids = ui === "status" ? [light(), label + " · ", el("span", { "data-ui": "swap" }, el("span", { "data-ui": "doing" }, doing))]
      : ui === "call" ? [light(), text] : [text];
    box.append(el("p", { "data-ui": ui, style }, ...kids));
  }

  function build() {
    const button = (id, key, attrs) => el("button", { type: "button", class: "btn ghost", id, "data-key": key, ...attrs });
    const choice = (kind, text) => el("button", { type: "button", class: "btn ghost", id: "intro-" + kind, "data-decide": kind }, text);
    // a chapter: its fragments, the decision's answers in the task card's lower half, then its line, one span per
    // sentence so the sentences rise one after the other
    const scene = (c) => {
      const box = el("div", { "data-id": c.id, hidden: "" });
      c.parts.forEach((p, k) => fragment(box, p, k));
      if (c.id === "tasks") box.append(el("div", { "data-ui": "choices", style: beat(c.parts.at(-1)[2]) }, choice("accept", "Accept"),
        choice("edit", "Edit"), choice("decline", "Decline")), el("p", { "data-ui": "result", id: "intro-result" }));
      if (c.line) box.append(el("p", { "data-ui": "line", style: beat(c.lineAt) },
        ...c.line.split(/(?<=\.) /).flatMap((s, k) => (k ? [" ", el("span", {}, s)] : [el("span", {}, s)]))));
      return box;
    };
    // the story is English on a Thai page too: screen readers voice it as English (a Tab stop only while it scrolls: fit)
    const stage = el("div", { id: "intro-stage", lang: "en", role: "region", "aria-labelledby": "intro-title" }, ...CHAPTERS.map(scene));
    const layer = el("dialog", { id: "intro", role: "dialog", "aria-modal": "true", "aria-labelledby": "intro-title", "data-theme": "deep",
      "data-mode": run.mode, "data-chapter": "0" },
      el("h2", { id: "intro-title", class: "sr", "data-key": KEYS.title }),
      el("div", { class: "intro-bar" }, button("intro-skip", KEYS.skip)),
      stage,
      el("p", { id: "intro-live", class: "sr", "aria-live": "polite", lang: "en" }),
      // the chapter dots are a numbered list, so "current step" reaches screen readers in either page language (role=list:
      // Safari drops a list's role when its bullets are off; named after the story, no new words)
      el("div", { class: "intro-bar" }, el("ol", { id: "intro-dots", role: "list", "aria-labelledby": "intro-title" }, ...CHAPTERS.map((_, k) => el("li", {}, el("span", { class: "sr" }, String(k + 1))))),
        // every run starts silent; with no Web Audio there is nothing to switch on, and the story plays without sound
        button("intro-sound", KEYS.sound, { "aria-pressed": "false", ...(window.DoryIntroAudio?.supported ? {} : { hidden: "" }) }),
        button("intro-pause", KEYS.pause), button("intro-next", KEYS.next)));
    // a chapter that leaves stays on screen until its fade ends (intro.css), then hides
    stage.addEventListener("animationend", guard((e) => leave(e.target)));
    const actions = { "intro-skip": finish, "intro-next": () => go(run.i + 1), "intro-pause": togglePause, "intro-sound": toggleSound };
    layer.addEventListener("click", guard((e) => {
      const b = e.target.closest("button");
      if (b && actions[b.id]) actions[b.id](b);
      else if (b && b.dataset.decide) decide(b.dataset.decide);
    }));
    layer.addEventListener("keydown", guard(wrapTab));
    // Esc closes a modal dialog; the close event is queued, so the one finish() itself causes can arrive after the next
    // run began: only this run ends on it
    const mine = run;
    layer.addEventListener("close", guard(() => { if (run === mine) finish(); }));
    return layer;
  }

  const leave = (s) => { if (s.hasAttribute("data-leaving")) { s.hidden = true; s.removeAttribute("data-leaving"); } };

  // The stage is a Tab stop only while its chapter is taller than it, so the keyboard can scroll it (axe:
  // scrollable-region-focusable); it never keeps the focus once it fits.
  function fit() {
    const stage = $("intro-stage"), chapter = stage.children[run.i], z = run.exact ? 1 : +getComputedStyle(chapter).zoom || 1;
    if (chapter.getBoundingClientRect().height * z > stage.clientHeight) return stage.setAttribute("tabindex", "0");
    if (document.activeElement === stage) $("intro-next").focus();
    stage.removeAttribute("tabindex");
  }
  const refit = guard(() => run && fit());

  // Rects inside a zoomed box (intro.css zooms the chapters on large screens): Chromium and Firefox give them after the
  // zoom, in viewport pixels; older WebKit gives them before it (WebKit bugs 77998, 185034). There the hand-off only
  // fades and fit() applies the zoom itself.
  function zoomedRects() {
    if (!CSS.supports("zoom", "2")) return true; // no zoom anywhere, so nothing to correct
    const box = el("div", { style: "zoom:2;position:absolute;visibility:hidden" }, el("div", { style: "width:100px" }));
    document.body.append(box);
    const w = box.firstChild.getBoundingClientRect().width;
    box.remove();
    return w > 150;
  }

  function label() {
    for (const e of $("intro").querySelectorAll("[data-key]")) e.textContent = run.t(e.dataset.key);
  }

  // The page behind is inert, but Tab still leaves for the browser after the last control: wrap it around.
  function wrapTab(e) {
    if (e.key !== "Tab") return;
    const shown = [...$("intro").querySelectorAll("button")].filter((b) => b.offsetParent);
    if (document.activeElement !== (e.shiftKey ? shown[0] : shown[shown.length - 1])) return;
    e.preventDefault();
    (e.shiftKey ? shown[shown.length - 1] : shown[0]).focus();
  }

  // One beat timer at a time (stills keep the same timeline, they only do not move); a pause keeps what is left of it.
  function wait(ms, fn) {
    clearTimeout(run.timer);
    Object.assign(run, { after: fn, left: ms });
    if (!run.paused) { run.due = Date.now() + ms; run.timer = setTimeout(guard(fn), ms); }
  }

  function go(n) {
    if (n >= CHAPTERS.length) return finish();
    const c = CHAPTERS[n], stage = $("intro-stage"), was = stage.children[run.i], focused = document.activeElement;
    if (focused !== stage && stage.contains(focused)) $("intro-next").focus(); // a hidden button would drop the focus
    // the chapter that was on screen fades out over the new one, then hides; only the new one is live
    [...stage.children].forEach((s, k) => {
      const leaving = s === was && k !== n;
      s.hidden = k !== n && !leaving;
      s.inert = k !== n;
      s.toggleAttribute("data-leaving", leaving);
    });
    if (was !== stage.children[n]) setTimeout(guard(() => leave(was)), LEAVE_MS);
    stage.scrollTop = 0; // every chapter starts at its top
    [...$("intro-dots").children].forEach((d, k) => (k === n ? d.setAttribute("aria-current", "step") : d.removeAttribute("aria-current")));
    run.i = n;
    $("intro").dataset.chapter = n;
    fit();
    $("intro-live").textContent = [c.live, c.line].filter(Boolean).join(" ");
    sound((a) => { // a chapter's sounds are scheduled when it starts; the last chapter's unplayed ones go
      a.clear();
      a.cue(n === DECIDE ? "dip" : "lift");
      for (const [ms, name] of c.cues || []) a.cue(name, ms / 1000);
    });
    if (n === DECIDE) wait(DECISION_WAIT_MS, () => decide("accept"));
    else if (c.handoff) wait(c.ms, () => wait(handoff($("tries")?.querySelector("a")), () => go(n + 1)));
    else wait(c.ms, () => go(n + 1));
  }

  // The surfacing's last beat: the last thing said lands on step 4's first example, its words on the example's first
  // line (lifted out of the scrolling stage onto the layer, so nothing clips it); then the layer fades (intro.css) and
  // the real example is underneath. In stills, with no example on screen (the preview, a short landscape phone), or
  // where rects ignore the zoom (zoomedRects), the layer only fades. Returns how long that fade plays: the layer closes
  // when it ends.
  function handoff(target) {
    const layer = $("intro"), chip = [...layer.querySelectorAll("[data-id=surface] [data-ui=said]")].pop();
    const words = (e) => { const r = document.createRange(); r.selectNodeContents(e); return r.getClientRects()[0]; };
    chip.getAnimations().forEach((a) => a.finish()); // measured where it rests, not partway in
    const box = target && target.getBoundingClientRect(), from = words(chip), to = target && words(target);
    const lands = run.exact && run.mode === "motion" && !!(from && to) && box.top >= 0 && box.left >= 0 && box.bottom <= innerHeight && box.right <= innerWidth;
    if (lands) {
      // the stage's zoom on a large screen (intro.css) goes with the chip, so its lengths are given unzoomed
      const at = chip.getBoundingClientRect(), fly = chip.cloneNode(true), z = +getComputedStyle(chip.parentElement).zoom || 1;
      fly.setAttribute("aria-hidden", "true");
      fly.setAttribute("style", `zoom:${z};left:${at.left / z}px;top:${at.top / z}px;width:${at.width / z}px;--dx:${(to.left - from.left) / z}px;`
        + `--dy:${(to.top + to.height / 2 - from.top - from.height / 2) / z}px`);
      fly.toggleAttribute("data-fly", true);
      layer.append(fly);
      chip.style.visibility = "hidden";
    }
    layer.dataset.handoff = lands ? "land" : "fade";
    const fade = layer.getAnimations().find((a) => a.animationName === "intro-gone" && !a.effect.pseudoElement);
    return fade ? fade.effect.getComputedTiming().endTime : 0;
  }

  function decide(kind) {
    if (run.decided || run.i !== DECIDE) return;
    run.decided = true;
    if (kind === "accept") sound((a) => a.cue("chime"));
    $("intro").dataset.decision = kind; // intro.css presses the chosen button (140 ms) as the result shows, never before it
    for (const b of $("intro").querySelectorAll("[data-decide]")) b.setAttribute("aria-disabled", "true");
    $("intro-result").textContent = $("intro-live").textContent = RESULT[kind];
    wait(CHAPTERS[DECIDE].ms, () => go(DECIDE + 1));
  }

  function togglePause() {
    run.paused = !run.paused;
    $("intro-pause").dataset.key = run.paused ? KEYS.play : KEYS.pause;
    label();
    if (run.paused) { clearTimeout(run.timer); run.left = Math.max(0, run.due - Date.now()); }
    else wait(run.left, run.after);
    sound((a) => a[run.paused ? "suspend" : "resume"]()); // the sound holds too
    // what moves holds too (only what is running: play() would rewind a finished one), except a chapter on its way out;
    // anything that starts while paused still plays, so Next brings its chapter in whole
    for (const a of $("intro").getAnimations({ subtree: true })) {
      if (run.paused && a.playState === "running" && !a.effect.target.hasAttribute("data-leaving")) a.pause();
      else if (!run.paused && a.playState === "paused") a.play();
    }
  }

  // The first press makes the audio (inside the click, as browsers require); the context stays for the rest of the run.
  function toggleSound(b) {
    const on = b.getAttribute("aria-pressed") !== "true", r = run, failed = (e) => noSound(e, r);
    b.setAttribute("aria-pressed", String(on));
    try {
      if (!run.audio) { // a pause that began before the first press holds this sound too
        run.audio = window.DoryIntroAudio.create(failed);
        if (run.paused) run.audio.suspend();
      }
      run.audio.setOn(on).catch(failed);
      if (on && run.i === DECIDE && !run.decided) run.audio.cue("dip"); // turned on while the card waits: the music starts low
    } catch (e) { noSound(e); }
  }

  function finish() {
    if (!run) return;
    const { done, preview, timer, audio } = run;
    run = null;
    clearTimeout(timer);
    removeEventListener("resize", refit);
    try { audio?.close(); } catch (e) { console.error(e); /* the layer still goes */ }
    if (!preview) stored(SEEN_KEY, "seen");
    const layer = $("intro");
    if (layer) { if (layer.open) layer.close(); layer.remove(); }
    done();
  }

  window.DoryIntro = {
    shouldPlay(opts) { // never throws: the travel step's submit handler would show its offline note
      try { return !run && animates() && (!!opts?.preview || stored(SEEN_KEY) !== "seen"); } catch { return false; }
    },
    play(opts) { // never rejects: whatever happens, the layer goes and onDone runs
      return new Promise((resolve) => {
        const { t, preview = false, onDone } = opts || {};
        const done = () => { try { if (onDone) onDone(); } catch { /* the page keeps its own focus */ } resolve(); };
        if (run) return done(); // one intro at a time
        run = { t, preview: !!preview, done, i: 0, paused: false, decided: false };
        try {
          // either one means stills: the OS setting wins over a "dory-motion" of "on" saved on the homepage
          run.mode = matchMedia("(prefers-reduced-motion: reduce)").matches || stored("dory-motion") === "off" ? "stills" : "motion";
          run.exact = zoomedRects();
          document.body.append(build());
          label();
          $("intro").showModal();
          addEventListener("resize", refit);
          $("intro-skip").focus();
          go(0);
        } catch (e) { console.error(e); finish(); }
      });
    },
    relabel() { // start.html calls it after a language switch: only the controls follow the language
      try { if (run) label(); } catch (e) { console.error(e); /* the controls keep their labels */ }
    },
  };
})();
