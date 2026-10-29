/* Dory intro: a first-time story over /start's last step. This is the wiring only: start.html already calls this API
   (at the two exits of the travel step and for /start?intro=1), and it never plays yet, so step 4 shows at once. */
(() => {
  "use strict";
  // the controls' dictionary keys in start.html (Thai + English); the story itself is English only
  const KEYS = ["intro_label", "intro_skip", "intro_next", "intro_pause", "intro_play", "intro_sound"];
  window.DoryIntro = {
    shouldPlay: () => false,
    play: async ({ onDone }) => { onDone(); },
    relabel: () => {}, // start.html calls it after a language switch
  };
})();
