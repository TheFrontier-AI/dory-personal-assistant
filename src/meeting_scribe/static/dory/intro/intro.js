/* Dory intro: the first-time story over /start's last step (about 40 s, once per browser, skippable). start.html draws
   step 4, then calls play(): the layer is a modal <dialog>, so the page behind it is inert, and onDone hands the focus
   back when it closes. Beats run on setTimeout (the tests drive them with a fake clock); the look is intro.css's. */
(() => {
  "use strict";
  // the controls' dictionary keys in start.html (Thai + English); the story itself is English only
  const KEYS = { title: "intro_label", skip: "intro_skip", next: "intro_next", pause: "intro_pause", play: "intro_play", sound: "intro_sound" };
  const SEEN_KEY = "dory-intro";
  const DECISION_WAIT_MS = 4000; // the live decision never blocks: with no answer, Dory accepts
  const NOTE = ["notice", "Example with fictional names"];
  const SAID = [["said", "I'll send the deck Friday."], ["said", "ABC confirmed 42,000 THB for Q4."], ["said", "Who's going to Singapore next week?"]];
  // The spec's copy deck, English in both page languages. ms: how long a chapter plays on its own (the decision chapter:
  // after the decision); line: its line on screen; live: the example in words, read by the polite live region before
  // the line; parts: the example's fragments [data-ui, text] (no text: a drawing, hidden from screen readers).
  const CHAPTERS = [
    { id: "brand", ms: 1400, line: "", live: "", parts: [["mark", ""]] },
    { id: "promise", ms: 3200, line: "Ask once. Dory remembers.", live: "", parts: SAID },
    { id: "answers", ms: 5000, line: "She answers with the source.",
      live: "Example with fictional names. What price did we agree with ABC? 42,000 THB for the Q4 package. Ploy confirmed it in #sales.",
      parts: [NOTE, ["ask", "What price did we agree with ABC?"], ["status", "Dory is working · searching your chat"], ["found", "found it"],
        ["answer", "42,000 THB for the Q4 package. Ploy confirmed it in #sales."], ["source", "Ploy · #sales"]] },
    { id: "tasks", ms: 1600, line: "Say it once, and it becomes a task with an owner.", live: "Send the ABC deck · Ploy · due Fri.",
      parts: [NOTE, ["task", "Send the ABC deck · Ploy · due Fri"]] },
    { id: "receipts", ms: 4400, line: "Snap a receipt. She files it.", live: "Filed: Taxi · 240 THB · Travel. Travel this month: 3,180 THB.",
      parts: [NOTE, ["receipt", ""], ["filed", "Filed: Taxi · 240 THB · Travel"], ["total", "Travel this month: 3,180 THB"]] },
    { id: "voice", ms: 4400, line: "Or ask out loud.",
      live: "Remind me to send the ABC deck on Friday at 4 pm. Done. I'll remind you on Friday at 4 pm.",
      parts: [NOTE, ["call", "I'm listening…"], ["ask", "Remind me to send the ABC deck on Friday at 4 pm."], ["answer", "Done. I'll remind you on Friday at 4 pm."]] },
    { id: "travel", ms: 5000, line: "Plan a trip in one sentence.",
      live: "Find a flight for two from Bangkok to Singapore next Tuesday, and a hotel for two nights. Sample itinerary · Sample price. Fictional property. Booked in the sandbox.",
      parts: [NOTE, ["ask", "Find a flight for two from Bangkok to Singapore next Tuesday, and a hotel for two nights."],
        ["flight", "Sample itinerary · Sample price"], ["hotel", "Fictional property"], ["booked", "Booked in the sandbox"]] },
    { id: "roles", ms: 5000, line: "She only shares what your role allows.",
      live: "Nok: How much did we spend this month? 48,200 THB across 31 receipts. Ploy: How much did we spend this month? Your receipts this month: 3,180 THB. Company totals are for managers.",
      parts: [NOTE, ["ask", "Nok: How much did we spend this month?"], ["answer", "48,200 THB across 31 receipts."],
        ["ask", "Ploy: How much did we spend this month?"], ["answer", "Your receipts this month: 3,180 THB. Company totals are for managers."]] },
    { id: "surface", ms: 2200, line: "", live: "", parts: SAID },
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

  let run = null; // the open intro: { t, preview, done, mode, i, paused, decided, timer, due, left, after }
  const guard = (fn) => (...a) => { try { fn(...a); } catch { finish(); } }; // an error ends the intro, never a stuck layer

  function build() {
    const button = (id, key, attrs) => el("button", { type: "button", class: "btn ghost", id, "data-key": key, ...attrs });
    const choice = (kind, text) => el("button", { type: "button", class: "btn ghost", id: "intro-" + kind, "data-decide": kind }, text);
    const scene = (c) => el("div", { "data-id": c.id, hidden: "" },
      ...c.parts.map(([ui, text]) => (text ? el("p", { "data-ui": ui }, text) : el("div", { "data-ui": ui, "aria-hidden": "true" }))),
      ...(c.id === "tasks" ? [el("div", { "data-ui": "choices" }, choice("accept", "Accept"), choice("edit", "Edit"), choice("decline", "Decline")),
        el("p", { "data-ui": "result", id: "intro-result" })] : []),
      ...(c.line ? [el("p", { "data-ui": "line" }, c.line)] : []));
    const layer = el("dialog", { id: "intro", role: "dialog", "aria-modal": "true", "aria-labelledby": "intro-title", "data-theme": "deep",
      "data-mode": run.mode, "data-chapter": "0" },
      el("h2", { id: "intro-title", class: "sr", "data-key": KEYS.title }),
      el("div", { class: "intro-bar" }, button("intro-skip", KEYS.skip)),
      // the story is English on a Thai page too: screen readers voice it as English
      el("div", { id: "intro-stage", lang: "en" }, ...CHAPTERS.map(scene)),
      el("p", { id: "intro-live", class: "sr", "aria-live": "polite", lang: "en" }),
      el("div", { class: "intro-bar" }, el("ol", { id: "intro-dots", "aria-hidden": "true" }, ...CHAPTERS.map(() => el("li"))),
        button("intro-sound", KEYS.sound, { "aria-pressed": "false" }), // every run starts silent
        button("intro-pause", KEYS.pause), button("intro-next", KEYS.next)));
    const actions = { "intro-skip": finish, "intro-next": () => go(run.i + 1), "intro-pause": togglePause, "intro-sound": toggleSound };
    layer.addEventListener("click", guard((e) => {
      const b = e.target.closest("button");
      if (b && actions[b.id]) actions[b.id](b);
      else if (b && b.dataset.decide) decide(b.dataset.decide);
    }));
    layer.addEventListener("keydown", guard(wrapTab));
    layer.addEventListener("close", guard(finish)); // Esc closes a modal dialog
    return layer;
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
    const c = CHAPTERS[n], stage = $("intro-stage");
    if (stage.contains(document.activeElement)) $("intro-next").focus(); // a hidden button would drop the focus
    [...stage.children].forEach((s, k) => { s.hidden = k !== n; });
    [...$("intro-dots").children].forEach((d, k) => (k === n ? d.setAttribute("aria-current", "step") : d.removeAttribute("aria-current")));
    run.i = n;
    $("intro").dataset.chapter = n;
    $("intro-live").textContent = [c.live, c.line].filter(Boolean).join(" ");
    if (n === DECIDE) wait(DECISION_WAIT_MS, () => decide("accept"));
    else wait(c.ms, () => go(n + 1));
  }

  function decide(kind) {
    if (run.decided || run.i !== DECIDE) return;
    run.decided = true;
    $("intro").dataset.decision = kind;
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
  }

  function toggleSound(b) {
    b.setAttribute("aria-pressed", String(b.getAttribute("aria-pressed") !== "true"));
  }

  function finish() {
    if (!run) return;
    const { done, preview, timer } = run;
    run = null;
    clearTimeout(timer);
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
          document.body.append(build());
          label();
          $("intro").showModal();
          $("intro-skip").focus();
          go(0);
        } catch { finish(); }
      });
    },
    relabel() { // start.html calls it after a language switch: only the controls follow the language
      try { if (run) label(); } catch { /* the controls keep their labels */ }
    },
  };
})();
