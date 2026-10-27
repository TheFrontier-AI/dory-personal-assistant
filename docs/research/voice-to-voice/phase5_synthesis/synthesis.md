# Phase 5 — Synthesis: real-time voice-to-voice for Dory

Date: 2026-10-25. Built from the ten evidence files of phases 0-4 (read in full), not from their summaries.
Labels: **Confirmed** (peer-reviewed paper, official page or Dory's code, with file:line), **Secondary**
(non-official page), **Assumption** (our reading of confirmed inputs), **Hypothesis** (untested; needs a probe).
Citations `[@key]` resolve in `phase6_report/references.bib`; `(preprint)` marks work without a peer-reviewed venue.
Peer-reviewed findings are weighted above preprints and vendor pages throughout.

Dory's constraints (Confirmed, phase 0 + CLAUDE.md): Thai first, English second; Nebius x NVIDIA hackathon deadline
2026-10-30 10:00 PDT; one bot process (`IndexedMemoryStore` / `RecentMessages` assume it); web service on Cloud Run
with `max-instances=1`; the text brain (Nemotron 3 Super) already runs on Nebius Token Factory; both voice paths run on
`gemini-live-2.5-flash-native-audio` at `us-central1`, a Vertex model that **retires 2026-12-13**.

---

## 1. Taxonomy of voice-to-voice architectures

```
Voice-to-voice assistant
├── A. Native full-duplex speech-to-speech (one model listens while it speaks; no VAD)
│     papers: Moshi [@defossez2024moshi] (preprint), SyncLLM [@veluri2024beyond], NTPP [@wang2025ntpp],
│             SALM-Duplex [@hu2025salm], LSLM [@ma2024language], D2 [@chang2026high] (preprint), dGSLM
│     products/models: NVIDIA PersonaPlex-7B, NemotronLabs VoiceChat-11B (both English only), Kyutai Moshi
│     Thai: none
├── B. Speech-to-speech voice layer + delegated text brain ("S2S with tools"; Dory today)
│     products: Gemini Live `gemini-3.8-live` + a tool (Dory's `ask_dory`), OpenAI GPT-Live `gpt-live-1`
│               (delegation to a backend), OpenAI `gpt-realtime-2.1` (one model with tools), Amazon Nova 2 Sonic,
│               ElevenLabs Realtime v1
│     academic cousins (speech encoder -> text LLM -> streaming speech decoder, turn-based with VAD):
│               Freeze-Omni [@wang2024freeze] (preprint), LLaMA-Omni [@fang2024llama], Qwen2.5-Omni [@xu2025qwen]
│               (preprint), Stream-Omni [@zhang2025stream] (preprint), Mini-Omni, GLM-4-Voice, Kimi-Audio
│     Thai: Gemini Live and gpt-realtime (managed) yes; open models no (Typhoon2-Audio is Thai but CC-BY-NC speech out)
├── C. VAD-free / micro-turn cascade (ASR -> LLM -> TTS kept for intelligence, turn gate replaced by a learned
│     end-of-turn / interruption model, stages overlapped)
│     papers: DuplexCascade [@yang2026duplexcascade] (preprint), Duplex Conversation [@lin2022duplex],
│             Speculative End-Turn Detector [@ok2025speculative], hierarchical EOT [@helwani2026hierarchical],
│             semantic interruption detection [@xia2026semantic], LLMVoX [@shikhar2025llmvox], CosyVoice 2
│             [@du2024cosyvoice] (preprint)
│     products: NVIDIA nemotron-voice-agent (Pipecat + Smart Turn), LiveKit Agents + turn detector, Deepgram Flux
│               + Voice Agent API, Kyutai Unmute, ElevenLabs Agents
│     Thai: ASR yes (Typhoon ASR Realtime, Deepgram Nova-3, Chirp 3 preview); TTS yes (Chirp 3 HD, Gemini TTS,
│           Cartesia, Azure); end-of-turn model: NONE for Thai (Silero VAD + silence only)
└── D. Classic turn-based cascade (silence VAD -> whole-utterance ASR -> LLM -> whole-utterance TTS)
      Dory's `voice_mode="classic"` fallback (~11 s per answer per `config.py:88-90`, unmeasured);
      VoiceBench's "Naive" Whisper + LLaMA-3.1-8B pipeline [@chen2024voicebench]; ESPnet-SDS toolkit
```

The two 2025-2026 surveys agree on the axis that matters: "engineered synchronisation" (modular, families C-D) vs
"learned synchronisation" (end-to-end, family A), with family B as the commercial middle [@chen2025from] (preprint),
[@lu2026survey] (preprint). Dory already sits in B; the evidence below says it should stay there for Thai and
harden the engineering around it, with C as the measured experiment.

---

## 2. Comparative tables

### 2.1 Latency as reported (what each number measures matters more than the number)

| System | Family | Reported latency | What was measured | Source / label |
| --- | --- | --- | --- | --- |
| Moshi (7B) | A | 160 ms theoretical, 200 ms practical | codec frame + acoustic delay; hardware unstated | [@defossez2024moshi] (preprint) |
| SyncLLM (Llama3-8b) | A | 160-240 ms chunks | chunk = generation deadline = tolerated network delay | [@veluri2024beyond] Confirmed |
| Moshi / dGSLM / Freeze-Omni / Gemini Live (2.0 flash live) | A/A/B/B | 0.265 / 0.352 / 0.953 / 1.301 s | end of user turn -> model speech, only on turns the model took | [@lin2025full] Confirmed |
| same four, after a user interruption | | 0.257 / 2.531 / 1.409 / 1.183 s | interruption -> model speech | [@lin2025full] Confirmed |
| LLaMA-Omni (8B, 1x L40) | B-academic | 236 ms (Ω=10) to 563 ms (Ω=100) | speech-instruction end -> first speech; excludes network and endpointing | [@fang2024llama] Confirmed |
| Freeze-Omni | B-academic | 745 ms avg / 1,020 ms p90; ≈1.2 s real | LLM interrupt -> first PCM, + 160-320 ms endpointing + 200-300 ms network | [@wang2024freeze] (preprint) |
| Streaming FastConformer (114M) | ASR stage | 0 / 40 / 240 / 520 / 680 / 1,360 ms look-ahead; WER 9.5 -> 6.3 on test-other | algorithmic look-ahead only; excludes decoder and endpointing | [@noroozi2024stateful] Confirmed |
| CosyVoice 2 | TTS stage | formula only: L_TTS = M·(d_lm + d_fm + d_voc), N=5 text / M=15 speech tokens | first package; no ms given | [@du2024cosyvoice] (preprint) |
| NVIDIA nemotron-voice-agent v2.3.0 (4x B200) | C | E2E 0.86-0.93; ASR+turn-taking 0.47-0.49; TTS TTFB 0.07-0.10; LLM TTFT 0.13-0.23 | units not printed ("sub-second" implies s); 1-64 parallel streams | build.nvidia.com, Confirmed page, units Assumption |
| Gemini 3.8 Live | B | TTFA 1.18 s (Extended Thinking 1.35 s) | Artificial Analysis Big Bench Audio | Secondary |
| Gemini 2.5 native audio (Dory's model) | B | TTFA 0.63 s | same | Secondary |
| GPT-Realtime-2.1 | B | 0.97 s (minimal) / 1.21 s (high) | same | Secondary |
| GPT-Live-1 | B | 1.24-1.34 s | same | Secondary |
| Nova 2 Sonic / Grok Voice 3.0 / Eleven Realtime v1 Max | B | 1.14 / 0.81 / 0.57 s | same | Secondary |
| Deepgram Flux | EoT stage | ~260 ms end-of-turn p50 | vendor | Confirmed vendor page |
| Pipecat Smart Turn v3 | EoT stage | 10-100 ms inference (~65 ms Pipecat Cloud) | vendor | Confirmed vendor page |
| Dory, Discord live path | B | "~1.5 s" (comment only) | `config.py:88-90`; one partial log line `live_voice.py:2302-2306` | Hypothesis (unmeasured) |
| Dory, classic path | D | "~11 s" (comment only) | `config.py:90` | Hypothesis (unmeasured) |

Reading: native duplex models are 0.5-1 s faster than any managed S2S product, but every managed product sits at
1.0-1.3 s TTFA, and a well-built cascade (nemotron-voice-agent on top-end GPUs) lands at 0.86-0.93 s. The gap between
families B and C is small; the gap between all of them and the "sub-800 ms" marketing is the one Dory can actually
work on (section 4).

### 2.2 Answer quality

| Evidence | Finding | Label |
| --- | --- | --- |
| VoiceBench overall, speech input: Whisper-large-v3 + LLaMA-3.1-8B **79.06** vs LLaMA-Omni **37.51**, VITA 34.68, Moshi **27.47**; GPT-4o-Audio 86.42 vs its own pipeline 87.23 | the cascade still wins on knowledge, instruction following and safety; LLaMA-Omni's AdvBench refusal fell from 98 % (text) to 11 % (speech) | [@chen2024voicebench] Confirmed |
| Qwen2.5-Omni VoiceBench 74.12 | the gap closes in 2025 for English/Chinese at 7B+ scale; no Thai rows anywhere | [@xu2025qwen] (preprint) |
| Thai: Qwen-Audio 95.1 % / SALMONN 98.1 % WER on CommonVoice-17 Thai; Typhoon-Audio 14.17 % (Thai-matched Whisper + Thai LLM); Gemini-1.5-Pro 13.6 % | vanilla multilingual audio LLMs collapse on Thai; both encoder and LLM must be Thai-matched; ≥10 % Thai in the mix or the ability vanishes | [@manakul2024enhancing] Confirmed (Interspeech 2025) |
| Whisper large-v2 Fleurs Thai 11.5 (letter-spaced, effectively CER) with 226 h of Thai data | the baseline everybody fine-tunes; Thai is far below the ~1,000 h knee | [@radford2022robust] Confirmed |
| Typhoon ASR Realtime CER 9.99 / 6.81 / 13.87 (TVSpeech / Gigaspeech2 / FLEURS-orig); Typhoon Whisper Large-v3 6.32 / 4.69 / 9.98; Gemini 3 Pro 10.95 / 12.50 / 11.35 (same table) | a 114M streaming Thai model is within a few CER points of offline Whisper fine-tunes and beats Gemini 3 Pro on two of three sets | [@sirichotedumrong2026typhoon] (preprint) Table 6 |

### 2.3 Barge-in and turn-taking behaviour

| Evidence | Finding | Label |
| --- | --- | --- |
| Full-Duplex-Bench pause-handling takeover rate: dGSLM 0.93, Moshi 0.98, Freeze-Omni 0.48-0.64, Gemini Live 0.26-0.31 | end-to-end duplex models interrupt a thinking pause 93-98 % of the time; an explicit speak/listen controller halves it | [@lin2025full] Confirmed |
| post-interruption answer quality (GPT-4o 0-5): Moshi 0.77, Freeze-Omni 3.62, Gemini Live 3.38 | manners and coherence come from the controller, not from being end-to-end | [@lin2025full] Confirmed |
| LSLM interruption detection F1 98.0 clean / **85.2 in noise, unseen speakers** | even a dedicated listening channel misses ~15 % of real barge-ins in noise; production stacks keep an external interrupt path | [@ma2024language] Confirmed |
| Semantic interruption detection: VAD is "trigger-happy" on backchannels, e2e models respond too slowly | the gap a semantic interruption model fills; no Thai model exists | [@xia2026semantic] Confirmed |
| End-of-turn: text cues beat prosody; fusion +3.7 % AUC over text, +22.6 % over acoustic-only (Switchboard) | a Thai EoT model needs a Thai small LM and Thai two-channel data (none public) | [@wang2024turn] Confirmed |
| 2026 ablation: acoustic + prosodic cues give the best accuracy/latency balance | if it holds for Thai, a language-light EoT model is possible | [@sharon2026less] (preprint) |
| Products: Gemini server VAD (default silence ~800 ms, recommended 500-800; 3.8 adds "polite interruption downgrade"); OpenAI `semantic_vad`; Deepgram Flux ~260 ms; LiveKit v1 (14 languages); Smart Turn v3.2 (23 languages); Krisp v3 | no semantic end-of-turn product lists Thai; LiveKit's own advice for uncovered languages is "VAD only" | Confirmed vendor pages |
| Dory: server `NO_INTERRUPTION` + code-side partner RMS ≥ 500 for 0.8 s; server keeps generating the muted turn; `ask_dory` never cancelled (`live_voice.py:126-130`, `2650-2678`, `1679`); web: server interrupts, but a tool call blocks the receiver (`web_live.py:239-240`) | Dory's barge-in is engineered, which the evidence favours, but it stops only playback | Confirmed (phase 0) |

### 2.4 Thai coverage per component (2026-10-25)

| Component | Managed, Thai = yes | Open, Thai = yes (licence) | Thai = no (do not plan on) |
| --- | --- | --- | --- |
| S2S / voice layer | Gemini Live 3.8 (99 langs, `th-TH`), OpenAI gpt-realtime-2.1 (+mini; Microsoft list), gpt-live-1 (Hypothesis), ElevenLabs Realtime v1 (Assumption from family claim) | Typhoon2-Audio (speech out **CC-BY-NC**, Llama 3.1 licence) | Moshi, Qwen3-Omni (speech out 10 langs), Step-Audio 2, Kimi-Audio, GLM-4-Voice, PersonaPlex, VoiceChat-11B, Nova 2 Sonic, Hume, Kyutai |
| Streaming ASR | Deepgram Nova-3, ElevenLabs Scribe v2 RT ("Good" 10-20 % WER band), Speechmatics, Google Chirp 3 (`th-TH` Preview, `us`/`eu` only), Gemini Live input transcription | **Typhoon ASR Realtime** (NeMo FastConformer-Transducer 114M, CC-BY-4.0, streaming), Qwen3-ASR-1.7B (Apache-2.0, vLLM `/v1/realtime`), NVIDIA Parakeet 1.1B RNNT Multilingual NIM (`th-TH` in `type=default`, Thai WER unpublished, NVAIE for prod) | Nemotron 3.5 ASR Streaming (Thai = adaptation-ready tier, fine-tune first), Parakeet TDT v3 / Canary (25 European), Moonshine, Kyutai STT, Vosk |
| Offline ASR (transcripts) | Gemini (Dory today, `gemini-3.5-flash` at asia-southeast1) | Typhoon Whisper Large-v3 (licence unverified), Thonburian whisper-large-v3 (Apache-2.0), whisper-large-v3-turbo (MIT), sherpa-onnx Thai zipformer (offline) | — |
| End-of-turn / interruption model | none (Gemini / OpenAI server VAD is silence-based with sensitivity knobs) | **none** (Silero VAD v6, MIT, language-agnostic silence only) | LiveKit turn detector (14), Smart Turn v3.2 (23), Deepgram Flux multi (10), Krisp v3 (Thai not listed), TEN Turn Detection |
| LLM brain | Gemini; Nemotron 3 Super on Token Factory (Dory today; Thai text quality is the team's measured experience, not in these files) | Typhoon 2 text LLMs | — |
| TTS | Google Chirp 3 HD (`th-TH` GA incl. `asia-southeast1`, streaming, $30/1M chars), Gemini 3.8 Flash TTS (Thai; Flash-Lite no), Azure th-TH Neural/HD, Cartesia Sonic 3.6, ElevenLabs v3/v4 (not Flash v2.5) | F5-TTS-THAI (CC-BY-4.0, not streaming, no latency claim), PyThaiTTS 0.8.0 (Apache-2.0 lib; streaming path) + VachanaTTS (VITS; HF MIT, repo no LICENSE), OpenJaiTTS / ThonburianTTS (**non-commercial**) | Magpie TTS (12 langs), Kokoro, CosyVoice 2/3, Chatterbox, Fish Speech (Thai unlisted), Deepgram Aura-2, Kyutai TTS |

Confirmed on the live Nebius endpoints (phase 4): Token Factory serves **no** ASR, TTS or audio-input model and has no
realtime/WebSocket API; speech on Nebius means a GPU VM (L40S from $1.55/GPU-h, H100 $4.50, no Southeast-Asia region).

---

## 3. Trade-off analysis with verdicts for Dory

### 3.1 End-to-end speech-to-speech vs modular cascade

| | Native full-duplex S2S (A) | S2S layer + delegated brain (B, Dory today) | VAD-free / classic cascade (C, D) |
| --- | --- | --- | --- |
| Latency | 0.2-0.35 s measured [@lin2025full]; 236-563 ms on one L40 [@fang2024llama] | 1.0-1.3 s TTFA for every managed product (Secondary, AA); 0.63 s for Gemini 2.5 native audio | 0.86-0.93 s on 4x B200 (NVIDIA, Confirmed page); ≈1.2 s real for Freeze-Omni incl. endpointing + network (preprint); typically 0.8-1.5 s (Assumption) |
| Answer quality, safety, tools | 20-50 points below a cascade on VoiceBench; safety regressions [@chen2024voicebench] | brain quality = the text LLM's (Nemotron 3 Super); tools proven in Dory | brain quality = the text LLM's; tool calls natural |
| Turn-taking manners | interrupts pauses 93-98 % [@lin2025full] | server VAD + Dory's code gate; "polite interruption downgrade" on 3.8 (Confirmed) | whatever the EoT module does; nothing semantic for Thai |
| Thai | no open model; no paper reports Thai (phase 3: zero Thai latency numbers) | Gemini Live Thai in/out Confirmed | Thai ASR (Typhoon) and TTS (Chirp 3 HD) exist; EoT = silence only |
| Build cost | 7B-class model that is ASR+LLM+TTS at once, duplex training data (Fisher-like or SyncLLM's 212k synthetic hours), echo/noise augmentation [@defossez2024moshi] [@veluri2024beyond] | config + glue; vendor lock-in; model retirements (2.5 on 2026-12-13) | glue: endpointer, streaming ASR, incremental LLM, sentence-level TTS, interruption path; each measurable and swappable |

**Verdict (Recommendation):** stay in family B for Thai through the hackathon and the 2026-12-13 migration; the
peer-reviewed evidence says a cascade or delegated-brain design wins on what the assistant says and on manners, and
Thai has no S2S alternative at all. Build family C as the **measured** experiment (Phase C), not as a replacement
decided on paper: its advantage over B is control (Thai ASR choice, Bangkok-side placement, cost at scale), not a
proven latency win.

### 3.2 Self-hosted vs managed

| | Managed S2S (Gemini Live, OpenAI) | Managed components (Deepgram, ElevenLabs, Google STT/TTS) | Self-hosted on Nebius GPU |
| --- | --- | --- | --- |
| Price per 50/50 conversation minute | Gemini 3.8 Live **$0.011** ($0.0135 always-on) + text tokens + per-turn context re-billing (Hypothesis 1.5-3x over 15 min); gpt-realtime-2.1 $0.048; gpt-live-1 $0.05 flat (Confirmed inputs, Assumption arithmetic) | Google cascade ≈ $0.025-0.030; Deepgram / AssemblyAI $0.075; ElevenLabs $0.08; Cartesia $0.06 | L40S $1.55/h = $37/day whether busy or idle; ≈ $0.026 per stream-minute at one busy stream, $0.0026 at ten (Assumption) |
| Thai | yes | yes (per table 2.4) | ASR yes; TTS weak and partly NC; EoT none |
| Ops | none | low | GPU VM, model updates, no SLA; Nebius has no SEA region (+RTT, Assumption 150-250 ms) |
| Data residency | Vertex region (Dory: `us-central1`; 3.8 Live is listed in the Asia Pacific table, check marks unreadable) | AssemblyAI EU; others US-centric | full control, but the GPU sits in eu-north1 / us-central1 |

**Verdict (Recommendation):** managed S2S is the cheapest Thai voice loop with tools today and the only one with
barge-in built in; self-host exactly the piece that is (a) Thai-capable, (b) permissively licensed and (c) tells
the NVIDIA/Nebius story: **Typhoon ASR Realtime on one L40S** for transcripts and captions, replacing the duplicate
per-segment Gemini ASR (phase 0, improvement #7). Self-hosting the whole loop only pays at sustained concurrency or
under a residency rule the owner has not stated (open question).

### 3.3 CPU vs GPU

- CPU is enough for: Silero VAD (<1 ms per 30 ms chunk, Confirmed README), Smart Turn v3 (8 MB int8, 10-100 ms),
  sherpa-onnx Thai zipformer (offline, RTF 0.04 on 2 threads), VachanaTTS (VITS), the Opus decode and mixing Dory
  already does. Dory's pure-Python 48k->16k box filter and sample-by-sample sum run on the event loop per 20 ms
  frame per speaker (`live_voice.py:435-490`): a CPU problem to fix with `audioop.ratecv` / numpy, not a GPU one.
- GPU is needed for: any FastConformer / Whisper ASR at scale (Typhoon ASR Realtime RTFx 4,097 on GPU; 115M params
  would also run on CPU for one or two streams, Hypothesis), F5-TTS-THAI (32 diffusion steps; >1 s first audio on an
  L40S is a Hypothesis with no published number), Ultravox-8B (~16 GB bf16), anything full-duplex (Moshi 24 GB).
- NVIDIA's own numbers: Nemotron ASR Streaming EN on H100, 160 ms chunks, 1 stream avg 6.6 ms; Magpie TTS first
  audio 35 ms (H100) / 9 ms (NeMo-Speech.cpp on RTX 4090) — the speech stages are not where a GPU cascade loses time;
  the LLM TTFT (0.13-0.23 s) and ASR+turn-taking (0.47-0.49 s) are (Confirmed page).

**Verdict (Recommendation):** one L40S (48 GB) is the right first GPU: it holds Typhoon ASR (114M) plus a NeMo-Speech.cpp
Nemotron ASR + Magpie pair for English with room to spare; no H100 until concurrency demands it.

### 3.4 Batch vs real-time streaming

- Streaming everywhere is what buys latency in a cascade: cache-aware streaming encoders at 240-520 ms look-ahead
  cost < 1 WER point vs offline and beat 1.5-2 s buffered Whisper-style streaming [@noroozi2024stateful]; TTS that
  starts after ~5 text tokens removes the sentence-length wait [@du2024cosyvoice] (preprint), [@shikhar2025llmvox].
- Dory's classic path is batch at every stage (whole 1.2 s-gap segments, whole-answer TTS, 20 s timeout) which is
  why it is documented at ~11 s; the Live path streams audio both ways but still batch-waits the brain.
- Batch is right for: minutes, memory, day summaries, the end-of-meeting summary (150k chars), Typhoon Whisper
  Large-v3 re-transcription for accuracy. Keep those batch.
- Chunk size: Google's best practice is **20-40 ms** audio chunks (Confirmed); the phase-0 suggestion to batch web
  frames to 100-200 ms conflicts with it. Reconciled: keep 40 ms frames, remove the waste instead (zeros while muted,
  continuous idle streaming), and never coalesce beyond ~100 ms (Dory's Discord sender already ticks at 100 ms).

### 3.5 Accuracy vs latency vs cost

- The largest avoidable latency in Dory is **turn-end detection**: web `silence_duration_ms` 2000 (`web_live.py:38`,
  comment "API max 2000", unverified) and Discord 1000 + a 1.8 s client silence tail, against Google's recommended
  500-800 ms and a server default of ~800 ms. Cutting web to 800 ms removes ~1.2 s per turn before any model change
  (Assumption; risk = more cut-offs during Thai thinking pauses, measure takeover rate).
- Model choice: AA measured Gemini 2.5 native audio at 0.63 s TTFA and 3.8 Live at 1.18 s (Secondary); 3.8 brings
  NON_BLOCKING tools, polite interruption and the GA future; 2.5 retires 2026-12-13. The latency cost of 3.8 is the
  price of staying supported (Hypothesis until measured on Dory's own turns).
- The brain: every `ask_dory` turn adds the full agent round trip (Nemotron, max 4 tool rounds; only "brain seconds"
  is logged). NON_BLOCKING + a spoken filler converts brain latency from dead air to a short acknowledgement; the
  measured cost is tokens, not seconds.
- Accuracy: Thai ASR CER 6-14 depending on model and set; Gemini's own Live transcription quality on Thai meetings is
  unmeasured (phase 0 open question 5). Cost: the second ASR pass per segment is Dory's main per-minute cost after
  Live itself (Confirmed by code; amount unknown).

---

## 4. Latency budget model for Dory's two paths

Stages from the last voiced frame to the first audible frame. "Today" = what phase 0 found measured; "Evidence" =
what the literature and vendor pages suggest the stage costs; estimates are **Hypothesis** until `StageTimer` logs exist.

### 4.1 Discord live path (`meeting.py` + `live_voice.py`)

| # | Stage | Measured today | Evidence / estimate | Lever |
| --- | --- | --- | --- | --- |
| 1 | Discord Opus frame -> bot sink (DAVE decrypt, Opus decode, 20 ms frames) | no | 20 ms frame + Discord RTT to the worker pool (asia-southeast1): ~50-150 ms | none needed |
| 2 | sink thread -> loop -> Mixer (box-filter 48k->16k, pure-Python sum) -> `_sender` tick 100 ms | no | 0-100 ms tick + CPU per frame per speaker | `audioop.ratecv`, numpy (phase 0 #5) |
| 3 | network bot -> Gemini Live `us-central1` | no | one-way ~90-125 ms from Singapore (Assumption) | try `global` / an Asia Pacific region for 3.8 (verify availability) |
| 4 | server VAD end of turn | no | `silence_duration_ms` **1000** (+ client sends 1.8 s of silence so it can fire); recommended 500-800 | 600-800 ms (measure takeover rate on Thai) |
| 5 | model first audio | partly: "user audio ended -> first audio" log line, gate-filtered | TTFA 0.63 s (2.5) / 1.18 s (3.8), Secondary | model choice; fillers |
| 5b | `ask_dory` turns: brain round trip | yes: "ask_dory answered in %.1fs", 25 s foreground cap, 150 s hard | Nemotron agent, 1-4 tool rounds; seconds | NON_BLOCKING (3.8 default), filler, cancel on barge-in |
| 6 | mouth gate / yield rule (hold up to 0.5 s quiet, drop after 6 s) | no | 0-500 ms when someone just spoke | keep; log it |
| 7 | `LiveAudioSource` 24k->48k repeat, player thread 20 ms reads, `vc.play` retries | no | 20-250 ms (5 x 50 ms retries while the previous source winds down) | log `first_read_at` |
| 8 | Discord playout to listeners | no | ~100-200 ms (Assumption) | none |
| | **Total, non-tool turn** | **unmeasured** ("~1.5 s" comment) | ≈ 1.0 (VAD) + 0.6-1.2 (TTFA) + 0.3-0.6 (network, gate, playout) = **1.9-2.8 s** Hypothesis | levers 4, 5, 2 |
| | **Total, tool turn** | brain seconds only | above + brain seconds unless NON_BLOCKING + filler | lever 5b |

### 4.2 Web Live path (`center.html` + `web_live.py`)

| # | Stage | Measured today | Evidence / estimate | Lever |
| --- | --- | --- | --- | --- |
| 1 | mic -> AudioWorklet linear resample -> 40 ms PCM16 frames -> WebSocket (continuous, zeros while muted) | no | 40 ms + browser->Cloud Run RTT | mic gate (stop zeros, `audio_stream_end`), keep 40 ms frames |
| 2 | `WebLive.feed` queue (200, drop oldest) -> one `send_realtime_input` per frame | no | ≈0 added; 25 sends/s | fine; drop count should be logged |
| 3 | network web service -> `us-central1` | no | as 4.1 #3 | as 4.1 #3 |
| 4 | server VAD end of turn | no | `silence_duration_ms` **2000** (`WEB_SILENCE_MS`) | **800 ms: the single largest lever on the web path** |
| 5 | model first audio | no | TTFA 0.63 / 1.18 s (Secondary) | model choice |
| 5b | `ask_dory` (`to_thread(center.answer_question)`, 90 s cap) **awaited inline in the receiver** | no | brain seconds; barge-in and transcripts stall meanwhile | background task + cancel on `interrupted` |
| 6 | 24 kHz chunks -> browser `AudioBuffer` scheduled ≥ now + 50 ms | no | 50 ms + chunk size | post a `metric` message with first-play time |
| | **Total, non-tool turn** | **unmeasured** | ≈ 2.0 + 0.6-1.2 + 0.2-0.4 = **2.8-3.6 s** Hypothesis | lever 4 first |

### 4.3 Where the budget could land (Hypothesis, to be replaced by measurements)

| Path / configuration | speech-end -> first-audio p50 (estimate) |
| --- | --- |
| Web today (2.5, silence 2000) | 2.8-3.6 s |
| Web after Phase A (silence 800, mic gate, 3.8 Live) | 1.5-2.3 s (3.8 TTFA 1.18 s dominates) |
| Discord today (2.5, silence 1000) | 1.9-2.8 s |
| Discord after Phase A (silence 700, same model) | 1.5-2.4 s |
| Industry target (vendor "800 ms rule", Secondary) | < 0.8 s p50, < 1.5 s p95 |
| Reachable with a managed S2S model alone | not below the model's own TTFA (0.6-1.3 s measured, Secondary) |
| Phase C cascade on Nebius (Typhoon ASR + Nemotron + Chirp 3 HD, Silero 600 ms) | 0.6 (VAD) + LLM TTFT 0.2-0.5 + TTS TTFA 0.1-0.4 + network = 1.0-1.6 s; sub-0.8 s only with Bangkok-side placement and a faster brain |

The honest conclusion: the user's requested p50 < 800 ms is the industry's number for an all-streaming cascade on
nearby GPUs; with any managed S2S model it is out of reach by construction. Dory's Phase A/B targets must therefore be
relative (halve today's turn-end wait, instrument everything) and the sub-800 ms figure belongs to the Phase C experiment.

---

## 5. Conflicts between the evidence files, reconciled

| Conflict | Resolution |
| --- | --- |
| Phase 4 (ecosystem) flags `discord-ext-voice-recv` (last commit 2025-06) as predating discord.py 2.7's DAVE E2EE, a risk to voice receive; Pycord docs warn recording may break under DAVE | Phase 0 shows Dory already bypasses the extension's decoder: `wants_opus()` returns raw Opus, `_dave_decrypt` uses `davey 0.1.7` per user, then Dory decodes with `discord.opus.Decoder` (`meeting.py:677-721`). **Mitigated in Dory's tree.** Residual risk: `davey` version drift and the "unencrypted" passthrough branch; no production incident data (phase 0 open question 10). |
| Affective dialog on `gemini-3.8-live`: Developer API model card says removed; Vertex guide says enabled by default | Both say the `enable_affective_dialog` flag must not be passed and that `proactive_audio` is permanently on. Dory passes `proactive_audio=True` today (`live_voice.py:1257-1261`); on 3.8 gate both flags on the model id and test on the Vertex `us-central1` endpoint (Phase A task). Whether affect is modelled is an open question that changes nothing in code. |
| Thai CER/WER numbers differ across files (Typhoon table vs HF cards vs Thonburian self-reported WER 6.59 on CV13 with Deepcut) | Compare only within one source's row: test sets, normalisation and tokenisers differ; Thai WER needs a word segmenter, so report CER first (phase 4 H). |
| Audit improvement #2 says batch web frames to 100-200 ms; Google best practice says 20-40 ms chunks | Keep 40 ms; the saving is in not streaming silence/zeros, not in bigger chunks (section 3.4). |
| `web_live.py:38` comment "API max 2000" for `silence_duration_ms` | No maximum found on the Live docs read today; recommended 500-800 ms. Treat the cap claim as unverified and the 2000 ms as a latency bug. |
| Nebius H100 "from $0.79" (industry brief, secondary tracker) vs $4.50 (nvidia_nebius file, nebius.com/prices) | $4.50 is the on-demand list price read on nebius.com; $0.79 is a third-party spot quote. Plan with on-demand. |
| VoiceBench venue "TACL (per OpenAlex / Semantic Scholar)" while arXiv v3 says "work in progress"; phase 4 writes "TACL'26" | Treated as peer-reviewed (two indexes agree) but the proceedings page was not fetched. |
| nemotron-voice-agent latency table prints 0.93 etc. without units | "sub-second" on the same page implies seconds; labelled Assumption. |
| Gemini Live latency: Full-Duplex-Bench 1.301 s (gemini-2.0-flash-live-001, 2025) vs AA 0.63 s (2.5 native audio) vs 1.18 s (3.8) | Different models and different measurements (turn-end -> speech on Candor vs TTFA on Big Bench Audio). Only Dory's own `StageTimer` numbers will settle what Dory sees. |
| Smart Turn language count: "23 languages" in both files; LiveKit "14" in both | Consistent; neither includes Thai. |
