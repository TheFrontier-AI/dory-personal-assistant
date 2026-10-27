# Phase 5 — Gaps

Date: 2026-10-25. Three kinds: research gaps (nobody has the evidence), product gaps in Dory (phase 0), and
verification debts (facts the research agents could not check today). Peer-reviewed findings weighted above
preprints `(preprint)` and vendor pages.

## 1. Research gaps

| Gap | What exists instead | Consequence for Dory |
| --- | --- | --- |
| **No Thai end-of-turn / interruption model**, open or managed | silence VAD (Silero v6, MIT; Gemini / OpenAI server VAD); one text-only Thai EoT paper (arXiv 2510.04016, IEEE ICSEC 2025, no model released); 2026 ablation suggests acoustic + prosodic cues may be language-light [@sharon2026less] (preprint) | Thai turn-end = a silence timer; every 100 ms shaved raises the cut-off rate during Thai thinking pauses. Fine-tuning Smart Turn (open training code, BSD-2) or a VAP model [@inoue2024multilingual] on Thai two-channel speech is a research project, not a sprint. |
| **No Thai streaming TTS with a permissive licence** | Chirp 3 HD (managed, streaming, `asia-southeast1`), Gemini 3.8 Flash TTS (managed); open: F5-TTS-THAI (CC-BY-4.0, not streaming, no latency number), VachanaTTS (VITS, repo licence missing), PyThaiTTS streaming path; OpenJaiTTS / ThonburianTTS are non-commercial; JaiTTS closed [@karnjanaekarin2026jaitts] (preprint) | A self-hosted cascade speaks Thai through Google anyway, or accepts weaker open voices; "all-NVIDIA speech" is impossible for Thai (Magpie has 12 languages, none Thai). |
| **No Thai speech-to-speech model** (open) and no Thai full-duplex model (anywhere) | Typhoon2-Audio (speech out CC-BY-NC, no realtime story) [@pipatanakul2024typhoon] (preprint); SeaLLMs-Audio (Thai understanding + voice interaction, preprint) [@liu2025seallms]; Ultravox (Thai audio **in**, text out, MIT) | Family A is closed to Thai; family B is Gemini / OpenAI only. |
| **No paper reports Thai end-to-end voice latency** | all latency numbers are English (or Chinese); Thai papers report ASR CER / spoken-QA F1 only [@manakul2024enhancing] [@sirichotedumrong2026typhoon] | Every Thai latency figure in this corpus is a Hypothesis until Dory measures its own. |
| **Thai benchmarks for duplex behaviour do not exist** | VoiceBench, Full-Duplex-Bench v1 / v1.5 / v3, FD-Bench, TurnBench, Talking Turns are English; SeaBench-Audio (SeaLLMs-Audio) is the only SEA audio-LLM benchmark; Typhoon ASR Benchmark covers ASR only | Phase C's A/B needs a small Thai set built in-house (consented meeting clips + translated VoiceBench items). |
| Latency reporting is not comparable across papers | "theoretical" codec delay (Moshi), chunk size (SyncLLM), speech-end -> first speech on one GPU (LLaMA-Omni), benchmark turn-end -> speech (Full-Duplex-Bench), TTFA on a hosted API (Artificial Analysis), formula only (CosyVoice 2) | Use one definition for Dory (speech-end -> first audible frame, per path, p50/p95) and never mix it with vendor TTFA. |
| Citation counts | Semantic Scholar answered HTTP 429 to every unauthenticated request; counts in `paper_db.jsonl` are OpenAlex (`citation_source: openalex`, 5 null) and undercount arXiv-only preprints | Treat counts as lower bounds; do not rank by them. |
| Peer-review status is self-reported-acceptance level | venues from arXiv comments / proceedings pages found by search / OpenAlex ("per OpenAlex" on 5 records); VoiceBench's TACL and LSLM's AAAI not checked on the proceedings page | Marked in the tables; does not change any conclusion (the two load-bearing benchmark papers, Full-Duplex-Bench ASRU 2025 and Typhoon-Audio Interspeech 2025, were verified). |

## 2. Product gaps in Dory (from phase 0, Confirmed with file:line)

| # | Gap | Where | Why it matters |
| --- | --- | --- | --- |
| P1 | **Latency is unmeasured.** Only brain seconds and one gate-filtered "user audio ended -> first audio" line (Discord); nothing on the web, nothing for ASR, TTS, connect, playout, barge-in reaction | `live_voice.py:2302-2306`, `2022-2027`; `web_live.py` has only `started` and `turns` | No model, region or provider decision can be judged; the "~1.5 s / ~11 s" figures are comments. |
| P2 | **Web turn-end waits 2000 ms** of silence ("API max 2000", unverified) vs Google's recommended 500-800 | `web_live.py:38`, `177-190` | ~1.2 s of avoidable dead air per turn. |
| P3 | **Web streams audio continuously, zeros while muted**, one API send per 40 ms frame, no `audio_stream_end` | `center.html:1952-1967`, `2109`; `web_live.py:210-223` | Input tokens billed while idle and muted (proactive audio bills input while listening, Confirmed pricing page). |
| P4 | **Web tool call blocks the receiver**: `ask_dory` awaited inline for up to 90 s; barge-in, transcripts and `interrupted` stall; the job is never cancelled | `web_live.py:239-240`, `262-280` | The person cannot interrupt while Dory "thinks". |
| P5 | **Web has no session resumption or reconnect**; `go_away` or any hiccup ends the call with a toast; no keep-alive | `web_live.py:160-175`, `193-208`; `center.html:2082-2098` | Live connections live ~10 min; the Discord path already solved this (`live_voice.py:1272-1311`). |
| P6 | **Duplicate ASR**: every ≥0.4 s segment is also transcribed by `gemini-3.5-flash` (ffmpeg fork + FLAC + one `generate_content`) in live mode, on top of the Live input transcription | `meeting.py:2181-2187`, `596-611`, `838-842` | Main per-minute cost after Live; also the hook for the Nebius/Typhoon showcase. |
| P7 | **Code-side barge-in stops playback only**: server keeps generating the muted turn (`NO_INTERRUPTION`), running `ask_dory` jobs are never cancelled | `live_voice.py:126-130`, `2650-2678`, `1679` | Wasted output tokens; the next turn can queue behind a muted one (phase 0 open question 6). |
| P8 | **Model pinned to a retiring id** (`gemini-live-2.5-flash-native-audio`, retirement 2026-12-13); `proactive_audio=True` and affective flags would error / be ignored on 3.8 | `config.py:92-94`; `live_voice.py:1257-1261` | Hard deadline; behaviour differences (NON_BLOCKING default, polite interruption) untested. |
| P9 | **Pure-Python DSP on the event loop**: box-filter decimation, sample-by-sample mixing, sample-repeat upsampling; browser linear resample without anti-aliasing | `live_voice.py:435-490`, `450-457`; `center.html:1955-1965` | CPU per frame per speaker; aliasing may hurt Thai sibilants / tone cues for ASR (Hypothesis). |
| P10 | **Voice invisible to the workflow monitor**; no metrics export; default thread pool shared with every other `to_thread` | `monitor_sources.py` (no voice source), `meeting.py:2185`, `live_voice.py:2442` | The most fragile path has the least observability; a slow chat tool can starve transcription workers. |
| P11 | **Concurrency is in-process**: `_live_open` set, one session per person, `max-instances=1`; Discord parallel rooms need helper bot accounts (`VoicePool`) | `center.py:4433-4437`; `voice_pool.py` | A second web instance would allow two calls per person; voice CPU competes with HTTP. |
| P12 | **Nothing probes speech on Nebius**; neither probe script touches audio | `scripts/dory_tool_calls_probe.py`, `scripts/dory_nemotron_probe.py` | The hackathon story has no speech measurement behind it yet. |

## 3. Verification debts (not checked today; each is a probe or a page to read)

Gemini / Google
- Affective dialog on `gemini-3.8-live` at Vertex `us-central1` (Developer API says removed, Vertex says on by default).
- Vertex region availability of `gemini-3.8-live` in `asia-southeast1` / `global`, and TTFA from Bangkok on each.
- Whether `silence_duration_ms` really has a 2000 ms cap (`web_live.py:38` comment); recommended range is 500-800.
- Real cost of a 15-minute Dory session with context compression on vs off (per-turn re-billing multiplier is a Hypothesis).
- Behaviour of `NO_INTERRUPTION` + code-side stop: does the server bill and finish the muted turn, does the next turn wait.
- Gemini Live input-transcription quality on Thai meeting audio vs the per-segment `gemini-3.5-flash` JSON transcription (the `live_eval` harness exists but points at a Linux dev-box ledger path).
- `gemini-3.5-transcribe-live` language list (candidate for Thai captions in Asia).

OpenAI / others
- OpenAI Realtime session duration limit; official audio tokens-per-minute (Microsoft's ~10/~20 tokens per s was used).
- Azure Voice Live and Nova 2.5 Sonic prices (JavaScript pages); AssemblyAI streaming Thai (page 404); ElevenLabs Realtime v1 Thai (family claim only).
- Typhoon hosted API terms (opentyphoon.ai is JS-only); iApp / Botnoi / Vaja details (search snippets only).

NVIDIA / Nebius
- Parakeet 1.1B RNNT Multilingual Thai WER/CER (HF card gated, 401); Nemotron 3.5 ASR Streaming card gated.
- Nebius dedicated-endpoint $/GPU-hour (console only); spot prices and the reported 2026-10-01 Hopper price rise (secondary sources).
- Whether Typhoon ASR Realtime (`.nemo` FastConformer-Transducer) converts to NeMo-Speech.cpp GGUF / Riva RMIR, and whether it streams cache-aware or chunked.
- F5-TTS-THAI real time-to-first-audio on an L40S (no published number); Typhoon Whisper Large-v3 licence and HF id.
- Riva NMT Thai language pairs; whether the single-GPU recipe builds all 12 Magpie languages by default.
- nemotron-voice-agent latency units (table prints 0.93 without "s").

Ecosystem / Python
- `discord-ext-voice-recv` behaviour under DAVE without Dory's own decrypt path (Dory mitigates it; the upstream status is unknown).
- Qwen2.5-Omni GPU table, Step-Audio-2-mini size, TEN Turn Detection and Baichuan-Audio language lists, Open ASR Leaderboard's exact multilingual set, Porjai licence.
- `nemo_toolkit` 3.0.0 classifiers stop at 3.10; it is assumed to run on 3.12 (phase 4 [A]).

Dory-side (phase 0 open questions)
- Production distribution of "user audio ended -> first audio" and the frequency of the classic fallback.
- Number of `DORY_VOICE_TOKENS` configured and whether `pick_victim` has ever fired.
- Any `dave_dropped` / Opus decode failures in production logs.
- Browser `AudioContext` rate vs the worklet's linear resample on Thai ASR; whether Chrome AEC fully removes Dory's 24 kHz output from the mic.
