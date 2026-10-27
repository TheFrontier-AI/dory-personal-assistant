# Dory voice stack — phase 0 audit of the existing real-time voice paths

Date: 2026-10-25. Branch `rename/dory`. Read-only audit of `src/dory/` and `src/meeting_scribe/`;
no code was run, no paid API called. Every statement is marked **C** (Confirmed from code, with
file:line) or **I** (Inferred). Line numbers are those of the working tree on this date.

Two voice paths exist today:

1. **Discord voice rooms** — `meeting.py` (session, capture, segmenter, classic path),
   `live_voice.py` (Gemini Live native-audio session), `speech.py` (TTS), `voice_pool.py`
   (extra bot accounts), `captions.py`, `voice_actions.py`, behaviour spec `docs/voice_behaviour.md`.
2. **Web Live** — `web_live.py` + WebSocket `/api/center/orgs/{id}/live` in `center.py` +
   the floating call panel in `static/center.html`. (A third, non-real-time path, `web_voice.py` +
   `POST /orgs/{id}/voice/transcribe`, records one utterance for the typed chat box.)

Both paths use **Gemini Live 2.5 Flash native audio** as the speech-to-speech layer and hand the
"thinking" to the text brain through one tool, `ask_dory`. Nothing in the audio chain touches Nebius
Token Factory today (section 13).

---

## 1. Dependencies and runtime (both paths)

| Item | Value | Evidence |
| --- | --- | --- |
| Discord library | `discord-py[voice] 2.7.1` (not py-cord) | **C** `pyproject.toml:11`, `uv.lock:848-849` |
| Voice receive | `discord-ext-voice-recv 0.5.2a179` | **C** `pyproject.toml:10`, `uv.lock:836-837` |
| E2EE (DAVE / MLS) | `davey 0.1.7` | **C** `pyproject.toml:9`, `uv.lock:743-744` |
| Transport crypto | `pynacl 1.5.0` (transitive of discord.py[voice]) | **C** `uv.lock:3240-3241` |
| Opus codec | system `libopus0` (Docker), `discord.opus.Decoder` | **C** `Dockerfile.dory:17`, `meeting.py:713-716` |
| ffmpeg | playback resample/pitch and 16 kHz FLAC for ASR | **C** `Dockerfile.dory:17`, `speech.py:288-293`, `meeting_scribe/audio.py:8-13` |
| Gemini SDK | `google-genai 2.29.0` (`client.aio.live.connect`) | **C** `uv.lock:1330-1331`, `live_voice.py:1191`, `web_live.py:92` |
| Live model / region / voice | `gemini-live-2.5-flash-native-audio` @ `us-central1`, voice `Leda` | **C** `config.py:92-94` |
| Cloud TTS | REST `texttospeech.googleapis.com/v1/text:synthesize`, Chirp 3 HD, LINEAR16 24 kHz | **C** `speech.py:188`, `speech.py:212-244` |
| Gemini TTS fallback | `gemini-2.5-flash-tts`, voice `Leda` | **C** `config.py:86-87`, `speech.py:162-185` |
| Segment ASR model | `gemini_model` = `gemini-3.5-flash` at `transcribe_location` = `asia-southeast1` | **C** `config.py:37`, `config.py:215`, `meeting.py:883-893` |
| No VAD library | no Silero / webrtcvad in `pyproject.toml`; `audioop-lts` present only transitively | **C** `pyproject.toml:7-37`, `uv.lock:239` |

---

## 2. Path 1 — Discord voice rooms

### 2.1 Audio capture

- **Library and threading.** `MeetingManager._connect` joins with `hchan.connect(cls=voice_recv.VoiceRecvClient)` (**C** `meeting.py:934`) and `vc.listen(MeetingSink(session))` (**C** `meeting.py:1523`, resume `1932`, reconnect `1975`). `MeetingSink(voice_recv.AudioSink)` runs on the extension's router thread (**C** `meeting.py:667-669`).
- **Raw Opus, own DAVE decrypt, own decode.** `wants_opus()` returns True so the extension never decodes (**C** `meeting.py:677-678`); `_dave_decrypt` calls `dave_session.decrypt(user_id, davey.MediaType.audio, opus)` and passes plain frames through on "unencrypted" errors (**C** `meeting.py:683-698`); one `discord.opus.Decoder` per user, `decode(plain, fec=False)` in its own try/except (**C** `meeting.py:709-721`). Reason documented: the extension's decoder thread dies on the first undecodable frame (**C** `meeting.py:8-11`).
- **Format.** Decoder output is 48 kHz stereo s16le (**C** `meeting.py:67-69`); one 20 ms frame = 3840 bytes (**C** `live_voice.py:75`). Speaker identity is exact (one SSRC per member), no diarization (**C** `meeting.py:11-12`).
- **Hand-off to the loop.** `push_threadsafe` → `loop.call_soon_threadsafe(on_pcm, ...)` per frame per speaker (**C** `meeting.py:834-836`). `on_pcm` feeds the per-speaker `Segmenter` for the classic/ASR path and, in live mode, `self.live.feed(user_id, pcm)` for humans only (**C** `meeting.py:838-842`).
- **Segmenter (classic/ASR path).** Per-speaker buffers cut on a gap > `SILENCE_S` 1.2 s or at `MAX_SEGMENT_S` 20 s; segments < `MIN_SEGMENT_S` 0.4 s dropped; gaps > `PAD_GAP_S` 0.15 s are zero-filled to keep timing (**C** `meeting.py:72-75`, `349-407`). A 0.5 s ticker closes idle buffers (**C** `TICK_S` `meeting.py:92`, `_ticker` `2092-2097`). Segments with whole-segment RMS < `MIN_RMS` 120 are dropped before the queue; queue is `QUEUE_MAX` 60, overflow drops with a warning (**C** `meeting.py:76`, `844-852`).
- **Mixer (Live path).** `Mixer.feed` converts each speaker's 48 kHz stereo to 16 kHz mono by averaging 6 samples (L+R × 3 frames) — a box filter, no proper anti-alias filter (**C** `live_voice.py:435-447`, `460-471`). Per-speaker buffer capped at `MIXER_MAX_S` 3 s (older audio dropped) (**C** `live_voice.py:83`, `470-471`). `Mixer.pop` sums speakers sample-by-sample in pure Python with clipping, up to `MAX_CHUNK_SAMPLES` 300 ms per call (**C** `live_voice.py:80`, `474-490`). Note: all of this runs on the asyncio event loop thread (**I** from `feed` being called from `on_pcm` on the loop, `meeting.py:841-842`).
- **Buffering while connecting.** `LiveVoice.feed` keeps accepting frames while the session is (re)connecting so a greeting right after joining is not lost (**C** `live_voice.py:1097-1107`); `_serve` sets `_streaming=False` so queued audio is sent first (**C** `live_voice.py:1314`).

### 2.2 VAD / turn detection

Two layers:

1. **Gemini Live server VAD** configured in `build_realtime_input` (**C** `live_voice.py:121-143`): `start_of_speech_sensitivity` from `live_start_sensitivity` (default `high`), `end_of_speech_sensitivity` from `live_end_sensitivity` (default `low`), `prefix_padding_ms` 300, `silence_duration_ms` = `live_silence_ms` 1000 (**C** `config.py:97-100`). With `live_barge_in="intentional"` (default, `config.py:105`) `activity_handling=NO_INTERRUPTION` is set, so the server never interrupts Dory on incoming audio (**C** `live_voice.py:126-130`). `proactive_audio=True` lets the model stay silent for talk not addressed to it (**C** `config.py:101`, `live_voice.py:1257-1261`).
2. **Client-side stream shaping.** `_sender` ticks every `SEND_INTERVAL_S` 0.1 s; while the mixer has audio it sends it; after the last voice it sends real silence for `_idle_s()` = max(1.0 s, `live_silence_ms`/1000 + 0.8) = 1.8 s so the server VAD can end the turn, then `audio_stream_end=True` once and stops (**C** `live_voice.py:79-81`, `1567-1594`). Discord stops sending frames during silence, so "silence" on the client is the absence of frames (**C** `meeting.py:351-353`).

Classic-mode turn detection is purely the Segmenter gap rule above (**C** `meeting.py:349-353`). There is no energy VAD before the model other than `MIN_RMS` (drop) and the name-hit "looks like speech" gate (`name_min_voiced_seconds` 0.35, `name_min_cv` 0.25, `name_min_rms` 250, `name_bare_min_voiced_seconds` 0.45; **C** `config.py:179-186`, `meeting.py:465-489`).

### 2.3 ASR

- **Live transcript (streaming).** The Live session has `input_audio_transcription={}` and `output_audio_transcription={}` (**C** `live_voice.py:1262-1263`). Input transcript chunks go to `_on_heard` (**C** `live_voice.py:1633-1635`), which detects hush, stop requests and the wake name (`parse_wake`, same detector as classic) and starts a forced-reply timer (**C** `live_voice.py:1419-1484`). Output transcript is accumulated and posted as "🔊 text" at `turn_complete` (**C** `live_voice.py:1636-1638`, `2636-2639`).
- **Per-segment transcription (always on, both modes).** `handle_segment` runs `transcribe_heard` in a thread for every queued segment (**C** `meeting.py:2181-2187`): 48 kHz stereo PCM → WAV → ffmpeg → 16 kHz mono FLAC (**C** `meeting.py:570-578`, `596-600`, `meeting_scribe/audio.py:8-34`) → `generate(client, gemini_model, [audio/flac Part, prompt], JSON schema _Heard{text, name_called}, temperature 0)` (**C** `meeting.py:501-505`, `600-611`). Two workers per session (`TRANSCRIBE_WORKERS` 2, **C** `meeting.py:88`, `1529-1531`). The dedicated client points at `transcribe_location` asia-southeast1 (**C** `meeting.py:883-893`).
- **Thai handling.** Prompt is Thai (`TRANSCRIBE_PROMPT`) unless the session language is `en`, plus a note for second-tier languages; verbatim, never translated (**C** `meeting.py:516-540`, `580-593`). Transcript lines feed `Transcript` (memory only, 3 h, 6000 lines) and `bot.record_voice` → team memory (**C** `meeting.py:78-79`, `2210-2213`, `bot.py record_voice`).
- **Classic mode** uses the same per-segment text for wake word, question extraction and answers (**C** `meeting.py:2231-2328`).

### 2.4 Orchestration

- **Live session setup.** `MeetingManager._start_live` creates `LiveVoice` when `voice_reply` and `voice_mode == "live"` (default `live`, **C** `config.py:91`) and not listen-only (**C** `meeting.py:2040-2058`). `build_config` declares tools `set_minutes_destination, post_note, ask_consent, set_recording, set_captions, end_conversation` (+ `ask_dory`, `answer_privately` when the `qa` feature is on), builds the system instruction from `build_instruction` (persona, tone, language rule, state, last 120 s / 1500 chars of transcript on first connect), `response_modalities=["AUDIO"]`, voice `live_voice`, session resumption with the last handle, sliding-window context compression (**C** `live_voice.py:1214-1270`).
- **Brain call.** `ask_dory` is run as a `_Job` by `_one_brain`: waits `live_foreground_seconds` 25 s for the answer, else returns `{"status":"working"}` and announces the result at the next room pause (`_announce` → `announce_cue`, needs `live_result_pause_seconds` 1.5 s of quiet within `live_result_wait_seconds` 90 s) (**C** `live_voice.py:1672-1711`, `1810-1847`, `config.py:145-158`). `_ask_dory` builds the same ADK agent as chat (`bot._agent_kwargs`, `qa.ask`) for the LOWEST-ranked human in the room, re-binds action tools to the actual speaker via `voice_actions.rebind_actions`, limits memory to what everyone present may read, adds a ROOM_NOTE naming the asker, caps the answer at `ANSWER_MAX_CHARS` 700 and translates a wrong-script answer (**C** `live_voice.py:1915-2053`, `voice_actions.py:1-7`, `live_voice.py:338`). Hard limit per job `live_ask_timeout_seconds` 150 s in `_guarded` (**C** `live_voice.py:1849-1876`). At most `live_max_jobs` 3 concurrent (**C** `live_voice.py:1686-1688`).
- **Conversation state** lives in `MeetingSession` (engaged / caller / hushed / recording / consent flags, **C** `meeting.py:725-818`) and is pushed to the model as bracketed state text (`notify_state` → `_send_state`, **C** `live_voice.py:1334-1346`). Mouth gate and tool gate are in code: model audio is only played when engaged (or within `live_reengage_grace_seconds` 60 s, or answering an engaged tool call, or an announced job); unsolicited turns are held `live_call_grace_seconds` 4 s for a name then dropped (**C** `live_voice.py:2234-2290`); `ask_dory` while listening needs speech evidence and, under `strict` wake policy, a recent name hit (**C** `live_voice.py:2141-2174`).
- **Forced turns and fallback.** Name heard but no model audio after `live_name_reply_seconds` 1.0 s (Live transcript) / `live_force_reply_seconds` 2.0 s (ASR): send a text cue; retry after `live_cue_retry_seconds` 4 s; after `live_fallback_seconds` 4 s more, the classic path answers (`meetings.live_fallback`) (**C** `live_voice.py:1395-1417`, `1515-1565`, `meeting.py:2784-2797`).
- **Speaker notes.** On a speaker change (≥ `SPEAKER_NOTE_MIN_S` 3 s apart) a text part "(Now speaking: name)" is sent with `turn_complete=False` (**C** `live_voice.py:1136-1170`).
- **Cancellation.** Nothing cancels a running ask_dory job: not a new question, not barge-in (**C** docstring `live_voice.py:1678-1679`, test `test_voice_async.py:351`). Barge-in cancels the filler task and playback only (**C** `live_voice.py:2659-2668`).
- **Classic mode** (fallback when Live cannot connect): `handle_segment` → `answer` (`qa.ask` in a thread under `answer_lock`) → `speak` (`spoken_text` rewrite with `gate_model` → `say` TTS → `_play`) with an "acknowledge" filler clip raced against `voice_ack_timeout_s` 3 s (**C** `meeting.py:2693-2770`, `2799-2856`, `2879-2927`). Comment states ~11 s end to end for classic vs ~1.5 s for live (**C** `config.py:88-90`; not measured in code, **I**).

### 2.5 TTS

- **Live mode:** Dory's voice is the Gemini Live model's own native audio (24 kHz mono PCM16, `LIVE_OUT_RATE`, **C** `live_voice.py:74`). No separate TTS for answers.
- **Fillers / acks / classic answers:** `speech.say` → Cloud TTS Chirp 3 HD (`cloud_tts_voice` Leda, `tts_speaking_rate` 1.08, LINEAR16 24 kHz) with fallback to Gemini TTS `gemini-2.5-flash-tts` on any error (**C** `speech.py:257-273`, `config.py:82-87`). Whole-utterance synthesis, blocking HTTP with 20 s timeout, run in `asyncio.to_thread` (**C** `speech.py:233`, `meeting.py:2866`, `live_voice.py:2442`).
- **Language → voice table:** `_LANG_CODES` th→th-TH, en→en-US, zh→cmn-CN, hi→hi-IN, ms→ms-MY, id→id-ID, vi→vi-VN, ko→ko-KR, ja→ja-JP; `_VOICE_FALLBACK` ms→id-ID (no Malay Chirp 3 HD voices); voice name becomes `{code}-Chirp3-HD-{voice}` (**C** `speech.py:189-209`).
- **Pitch.** `tts_pitch` 1.06 applied by ffmpeg (`asetrate/aresample/atempo`) at playback (`pcm_source`) or on raw PCM (`pitch_pcm`, a subprocess per clip) (**C** `config.py:85`, `speech.py:280-313`). Live-model audio is NOT pitched (**I**: `_feed_player` feeds `LiveAudioSource` directly, `live_voice.py:2328-2333`).
- **Filler clip pool.** 4 fallback clips per language pre-rendered per session (`PRERENDER_FIRST`), cached in memory and on disk (`ClipCache`), plus LLM-written lines (`FillerWriter`, cheap model) raced against `voice_ack_timeout_s` (**C** `live_voice.py:270`, `2419-2452`, `2512-2563`).

### 2.6 Playback

- `LiveAudioSource(discord.AudioSource)`: the discord.py player thread calls `read()` every 20 ms; it returns 3840 bytes of 48 kHz stereo (24 kHz mono upsampled by sample repetition, `upsample_output`, no interpolation), silence while the turn is open and the buffer is dry, and `b""` after `finish()` + drain or after `SOURCE_STALL_S` 20 s without a feed (**C** `live_voice.py:450-457`, `496-566`). `_ensure_playing` starts `vc.play(src)` with up to `PLAY_RETRIES` 5 × 50 ms retries while the previous source winds down (**C** `live_voice.py:2578-2602`).
- Classic clips: `pcm_source` → `FFmpegPCMAudio` from a BytesIO pipe, played under `play_lock`, awaited with `pcm_duration_s + SPEAK_TIMEOUT_PAD_S` 10 s (**C** `meeting.py:2942-2984`).
- `_stop_playback` uses `stop_playing()` where it exists because `VoiceRecvClient.stop()` also stops listening (**C** `meeting.py:657-664`).
- Yield rule: model audio arriving while a person spoke < `YIELD_ACTIVE_S` 0.5 s ago is buffered until `YIELD_QUIET_S` 0.5 s of quiet; after `YIELD_MAX_S` 6 s it is dropped and the model is told they were still talking (**C** `live_voice.py:280-282`, `2318-2326`, `2335-2370`).

### 2.7 Barge-in / interruption

- Server side is disabled (`NO_INTERRUPTION`) under the default "intentional" policy (**C** `live_voice.py:126-130`). Under `live_barge_in="any"` the server interrupts and `sc.interrupted` → `_interrupt()` (**C** `live_voice.py:1620-1621`, `2659-2668`).
- Code-side triggers while `_speaking()`: (a) the **partner** (whoever spoke just before the answer, `_partners = recent_speakers()`) talks at ≥ `TALKOVER_RMS` 500 for `TALKOVER_S` 0.8 s (gaps ≤ 0.35 s), or `EARLY_CUT_SPEECH_S` 0.3 s within the first `EARLY_CUT_S` 2.5 s of the answer (**C** `live_voice.py:289-293`, `1115-1134`, `2296-2300`); (b) a stop phrase or her name in the Live input transcript (`is_stop_request`, **C** `live_voice.py:107-118`, `1431-1437`). Anyone else talking never stops her (**C** `live_voice.py:1116-1119`).
- What is cancelled: filler task, playback (`stop_playback` clears and finishes the source, `vc.stop_playing`), `_said`, `_held`, `_turn_audio`, `_awaiting_answer`; the rest of the current model turn is muted (`_muted_turn = _turn_open`) (**C** `live_voice.py:2650-2678`). What is NOT cancelled: server generation of the turn (it keeps streaming, audio is discarded — **C** comment `live_voice.py:2651-2653`), running ask_dory jobs (**C** `live_voice.py:1679`), output-transcript posting of the muted turn is suppressed (**C** `live_voice.py:2633-2636`).
- Echo guard: `speaking_until = now + SPEAK_COOLDOWN_S` 1.5 s after playback; `_is_echo` ignores wake words that soon (**C** `meeting.py:93`, `2978-2979`, `2684-2691`).

### 2.8 Latency — measured today

| Measured | Where | Scope |
| --- | --- | --- |
| "user audio ended -> first audio %.1fs" | **C** `live_voice.py:2302-2306` | last mixer send with voice → first model audio accepted by the gate; excludes yield/hold delays and Discord playback start |
| "ask_dory answered in %.1fs (%d rounds, %d chars)" | **C** `live_voice.py:2022-2027` (`Answer.seconds`, `qa.py:1777`) | brain only |
| `_log_answer`: `ms_total ms_context ms_agent tools=name:ms tok_*` | **C** `bot.py:2766-2780`, called from classic `answer` `meeting.py:2738-2740` | classic brain path only |
| FLAC conversion byte sizes (no time) | **C** `audio.py:33` | — |
| Connection lifetime `lived` (stability only, not logged) | **C** `live_voice.py:1282`, `1296-1299` | — |

Not measured (**C** by absence): per-segment ASR latency in `handle_segment`; TTS synthesis time (`say`); time from `vc.play` to first audible frame; Live connect time; time held in the mouth gate / yield buffer; end-of-turn-to-playback on the Discord side; jitter / underruns (silence frames inserted by `read()` are not counted); barge-in reaction time; web path: nothing at all (no timing in `web_live.py` or the browser).

### 2.9 Concurrency

- One `MeetingSession` per (guild, voice channel); one voice connection per bot account per guild, so parallel rooms need helper accounts (`VoicePool`, `DORY_VOICE_TOKENS`) that only hold voice; text, memory, answers and TTS stay in the main bot (**C** `voice_pool.py:1-10`, `config.py:19-21`, `meeting.py:855-858`). Room importance / preemption rules `room_score`, `pick_victim` (**C** `voice_pool.py:36-77`).
- Per session: 2 transcription workers, 1 ticker, 1 `LiveVoice.run` task plus its sender/receiver and `_bg` tasks; `answer_lock` (classic), `play_lock` (classic clips), `speech_pending` flag, `_join_lock` per guild (**C** `meeting.py:1529-1534`, `MeetingSession` fields `737-746`, `951-952`).
- Thread/async boundaries: sink thread → loop (`call_soon_threadsafe`); ASR / TTS / `qa.ask` / `pitch_pcm` in `asyncio.to_thread` (default executor); player thread reads `LiveAudioSource` under a `threading.Lock`; `after=` callbacks re-enter the loop via `call_soon_threadsafe` (**C** `meeting.py:834-836`, `2185`, `live_voice.py:503-512`, `2604-2606`). The transcription executor is the default thread pool shared with every other `to_thread` in the bot (**I**).
- Caps: `MEETING_MAX_S` 6 h when the room is empty, `EMPTY_GRACE_S` 10 min (`meeting_empty_minutes`), `live_max_jobs` 3, `QUEUE_MAX` 60 segments, `MIXER_MAX_S` 3 s per speaker, `TRANSCRIPT_KEEP_S` 3 h (**C** `meeting.py:78-83`, `config.py:272`).
- The `IndexedMemoryStore` / `RecentMessages` assumptions of ONE bot process apply to voice too (**C** CLAUDE.md code map; `_live_open` style globals are not used on the bot side).

### 2.10 Failure handling

- **Live (re)connect:** `run()` loops with session resumption handle; failures back off `BACKOFF_S` (0.5, 1, 2, 4); a connection that lived `STABLE_S` 10 s resets the counter; `MAX_FAILURES` 4 → `on_failed` → `voice_mode="classic"` (wake words + TTS) (**C** `live_voice.py:86-89`, `1272-1311`, `meeting.py:2060-2064`). `go_away` → reconnect; three empty `receive()` iterations → `ConnectionError` → reconnect (**C** `live_voice.py:1596-1615`).
- **Voice connection drop:** `on_disconnected` retries `RECONNECT_DELAYS` (2, 5, 10 s) with a fresh `VoiceRecvClient` + sink, posts `meet_reconnected` or `meet_reconnect_failed` then ends (**C** `meeting.py:82`, `1948-1989`). Join failures: `JOIN_FAIL_LIMIT` 3 in 120 s → `JOIN_BACKOFF_S` 300 s; `voice_connect_timeout_seconds` 20 (**C** `meeting.py:99-102`, `config.py:283`).
- **Model silent after the name:** cue → cue → classic fallback (2.4). **Tool failure / timeout:** honest typed line `voice_tool_failed` + spoken `voice_tool_failed_say`; never invented (**C** `live_voice.py:1849-1876`). **TTS failure:** Cloud → Gemini TTS; still failing → the answer stays typed only (**C** `speech.py:262-273`, `meeting.py:2879-2927`). **Playback:** 10 s pad timeout, stall 20 s on the Live source (**C** `meeting.py:94`, `live_voice.py:86`).
- **Graceful shutdown / restart:** `MeetingManager.shutdown` closes Live, stops listening, disconnects but keeps the Firestore/SQLite record (`_persist`) so `resume_all` rejoins on `on_ready` (**C** `meeting.py:1776-1807`, `3165-3184`, `bot.py:648`, `1368-1369`). `end()` drains the segment queue up to 90 s, then posts the summary (**C** `meeting.py:2986-3024`).
- **What the user hears on failure:** live → a spoken fallback from the classic path or nothing plus a typed line in the meeting chat; the "listening / in conversation" state lines are text (**C** `_post_state`, `meeting.py:2608`, `voice_behaviour.md:17`).

### 2.11 Observability

Python `logging` only: structured-ish `logger.info` lines with counts, never content (e.g. `live: connected`, `live: name hit accepted dur= rms= voiced= vf= cv=`, `live: tool call <name>`, `live: interrupted`, `live: answer dropped: they were still talking`, `meeting %s: %s said %d chars`) (**C** `live_voice.py:1284-2661` grep, `meeting.py:2214`). No metrics export, no tracing, no per-session audit record. The workflow monitor lists a `meeting` kind but no voice/meeting source is registered (**C** `monitor.py:55`; grep of `monitor_sources.py` finds no meeting/voice/live source — **I** voice sessions are invisible to `/center` monitor). `/health` exists only on the web service (**C** `app.py:174-176`); the bot's monitor heartbeat carries queue sizes but nothing voice-specific (**C** CLAUDE.md `monitor_bot.py`).

### 2.12 Tests

All offline unless marked. Counts from `grep -c 'def test_'`:

| File | Tests | What is faked |
| --- | --- | --- |
| `tests/dory/test_live_voice.py` | 71 | `FakeLive` / `FakeConnect` (scripted Live session), `_connect`, `say` (TTS → zero bytes), `pitch_pcm`, `qa.ask`, memory/web tools, `SEND_INTERVAL_S`, `BACKOFF_S` (**C** lines 203-306, 493-511) |
| `tests/dory/test_meeting.py` | 76 | `FakeVoiceChannel` / `FakeVC` / `FakeGuild`, `_connect`, `transcribe_pcm`, `qa.ask`, `to_flac`, `pcm_source`, `say` (**C** lines 170-258, 335-672) |
| `test_meeting_behaviour.py` 40, `test_voice_listen.py` 26, `test_voice_async.py` 25, `test_voice_talk.py` 9, `test_voice_join.py` 8, `test_voice_eval_fixes.py` 8, `test_voice_hotfix.py` 5, `test_english_voice.py` 5, `test_v011_live_decides.py` 11, `test_voice_actions.py` 1 | — | same harness family; `test_voice_async.py` covers jobs/background/announce/mouth gate (**C** `test_voice_async.py:85-491`) |
| `tests/dory/test_speech.py` 20, `test_voice_pool.py` 34, `test_captions.py` 11 | — | pure functions / fake Discord clients |
| `tests/dory/test_center_api.py:1728-1866` | 3 | web Live: `FakeLive` async generator injected through `center.get_live_connect`; checks ready → greet audio → tool call → interrupted; config knobs; instruction text |
| `tests/dory/live_eval/` (`pytestmark = live`) | 1 parametrized (classic, live) | REAL Cloud TTS audio → real Segmenter/Gemini ASR → REAL Gemini Live, fake Discord objects; counters `LIVE_CALLS`; hard-coded `LEDGER_SRC=/home/ubuntu/.dory-dev/ledger.db` (**C** `voice_harness.py:1-29`, `test_live_voice_eval.py:8-12`) |

Not covered (**I**): real Opus/DAVE decode, real `VoiceRecvClient`, audio quality of `to_live_input` / `upsample_output`, timing under load, browser worklet.

### 2.13 Cost drivers per minute of room audio (live mode)

1. Gemini Live session: input audio whenever anyone speaks + 1.8 s silence tails + text notes (speaker changes, state lines, cues) + output audio and transcripts (**C** `live_voice.py:1572-1594`, `1163-1170`).
2. Per-segment Gemini ASR on `gemini-3.5-flash` for EVERY segment ≥ 0.4 s with RMS ≥ 120, in BOTH modes (the transcript, minutes, memory and name backup need it) — one `generate_content` with a FLAC part plus one ffmpeg subprocess per segment (**C** `meeting.py:2181-2187`, `596-611`).
3. `ask_dory`: one full ADK agent run (Nemotron on Token Factory when `DORY_NEBIUS_API_KEY` is set, else Gemini) + memory embedding lookups (**C** `live_voice.py:1986-2008`, `llm.py:48-64`).
4. Cloud TTS: 4 pre-rendered filler clips per session per language (disk-cached) + one generated filler line per slow tool (cheap-model write + Cloud TTS) (**C** `live_voice.py:2419-2430`, `2497-2510`).
5. Captions when on: one `gate_model` translation call per `FLUSH_EVERY_S` 12 s (**C** `captions.py:27`, `89-111`).
6. Classic mode adds: `gate_model` `spoken_text` per answer, Cloud TTS per answer and per ack, `notes_from_transcript` on `gate_model` every `notes_batch_seconds` 60 s (**C** `meeting.py:2879-2906`, `2140-2167`, `1335-1357`).
7. End of meeting: one summary call on `gemini_model` over up to 150k chars (**C** `meeting.py:86`, `629-647`).

---

## 3. Path 2 — Web Live (`/api/center/orgs/{id}/live`)

### 3.1 Audio capture (browser)

- `getUserMedia({audio:{echoCancellation, noiseSuppression, autoGainControl, channelCount:1}})` (**C** `center.html:2103`). An `AudioWorkletProcessor` `DoryMic` (loaded from a Blob URL) resamples the context rate to 16 kHz by linear interpolation (no anti-alias filter), converts to Int16 and posts 640-sample = 40 ms frames; fallback `ScriptProcessor(4096)` on the main thread (**C** `center.html:1948-1990`). Muted → frames of zeros keep streaming "so the server keeps hearing a steady stream" (**C** `center.html:1952`, `1955`).
- Frames are sent as binary WebSocket messages when `readyState === 1` (**C** `center.html:2109`). No batching, no client-side VAD, no pause when idle (**C** by absence).

### 3.2 Server ingest and VAD

- Route `@router.websocket("/orgs/{org_id}/live")`: first JSON hello `{token, lang, page, greet}` within 15 s; auth via `hub.user_from_token`, org membership, licence (`license_ok`), one session per `org:email` in a process-global `_live_open` set (**C** `center.py:4389-4437`). Binary frames → `live.feed(bytes)`; JSON `{"type":"say"}` → `live.say(text[:500])`; `{"type":"close"}` ends (**C** `center.py:4483-4496`).
- `WebLive.feed` puts frames in an `asyncio.Queue(maxsize=MAX_QUEUE 200)`, dropping the OLDEST when full (the comment says ~4 s of 20 ms frames; with 40 ms browser frames it is ~8 s, **I**) (**C** `web_live.py:36`, `131-140`). `_send` forwards each frame as its own `send_realtime_input(audio=Blob(... "audio/pcm;rate=16000"))` — 25 sends/s, no silence tail, no `audio_stream_end` (**C** `web_live.py:210-223`).
- VAD = Gemini server VAD via the same `build_realtime_input` with "patient" settings: `live_barge_in="any"` (so NO `NO_INTERRUPTION`: the server interrupts), end sensitivity `low`, `silence_duration_ms = max(live_silence_ms, WEB_SILENCE_MS 2000)` ("API max 2000"), start sensitivity from settings (**C** `web_live.py:38`, `177-190`).

### 3.3 ASR

Only the Live model's `input_audio_transcription` / `output_audio_transcription`, forwarded as `("heard", text)` / `("said", text)` events (**C** `web_live.py:169-170`, `251-256`). The browser accumulates them per turn and appends them to the chat log at `turn` (**C** `center.html:2073-2078`). Languages: the instruction says understand Thai or English, ALWAYS answer in the company language (**C** `web_live.py:55-56`); server-side `conform_language` applies to text chat, not to Live audio (**I** from CLAUDE.md "web Live answers only in the set language" and no translation code in `web_live.py`).

### 3.4 Orchestration

- One tool, `ask_dory(question)`; `_tool_call` sends `("thinking", question)`, runs `asyncio.to_thread(self.ask, question)` with `TOOL_TIMEOUT_S` 90, returns `{"answer"}` or `{"error": "could not get the answer right now"}` (**C** `web_live.py:37`, `262-280`). `ask` = `center.answer_question(ctx, orgs, lib, ask, guilds, ws, question, page, language=lang)` — the same text brain as web chat with the caller's scope and web tools (**C** `center.py:4453-4454`, `4089-4102`). `greet(lang)` sends a text cue so Dory speaks first (**C** `web_live.py:119-129`, `center.py:4474-4475`). Typed turns go through `send_client_content(turn_complete=True)` (**C** `web_live.py:215-220`).
- Conversation state: none server-side beyond the Live session itself (no engaged/mouth gate); `turns` counter only (**C** `web_live.py:98`, `257-259`). No session resumption handle, no sliding-window handle reuse across reconnects (config has `context_window_compression` only) (**C** `web_live.py:160-175`).
- Cancellation: a tool call blocks `_receive` while it runs (it is awaited inline in `_on_message`, **C** `web_live.py:239-240`), so a barge-in during a 90 s brain call is not processed until the call returns (**I**).

### 3.5 TTS and playback

- Dory's audio = Live model native audio, 24 kHz PCM16, forwarded chunk by chunk as binary frames (**C** `web_live.py:246-250`, `center.py:4456-4458`). No Cloud TTS on this path (**C** by absence).
- Browser: each chunk becomes an `AudioBuffer(1, n, 24000)` scheduled back-to-back from `S.next` (≥ now + 50 ms), RMS per chunk drives the mouth animation (**C** `center.html:2039-2049`). `stopPlayback` stops all scheduled sources (**C** `center.html:2050`).

### 3.6 Barge-in

Server-side only: `live_barge_in="any"` → the Live VAD interrupts the model; `sc.interrupted` → `("interrupted","")` → browser `stopPlayback()`, logs the partial said-text with " …" (**C** `web_live.py:244-245`, `center.html:2076`). A running `ask_dory` is not cancelled (**C** by absence in `web_live.py:262-280`).

### 3.7 Latency, concurrency, failures, observability

- **Latency:** nothing measured on the server or in the browser (**C** by absence: `web_live.py` has only `started` and `turns`).
- **Concurrency:** one session per person (`_live_open`, in-process), `LIVE_MAX_S` 30 min, a new `genai.Client(... location=live_location)` per socket built in a threadpool (**C** `center.py:4380-4381`, `4433-4437`, `4467-4469`, `4480-4482`). The web service runs with `max-instances=1`, so the in-process set is effectively global (**C** CLAUDE.md infrastructure).
- **Failures:** any session exception → `("error", ExceptionTypeName)`; `go_away` → `("error","go_away")` and end — NO reconnect, no resumption (**C** `web_live.py:203-208`, `236-238`). Browser maps codes to toasts (`auth`, `forbidden`, `unavailable`, `already_open`, `time_limit`, `go_away`, else generic) and ends the call; `onclose` → "Connection lost. Press Live to call again." (**C** `center.html:2082-2098`, `1001`). No keep-alive ping (**C** by absence).
- **Observability:** `logger.warning("web live: session error ...")`, `("web live: ask_dory failed (%s)")` (**C** `web_live.py:206`, `276`); `logger.exception("live voice session failed")` (**C** `center.py:4500`). No metrics.
- **Cost per minute:** a Gemini Live session streaming mic audio CONTINUOUSLY (silence included, even muted) for up to 30 min, plus one `answer_question` agent run per tool call (**C** `center.html:1952`, `web_live.py:210-223`).

### 3.8 The third, non-live web path (`/voice/transcribe`)

`POST /orgs/{org_id}/voice/transcribe` takes one MediaRecorder blob (≤ 8 MiB), ffmpeg → FLAC → `gemini_model` JSON `{text, language, translated}`; the browser puts `translated or text` in the chat box (**C** `center.py:3811-3850`, `web_voice.py:23-65`). Rate-limited by `_chat_allowed`. Not real time; mentioned for completeness.

---

## 4. The Nebius constraint

- **Routing rule.** `RoutedClient.accepts` returns False for any model id containing `tts`, `image`, `banana`, `embedding`, `live`, `omni` (`_NOT_TEXT`), for configs with `tools`, `response_modalities`, `speech_config` or `cached_content`, and for contents that are not text / inline images (`_messages` → None for audio, PDF bytes, file URIs) (**C** `llm.py:25-26`, `108`, `237-249`). `generate` only reroutes when `accepts` is True (**C** `llm.py:335-346`).
- **What therefore stays on Google today (both paths):**
  1. Gemini Live sessions — opened directly on `genai.Client(vertexai=True, location=live_location).aio.live.connect`, bypassing `RoutedClient` entirely (**C** `live_voice.py:1183-1191`, `web_live.py:91-93`, `center.py:4467-4469`).
  2. Per-segment ASR (`audio/flac` part → `accepts` False) on Vertex `gemini-3.5-flash` at asia-southeast1 (**C** `meeting.py:600-606`, `883-893`); web one-shot ASR likewise (**C** `web_voice.py:51-53`).
  3. Cloud Text-to-Speech REST (not through `generate` at all) and the Gemini TTS fallback (`tts` in the model id, `speech_config`) (**C** `speech.py:188-244`, `162-173`).
  4. Caption translation and `spoken_text` / fillers use `gate_model` = `gemini-3.5-flash-lite` — text-only, so they DO go to Nemotron when the key is set (**C** `llm.py:239`: `model.startswith("gemini")` and no `_NOT_TEXT` → accepted) (**I** for fillers: `FillerWriter` uses `generate`, not inspected line by line).
- **Why (documented):** "Audio, PDFs sent as bytes, TTS, live voice, image generation and grounded web search stay on Gemini: Token Factory has no open model for them" (**C** `config.py:67-70`). No speech model id (Parakeet, Canary, Riva, Whisper, Magpie) appears anywhere in `src/` (**C** grep in `llm.py`, `config.py`; **I** repo-wide).
- **Probe scripts.** `scripts/dory_tool_calls_probe.py` is a headless text harness (its only voice-ish line is the reminder prompt at line 110); `scripts/dory_nemotron_probe.py` has no speech, audio, TTS or ASR mention (**C** grep returned nothing). Neither tests speech on Token Factory.
- **Already on Token Factory in the voice loop:** the brain behind `ask_dory` — `qa.ask` → `build_agent` → `make_agent_model` (`LiteLlm` on Nemotron 3 Super, reasoning ON) when the key is set (**C** `llm.py:48-64`; CLAUDE.md `llm.py` row). So in a Nebius-only world the missing pieces are exactly ASR, TTS and the speech-to-speech/VAD layer.

---

## 5. Architecture diagrams

### 5.1 Discord voice room (live mode; classic fallback dotted)

```
Discord voice (Opus, DAVE E2EE)         discord-ext-voice-recv router thread
   │ per-speaker RTP/SSRC                MeetingSink.write  (meeting.py:700)
   ▼                                        │ dave.decrypt → opus.Decoder (48k stereo, 20 ms)
                                            ▼ loop.call_soon_threadsafe
                                  MeetingSession.on_pcm (meeting.py:838)
                       ┌────────────────────┴───────────────────────┐
                       ▼                                            ▼
            Segmenter (gap 1.2 s / 20 s / ≥0.4 s)         LiveVoice.feed → Mixer (16k mono sum,
            RMS≥120 → asyncio.Queue(60)                   3 s/speaker) + RMS ring + talkover
                       │ 2 workers                                  │ _sender every 100 ms
                       ▼ to_thread                                  ▼ (+1.8 s silence, stream_end)
            ffmpeg → FLAC → Gemini 3.5 Flash           Gemini Live 2.5 Flash native audio
            (asia-southeast1) JSON{text,name_called}    us-central1 · server VAD (start HIGH,
                       │                                 end LOW, 300/1000 ms) · NO_INTERRUPTION
         Transcript + memory + name backup               · proactive audio · resumption handle
         + captions + engaged/hush state        ◄────── input/output transcription, tool_calls,
                       │                                 24 kHz PCM audio
                       │ (classic only) qa.ask ──► TTS   │
                       ╎                                 ▼ _on_message (live_voice.py:1609)
                       ╎                   tool_call ──► _on_tool_call → _run_tool_call (bg task)
                       ╎                                 ask_dory → _one_brain job (25 s fg,
                       ╎                                 150 s cap, ≤3) → qa.ask (ADK, Nemotron
                       ╎                                 or Gemini) → answer ≤700 chars → tool resp
                       ╎                                 │
                       ╎              model audio ──► _gate_audio (mouth gate, 4 s hold)
                       ╎                              → _on_audio (yield 0.5/0.5/6 s)
                       ╎                              → LiveAudioSource (24k→48k stereo)
                       ╎                                 │ player thread read() 20 ms
                       ╎                                 ▼
                       └╶╶ FFmpegPCMAudio (pitch 1.06) ─► VoiceRecvClient.play ─► Discord room
                                                     ▲
   barge-in: partner RMS≥500 for 0.8 s (0.3 s early) or "stop"/name in Live transcript
             → stop_playback + mute rest of turn (server keeps generating)
   fillers: Cloud TTS Chirp 3 HD "one moment" clips (4 pre-rendered, disk cache)
```

### 5.2 Web Live

```
Browser (center.html)                        FastAPI web service (center.py:4389)
 getUserMedia(AEC/NS/AGC, mono)              WS /api/center/orgs/{id}/live
   │ AudioWorklet DoryMic: linear resample     hello{token,lang,page,greet} → auth, org, licence,
   │ → 16 kHz PCM16, 640-sample (40 ms)        one per org:email (_live_open), 30 min cap
   ▼ ws.send(binary) continuously (zeros when muted)
 ─────────────────────────────────────────►  WebLive.feed → Queue(200, drop oldest)
                                                │ _send: one send_realtime_input per frame
                                                ▼
                                      Gemini Live 2.5 Flash native audio (us-central1)
                                      server VAD start HIGH / end LOW / silence 2000 ms,
                                      barge-in "any" (server interrupts), in/out transcription,
                                      sliding-window compression, NO resumption handle
                                                │
                              tool_call ask_dory ─► to_thread(center.answer_question) ≤90 s
                                                │   (same text brain + web tools as chat)
                                                ▼ _on_message (web_live.py:235)
 ◄─────────────────────────────────────────  binary 24 kHz PCM chunks
 ◄─────────────────────────────────────────  JSON {ready|heard|said|thinking|interrupted|turn|error}
   enqueue → AudioBuffer(24k) scheduled back-to-back; "interrupted" → stopPlayback()
   any error / go_away / ws close → toast + call ends (no reconnect)
```

---

## 6. Ten most valuable concrete improvements (ordered by value)

| # | What | Where | Why | Effort | Risk |
| --- | --- | --- | --- | --- | --- |
| 1 | Add end-to-end latency instrumentation: timestamp last-voice-frame, server `turn end`/first audio chunk, first frame actually read by the player (Discord) or scheduled (web), ASR per segment, TTS per clip; one `voice_latency ...` log line per turn + optional histogram | `live_voice.py:1577-1580`, `2302-2306`, `2578-2602`, `542-559` (add `first_read_at`); `web_live.py:235-260`; `center.html:2039-2049` (post a `{"type":"metric"}` back); `meeting.py:2185`, `speech.py:257` | Today only brain time and one partial gate-to-audio number exist; nothing on the web. Without this no model/provider swap can be judged | M | Low |
| 2 | Web: stop streaming silence; add client VAD/energy gate and `audio_stream_end`, send 100 ms batches instead of 40 ms frames; stop sending while muted | `center.html:1952-1967`, `2109`; `web_live.py:210-223` (mirror `_sender` idle logic from `live_voice.py:1572-1594`) | Cuts Live input-token cost up to ~100% during idle and mute, 2.5× fewer WS/API sends; pure saving with no UX change | S | Low |
| 3 | Web: session resumption + reconnect loop (reuse `LiveVoice.run` pattern) and a keep-alive ping; keep the mic queue across reconnects | `web_live.py:160-175` (add `session_resumption`), `193-208` (loop with `BACKOFF_S`, `go_away` → reconnect), `center.py:4476-4496` | Today every `go_away` or hiccup drops the call with a toast; the Discord path already solved this (`live_voice.py:1272-1311`) | M | Medium |
| 4 | Run `ask_dory` off the receiver loop on the web path (background task + `send_tool_response` later), so barge-in / interrupted / transcripts keep flowing during a 90 s brain call; optionally cancel the job on interruption | `web_live.py:239-240`, `262-280` (copy `_on_tool_call` shape from `live_voice.py:2109-2125`) | Awaited inline today: the user cannot interrupt while Dory "thinks" | S | Low |
| 5 | Replace pure-Python resampling/mixing with `audioop.ratecv` (audioop-lts already in the lock) or ffmpeg/numpy: proper anti-aliased 48k→16k, interpolated 24k→48k, vectorised sum | `live_voice.py:435-457`, `474-490`; browser `center.html:1955-1965` (use `AudioContext({sampleRate:16000})` or a windowed-sinc) | Box-filter decimation and linear interpolation alias high frequencies (hurts Thai sibilants/tone cues for the ASR) and burn event-loop CPU per 20 ms frame per speaker | S | Low |
| 6 | Make the Live audio path interruptible server-side when it is cheap: send `activity_end`/stop or `send_client_content` cancel on code-side barge-in so the model stops generating the muted turn | `live_voice.py:2650-2657` (`_stop_requested`), `126-130` | With `NO_INTERRUPTION` the server keeps generating audio that is thrown away (cost + the next turn is delayed by the muted one) | S | Medium (API semantics, verify in docs) |
| 7 | Decouple ASR from the Live session: in live mode skip the per-segment Gemini transcription when the Live input transcript is good enough, or gate it to name-backup + minutes only (e.g. every N s or on `recording` only) | `meeting.py:2181-2187`, `838-842`, `2040-2058` | Two ASR passes run on all room audio today (Live transcription + one `generate_content` per segment with an ffmpeg fork); the second is the main per-minute cost after Live itself | M | Medium (name backup, captions and minutes depend on segment text) |
| 8 | Voice session telemetry in the workflow monitor: register a `meeting`/`voice` source (session start/end, mode live/classic, reconnects, fallbacks, jobs, dropped segments) | `monitor_sources.py` (register), `monitor.py:55` (kind exists), `meeting.py:1444-1557`, `2986-3024`, `live_voice.py:1272-1311` | Voice is the most fragile path and the only one invisible to `/center` monitor | M | Low |
| 9 | Bound the executor: a dedicated `ThreadPoolExecutor` for ASR/TTS/`qa.ask` from voice (and `to_flac` without the WAV round-trip, feed raw s16le to ffmpeg) | `meeting.py:2185`, `570-578`, `596-600`, `2866`, `live_voice.py:2442` | Voice work shares the default pool with every other `to_thread`; a slow web/chat tool can starve transcription workers (seen as a 3 min stall, `llm.py:19-21`) | S | Low |
| 10 | Pin and surface model/region facts: log `live_model`, `live_location`, `transcribe_location`, Live connect time and handle presence at session start; add a `--voice` smoke to the probe scripts that measures one Live round-trip and one ASR segment against the configured endpoints | `live_voice.py:1282-1284`, `web_live.py:195-196`, `scripts/dory_nemotron_probe.py`, `scripts/dory_tool_calls_probe.py` | Prerequisite for any provider comparison (Nebius speech, Nemotron ASR/TTS NIMs, etc.); today no script exercises speech at all | S | Low |

Not listed on purpose (bigger than one item): replacing Gemini Live with an ASR→LLM→TTS cascade on Token Factory. The hooks for it already exist — `voice_mode="classic"` is that cascade on Google services (`meeting.py:2181-2328`, `2693-2927`) — but the classic path is documented at ~11 s per answer (`config.py:90`) and has no streaming anywhere (whole-segment ASR, whole-answer TTS). A cascade that competes with Live needs streaming ASR, sentence-level TTS and a brain that answers in < 1 s on Nemotron; measure (#1, #10) before deciding.

---

## 7. Open questions (not answerable from code)

1. Real measured numbers: the "~1.5 s" (live) and "~11 s" (classic) figures are comments (`config.py:88-90`); no log corpus or eval report is in the repo. What do `live: user audio ended -> first audio` lines show in production, and how often does the classic fallback (`live: no audio from the model`) fire?
2. Does `gemini-live-2.5-flash-native-audio` at `us-central1` still exist / is it the intended model (CLAUDE.md names `gemini-3.5-flash` elsewhere; the Live model id was not verified)? Is `silence_duration_ms` really capped at 2000 (`web_live.py:38` comment)?
3. Token Factory catalogue: does Nebius serve any ASR / TTS / speech-to-speech model (Nemotron speech family, Parakeet, Canary, Magpie TTS) and with what latency from asia-southeast1? Nothing in the repo probes this.
4. How much of the Live cost is the second ASR pass (per-segment `generate_content`)? Needs billing export or request counts per meeting minute.
5. Thai quality: how does the Live model's input transcription compare with the per-segment `gemini-3.5-flash` JSON transcription on real meeting audio (the `live_eval` harness exists but its ledger path is a Linux dev box, `voice_harness.py:27`)?
6. Behaviour of `NO_INTERRUPTION` + code-side stop: does the server bill and keep generating the muted turn to its end, and does the next user turn wait behind it (see improvement #6)?
7. Discord helper bodies in production: how many `DORY_VOICE_TOKENS` are configured on `dory-bot`, and has preemption (`pick_victim`) ever triggered?
8. Web concurrency: `_live_open` is in-process; is `max-instances=1` guaranteed to stay (it also protects the finalize lock), or will a second instance allow two calls per person?
9. The browser `AudioContext` default sample rate (44.1 / 48 kHz) vs the worklet's linear resample: is there measurable ASR degradation on Thai, and does Chrome's AEC fully suppress Dory's own 24 kHz output from the mic (no server-side echo guard on the web path)?
10. Is there any production incident data on `dave_dropped` (DAVE decrypt failures, `meeting.py:694-698`) or Opus decode failures that would argue for keeping the custom sink versus upgrading `discord-ext-voice-recv`?
