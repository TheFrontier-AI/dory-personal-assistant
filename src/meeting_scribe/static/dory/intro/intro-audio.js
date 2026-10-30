/* Dory intro sound: a small Web Audio synth, no audio files. intro.js calls create() inside the Sound button's first click
   (a browser only lets audio start from a gesture), then asks for cues at the story's beats. Cues are scheduled on the
   audio clock, so a suspended context (Pause, a hidden tab) holds them too. Everything is soft: gains ramp, nothing
   starts or stops with a click, and the master level is -18 dB. */
(() => {
  "use strict";
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  const hz = (midi) => 440 * 2 ** ((midi - 69) / 12);
  const db = (x) => 10 ** (x / 20);
  const [D3, A3, D4, A4, D5, E5, FS5, A5, D6, A6] = [50, 57, 62, 69, 74, 76, 78, 81, 86, 93].map(hz);
  const MASTER = db(-18), PAD = 0.12, DIP = PAD * db(-9);

  function create() {
    let ctx = null, master = null, bus = null, padGain = null, noise = null;
    let on = false, paused = false, hidden = !!document.hidden, pops = 0;
    const voices = new Map(); // every sound source alive -> when it starts (audio clock)

    // the context runs unless the person paused the story or the tab is hidden
    const hold = () => { if (ctx) Promise.resolve(paused || hidden ? ctx.suspend() : ctx.resume()).catch(console.error); };
    const onVisible = () => { hidden = !!document.hidden; hold(); };

    function voice(src, at, end) {
      src.start(at);
      if (end) src.stop(end);
      voices.set(src, at);
      src.onended = () => voices.delete(src);
    }
    // a gain that rises over `attack` s to `peak` and dies away exponentially by `tail` s
    function envelope(at, peak, attack, tail) {
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, at);
      g.gain.linearRampToValueAtTime(peak, at + attack);
      g.gain.exponentialRampToValueAtTime(0.0001, at + tail);
      return g;
    }
    // a bell note: a sine with a quiet octave above it
    function bell(freq, at, peak, tail) {
      const g = envelope(at, peak, 0.015, tail);
      g.connect(bus);
      for (const [f, amp] of [[freq, 1], [freq * 2, 0.18]]) {
        const o = ctx.createOscillator(), p = ctx.createGain();
        o.frequency.value = f;
        p.gain.value = amp;
        o.connect(p).connect(g);
        voice(o, at, at + tail + 0.05);
      }
    }
    const padTo = (level, at, tc) => padGain.gain.setTargetAtTime(level, at, tc);

    // the low pad: D3 and A3 (the second a few cents sharp, so the pair breathes), filtered, fading in over about 1.5 s
    function startPad() {
      const lp = ctx.createBiquadFilter(), at = ctx.currentTime;
      lp.type = "lowpass";
      lp.frequency.value = 700;
      padGain = ctx.createGain();
      padGain.gain.value = 0;
      lp.connect(padGain).connect(bus);
      padTo(PAD, at, 0.5);
      for (const [f, cents] of [[D3, 0], [A3, 5]]) {
        const o = ctx.createOscillator();
        o.frequency.value = f;
        o.detune.value = cents;
        o.connect(lp);
        voice(o, at);
      }
    }

    // every voice goes at once: the bus fades over about 30 ms, then the sources stop
    function silence() {
      const t = ctx.currentTime;
      bus.gain.setTargetAtTime(0, t, 0.01);
      for (const src of voices.keys()) src.stop(t + 0.08);
      voices.clear();
    }

    const CUES = {
      // Dory's light turns on: D6 then A6
      ping(at) { bell(D6, at, 0.55, 1.1); bell(A6, at + 0.14, 0.55, 1.4); },
      // a soft bubble: a sine that rises a little as it opens
      pop(at) {
        const o = ctx.createOscillator(), g = envelope(at, 0.5, 0.006, 0.12), f = 480 + 70 * (pops++ % 3);
        o.frequency.value = f;
        o.frequency.exponentialRampToValueAtTime(f * 1.8, at + 0.06);
        o.connect(g).connect(bus);
        voice(o, at, at + 0.15);
      },
      // a status label swaps: a short band of noise
      tick(at) {
        if (!noise) {
          noise = ctx.createBuffer(1, ctx.sampleRate / 10, ctx.sampleRate);
          noise.getChannelData(0).forEach((_, k, a) => { a[k] = Math.random() * 2 - 1; });
        }
        const s = ctx.createBufferSource(), bp = ctx.createBiquadFilter();
        s.buffer = noise;
        bp.type = "bandpass";
        bp.frequency.value = 3200;
        bp.Q.value = 1.4;
        s.connect(bp).connect(envelope(at, 1, 0.003, 0.05)).connect(bus);
        voice(s, at, at + 0.08);
      },
      // the card waits for the person: the music drops nine decibels over about 400 ms
      dip(at) { padTo(DIP, at, 0.13); },
      lift(at) { padTo(PAD, at, 0.3); },
      // Accept: D5, F#5, A5, and the music comes back
      chime(at) {
        [D5, FS5, A5].forEach((f, k) => bell(f, at + 0.11 * k, 0.4, k === 2 ? 1.8 : 1.3));
        padTo(PAD, at, 0.3);
      },
      // the surface: a suspended chord (E5 over D and A) swells as a filter opens, resolves up to F#5, and fades
      swell(at) {
        const g = ctx.createGain(), lp = ctx.createBiquadFilter();
        g.gain.setValueAtTime(0.0001, at);
        g.gain.exponentialRampToValueAtTime(1, at + 1);
        g.gain.linearRampToValueAtTime(0, at + 2.05);
        lp.frequency.setValueAtTime(400, at);
        lp.frequency.exponentialRampToValueAtTime(2800, at + 1);
        lp.frequency.exponentialRampToValueAtTime(900, at + 2.05);
        lp.connect(g).connect(bus);
        for (const f of [D4, A4, D5, E5]) {
          const o = ctx.createOscillator(), p = ctx.createGain();
          o.frequency.value = f;
          p.gain.value = 0.18;
          if (f === E5) { o.frequency.setValueAtTime(E5, at + 0.8); o.frequency.exponentialRampToValueAtTime(FS5, at + 1.05); }
          o.connect(p).connect(lp);
          voice(o, at, at + 2.1);
        }
        padTo(0, at + 1.2, 0.3);
      },
    };

    return {
      // on creates the context (so call it from the click), starts the pad; off stops everything
      async setOn(next) {
        if (next === on) return;
        if (!next) { on = false; return silence(); }
        if (!ctx) {
          ctx = new AudioCtx();
          master = ctx.createGain();
          master.gain.value = MASTER;
          master.connect(ctx.destination);
          document.addEventListener("visibilitychange", onVisible);
        }
        bus = ctx.createGain();
        bus.connect(master);
        on = true;
        startPad();
        await (paused || hidden ? ctx.suspend() : ctx.resume());
      },
      // name: ping pop tick dip lift chime swell; delay: seconds from now, on the audio clock
      cue(name, delay = 0) {
        if (on) CUES[name](ctx.currentTime + 0.03 + delay);
      },
      // drops the cues that have not started yet (Next left their chapter); what already sounds rings out
      clear() {
        if (!ctx) return;
        const now = ctx.currentTime;
        for (const [src, at] of voices) if (at > now) { src.stop(now); voices.delete(src); }
      },
      suspend() { paused = true; hold(); },
      resume() { paused = false; hold(); },
      close() {
        document.removeEventListener("visibilitychange", onVisible);
        if (!ctx) return;
        if (on) silence();
        on = false;
        const gone = ctx;
        ctx = null;
        setTimeout(() => gone.close().catch(console.error), 150); // after the fade
      },
    };
  }

  window.DoryIntroAudio = { supported: !!AudioCtx, create };
})();
