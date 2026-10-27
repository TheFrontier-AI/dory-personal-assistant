# Voice-to-voice assistants: managed real-time APIs and the industry frontier

Research brief for Dory (Thai + English Discord bot and web assistant). Verified on **2026-10-25**.
Every fact is labelled **Confirmed** (official page, URL, date seen), **Secondary** (non-official page,
URL, date seen), **Assumption** (our estimate from confirmed inputs) or **Hypothesis** (untested).
No price, model id or version in this file comes from memory; each one was read on the cited page today.

Context recap: Dory already uses the Gemini Live API (`live_model`, Vertex location `us-central1`,
voice `live_voice`) with one tool `ask_dory` that hands each turn to a text brain, and Google Cloud TTS
Chirp 3 HD voices for classic TTS. Thai is a hard requirement.

---

## Summary

1. **Gemini Live's current production model is `gemini-3.8-live` (GA, audio-to-audio, native audio).** The
   half-cascade line is gone: the Developer API models page, the Live guide and every Vertex Live page fetched
   today contain zero mentions of "half-cascade". Companions: `gemini-3.8-live-extended-thinking` (configurable
   background reasoning), legacy `gemini-3.1-flash-live-preview`, and on Vertex the GA baseline
   `gemini-live-2.5-flash-native-audio` (retires 2026-12-13). Confirmed [S1][S2][S12][S14].
2. **Thai is supported end to end on Gemini Live** (listed among 99 languages on the Developer API and as `th-TH`
   on Vertex); native-audio models auto-detect and switch language, and do not accept an explicit output
   language code. Confirmed [S2][S13].
3. **Gemini Live list price is the lowest of the frontier end-to-end APIs**: $3.00/1M audio-in and $12.00/1M
   audio-out tokens at 25 tokens/s = $0.0045/min in, $0.018/min out (Google rounds to $0.005 and $0.018). A
   50/50 minute costs about **$0.011**, or **$0.0135** when you count that the mic is always on (proactive
   audio bills input while listening). Vertex bills the whole session context again every turn, so long
   sessions cost more than this floor. Confirmed prices [S5][S15]; estimates are Assumptions (arithmetic below).
4. **OpenAI now has two lines**: the Realtime API (`gpt-realtime-2.1`, audio $32/$64 per 1M, mini $10/$20) and
   **GPT-Live (`gpt-live-1`, $0.05/min flat, full duplex, delegates reasoning to a backend)**. GPT-Live is the
   same architecture Dory already runs on Gemini (voice layer + `ask_dory` brain). Thai is on the gpt-realtime
   language list published by Microsoft. Confirmed [S20][S21][S22][S27].
5. **Measured time-to-first-audio for frontier speech-to-speech models is 0.6-1.4 s, not the "sub-second" of
   the marketing pages.** Artificial Analysis (seen today): Gemini 3.8 Live 1.18 s, Gemini 3.8 Live Extended
   Thinking 1.35 s, GPT-Realtime-2.1 (minimal) 0.97 s, GPT-Live-1 1.24-1.34 s, Nova 2 Sonic 1.14 s, Grok Voice 3.0
   0.81 s, ElevenLabs Realtime v1 Max 0.57 s. Secondary [S40].
6. **Barge-in is standard everywhere; what differs is turn-end detection.** Gemini: server VAD with
   start/end sensitivity, `prefix_padding_ms`, `silence_duration_ms` (server default about 800 ms, Google recommends
   500-800 ms) and an `interrupted` flag; 3.8 Live adds a "polite interruption downgrade". OpenAI: `server_vad`
   or `semantic_vad` with `eagerness`. Component stacks use Deepgram Flux (about 260 ms end-of-turn p50),
   LiveKit Turn Detector v1 (14 languages) or Pipecat Smart Turn v3.2 (23 languages). Confirmed [S2][S14][S23][S51][S52][S54].
7. **No published semantic turn detector covers Thai.** LiveKit (14 languages), Pipecat Smart Turn v3.2
   (23 languages), Deepgram Flux Multilingual (10 languages) and Krisp Turn Prediction v3 (listed languages)
   all omit Thai; LiveKit's own advice for uncovered languages is "VAD only". The only Thai work found is an
   academic text-only EOT paper (arXiv 2510.04016). For Thai, the practical options are Gemini/OpenAI
   server-side VAD or silence VAD (Silero). Confirmed [S51][S52][S54][S56][S58].
8. **Thai TTS choices**: Gemini 3.8 Flash TTS (Thai yes; Flash-Lite TTS Thai no), Google Chirp 3 HD (`th-TH`,
   $30/1M characters, streaming, `asia-southeast1` GA), Azure Neural/HD (`th-TH-Premwadee/Niwat/Achara`, Krit,
   Nattapong), ElevenLabs v3/v4 (Thai yes; Flash v2.5 Thai **no**), Cartesia Sonic 3.6 (Thai yes). Deepgram
   Aura-2 and Amazon Nova Sonic have no Thai. Confirmed [S6][S31][S32][S36][S38][S45][S46].
9. **Thai streaming STT choices**: Deepgram Nova-3 (`th`), ElevenLabs Scribe v2 Realtime (Thai in the
   "Good" 10-20% WER band), Speechmatics (`th`), Google Chirp 3 (`th-TH` Preview, `us`/`eu` only; `asia-southeast1`
   only has `chirp`/`chirp_2`), AssemblyAI Universal-2 (Thai "Good" band; streaming coverage unconfirmed), and
   open-weights Typhoon ASR Real-Time (SCB10X, FastConformer, CER 0.098). Confirmed [S33][S36][S42][S44][S47][S60].
10. **Managed vs self-hosted**: a managed end-to-end session costs $0.011-0.06 per conversation minute at list;
    a self-hosted cascade needs a GPU (Nebius H100 listed from $0.79 to $4.50 per GPU-hour today) and there is
    no open Thai speech-to-speech model with tool calling (Typhoon2-Audio is Thai+English, speech out, Llama 3.1
    licence, self-host only). Self-hosting only wins at sustained high concurrency or for data residency.
    Confirmed inputs [S61][S62]; the conclusion is an Assumption.

---

## 1. Provider comparison (end-to-end and component)

Price column = estimate for ONE minute of conversation at a 50/50 talk ratio (0.5 min user speech, 0.5 min
bot speech). "Always-on" adds the other half minute of input audio because the mic stream is billed while the
model listens. Arithmetic in section 1.1. All list prices read today.

| Provider / product | Type | Thai in / out | Barge-in / VAD | Published latency | $/min (50/50) | Regions / residency | Source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Google Gemini Live `gemini-3.8-live`** | End-to-end (native audio), WebSocket | **Yes / Yes** (99 langs; `th-TH` on Vertex; auto-detect, no explicit code) | Server VAD: start/end sensitivity, `prefix_padding_ms`, `silence_duration_ms` (default ~800 ms); `interrupted` flag; manual `activity_start/end`; 3.8 "polite interruption downgrade"; proactive audio always on | Google: "sub-second" (marketing). AA TTFA **1.18 s** (3.8 Live), 1.35 s (Extended Thinking), 0.96 s (3.1 Flash Live minimal), 0.63 s (2.5 native audio) | **$0.011** (always-on **$0.0135**) + per-turn context re-billing | Dev API: Google-hosted. Vertex: `global`, `eu` multi-region, US, Europe, Asia Pacific and Middle East tables list it; "Non-global" price = global price | Confirmed [S1][S2][S5][S12][S14][S15]; latency Secondary [S40] |
| Google Gemini Live `gemini-live-2.5-flash-native-audio` (Vertex GA baseline) | End-to-end | Yes / Yes | Same VAD; immediate interruption; affective dialog & proactive audio need explicit config | AA TTFA 0.63 s (2.5 native audio dialog) | $0.011 (same $3/$12 audio) | Vertex US regions listed; retirement **2026-12-13** | Confirmed [S12][S15]; Secondary [S40] |
| **OpenAI GPT-Live `gpt-live-1`** | End-to-end voice layer + delegated backend (Responses or your own agent); WebRTC/WebSocket/SIP | Not listed on the model card; Thai on the gpt-realtime list (Microsoft) -> Hypothesis for gpt-live-1 | Full duplex (listens while speaking); interruption handling built in | AA TTFA **1.24 s** (Sol, low) / 1.34 s (Astra, medium) | **$0.05 flat** + backend tokens (+15 s billed at WebRTC session create, credited back) | OpenAI-hosted; data-residency endpoints +10% for models released after 2026-03-05 | Confirmed [S20][S21][S22][S27]; Secondary [S40] |
| **OpenAI Realtime `gpt-realtime-2.1`** | End-to-end (speech, reasoning, tools in one model), WebRTC/WebSocket/SIP | **Yes / Yes** (Microsoft list for gpt-realtime; OpenAI publishes no list) | `server_vad` (threshold, `prefix_padding_ms`, `silence_duration_ms`, `interrupt_response`) or `semantic_vad` (`eagerness` low/medium/high/auto) | AA TTFA 0.97 s (minimal) / 1.21 s (high); 2.0 high 1.14 s; 1.5 0.81 s | **$0.048** (always-on $0.058) at Azure's ~10/~20 tokens per s | OpenAI; Azure Voice Live offers `-datazone` / `-regional` variants | Confirmed [S20][S21][S23][S24][S27][S28]; Secondary [S40] |
| OpenAI Realtime `gpt-realtime-2.1-mini` | End-to-end | Yes / Yes (same list) | same | AA TTFA 0.81-0.85 s (mini variants) | **$0.015** (always-on $0.018) | same | Confirmed [S20]; Secondary [S40] |
| **Amazon Nova 2 Sonic** (`amazon.nova-2-sonic-v1:0`) | End-to-end, Bedrock bidirectional stream | **No / No** (en US/UK/IN/AU, fr, it, de, es, pt, hi) | Intelligent turn-taking, graceful interruptions, async tools; 8-min connection with renewal; quota 20 concurrent sessions/account/region (not adjustable) | AA TTFA **1.14 s** | ~**$0.011** from AA's $0.27/h in, $1.08/h out (Secondary); list "$3/$12 per 1M speech tokens" is Secondary only | Bedrock in-region, geo and global inference options | Confirmed langs/limits [S29][S30]; price Secondary [S40][S41] |
| **Azure Voice Live** (gpt-realtime-2.1 / mini / 1.5, gpt-4o+Azure STT/TTS, phi4-mm-realtime) | End-to-end managed (BYO LLM choice) + Azure STT/TTS/avatar | STT: multilingual auto model has **no Thai**; single-language config supports all Azure STT languages (Thai is one). gpt-realtime list includes Thai. Azure TTS has th-TH voices | "Robust interruption detection"; semantic end-of-utterance via Azure speech | None published on the overview | Token-billed in Pro/Standard/Lite tiers; page shows "$-" today (JS), so **not retrievable** | `-datazone` and `-regional` processing variants | Confirmed [S27][S28][S31]; price Open |
| **ElevenLabs Realtime v1 (Mini / Max)** | End-to-end speech-to-speech, "OpenAI Realtime-compatible" | 90+ languages listed for the family (Thai is in the v4 90+ list) -> Yes / Yes (Assumption that Realtime v1 inherits) | Proprietary turn-taking model; interruptions configurable | Vendor: TTFA **620 ms** (Mini) / **570 ms** (Max); AA 0.57 s (Max) | **$0.08 + LLM usage** | ElevenLabs-hosted | Confirmed [S34][S35]; Secondary [S40] |
| ElevenLabs Agents / Speech Engine | Cascade (Scribe STT + your LLM + Eleven TTS) managed | Scribe v2 Realtime Thai (Good band); TTS Thai via v3/v4 (not Flash v2.5) | Proprietary turn-taking; "take turn after silence", soft timeout, turn eagerness | Flash ~75 ms / v4 turbo ~100 ms / v3 conversational ~280 ms model inference (excl. network) | **$0.08** per call minute (burst $0.16) + LLM | ElevenLabs-hosted | Confirmed [S34][S35][S36][S37] |
| **Deepgram Voice Agent API** | Cascade managed (Nova-3/Flux + LLM + Aura) | STT Thai yes (Nova-3); **TTS Thai no** (Aura-2: en, es, de, fr, nl, it, ja) | Flux model-native end-of-turn (~260 ms p50) | Flux EOT ~260 ms; TTS Aura-2 P50 TTFA 329 ms (Coval, Secondary) | **$0.075** standard; $0.065 BYO LLM; $0.050 BYO LLM + TTS | Deepgram-hosted | Confirmed [S42][S43][S44][S45] |
| **AssemblyAI Voice Agent API** | Cascade managed | Universal-2 Thai (Good band); streaming Thai unconfirmed | Universal-Streaming turn events (`end_of_turn`, confidence) | not published | **$4.50/h = $0.075/min**; streaming STT alone $0.15-0.45/h | US and **EU endpoints, same price** | Confirmed [S46][S47] |
| **Cartesia Managed Agents** | Cascade managed | TTS Sonic 3.6: **Thai `th`** among 44 languages | Cartesia Ink STT turn handling (not verified) | Coval TTFA 440 ms for Sonic 3.6 (Secondary) | **$0.06/min** (+$0.014 with a Cartesia phone number) | Cartesia-hosted | Confirmed [S38][S39]; latency Secondary [S57] |
| **Google component stack**: Chirp 3 STT + Gemini 3.8 Flash + Chirp 3 HD TTS | Cascade (self-orchestrated) | STT `th-TH` **Preview, `us`/`eu` only** (not `asia-southeast1`, which has `chirp`/`chirp_2`); TTS `th-TH` GA incl. `asia-southeast1` | Your own VAD (Silero) or STT endpointing | Not published; Hypothesis 0.8-1.5 s to first audio with streaming everywhere | **~$0.030** (STT $0.008 + LLM ~$0.010 + TTS $0.012) | Chirp 3 HD: `global`, `us`, `eu`, `asia-southeast1`, `europe-west2`, `asia-northeast1` GA | Confirmed prices/regions [S31][S32][S33]; estimate Assumption |
| Google component stack with **Gemini 3.8 Flash TTS** | Cascade | TTS Thai yes (Flash); Flash-Lite **no** | same | not published | **~$0.025** ($9/1M audio tokens -> $0.0135 per spoken minute until 2026-12-31, $0.027 from 2027-01-01) | Dev API / Vertex | Confirmed [S5][S6] |
| **Kyutai Unmute** | Cascade, open weights (Kyutai STT en/fr 1B with semantic VAD + any LLM + Kyutai TTS) | **No Thai** (en, fr) | Semantic VAD in the STT | "response latency below a second" (vendor) | Self-host; commercial spinoff Gradium sells en/fr/es/pt/de APIs (Secondary) | Self-host | Confirmed [S48][S49]; Secondary [S41] |
| **Sesame CSM** | Research model, open weights CSM-1B (Mar 2025) | English-dominant data; no Thai | n/a (TTS-style generation) | n/a | No hosted API found | n/a | Confirmed [S50] |
| **Hume EVI 3 / EVI 4-mini** | End-to-end | EVI 3: English, Spanish. EVI 4-mini: 11 languages, **no Thai** | built-in | n/a | **Sunset: TTS and EVI APIs end 2026-11-13** | n/a | Confirmed [S58][S59] |

### 1.1 Price arithmetic (Assumptions built on confirmed list prices)

Definitions: one "conversation minute" = 0.5 min user speech + 0.5 min bot speech. "Always-on" = the input
stream is billed for the full minute (Gemini proactive audio: "input tokens are charged while LiveAPI is
listening" [S15]).

- **Gemini 3.8 Live** (25 audio tokens/s [S5][S15]; $3.00 in, $12.00 out per 1M):
  in = 25 x 60 x 0.5 x 3 / 1e6 = **$0.00225**; out = 25 x 60 x 0.5 x 12 / 1e6 = **$0.009**; total **$0.01125**.
  Always-on: 0.0045 + 0.009 = **$0.0135**. Not included: text tokens for the system prompt and `ask_dory` tool
  traffic ($0.75/$4.50 per 1M text), and Vertex's per-turn re-billing of the whole session context ("tokens from
  past turns are re-processed and billed in every new turn" [S15]) -> cost grows with session length unless
  context-window compression trims it; the multiplier is a Hypothesis (expect 1.5-3x over a 15-minute session).
- **OpenAI gpt-realtime-2.1** ($32 in, $64 out per 1M audio tokens [S20]; ~10 tokens/s in and ~20 tokens/s out
  per Microsoft's Voice Live estimate for Azure OpenAI models [S28]; Assumption that OpenAI direct is the same):
  in = 600 x 0.5 x 32 / 1e6 = **$0.0096**; out = 1200 x 0.5 x 64 / 1e6 = **$0.0384**; total **$0.048**.
  Always-on **$0.058**. Cached audio input is $0.40/1M, so prompt/context replay is cheap, but a long session still
  re-reads context each turn.
- **OpenAI gpt-realtime-2.1-mini** ($10 / $20): **$0.015** (always-on $0.018).
- **OpenAI gpt-live-1**: **$0.05/min** flat (per second, no rounding) + backend model tokens [S21][S22].
- **Nova 2 Sonic**: AA lists $0.27/h input audio and $1.08/h output audio [S40] -> 0.5 x 0.27/60 + 0.5 x 1.08/60 =
  **$0.011**. Secondary only; the Bedrock pricing page renders prices with JavaScript and could not be read.
- **Google cascade** (Assumptions marked): Chirp 3 STT at the Standard V2 tier $0.016/min for 0.5 min = $0.008
  (the pricing footnote lists `chirp`; `chirp_3`'s tier is an Assumption) [S33]; Gemini 3.8 Flash text at the
  introductory $0.75 / $3.75 per 1M [S15] with an assumed 9,000 input + 900 output tokens per minute (6 turns,
  1,500-token prompt each) = $0.0101; Chirp 3 HD at $30/1M characters [S32] with an assumed **800 Thai characters
  per spoken minute** (Thai has no spaces; roughly 4-5 syllables/s at ~3 characters per syllable) x 0.5 min =
  $0.012. Total **~$0.030**; with Gemini 3.8 Flash TTS instead ($0.0135 per spoken minute) **~$0.025**.
- **ElevenLabs** Realtime v1 or Agents: $0.08/min + LLM [S34][S35]. **Deepgram** Voice Agent $0.075 [S43].
  **AssemblyAI** Voice Agent $0.075 [S47]. **Cartesia** $0.06 [S39].

---

## 2. Gemini Live API in detail (what Dory runs on)

| Item | Finding | Label / source |
| --- | --- | --- |
| Model ids (Developer API, models page updated 2026-10-22) | `gemini-3.8-live` (stable, "default Live API model for most low-latency voice agent experiences without reasoning delays"), `gemini-3.8-live-extended-thinking`, `gemini-3.1-flash-live-preview` (legacy), `gemini-2.5-flash-native-audio-preview-12-2025` (2.5 models limited to existing users), `gemini-3.5-transcribe-live`, `gemini-3.5-live-translate-preview`. TTS: `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`, `gemini-3.1-flash-tts-preview` (legacy), `gemini-2.5-flash-preview-tts`, `gemini-2.5-pro-preview-tts`. | Confirmed [S1] 2026-10-25 |
| Model ids (Vertex, pages updated 2026-10-22) | `gemini-3.8-live` (GA), `gemini-live-2.5-flash-native-audio` (GA; retirement 2026-12-13), `gemini-3.5-transcribe-live-preview` (STT only). | Confirmed [S12][S14] |
| Native audio vs half-cascade | Only native audio-to-audio models are documented; "half-cascade" appears on none of the fetched Google pages. The 3.8 model card says audio is the only response modality (use output transcription for text). | Confirmed by absence [S1][S2][S12]; [S3] |
| Thinking variants | `gemini-3.8-live`: interleaved reasoning, `thinking_level` NOT supported (omit it). `gemini-3.8-live-extended-thinking`: `thinking_level` low/medium/high (no minimal); `turnComplete` does not mean idle, read `interaction_status`. 3.1 Flash Live: `thinking_level` minimal..high, default minimal. | Confirmed [S2][S3] |
| Languages | Live guide: "Live API supports the following 99 languages", **Thai listed**; native audio models switch languages during the conversation and "don't support explicitly setting the language code". Vertex language page lists **Thai (Thailand) `th-TH`**. The Live overview page still says "70 supported languages" (older text). | Confirmed [S2][S13][S4] |
| Server VAD and barge-in | `realtime_input_config.automatic_activity_detection`: `disabled`, `start_of_speech_sensitivity` (HIGH/LOW), `end_of_speech_sensitivity` (HIGH/LOW), `prefix_padding_ms`, `silence_duration_ms`. Server default silence about **800 ms**; Google recommends **500-800 ms**; 100-200 ms fragments utterances. A VAD-detected interruption cancels generation, drops unsent audio and sends `server_content.interrupted = true`. VAD off -> client sends `activity_start` / `activity_end`. `activity_handling`: `START_OF_ACTIVITY_INTERRUPTS` (default) or `NO_INTERRUPTION`; `turn_coverage` default on 3.8 is `TURN_INCLUDES_AUDIO_ACTIVITY_AND_ALL_VIDEO`. | Confirmed [S2][S3]; `activity_handling` enums from the local skill reference `client_server_messages.md` (copy of the Vertex reference, not re-verified on the live page today) |
| 3.8 Live barge-in behaviour | Vertex: "Polite interruption downgrade (waits when user speaks)" vs 2.5's "Immediate interruption (can overlap user audio)"; a tool response scheduled `INTERRUPT` while the user speaks is downgraded to `WHEN_IDLE`; blocking tool calls are auto-cancelled when new user input arrives. | Confirmed [S14] |
| Session limits | Without compression: audio-only session **15 min**, audio+video **2 min**. Context-window compression (`sliding_window`, `trigger_tokens`) -> "unlimited". Connection lifetime about **10 min**, `GoAway` with `time_left` before it ends. Session resumption handles valid **2 h** after termination. Ephemeral tokens for client-side connections. | Confirmed [S7][S4] |
| Audio formats | Input raw 16-bit PCM, **16 kHz**, little-endian (`audio/pcm;rate=16000`; server resamples other rates when the mime type says so). Output **24 kHz** 16-bit PCM. Vertex: input 16 kHz PCM, video 1 FPS JPEG; output 24 kHz PCM (+ 24 FPS avatar video on 3.8). Send 20-40 ms chunks. | Confirmed [S2][S14][S16] |
| Tool calling during live | Function calling supported; on 3.8 async `behavior: NON_BLOCKING` is the **default**, `BLOCKING` for compatibility, scheduling `SILENT` / `WHEN_IDLE` / `INTERRUPTED`; `tool_call_cancellation` on user interruption; Google Search grounding supported (5,000 free requests/month then $14 per 1,000); code execution not supported on 3.8 Live; no automatic tool-response handling in the SDK. Extended Thinking: NON_BLOCKING only. | Confirmed [S3][S8][S2] |
| Affective dialog / proactive audio | **Conflict.** Developer API 3.8 model card (updated 2026-10-19): "Proactive audio is now permanently enabled. Setting `proactive_audio: false` returns an error" and "Affective dialogue is removed from the API. Remove any `enable_affective_dialog` configurations". Vertex 3.8 guide (updated 2026-10-22): affective dialogue and proactive audio "Enabled by default" and "Don't pass `enable_affective_dialog`". Both agree the flags must go; they disagree on whether affect is still modelled. Older models: `enable_affective_dialog=True` and `proactivity={'proactive_audio': True}` on `v1beta`. | Confirmed [S3][S14][S2] |
| Regions | Developer API: Google-hosted, no region choice. Vertex: `gemini-3.8-live` appears in the Global, Multi-region (`eu`), United States, Europe, Asia Pacific and Middle East tables of the locations page (per-region check marks are not extractable from the page text; verify in the console). Vertex 3.8 sample uses `us-central1`; the 2.5 native-audio page lists US regions only. Live API pricing is the same "Non-global" rate. Dory uses `us-central1`; `global` is listed for 3.8 Live. | Confirmed [S17][S14][S12]; Dory note = Assumption |
| Pricing (Developer API, 2026-10-22) | 3.8 Live / Extended Thinking / 3.1 Flash Live: input $0.75 text, **$3.00 audio ($0.005/min)**, $1.00 image/video ($0.002/min); output $4.50 text, **$12.00 audio ($0.018/min)**, thinking tokens included. 2.5 Flash native audio preview: $0.50 text / $3.00 audio in, $2.00 text / $12.00 audio out. Live Transcribe (`gemini-3.5-transcribe-live`): $3.50/1M audio in ($0.005/min), $21/1M text out, blended about $0.009/min. | Confirmed [S5] |
| Pricing (Vertex, 2026-10-22) | Gemini 3.8 Live API, Non-global: text in $0.75, image/video in $1.00, **audio in $3.00**, text out (response + reasoning) $4.50, **audio out $12.00**, avatar video out $1.00 per 1M; audio 25 tokens/s, image 258 tokens; transcription billed at text-output rate; **context re-billed every turn**; proactive audio bills input while listening. | Confirmed [S15] |
| Gemini TTS models | `gemini-3.8-flash-tts`: 130+ languages, **Thai yes**; `gemini-3.8-flash-lite-tts`: 100+ languages, **Thai no** ("—" in the table). Served through the Interactions API; streaming returns raw 16-bit PCM 24 kHz mono; 30 featured voices + an Extended Voice Library with `language_code` filters; up to 2 speakers. Price (through 2026-12-31): Flash TTS $0.50/1M text in, **$9.00/1M audio out = $0.00225 per 10 s = $0.0135/min**; from 2027-01-01 $18.00 ($0.027/min). Flash-Lite TTS $6.00 -> $12.00. 3.1 Flash TTS preview $20.00/1M audio out. | Confirmed [S6][S5] |
| Best-practice latency knobs | Send 20-40 ms audio chunks; custom vocabulary up to 1,000 terms in `AudioTranscriptionConfig`; single function calls perform best. | Confirmed [S16] |

**Dory-specific reading (Assumption):** the current design (Gemini Live voice layer + `ask_dory` text brain) is
exactly the pattern OpenAI formalised as GPT-Live "delegation"; moving `ask_dory` to `behavior: NON_BLOCKING`
on `gemini-3.8-live` lets Dory keep talking while the brain works, and the 3.8 "polite interruption" means a tool
result that lands while the user speaks is held until they stop.

---

## 3. OpenAI: Realtime API and GPT-Live

| Item | Finding | Label / source |
| --- | --- | --- |
| Model ids | Realtime: `gpt-realtime-2.1`, `gpt-realtime-2.1-mini`, `gpt-realtime-2`, `gpt-realtime-1.5`, `gpt-realtime` (snapshot `gpt-realtime-2025-08-28`, deprecated), `gpt-realtime-mini` (snapshot `2025-12-15` deprecated; `2025-10-06` shut down). GPT-Live: **`gpt-live-1`** (knowledge cutoff 2025-07-31; audio+text in/out, no image/video; endpoint `v1/live/sessions` only). Transcription: `gpt-live-transcribe`, `gpt-realtime-whisper`, `gpt-realtime-translate`, `gpt-transcribe`. | Confirmed [S20][S21][S24][S25] 2026-10-25 |
| Architecture | Realtime = one model for speech, reasoning and tools. GPT-Live = full duplex ("listen and speak at the same time") voice model that **delegates** reasoning and tools to a backend: *Responses delegation* (OpenAI-hosted Responses model) or *client delegation* (your own agent). Backend work continues through interruptions. | Confirmed [S22][S26] |
| Transports | WebRTC (recommended for browser, mobile and server), WebSocket, SIP. Direct SIP: TLS signalling, SRTP media; raw G.711 u-law/A-law 8 kHz over WebSocket; outbound SIP: ringing limited to 3 min, connected call to **2 h**. Audio examples use PCM16 **24 kHz** mono. WebRTC via Cloudflare WARP offered to cut connection latency. | Confirmed [S23][S24][S25][S26] |
| VAD modes | `server_vad` (default; `threshold` 0-1, `prefix_padding_ms`, `silence_duration_ms`, `create_response`, `interrupt_response`; docs example 0.5 / 300 ms / 500 ms) and `semantic_vad` (model judges completion; `eagerness` low / medium / high / auto where auto = medium). | Confirmed [S23] |
| Thai | OpenAI publishes no Realtime language list on the fetched pages. Microsoft's Voice Live page: "the underlying model was trained on 98 languages, OpenAI only lists the languages that exceeded <50% WER"; the gpt-realtime / gpt-realtime-mini list **includes Thai**. | Confirmed [S27] (Microsoft Learn) |
| Context | gpt-realtime / mini: 32,000-token context, 4,096 max output. | Confirmed [S24][S25] |
| Pricing | Per 1M tokens: gpt-realtime-2.1 audio **$32 in / $64 out / $0.40 cached**, text $4 / $24; gpt-realtime-2.1-mini audio **$10 / $20 / $0.30**, text $0.60 / $2.40; gpt-realtime-2 and 1.5 same audio rates. **gpt-live-1 $0.05 per minute, billed per second**, backend separate; WebRTC session create bills 15 s (credited). Transcription: gpt-live-transcribe $0.017/min, gpt-realtime-translate $0.034/min, gpt-transcribe $0.0045/min. Data-residency and FedRAMP endpoints: +10% for models released on/after 2026-03-05. | Confirmed [S20][S21][S22] |
| Token rate per minute | Not stated on OpenAI pages today; Microsoft's estimate for Azure OpenAI realtime models: ~10 input and ~20 output audio tokens per second. | Confirmed [S28] (Microsoft), Assumption when applied to OpenAI direct |
| Session duration limit (Realtime) | Not found on the pages fetched today. | Open |

---

## 4. Other end-to-end and component vendors (details behind the table)

- **Amazon Nova 2 Sonic**: languages English (US, UK, India, Australia), French, Italian, German, Spanish,
  Portuguese, Hindi; "polyglot voices"; intelligent turn-taking; graceful interruptions; async tool handling;
  8-minute connection limit with renewal pattern; default quota 20 concurrent bidirectional sessions per account
  per region, not adjustable. Confirmed [S29][S30]. Nova 2.5 Sonic GA in Oct 2026 and "$3/$12 per 1M speech
  tokens" are Secondary [S41][S63].
- **Azure Voice Live**: models and tiers (Pro: gpt-realtime-2.1 family, gpt-5 etc.; Standard: 2.1-mini,
  gpt-5-mini etc.; Lite: nano, phi4-mm-realtime); token estimate ~10/~20 tokens per s (Azure OpenAI) and
  ~12.5/~20 (Phi); charged also for cached audio and text context. Multilingual STT auto model = 15 locales
  without Thai; single-language mode supports every Azure STT language; MAI Transcribe list includes Thai;
  Azure TTS Thai voices `th-TH-PremwadeeNeural`, `th-TH-NiwatNeural`, `th-TH-AcharaNeural` plus Neural HD /
  HD Flash `th-TH-Krit`, `th-TH-Nattapong`. Prices on the Azure pricing page did not render ("$-"). Confirmed
  [S27][S28][S31]; price Open.
- **ElevenLabs**: `eleven_flash_v2_5` = the 29 `eleven_multilingual_v2` languages + hu, no, vi (**no Thai**),
  ~75 ms model inference; `eleven_v3` / `eleven_v3_conversational` (~280 ms) 70+ languages and `eleven_v4` /
  `eleven_v4_turbo` (~100 ms) 90+ languages **include Thai (th)**; `scribe_v2_realtime` ~150 ms, 90+ languages,
  Thai in the "Good (>10% to <=20% WER)" band; billing on every second of audio sent including silence.
  Realtime v1 Mini/Max $0.08/min + LLM, vendor TTFA 620/570 ms; Agents $0.08 per extra minute (burst $0.16);
  conversation `max_duration_seconds` default 600 (60-7,200). Confirmed [S34][S35][S36][S37].
- **Deepgram**: Nova-3 multilingual and monolingual lists include **Thai `th`**; Flux `flux-general-en` and
  `flux-general-multi` (en, es, fr, de, hi, ru, pt, ja, it, nl; **no Thai**), ~260 ms end-of-turn p50 at defaults,
  `eot_threshold` default 0.7, `eot_timeout_ms` default 5,000, `eager_eot_threshold` for early LLM start, 80 ms
  chunks recommended; Aura-2 languages en, es, de, fr, nl, it, ja (**no Thai**), $0.030/1k characters; pay-as-you-go
  streaming Nova-3 mono $0.0048/min (promo; list $0.0077 struck through), Flux English $0.0065/min (promo),
  Voice Agent API $0.075/min standard, $0.065 BYO LLM, $0.050 BYO LLM+TTS, Advanced $0.163. Confirmed
  [S42][S43][S44][S45].
- **AssemblyAI**: Universal-2 99 languages, **Thai in "Good accuracy (>10% to <=25% WER)"**; streaming models
  `universal-3-6-pro` ($0.45/h base), `universal-streaming-multilingual` ($0.15/h), billed on WebSocket
  session time; Voice Agent API $4.50/h; EU endpoint same price; Turn events carry `end_of_turn` and
  `end_of_turn_confidence`. Whether streaming covers Thai: the multilingual-streaming page returned 404 today.
  Confirmed [S46][S47]; streaming Thai Open.
- **Cartesia**: Sonic 3.6 (`sonic-3.6-2026-08-27`), 44 languages incl. **`th`**; Managed Agents $0.06/min.
  Confirmed [S38][S39]. Coval's September 2026 read: Sonic 3.6 TTFA 440 ms (Secondary [S57]).
- **Speechmatics**: Thai `th` in the transcription language table; the Agent STT API ("Linden 1") supports the
  same languages as Realtime transcription. Vendor Thai page claims "<1 second latency" (marketing). Confirmed
  [S60]; latency Secondary.
- **Google Cloud Speech-to-Text Chirp 3** (docs updated 2026-10-22): `StreamingRecognize`, `Recognize`,
  `BatchRecognize`; regions `us` and `eu` multi-region GA; **Thai `th-TH` listed as Preview**; the big language
  table shows `th-TH` + `chirp_3` only under `us` and `eu`, while `asia-southeast1` has `chirp` and `chirp_2`.
  Streaming request limit 10 MB; the samples cap a stream at 4-5 minutes and reconnect. V2 Standard recognition
  $0.016/min (0-500k min), $0.003/min dynamic batch. Confirmed [S31][S33][S64].
- **Google Cloud Text-to-Speech Chirp 3 HD** (docs updated 2026-10-22): `th-TH` supported; 30 named voices
  (Achernar, Achird, Algenib, Algieba, Alnilam, Aoede, ... Charon ...); regions `global`, `us`, `eu`,
  `asia-southeast1`, `europe-west2`, `asia-northeast1` all GA; bidirectional streaming synthesis with PCM, A-law,
  mu-law, OGG_OPUS; **$30 per 1M characters** after the first 1M free per month. Confirmed [S31][S32].
- **Kyutai / Unmute**: cascade of `kyutai/stt-1b-en_fr` (English + French, ~1B params, 0.5 s delay, semantic
  VAD "doesn't interrupt you mid-sentence") + any LLM + Kyutai TTS; "response latency is below a second"; an
  H100 serves 400 STT streams; open weights, self-host. Confirmed [S48][S49]. Commercial spinoff Gradium sells
  STT/TTS APIs in en, fr, es, pt, de (Secondary [S41]). No Thai.
- **Sesame**: CSM-1B open weights (Mar 2025), research post only; dataset "predominantly English"; no hosted
  API found. Confirmed [S50].
- **Hume**: EVI 3 English + Spanish; EVI 4-mini English, Japanese, Korean, Spanish, French, Portuguese, Italian,
  German, Russian, Hindi, Arabic (no Thai); **TTS and EVI APIs sunset 2026-11-13**, data deleted after.
  Confirmed [S58][S59].

---

## 5. Turn detection and barge-in: state of the art

| Component | What it is | Size / cost | Languages (Thai?) | Published latency | Label / source |
| --- | --- | --- | --- | --- | --- |
| Gemini Live server VAD | Silence-based VAD with HIGH/LOW start and end sensitivity, `prefix_padding_ms`, `silence_duration_ms`; interruption cancels generation, `interrupted` flag; 3.8 Live "polite interruption downgrade" | Included | Model-side; Thai supported by the model | Server default silence ~800 ms; Google recommends 500-800 ms; AA TTFA 1.18 s (3.8 Live) | Confirmed [S2][S14]; Secondary [S40] |
| OpenAI `server_vad` / `semantic_vad` | Silence VAD (threshold, padding, silence) or a classifier scoring "probability the user is done" with `eagerness` low/medium/high/auto | Included | Model-side; Thai on the Microsoft list | Docs example `silence_duration_ms` 500, LiveKit telephony example 400 ms | Confirmed [S23][S53] |
| **Deepgram Flux** | STT with model-native end-of-turn (`StartOfTurn`, `EagerEndOfTurn`, `TurnResumed`, `EndOfTurn`), `eot_threshold` 0.7 default, `eot_timeout_ms` 5,000 default | $0.0065-0.0078/min | en + 10-language multi (**no Thai**) | **~260 ms EOT p50** at defaults; "cuts 200-600 ms vs pipeline approaches"; LiveKit eot-bench: 12.9% false-cutoff at a 300 ms budget | Confirmed [S42][S44][S55]; bench Secondary [S52] |
| **LiveKit Turn Detector v1 / v1-mini** | Audio model (semantic + acoustic branches, LLM backbone), on top of Silero VAD; v1 on LiveKit Inference (free on LiveKit Cloud), v1-mini local CPU | not disclosed | **14 languages**: en, ar, de, es, fr, hi, id, it, ja, ko, nl, pt, tr, zh (**no Thai**; "VAD only" advised for uncovered languages) | Endpointing waits 0.5-3.0 s by default; VAD `min_silence_duration` >= 250 ms; eot-bench: 9.9% false-cutoff at 300 ms budget, 4.5% at 600 ms; earlier text model v0.4.1 cut false interruptions 39% | Confirmed [S51][S52][S53] |
| **Pipecat Smart Turn v3.2** | Open (BSD-2) native-audio end-of-turn classifier: Whisper Tiny encoder + linear head, ~8M params | CPU int8 **8 MB**, GPU fp32 32 MB | **23 languages**: ar, bn, zh, da, nl, de, en, fi, fr, hi, id, it, ja, ko, mr, no, pl, pt, ru, es, tr, uk, vi (**no Thai**) | "as little as 10 ms on some CPUs, under 100 ms on most cloud instances"; ~65 ms on Pipecat Cloud 1x | Confirmed [S54] |
| **Krisp Turn Prediction v3 + Interruption Prediction v1** (VIVA SDK) | Audio-only end-of-turn probability refined during silence; interruption model separates backchannels ("uh-huh") from real interruptions; Pipecat `KrispVivaTurn` (frames 10-40 ms) | SDK licence | en, de, fr, es, hi, fi, it, pt, zh, ja, ko, ru "and additional languages" (Thai not listed) | "fast responses (under 200 ms) jumped from 47% to 69%" vs v2 | Confirmed [S56]; Pipecat integration [S65] |
| **Silero VAD** | Open (MIT) silence VAD | JIT ~2 MB | Trained on 6,000+ languages; 8 / 16 kHz | <1 ms per 30 ms chunk on one CPU thread | Confirmed [S62] |
| ElevenLabs turn-taking | Proprietary turn-taking model in Agents; "take turn after silence", soft timeout, turn eagerness, interruptions on/off | Included in $0.08/min | 90+ (Agents TTS "70+", voice page "31", inconsistent) | not published | Confirmed [S35][S37] |
| Semantic end-of-turn for Thai | arXiv 2510.04016 (IEEE ICSEC 2025): text-only Thai EOT, compact LLM prompting vs fine-tuned lightweight transformers, YODAS subtitles, sentence-final particles; "small, fine-tuned models can deliver near-instant EOT decisions" | Research | **Thai** | Accuracy-latency trade-off reported; no deployable model/API found | Confirmed abstract [S58b] |

Published end-to-end figures (Secondary unless marked): Artificial Analysis "Time to First Audio" seen today
[S40]: Eleven Realtime v1 Max 0.57 s, Grok Voice 2.0 0.70 s / 3.0 0.81 s, GPT-Realtime-1.5 0.81 s, GPT Realtime
Mini 0.81 s, Gemini 3.1 Flash Live (minimal) 0.96 s, GPT-Realtime-2.1 (minimal) 0.97 s, Nova 2 Sonic 1.14 s,
Gemini 3.8 Live 1.18 s, GPT-Realtime-2.1 (high) 1.21 s, GPT-Live-1 1.24-1.34 s, Gemini 3.8 Live Extended Thinking
1.35 s, Gemini 3.1 Flash Live (high) 2.99 s. "Conversational dynamics" (Full Duplex Bench): Gemini 3.8 Live 96.1%,
GPT-Realtime-2.1 high 95.7%, Grok 3.0 97.0%, Eleven Realtime v1 Max 94.1%. Softcery (April 2026, citing AA):
Grok 0.78 s, gpt-realtime-1.5 0.82 s, Nova 2 Sonic 1.14 s, Gemini 3.1 Flash Live 2.98 s [S41]. TTS-only TTFA
(Coval, 2026): ElevenLabs Flash v2.5 ~185-202 ms, Deepgram Aura-2 329 ms, Cartesia Sonic 3.6 440 ms [S57].

---

## 6. Thai speech: what is actually offered

| Vendor / model | STT | TTS | Speech-to-speech | Hosted? | Latency / quality claims | Label / source |
| --- | --- | --- | --- | --- | --- | --- |
| Google Gemini 3.8 Live | Thai (99-language list; `th-TH` on Vertex) | Thai (native audio output, auto language) | **Yes** | Yes (Dev API, Vertex) | AA TTFA 1.18 s; no Thai-specific quality number published | Confirmed [S2][S13]; Secondary [S40] |
| Google Gemini 3.8 Flash TTS / Flash-Lite TTS | - | Flash: **Thai yes**; Flash-Lite: **no** | - | Yes | $0.0135/min of audio (to 2026-12-31) | Confirmed [S6][S5] |
| Google Chirp 3 (STT) | `th-TH` **Preview**, `us` / `eu` multi-region only | - | - | Yes | not published | Confirmed [S33][S64] |
| Google Chirp 3 HD (TTS) | - | `th-TH` GA, incl. `asia-southeast1` | - | Yes | $30/1M chars; streaming | Confirmed [S31][S32] |
| OpenAI gpt-realtime-2.1 / mini | Thai (Microsoft list) | Thai (same model) | Yes | Yes | AA TTFA 0.97-1.21 s | Confirmed [S27]; Secondary [S40] |
| Azure Speech / Voice Live | Thai via single-language config and MAI Transcribe; not in the auto multilingual model | `th-TH` Premwadee / Niwat / Achara Neural, Krit and Nattapong Neural HD | Via gpt-realtime models | Yes | none published | Confirmed [S27][S28][S31] |
| Deepgram Nova-3 | **Thai `th`** (mono and multi) | Aura-2 **no Thai** | - | Yes | $0.0048-0.0052/min streaming | Confirmed [S42][S43][S45] |
| ElevenLabs | Scribe v2 / v2 Realtime Thai, "Good" band (10-20% WER) | v3 / v4 / v4 turbo Thai; **Flash v2.5 no Thai** | Realtime v1 "90+ languages" (Assumption: incl. Thai) | Yes | Scribe RT ~150 ms; v4 turbo ~100 ms | Confirmed [S34][S36] |
| AssemblyAI | Universal-2 Thai "Good" band (10-25% WER); streaming Thai unconfirmed | - | - | Yes | - | Confirmed [S46]; Open |
| Cartesia Sonic 3.6 | (Ink STT: not checked) | **Thai `th`** | Managed Agents | Yes | Coval TTFA 440 ms | Confirmed [S38]; Secondary [S57] |
| Speechmatics | **Thai `th`** (realtime and Agent STT) | - | - | Yes | vendor "<1 s" | Confirmed [S60] |
| Amazon Nova 2 Sonic | no | no | no Thai | Yes | - | Confirmed [S29] |
| **Typhoon (SCB10X) ASR Real-Time** | Thai streaming ASR, FastConformer-Transducer (~115M params per the paper), **open weights CC-BY-4.0**, CER 0.0984, RTFx 4097 | - | - | **Self-host** (no hosted ASR API found on opentyphoon.ai docs, which did not render) | Vendor: 720 h of audio for about $1.65 of compute | Confirmed HF card [S61]; blog claims Secondary [S66] |
| **Typhoon2-Audio** (`llama3.1-typhoon2-audio-8b-instruct`) | audio in | speech out | Thai + English audio-language model | **Self-host** (Transformers / vLLM; Llama 3.1 licence; speech output CC-BY-NC per search snippet) | none published | Confirmed card [S67]; licence detail Secondary |
| **iApp** (api.iapp.co.th) | Thai STT REST API | "Kaitom Voice" TTS v3, streamed 24 kHz; 1 IC (~1 THB) per 400 characters; vendor-claimed 91.23% STT accuracy on Common Voice 17 | - | Yes (Thai vendor) | not published | Secondary (iApp pages are JS-only today; from search snippets) [S68] |
| **Botnoi Voice** | - | AWS Marketplace listing: 200+ voices, 20+ languages incl. ASEAN, usage-based pricing | - | Yes | not published | Secondary (listing text via search; page JS-only) [S69] |
| **Vaja (NECTEC)** | - | Vaja 8.0 (2018) Thai/English commercial software (voices Nok, A; 44.1 kHz); Vaja 9 reachable through AIforThai `api.aiforthai.in.th/vaja9` per third-party code | - | AIforThai API (indirect evidence) | none | Secondary / Hypothesis [S70] |
| **Gowajee** | Thai-first STT | Thai-first TTS | Voice-agent platform (no-code flows + "enterprise API, low latency, real-time streaming ready") | Yes (enterprise, no public pricing) | none published | Confirmed site text [S71] |

---

## 7. Latency targets the industry uses

- **Human baseline about 200 ms gap; "800 ms rule".** Vendor explainer citing Stivers et al. (2009) and
  Levinson & Torreira (2015): median human turn gap ~200 ms; 0-500 ms "natural", 500-800 ms "thoughtful",
  800-1,500 ms "awkward", >1,500 ms "broken"; aim <800 ms first audio at p50 and <1,500 ms at p95; model-based
  endpointing fires in 200-400 ms vs 800 ms+ for naive silence thresholds. Secondary [S72] (the primary papers
  were not fetched).
- **Google**: Live API VAD server default ~800 ms silence, recommended 500-800 ms, warns 100-200 ms fragments
  speech; "sub-second native audio streaming" in the models table; send 20-40 ms chunks. Confirmed [S2][S1][S16].
- **OpenAI**: `server_vad` example `silence_duration_ms` 500 / `prefix_padding_ms` 300; GPT-Live is pitched on
  "low first-audio latency, natural turn taking"; the cost guide sells shorter waits as both UX and money
  ("closing saves $0.05 per minute of idle voice time"). Confirmed [S23][S22][S26].
- **LiveKit**: eot-bench evaluates at **300 ms and 600 ms latency budgets** (false-cutoff 9.9% / 4.5% for v1);
  session endpointing waits 0.5-3.0 s by default; VAD min silence >= 250 ms; telephony example 400 ms. Confirmed
  [S51][S52][S53].
- **Pipecat / Daily**: Smart Turn v3 inference 10-100 ms (about 65 ms on Pipecat Cloud) so turn detection adds
  tens of ms, not hundreds. Confirmed [S54]. Daily's "world's fastest voice bot" post did not render (SPA) -> its
  voice-to-voice number is Open.
- **Deepgram**: Flux ~260 ms end-of-turn p50; "cut agent response latency by 200-600 ms compared to pipeline
  approaches". Confirmed [S42][S55].
- **Krisp**: counts "fast responses" as **under 200 ms** end-of-turn decisions (69% with v3). Confirmed [S56].
- **ElevenLabs**: distinguishes model inference (~75 ms Flash) from TTFA; network 20-200 ms, a 500 ms player
  buffer "is common"; Realtime v1 TTFA 570-620 ms. Confirmed [S34][S37].
- **Kyutai Unmute**: "response latency is below a second" for a cascade. Confirmed [S48].
- **Benchmarks that exist**: Artificial Analysis Speech-to-Speech (TTFA on Big Bench Audio, Full Duplex
  Bench conversational dynamics, Speech Agent Arena Elo) [S40]; LiveKit eot-bench (open data) [S52]; Coval TTS
  TTFA leaderboard [S57]; Hugging Face Open ASR Leaderboard and TTS Arena V2 exist but their pages are
  JS-rendered and were not readable today; both are English-centred (Assumption) and neither covers Thai (Assumption).

**Working targets for Dory (Assumption):** p50 < 800 ms and p95 < 1,500 ms from end of user speech to first
audio; turn-end decision <= 500 ms (Gemini silence 500-600 ms is the main lever); barge-in stop-playback
< 200 ms locally (flush on `interrupted`). Today's AA measurement of 1.18 s for `gemini-3.8-live` means the
voice layer alone already spends the budget; the `ask_dory` round-trip must run NON_BLOCKING with a spoken filler.

---

## 8. Managed vs self-hosted, fairly

| | Managed end-to-end (Gemini Live, OpenAI Realtime/GPT-Live) | Managed cascade (ElevenLabs, Deepgram, AssemblyAI, Cartesia, Google components) | Self-hosted cascade (Typhoon ASR + LLM + open TTS, Kyutai, Silero/Smart Turn) |
| --- | --- | --- | --- |
| Thai today | Yes (Gemini, OpenAI) | STT yes (Deepgram, ElevenLabs, Speechmatics, Chirp 3 preview); TTS yes (Chirp 3 HD, Gemini TTS, Cartesia, ElevenLabs v3/v4) | STT yes (Typhoon ASR Real-Time); TTS: no production-grade open Thai TTS verified today (Thonburian TTS / F5-based are research, Secondary); turn detector: none |
| Barge-in / turn end | Built in (server VAD, semantic on OpenAI) | Flux / proprietary; LiveKit, Smart Turn, Krisp **not for Thai** | Silence VAD only (Silero) for Thai |
| Price per conversation minute | $0.011 (Gemini) to $0.048 (gpt-realtime-2.1); $0.05 flat GPT-Live | $0.06-0.08 (Cartesia, Deepgram, ElevenLabs) or ~$0.025-0.030 self-orchestrated on Google components | GPU time: Nebius H100 "from $0.79" up to $4.50 per GPU-hour today [S62b] (tier meaning is an Assumption). One H100 serving tens of concurrent Thai STT+TTS streams would be about $0.002-0.01 per stream-minute **only when kept busy**; idle GPUs cost the same |
| Latency | 0.6-1.4 s TTFA measured (AA) | Sum of parts: STT endpoint 250-600 ms + LLM first token + TTS TTFA 100-450 ms; typically 0.8-1.5 s (Assumption) | Same shape; you control placement (Bangkok region) so network is lowest, but model speed depends on your GPU |
| Data residency | Vertex regional (`asia-southeast1` for Chirp 3 HD; Live API region list per console); OpenAI regional +10% | AssemblyAI EU; Deepgram/ElevenLabs US-centric | Full control |
| Ops | None | Low | High: GPU capacity, model updates, no SLA |
| Verdict (Assumption) | Right for Dory now: cheapest Thai speech-to-speech with tool calling, barge-in included | Use for specific gaps (e.g. Chirp 3 HD / Gemini TTS for classic TTS, Deepgram Nova-3 for Thai captions) | Only for high sustained concurrency or strict residency; not viable for Thai speech-to-speech with tools today |

---

## 9. Open questions

1. **Affective dialog on `gemini-3.8-live`**: Developer API says removed, Vertex says enabled by default. Which
   is true on the Vertex `us-central1` endpoint Dory uses? Test: compare prosody-sensitive replies with 2.5.
2. **Vertex regions for `gemini-3.8-live`**: the locations page lists it in the Asia Pacific table but the
   per-region check marks could not be read; is `asia-southeast1` or `global` available, and does `global`
   cut Thailand round-trip vs `us-central1`? Measure TTFA from Bangkok on both.
3. **Context re-billing**: how much does a 15-minute Dory session actually cost on Vertex with compression on
   vs off? Read `usage_metadata` per turn.
4. **OpenAI Realtime session duration limit** and the official audio tokens-per-minute rate were not found on
   OpenAI's pages today; Microsoft's ~10/~20 tokens per s was used.
5. **Nova 2.5 Sonic / Azure Voice Live prices**: both pricing pages render with JavaScript; official per-token
   prices are unverified (Secondary figures only). Nova has no Thai anyway.
6. **AssemblyAI streaming Thai**: Universal-2 batch supports Thai; the streaming multilingual page 404'd.
7. **Thai turn detection**: no Thai semantic end-of-turn model is shipped by any vendor. Options: rely on Gemini
   server VAD at 500-600 ms, or fine-tune Smart Turn (open training code, "support for additional languages" is
   on its roadmap) with Thai data; the arXiv 2510.04016 approach is text-only and would sit after an STT.
8. **Chirp 3 STT Thai is Preview and only in `us`/`eu`**; for Thai captions in `asia-southeast1` the choice today
   is `chirp_2`, or Gemini Live Transcribe (`gemini-3.5-transcribe-live`, languages not checked today).
9. **ElevenLabs Realtime v1 Thai**: "90+ languages" is a family claim; Thai not verified for the Realtime
   models specifically.
10. **Typhoon hosted API**: opentyphoon.ai docs are JS-only; whether SCB10X hosts ASR/TTS/Typhoon2-Audio as a
    paid API is unknown; iApp, Botnoi and Vaja details come from search snippets, not fetched pages.
11. **Thai characters per spoken minute** (used for the Chirp 3 HD estimate, 800 chars/min) should be measured
    on Dory's own transcripts.

---

## Sources (all seen 2026-10-25; "updated" = the page's own date)

- [S1] Gemini API models page (updated 2026-10-22) https://ai.google.dev/gemini-api/docs/models
- [S2] Live API capabilities guide (updated 2026-09-18) https://ai.google.dev/gemini-api/docs/live-guide
- [S3] Gemini 3.8 Live model card (updated 2026-10-19) https://ai.google.dev/gemini-api/docs/models/gemini-3.8-live
- [S4] Live API overview (updated 2026-10-06) https://ai.google.dev/gemini-api/docs/live
- [S5] Gemini Developer API pricing (updated 2026-10-22) https://ai.google.dev/gemini-api/docs/pricing
- [S6] Gemini speech generation / TTS (updated 2026-10-12) https://ai.google.dev/gemini-api/docs/speech-generation
- [S7] Live API session management (updated 2026-09-15) https://ai.google.dev/gemini-api/docs/live-session
- [S8] Live API tool use (updated 2026-09-15) https://ai.google.dev/gemini-api/docs/live-tools
- [S12] Vertex / Gemini Enterprise Agent Platform Live API overview (updated 2026-10-22) https://docs.cloud.google.com/vertex-ai/generative-ai/docs/live-api
- [S13] Vertex Live API configure language and voice (updated 2026-10-22) https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/configure-language-voice
- [S14] Developer's guide to Gemini 3.8 Live, Vertex (updated 2026-10-22) https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-8-live ; 2.5 Flash Live model page https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash-live-api
- [S15] Vertex Agent Platform pricing https://docs.cloud.google.com/vertex-ai/generative-ai/pricing
- [S16] Vertex Live API best practices https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/best-practices
- [S17] Vertex generative AI locations https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/locations
- [S20] OpenAI API pricing https://platform.openai.com/docs/pricing
- [S21] GPT-Live 1 model card https://platform.openai.com/docs/models/gpt-live-1
- [S22] GPT-Live guide https://platform.openai.com/docs/guides/live ; cost optimization https://platform.openai.com/docs/guides/voice-latency-cost
- [S23] OpenAI Realtime VAD guide https://platform.openai.com/docs/guides/realtime-vad
- [S24] gpt-realtime model card https://platform.openai.com/docs/models/gpt-realtime
- [S25] gpt-realtime-mini model card https://platform.openai.com/docs/models/gpt-realtime-mini ; Telephony and SIP https://platform.openai.com/docs/guides/realtime-sip ; WebRTC guide https://platform.openai.com/docs/guides/realtime-webrtc ; conversations https://platform.openai.com/docs/guides/realtime-conversations
- [S26] OpenAI voice agents overview https://platform.openai.com/docs/guides/voice-agents ; Realtime getting started https://platform.openai.com/docs/guides/realtime
- [S27] Microsoft Learn, Voice Live API language support https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live-language-support
- [S28] Microsoft Learn, Voice Live API overview https://learn.microsoft.com/en-us/azure/ai-services/speech-service/voice-live
- [S29] AWS Nova 2 user guide, Speech-to-Speech https://docs.aws.amazon.com/nova/latest/nova2-userguide/using-conversational-speech.html
- [S30] Bedrock model card Nova 2 Sonic https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-sonic.md
- [S31] Azure Speech language and voice support https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support ; Google Chirp 3 HD voices (updated 2026-10-22) https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd
- [S32] Google Cloud Text-to-Speech pricing https://cloud.google.com/text-to-speech/pricing
- [S33] Google Cloud Speech-to-Text pricing https://cloud.google.com/speech-to-text/pricing ; supported languages table (updated 2026-10-22) https://docs.cloud.google.com/speech-to-text/docs/speech-to-text-supported-languages
- [S34] ElevenLabs models https://elevenlabs.io/docs/overview/models
- [S35] ElevenLabs API pricing https://elevenlabs.io/pricing/api ; Agents pricing https://elevenlabs.io/pricing/agents
- [S36] ElevenLabs speech to text https://elevenlabs.io/docs/overview/capabilities/speech-to-text
- [S37] ElevenLabs latency concepts https://elevenlabs.io/docs/eleven-api/concepts/latency ; conversation flow https://elevenlabs.io/docs/eleven-agents/customization/conversation-flow ; Agents overview https://elevenlabs.io/docs/agents-platform/overview
- [S38] Cartesia Sonic 3.6 docs https://docs.cartesia.ai/build-with-cartesia/models/tts
- [S39] Cartesia pricing https://cartesia.ai/pricing
- [S40] Artificial Analysis Speech to Speech https://artificialanalysis.ai/speech-to-speech
- [S41] Softcery, real-time vs turn-based voice agents (April 2026) https://softcery.com/lab/ai-voice-agents-real-time-vs-turn-based-tts-stt-architecture
- [S42] Deepgram models and languages https://developers.deepgram.com/docs/models-languages-overview ; Flux quickstart https://developers.deepgram.com/docs/flux/quickstart
- [S43] Deepgram pricing https://deepgram.com/pricing
- [S44] Deepgram Flux configuration https://developers.deepgram.com/docs/flux/configuration ; Nova-3 to Flux migration https://developers.deepgram.com/docs/flux/nova-3-migration
- [S45] Deepgram TTS voices and languages https://developers.deepgram.com/docs/tts-models
- [S46] AssemblyAI supported languages https://www.assemblyai.com/docs/speech-to-text/pre-recorded-audio/supported-languages ; Universal-Streaming https://www.assemblyai.com/docs/speech-to-text/universal-streaming
- [S47] AssemblyAI pricing https://www.assemblyai.com/pricing
- [S48] Kyutai Unmute https://kyutai.org/unmute
- [S49] Kyutai delayed-streams-modeling README https://github.com/kyutai-labs/delayed-streams-modeling
- [S50] Sesame, Crossing the uncanny valley of voice https://www.sesame.com/research/crossing_the_uncanny_valley_of_voice
- [S51] LiveKit turn detector docs https://docs.livekit.io/agents/logic/turns/turn-detector
- [S52] LiveKit blog, Turn Detector v1 and eot-bench https://livekit.com/blog/solving-end-of-turn-detection ; v0.4.1 blog https://livekit.com/blog/improved-end-of-turn-model-cuts-voice-ai-interruptions-39
- [S53] LiveKit turn detection overview https://docs.livekit.io/agents/logic/turns ; Silero VAD plugin https://docs.livekit.io/agents/logic/turns/vad
- [S54] Pipecat Smart Turn v3.2 README https://github.com/pipecat-ai/smart-turn ; weights https://huggingface.co/pipecat-ai/smart-turn-v3
- [S55] Deepgram, Introducing Flux https://deepgram.com/learn/introducing-flux-conversational-speech-recognition
- [S56] Krisp blog, Turn Prediction v3 and Interruption Prediction v1 (2026-05-06) https://krisp.ai/blog/voice-ai-turn-taking-interruption-prediction/
- [S57] Coval TTS latency benchmark 2026 https://www.coval.ai/blog/tts-latency-benchmark-2026/ (seen via search; vendor-adjacent)
- [S58] Hume EVI FAQ https://dev.hume.ai/docs/speech-to-speech-evi/faq ; [S59] Hume changelog (sunset notice 2026-10-02) https://dev.hume.ai/changelog
- [S58b] Thai Semantic End-of-Turn Detection for Real-Time Voice Agents, arXiv 2510.04016 https://arxiv.org/abs/2510.04016
- [S60] Speechmatics supported languages https://docs.speechmatics.com/introduction/supported-languages
- [S61] Typhoon ASR Real-Time model card https://huggingface.co/scb10x/typhoon-asr-realtime ; paper https://arxiv.org/abs/2601.13044
- [S62] Silero VAD README https://github.com/snakers4/silero-vad ; [S62b] Nebius GPU prices https://nebius.com/prices
- [S63] Nova 2.5 Sonic GA (Secondary) https://aiweekly.co/alerts/amazons-nova-25-sonic-voice-model-hits-bedrock-in-four-regions
- [S64] Google Chirp 3 transcription model (updated 2026-10-22) https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3
- [S65] Pipecat KrispVivaTurn https://docs.pipecat.ai/server/utilities/turn-detection/krisp-viva-turn
- [S66] Typhoon ASR Real-Time release blog https://opentyphoon.ai/blog/en/typhoon-asr-realtime-release
- [S67] Typhoon2-Audio model card https://huggingface.co/scb10x/llama3.1-typhoon2-audio-8b-instruct
- [S68] iApp Thai TTS docs (JS-only; snippets via search) https://iapp.co.th/docs/speech/text-to-speech ; Kaitom v3 blog https://iapp.co.th/blog/kaitom-voice-thai-text-to-speech-v3
- [S69] Botnoi Voice on AWS Marketplace (snippet) https://aws.amazon.com/marketplace/pp/prodview-36kove2muvo2g
- [S70] NECTEC Vaja 8.0 https://nectec.or.th/en/?p=17178 ; Vaja 9 endpoint seen in third-party code (Hugging Face space commit)
- [S71] Gowajee https://gowajee.ai/
- [S72] Twig, "The 800ms rule" (vendor explainer citing Stivers 2009, Levinson & Torreira 2015) https://www.twig.so/blog/voice-ai-agents-latency-budget-800ms

Local reference read first: `~/.claude/skills/gemini-live-api/SKILL.md` and `references/client_server_messages.md`
(Vertex `BidiGenerateContent` message schema: `automaticActivityDetection`, `activityHandling`, `turnCoverage`,
`contextWindowCompression`, `sessionResumption`, 16 kHz in / 24 kHz out, `interrupted`, `toolCallCancellation`).
