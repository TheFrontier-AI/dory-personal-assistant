# Voice behaviour (one design)

Source of truth for how Dory behaves in a voice room. Code, labels, prompts and tests follow this
file; change it first. Live mode = Gemini Live (hears the room). Classic mode = wake word, transcription,
text answer, TTS (fallback when Live cannot connect; its keyword rules stay and are marked CLASSIC).

## The rules

| # | Rule | Decided by | Where |
|---|------|-----------|-------|
| 1 | Two human switches only: `voice_talk` may_talk / listen_only (chair or executive, remembered per room, never an agent tool); `hush` ("Dory, be quiet", anyone, silent until her name comes with words, no timer) | people | `MeetingManager.set_voice_talk`, `_hush` / `_clear_hush` |
| 2a | WAKE: only when someone says her name (any language). Code keeps the mouth gate (model audio while listening is held up to `live_call_grace_seconds` for a name in the Live transcript or an ASR `name_called`, else dropped) and a backup cue when ASR hears the bare name twice in 15 s | Live model + code gate | `LiveVoice._gate_audio`, `_on_heard`, `MeetingManager._bare_name_backup` |
| 2b | STAY: the exchange belongs to the caller. What the caller says is for her unless clearly to someone else; she answers without the name; when the caller talks to others she waits quietly and answers when they speak to her again. Others count only when they address her. No keyword rules in live mode (`is_dismissal`, `_ASK_RE`, `_SELF_TALK_RE`, 3-strike, "next word after a bare name") | Live model | instruction + `STATE_ENGAGED*` |
| 2c | END: (a) the caller closes it in words (thanks / that's all / bye / talk later): the model calls `end_conversation`, code accepts reasons thanks / closed / hushed only and only when the caller has been quiet >= 2 s; (b) hush; (c) `engaged_timeout_seconds` with nobody talking to her and her not talking. The window is renewed by her own audio and by any utterance of the caller (`MeetingManager.renew_engaged`); someone else renews it only by saying her name | model + one timer | `end_conversation`, `_consent_tick`, `renew_engaged` |
| 2d | A bare name ("Dory?") is answered "Yes?" and she waits `engaged_bare_timeout_seconds` | code | `_set_engaged(bare=True)` |
| 3 | Turn-taking: she may start after `live_silence_ms` of silence; never starts while a person spoke < 0.5 s ago (hold until 0.5 s quiet, drop the answer after 6 s); in the first 2.5 s of her answer the caller's voice stops her after 0.3 s; later the caller stops her after 0.8 s of clear speech. Side talk, notifications, whispers never stop her. Explicit "stop" words / her name while she speaks also stop her | code | `build_realtime_input`, `_on_audio`, `_yield_until_quiet`, `_check_talkover`, `_on_heard` |
| 4 | Nothing about settings is spoken (mode, language, connection lines are text only). Every spoken answer is also posted ("💬 **Dory:** ..."). Status lines show the reason: called by name / said thanks / closed it / told to be quiet / quiet N min (N built from `engaged_timeout_seconds`) | code | `_post_state`, `_echo_answer`, i18n `voice_why_*` |
| 5 | Language: answers in the company language (+ the personal languages of the people in the room). The Live instruction, the spoken hint to the text agent and a translate-if-wrong-script safety net all use the session's resolved language (`MeetingSession.lang`, never "auto"; the server default is English until chosen, there are no per-channel overrides) | code | `build_instruction`, `_ask_dory`, `_qa_setting` |
| 6 | listen_only: ASR notes + captions + text answers to "name + request"; no engaged state, no state lines, no Live session | code | `_listen_only` |
| 7 | Leaving: never while people are in the room. "the meeting is over" / leave command leaves. Empty room: scheduled end, or `meeting_empty_minutes`. No "nothing to summarize" line | code | `_ticker`, `_leave_politely` |
| 8 | A spoken question posts "⏳ Looking into it: q · 🔎 ..." at once, edited per tool, then "✅ Done". Results up to 700 chars (`ANSWER_MAX_CHARS` = `SHORT_ANSWER_CHARS`) are spoken in full | code | `LiveVoice._one_brain`, `_status`, `_announce` |

## Timers and thresholds

| What | Config name (default) or constant |
|------|-----------------------------------|
| Quiet window after the last talk with her (renewed by her answer or the caller) | `engaged_timeout_seconds` (300) |
| Wait after a bare name | `engaged_bare_timeout_seconds` (300) |
| Hush | no timer |
| `end_conversation` needs the caller quiet for | 2 s (`MeetingManager.end_conversation`) |
| She may start after silence | `live_silence_ms` (1000) |
| Yield: a person spoke less than / hold until quiet / drop after | `YIELD_ACTIVE_S` 0.5 / `YIELD_QUIET_S` 0.5 / `YIELD_MAX_S` 6 |
| Early cut (first seconds of her answer) / speech needed | `EARLY_CUT_S` 2.5 / `EARLY_CUT_SPEECH_S` 0.3 |
| Barge-in by the caller / loud frame level / allowed gap | `TALKOVER_S` 0.8 / `TALKOVER_RMS` 500 / `TALKOVER_GAP_S` 0.35 (`live_barge_in` intentional) |
| Mouth gate: hold for a name | `live_call_grace_seconds` (4) |
| Gate stays open after an exchange ended without `forget_grace` | `live_reengage_grace_seconds` (60) |
| Name in Live transcript but no answer: force a turn after | `live_name_reply_seconds` (1.0); name from ASR: `live_force_reply_seconds` (2.0) |
| Cue retry / then classic fallback | `live_cue_retry_seconds` (4) / `live_fallback_seconds` (4) |
| ASR bare name twice within | `NAME_TWICE_S` 15 |
| Name from the same call seen by both detectors is one call | `NAME_DEDUPE_S` 10 |
| Name hit needs real speech | `name_min_voiced_seconds` 0.35, `name_bare_min_voiced_seconds` 0.45, `name_min_cv`, `name_min_rms` |
| ask_dory answers in the conversation within / hard limit | `live_foreground_seconds` (25) / `live_ask_timeout_seconds` (150) |
| Background result: pause needed / max wait / jobs at once | `live_result_pause_seconds` 1.5 / `live_result_wait_seconds` 90 / `live_max_jobs` 3 |
| One state line flips (edits the previous line) within | `STATE_FLIP_S` 15 |
| Empty room | `meeting_empty_minutes` (10) (`Settings.leave_empty_seconds`) |
| Meeting hard cap when empty | `MEETING_MAX_S` 6 h |
| GPU box: idle stop (cloud controller in the bot, polls `/health` of the voice server) | `nebius_vm.IDLE_STOP_S` 1800: no audio, no say, no TTS for that long (an open but silent call counts as idle) |
| GPU box: running but no voice server answering for | `nebius_vm.BOOT_GRACE_S` 5400 (then it is stopped, reason logged) |

Defaults in `getattr(settings, name, default)` inside the code equal the `Settings` defaults (one
source of truth: `config.py`).

## GPU box lifecycle (29 Oct 2026)

The GPU VM stops when idle and starts only on an EXPLICIT request. Nothing else wakes it.

| # | Rule | Where |
| --- | --- | --- |
| G1 | WAKE only by an explicit request: a web call, a person asking Dory to join a room, a typed "@Dory wake up" / "ดอรี่ ตื่น" (`parse_voice_wake_command`, with or without a meeting), or typed text on the web call. Room occupancy, reconnects, retries, a session resumed after a bot restart and loud sounds NEVER wake it | `GlmVoice.run` / `request_wake`, `bot._wake_voice_command` |
| G2 | A wake is used up by one attempt: after it (success or failure) the next wake needs a new explicit request. No retry loop starts the box | `GlmVoice.run` |
| G3 | Asleep and someone speaks: one hint per sleep ("type @Dory wake up"), no wake | `glm_asleep`, `GlmVoice.feed` |
| G4 | STOP by the always-on bot, not by a laptop: `IdleWatch` polls `/health` (`calls`, `idle_s`) every minute and stops the VM after `IDLE_STOP_S` without activity. `idle_s` is refreshed by audio, typed turns, say events and every TTS chunk, so an answer or playback in progress is never cut. An old server without `idle_s` counts an open call as busy | `nebius_vm.IdleWatch`, `gpu_lifecycle_bot` |
| G5 | Every wake and every stop logs its reason (`nebius vm: ... (reason=...)`) | `VmWaker.ensure_running` / `stop` |
| G6 | The Mac watchdog (`vm.sh idle-check`) stays as an optional second stopper; nothing needs it | `deploy/glm_voice/vm.sh` |

## Notes

- `wake_policy` strict (default) | natural (hub setting): natural also lets a direct reply within 8 s of
  her own words be heard without the name (`NATURAL_WINDOW_S`).
- Classic mode (not Live) keeps its keyword rules: `is_dismissal`, `_ASK_RE`, `_SELF_TALK_RE`, three
  unaddressed utterances, `pending_wake` (the words after a bare name). They never run in live mode.

## Cascade path (self-hosted ASR -> brain -> TTS), 27 Oct 2026

Cascade mode = `voice_mode` glm with `DORY_GLM_VOICE_URL` on the sidecar's port 8766
(`deploy/glm_voice/cascade.py`): the GPU box transcribes one utterance ("heard"), Dory's text brain
answers it (`qa.ask`, `spoken=True`, the same tools as chat) and Kokoro speaks the answer sentence
by sentence. The web call (`center.py` `/live`) and a Discord room (`glm_room.GlmRoom`) share
`glm_voice.GlmVoice`. The cascade decides from TEXT, so the classic keyword helpers (`parse_wake`,
`is_hush`, `_ACK_RE`) are allowed; the Live-only machinery (mouth gate, `end_conversation` tool,
`live_*_reply_seconds`, background jobs) is not used.

| # | Rule | Config (default) | Where | Test |
|---|------|------------------|-------|------|
| C1 | Voice: Kokoro `CASCADE_VOICE` (`af_bella,af_heart`: the bright A- voice blended with the A one, youthful and upbeat, 29 Oct 2026) at `CASCADE_SPEED` (1.08: lively, not rushed) with `CASCADE_SENTENCE_GAP_MS` (250) of silence after each sentence of a say, so facts breathe. Magpie ignores both | `/etc/glm-voice.env` | `cascade.py` `Engines.synth`, `speak_loop` | `test_glm_cascade.py::test_cascade_speaks_sentences_with_a_gap` |
| C2 | Spoken register: `qa.spoken_hint` tells the brain 1-3 short sentences, no emoji / markdown / lists / URLs, the person's name at most once and her own never, one question at a time and stop after it, calm with no exclamation on money / HR / health / conflict / something that failed, a correction ("no, Friday") redoes the last action, an action happened only when a tool result says so, say so when the audio was unclear. The tone preset still wins | `default_tone` etc. (existing) | `qa.spoken_hint` | `test_english_voice.py` / `test_glm_voice.py::test_spoken_hint_carries_the_register_rules` |
| C3 | Web call: everything heard is for her (the person opened the panel; the browser sends frames only while they speak, nothing while quiet, so there is no continuous listening and no name rule). The greeting is a fixed line (`meet_greet_spoken`), not a brain turn | `live_web_silence_ms` (800) | `GlmVoice.greet`, `center.py` `ask_fn(spoken=True)` | `test_glm_voice.py::test_glm_voice_greets_with_a_fixed_line_not_the_brain` |
| C4 | Room WAKE on the transcript: `naming.address_kind(text)` = `addressed` (her name opens or closes the utterance, after a cue word, or before a comma / question mark; every spelling `find_call` knows plus a phonetic key `d-r-` for Dori / Dorey / Doory / Dora), `mentioned` (a sentence about her: "Dory booked it", "ask Dory later") = nothing, `unclear` (a mention with a request shape) = a brief "Yes?" once, never an interruption; `wake_policy` natural also answers `unclear` without asking | `wake_policy` (strict) | `naming.address_kind`, `GlmRoom._on_heard` | `test_glm_room.py::test_glm_room_answers_only_when_addressed`, `test_meeting_behaviour.py::test_address_kind` |
| C5 | STAY: the speaker of the addressing utterance is the caller; their utterances need no name for `engaged_timeout_seconds` (renewed by every exchange); others count only when addressed. A bare "ok" / "got it" / "mm-hm" is not a question unless she just asked one (then it is the answer). A fragment within `MERGE_S` (2.0 s) of the caller's still-pending question is the same sentence cut by the ASR: asked once, merged, the window stays. When a new utterance cancels an answer she never got to speak (the person kept talking: 29 Oct 2026, 80 brain calls in 8 min, most cancelled), the window ENDS: her name again | `engaged_timeout_seconds` (300) | `GlmRoom._on_heard`, `GlmVoice.answer` (`_ACK_RE`) | `test_glm_room.py::test_glm_room_answers_only_when_addressed_and_follows_up_without_the_name`, `test_glm_room.py::test_glm_room_wants_the_name_again_after_a_cancelled_answer`, `test_glm_voice.py::test_answer_merges_a_split_sentence_and_reports_a_cancel` |
| C6 | Hush: "Dory, be quiet" (`is_hush`) stops playback and the pending answer; she stays silent until her name comes with words (`parse_wake` with a question) | none | `GlmRoom._on_heard` | `test_glm_room.py::test_glm_room_hush_stops_everything_until_the_name_with_words` |
| C7 | Barge-in: the server interrupts on the first voiced frame it receives (and only while it is speaking or has a say queued; a quiet room never cancels an answer), so while she speaks the room forwards frames only after `TALKOVER_S` of voiced audio (a cough or side talk never stops her); the web forwards its own frames unchanged (the browser cancels echo) | `TALKOVER_S` 0.8 | `cascade.py` `interrupt`, `GlmRoom._pump_mixer` | `test_glm_cascade.py::test_cascade_turn_heard_say_turn_and_barge_in`, `test_glm_room.py::test_glm_room_holds_side_talk_while_she_speaks` |
| C8 | Fillers that fit: none for a fast answer; after `FILLER_AFTER_S` (4.5 s: plain turns answer in 3.5-4.2 s, measured 29 Oct 2026, and 3.5 s still fired on them) without the answer ONE line, request-specific: `voice_ack.ack_line` (the cheap model, prepared while the brain works, names what she is doing for them, never a stock holding phrase, waited for up to `ACK_WAIT_S` 1.0 s), else an `ack_voice_*` line (brief, no "one moment" / "let me see"), never the same as the last three | none | `GlmVoice._answer_turn`, `voice_ack.py` | `test_glm_voice.py::test_glm_voice_cascade_answers_what_the_server_heard_and_fills_only_when_slow`, `test_glm_voice.py::test_ack_line_prefers_the_prepared_line_and_falls_back`, `test_voice_ack.py` |
| C9 | Context: `GlmVoice` keeps a rolling `meeting.Transcript` (memory only, dropped with the socket; never the meeting's minutes) of what was heard and what she said and passes the last 180 s / 3,000 chars as `history` to the brain, so "change that" / "try again" / "what happened?" work | none | `GlmVoice.transcript`, `GlmRoom._ask`, `center.answer_question(voice_history=)` | `test_glm_voice.py::test_glm_voice_passes_the_rolling_transcript_as_history` |
| C10 | Format: every say goes through `speech.speakable` (markdown, links, emoji, unspoken symbols removed) plus THB / % read as words; the room's text echo ("💬 **Dory:** ...", rule 4, `meeting_text_echo`) keeps the brain's original text | `meeting_text_echo` (true) | `GlmVoice._say`, `GlmRoom._out` | `test_glm_voice.py::test_glm_voice_speaks_plain_text` |

Not done on the cascade (open): hearing the name in audio (text only; Parakeet has no Thai, so a Thai
room needs `CASCADE_ASR=whisper`); who spoke is the user whose frames were loudest (one mixed stream);
`end_conversation` by the model (a thanks is answered, the window just runs out); the minutes stay
off; Thai speech out (Kokoro has no Thai voice); long jobs hit `TOOL_TIMEOUT_S` (90 s).

