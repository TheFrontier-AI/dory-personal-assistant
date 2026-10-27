# NVIDIA speech stack + Nebius infrastructure for a Thai/English voice-to-voice Dory

Research brief, written 2026-10-25 for the Nebius x NVIDIA hackathon (deadline 2026-10-30).
Scope: can Dory's speech layer (ASR, TTS, live voice), today on Google Gemini / Cloud TTS, move to NVIDIA models
hosted on Nebius, with Thai as a hard requirement.

Labels used on every fact:
- **Confirmed** = read on the cited page on 2026-10-25 (date in brackets where it differs). Model ids, prices and
  versions appear only when confirmed this way.
- **Assumption** = reasonable reading of confirmed facts, not stated verbatim by a source.
- **Hypothesis** = untested; needs a probe.

Local sources read first (12 installed skills under `~/.claude/skills/`): `nemotron-speech` (SKILL + asr, tts,
model-selection, pipelines, tts-pipelines, asr-custom, tts-custom, nmt, setup, readiness, BENCHMARK),
`nemotron-voice-agent-builder` (SKILL + models/catalog, asr, tts, llm, language-routing, frameworks/pipecat,
livekit, omni, platforms/single-gpu, deployment, dgx-spark, jetson-thor, readiness, preflight, intake,
output-contract, operations/*, networking/remote-webrtc, domain/*, BENCHMARK),
`ambient-healthcare-agent-with-nemotron-voice-agent`, `nemotron-asr-finetune`, `digital-health-clinical-asr-{setup,build,eval}`,
`nebius-dedicated-endpoint`, `nebius-finetune`, `nebius-observability`, `vllm`, `rtvi-cv-scaffold-vss-service` (skimmed).
**Not one of them mentions Thai** (`grep -ri thai` over all twelve = 0 hits, Confirmed, local). Every skill also says
"never take model ids, VRAM or catalogues from the skill text, fetch the NVIDIA support matrix", which this brief did.

---

## 1. Summary (10 bullets)

1. **Nebius Token Factory has no speech model at all.** The live `GET /v1/models` on 2026-10-25 (project key from
   `.env`, key name `DORY_NEBIUS_API_KEY`) returned 30 models, all text / vision / embedding (Nemotron 3 Super
   120B-A12B, Nemotron 3.5 Super VL, Nemotron 3.5 Lightning, Qwen3-Embedding-8B, DeepSeek, GLM, Kimi, ...). The
   dedicated-endpoint template list (58 templates) has types `text2text`, `image2text`, `embedding` only; the words
   audio / speech / whisper / tts / asr / voice occur 0 times in it. The docs index (`llms.txt`) has no page on
   audio, speech, transcription, realtime or WebSocket. **Confirmed** (API responses + docs, 2026-10-25).
2. **Speech on Nebius therefore means a GPU VM** (Nebius AI Cloud IaaS), not Token Factory. On-demand list prices:
   L40S from $1.55/GPU-h, RTX PRO 6000 $1.80, H100 $4.50, H200 $5.40, B200 $8.50, B300 $9.50 (nebius.com/prices,
   **Confirmed** 2026-10-25; a 2026-10-01 Hopper price rise is reported by usagepricing.com). Dedicated endpoints are
   "per GPU/hour, billed per minute" but rates are not published in the docs and the template API has no price field
   (**Confirmed**); custom weights are "beta, on request" and text-model only in practice.
3. **NVIDIA's speech catalogue has exactly two models that list Thai, both ASR, both with caveats:**
   Parakeet 1.1B RNNT Multilingual (NIM container `parakeet-1-1b-rnnt-multilingual`, `th-TH` in the `type=default`
   auto-detect variant, streaming profiles exist) and Nemotron 3.5 ASR Streaming 0.6B (`nemotron-asr-streaming`
   `type=multi`, 40 locales, Thai in the **"adaptation-ready" tier = tokenizer knows it, needs fine-tuning** before
   it transcribes). **Confirmed** (NIM ASR support matrix, last updated 2026-10-07; HF card 2026-10-25).
4. **No NVIDIA TTS speaks Thai.** Magpie TTS Multilingual = 12 languages, Magpie Zeroshot = 12, Chatterbox (community
   NIM) = 23; "Thai" does not appear on the TTS support matrix. The Magpie HF card says it is "not suitable for speech
   generation in any language other than the 12". **Confirmed** (2026-10-25).
5. **NVIDIA's full-duplex speech-to-speech models are English-only:** PersonaPlex-7B-v1 (Moshi-based, Jan 2026) and
   NemotronLabs VoiceChat-11B (Aug 2026, tool calling, ~450 ms turn-taking). Nemotron 3 Nano Omni (audio-in LLM) is
   also "Language support: English only". None can carry a Thai conversation. **Confirmed** (HF cards, 2026-10-25).
6. **NVIDIA's reference voice agent is Pipecat, not "ACE Controller".** `NVIDIA-AI-Blueprints/nemotron-voice-agent`
   v2.3.0 (Oct 2026): Nemotron ASR Streaming → Nemotron 3.5 Lightning 30B-A3B → Magpie TTS, WebRTC + RTVI + an
   OpenAI-Realtime-compatible `WS /v1/realtime` gateway; published benchmark 0.86-0.93 s end-to-end on 4x B200
   (ASR+turn-taking ≈0.47-0.49, TTS TTFB 0.07-0.10, LLM TTFT 0.13-0.23; units unstated, "sub-second" implies seconds).
   The older `NVIDIA/voice-agent-examples` (ACE/nvidia-pipecat) was archived 2026-07-17. **Confirmed**.
7. **Speech NIMs are free to self-host only for dev/test** (NVIDIA Developer Program, up to 16 GPUs); production needs
   an NVIDIA AI Enterprise licence. The licence-free route is **NeMo-Speech.cpp** (Apache 2.0, GGUF, Riva-compatible
   gRPC, 2.3 ms/160 ms chunk ASR and 9 ms TTS first-audio on an RTX 4090), which serves the same Nemotron ASR /
   Magpie models. **Confirmed** (developer.nvidia.com via search; GitHub README 2026-10-25).
8. **Best open Thai ASR today is not NVIDIA-branded but is NVIDIA-architected:** SCB10X **Typhoon ASR Realtime**
   (FastConformer-Transducer, 114-115M params, NeMo checkpoint, CC-BY-4.0, ~10-11k h Thai, streaming; CER 9.99
   TVSpeech / 6.81 Gigaspeech2 / 13.87 FLEURS-orig, 9.68 normalised). Offline Whisper-family fine-tunes beat it on
   accuracy (Typhoon Whisper Large-v3 6.32 / 4.69 / 9.98 (5.69); Pathumma-Whisper 10.36 / 5.84 / 6.29 (7.88)); Gemini 3
   Pro scored 10.95 / 12.50 / 11.35 (6.91) in the same table. **Qwen3-ASR-1.7B** (Apache 2.0, 30 languages incl.
   Thai, vLLM streaming) is the other hostable option. **Confirmed** (arXiv 2601.13044 Table 6; HF cards).
9. **Open Thai TTS exists but is weaker and licence-constrained:** F5-TTS-THAI (CC-BY-4.0 weights, ~500 h, 24 kHz, no
   latency claims, "long texts and some words not yet pronounced correctly"), ThonburianTTS (F5-TTS, CC-BY-NC-SA 4.0,
   CER 6.26), OpenJaiTTS-v1.0 (F5-TTS, CC-BY-NC-4.0, CER 4.78 short / 12.63 long, RTF 0.11), Typhoon2-Audio
   speech output CC-BY-NC (SpeechIF-Th CER 8.67, UTMOS 2.35). Kokoro (9 languages), Qwen3-TTS (10), Magpie (12) have
   **no Thai**. No "Typhoon TTS" for Thai exists (only an Isan demo). **Confirmed**.
10. **Realistic hackathon move:** keep Gemini Live (`th-TH` supported) as Dory's Thai voice path, and add one Nebius
    L40S/RTX PRO 6000 VM ($1.55-1.80/h) running Typhoon ASR Realtime or Qwen3-ASR for Thai transcription and, for the
    NVIDIA story, NeMo-Speech.cpp with Nemotron 3.5 ASR + Magpie for the **English** path. A Thai NVIDIA TTS does
    not exist; a Thai full-duplex NVIDIA model does not exist. Fine-tuning Nemotron 3.5 ASR's adaptation-ready Thai
    is the only route to "Thai on Nemotron Speech" and is not a 5-day job (**Assumption**, see section 7).

---

## 2. NVIDIA speech models (as of 2026-10-25)

Serving column: NIM = `nvcr.io/nim/nvidia/<container>` Speech NIM (gRPC :50051, HTTP/WS :9000, needs NGC key;
dev/test free, prod = NVAIE); NSC = NeMo-Speech.cpp GGUF; NeMo = Python toolkit; vLLM where stated.

| Model | Task | Streaming | Languages (Thai?) | Size | License | Serving | Latency / quality claim | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Nemotron 3.5 ASR Streaming 0.6B** (`nvidia/nemotron-3.5-asr-streaming-0.6b`; NIM `nemotron-asr-streaming`, `type=multi`) | ASR | Yes, cache-aware RNNT, chunks 80/160/320/560/1120 ms | 40 locales in 3 tiers: 19 transcription-ready, 13 broad-coverage, **8 adaptation-ready incl. Thai (th-TH) = "recognized by the tokenizer, designed for fine-tuning"**. Thai: **N for use, Y for fine-tune** | 600M | OpenMDW-1.1 | NIM (4 GB VRAM at batch 32, 12 GB at 128, 21 GB at 512), NSC (q8_0 GGUF), NeMo, Transformers >=5.13 | FLEURS avg WER transcription-ready tier 10.38 (80 ms) → 8.84 (1120 ms); no Thai number. Released 2026-06-04 | HF card + NIM ASR matrix (**Confirmed**) |
| **Nemotron ASR Streaming EN 0.6B** (`nvidia/nemotron-speech-streaming-en-0.6b`; NIM `type=en-US`) | ASR | Yes, 80-1120 ms | English only (**N**) | 600M | NVIDIA Open Model License | NIM, NSC, NeMo, Riva >=2.25, Transformers | OpenASR avg WER 6.93 (1120 ms) / 7.67 (160 ms) / 8.43 (80 ms). NIM perf page: H100 batch 32, 160 ms chunk, 1 stream avg 6.6 ms, p99 8.7 ms; B200 64 streams avg 11.6 ms. Released 2026-03-13 | HF card, NIM ASR perf page (**Confirmed**) |
| **Parakeet 1.1B RNNT Multilingual** (NIM `parakeet-1-1b-rnnt-multilingual`; HF `nvidia/parakeet-tdt-1.1b-rnnt-multilingual` is gated, HTTP 401) | ASR | Yes (`mode=str` profiles) + offline | 27 codes; **Thai th-TH = Y in `type=default` (auto-detect) only**, not in `type=prompt`/`indic` | 1.1B | not readable (gated card) | NIM only in practice (12.8-50.1 GB across profiles; Blackwell + DGX Spark) | No Thai WER published on the matrix | NIM ASR matrix (**Confirmed**); WER = **Open question** |
| **Parakeet CTC 0.6B / 1.1B English** (+ locale CTC variants vi, zh-CN, zh-TW, es) | ASR | Yes | en-US; locale variants vi/zh/es (**N**) | 0.6B / 1.1B | NIM | NIM (3-47 GB by profile), NSC (`parakeet-ctc-1.1b`) | NIM perf: 0.6B CTC H100 low-latency 160 ms chunk, 1 stream avg 12.4 ms p99 30 ms; 64 streams avg 32 ms; L40S 32 streams avg 21.4 ms | NIM ASR matrix + perf (**Confirmed**) |
| **Parakeet TDT 0.6B v3** (`nvidia/parakeet-tdt-0.6b-v3`; NIM `parakeet-0.6b-tdt`) | ASR | Offline in NIM; NeMo chunked script for streaming | 25 European languages (**N**) | 600M | CC-BY-4.0 | NIM (13.8-14 GB), NSC, NeMo | RTFx 3,332; Fleurs avg WER 11.97, OpenASR 6.34. Released 2025-08-14 | HF card (**Confirmed**) |
| **Canary 1B v2** (`nvidia/canary-1b-v2`; NIM `canary-1b` = older 4-language v1) | ASR + AST | Offline | 25 European (**N**) | 978M | CC-BY-4.0 | NeMo; NIM offline 13.4 GB (v1) | RTFx 749; Fleurs 25-lang WER 8.40. Released 2025-08-14 | HF card + NIM matrix (**Confirmed**) |
| **Canary-Qwen 2.5B** (`nvidia/canary-qwen-2.5b`) | ASR (SALM) | Offline | English (**N**) | 2.5B | per card | NeMo | — | HF card header (**Confirmed**) |
| **Whisper Large v3 NIM** (`whisper-large-v3`) | ASR + translate | Offline only | 99 languages, **Thai Y** (zero-shot Thai CER 6.56 FLEURS / 8.01 CV25 per BuzzASR card; Fleurs† incl. Thai WER 6.85 per Qwen3-ASR table) | 1.55B | Apache-2.0 (weights) | NIM `mode=ofl` 12.5 GB; vLLM `WhisperForConditionalGeneration` | HF card: "cannot be used for real-time transcription out of the box" | NIM matrix, HF cards (**Confirmed**) |
| **Magpie TTS Multilingual 357M** (`nvidia/magpie_tts_multilingual_357m`; NIM `magpie-tts-multilingual`) | TTS | Yes (streaming + offline) | 12: ar, zh, en, fr, de, hi, it, ja, ko, pt, es, vi (**Thai N**, card: "not suitable" for others) | 364M + NanoCodec 22.05 kHz | NVIDIA Open Model License | NIM (12.6 GB at batch 8, 41.5 GB at 32, 74.7 GB at 64), NSC GGUF, NeMo, TensorRT-LLM/Triton | NIM perf first-audio avg: H100 1 stream 35 ms, 64 streams 267 ms; A100 78 ms; B200 32 ms; NSC on RTX 4090: 9 ms TTFA, 3 ms inter-chunk. 5 English named voices in HF release v2607 (2026-07-21); NIM lists 140 voice/emotion entries. Zero-shot removed from HF release "for security reasons" | HF card, NIM TTS matrix + perf, NSC README (**Confirmed**) |
| **Magpie TTS Zeroshot** (NIM `magpie-tts-zeroshot`, access on application) | TTS + 3-10 s voice clone | Yes | 12 (same set, **Thai N**) | — | NIM | NIM 13.1 GB (batch 8) | L40S 1 stream first-audio 108 ms; DGX Spark 32 streams 1,744 ms | NIM TTS matrix + perf (**Confirmed**) |
| **Chatterbox TTS Multilingual** (community NIM `chatterbox-tts-multilingual`, Resemble AI) | TTS | Yes | 23 incl. ms-MY, ar, he, ...; **Thai N** | — | community | NIM 44.6-49.7 GB (A100/H100/L40S) | — | NIM TTS matrix (**Confirmed**) |
| **PersonaPlex-7B-v1** (`nvidia/personaplex-7b-v1`) | Full-duplex speech-to-speech | Yes (always-on) | English only (**N**) | 7B (card header 8B) | NVIDIA Open Model License (+ CC-BY-4.0 Moshiko) | PyTorch, A100/H100 | FullDuplexBench turn-taking latency 0.170, interruption latency 0.240 (units unstated); released 2026-01-15; trained on Fisher English | HF card (**Confirmed**) |
| **NemotronLabs VoiceChat-11B** (`nvidia/NVIDIA-NemotronLabs-VoiceChat-11B`) | Full-duplex speech-to-speech + tool calling | Yes | English (**N**) | 11B (Nemotron Nano v2 backbone + Nemotron-Speech-Streaming-En encoder + NVIDIA TTS decoder/codec) | OpenMDW-1.1 | vLLM; NVIDIA streaming container with bidirectional WebSocket; NSC lists it | ~450 ms turn-taking (448 ms), 480 ms interruption; in 16 kHz, out 22.05 kHz; released 2026-08-03 | HF card, NSC README (**Confirmed**) |
| **Nemotron 3 Nano Omni 30B-A3B** (`nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-{BF16,FP8,NVFP4}`) | Audio/video/image-in LLM (replaces ASR+LLM in the "Omni" pipeline) | Text-out LLM, streamed | "Language support: English only" (**N**) | 31B total / ~3B active | NVIDIA Open Model Agreement | vLLM 0.20.0 (`vllm/vllm-openai:v0.20.0` + `pip install "vllm[audio]"`); BF16 62 GB (H100), FP8 33 GB (L40S), NVFP4 21 GB (RTX 5090) | HF-ASR WER 5.95 (English); released 2026-04-28 | HF card (**Confirmed**) |
| **Riva Translate** (NMT) | translation | — | pairs per NMT matrix (not checked for Thai) | 1.6B / 4B | — | NIM, NSC (`Riva-Translate-4B-Instruct-v2`) | — | local skill + NSC README; Thai pair = **Open question** |

Hardware floor for every Speech NIM: compute capability 8.0+, >=16 GB VRAM; supported list A30/A100/H100/A2/A10/A16/
A40/L4/L40/RTX 40xx-60xx/DGX Spark (**Confirmed**, NIM matrices). Audio on the wire: mono 16-bit PCM WAV or Opus only
(local skill `nemotron-speech/references/asr.md`, **Confirmed** local). Server-side `chunk_size` is a deploy-time
setting (0.16 s low-latency, 0.8 s high-throughput); partials arrive once per server chunk (`pipelines.md`, local).

---

## 3. NVIDIA voice-agent reference architecture

**Nemotron Voice Agent blueprint** — `github.com/NVIDIA-AI-Blueprints/nemotron-voice-agent`, v2.3.0 (October 2026,
Pipecat upgraded to 1.12.0; **Confirmed** README + releases via search).

- Orchestrator: **Pipecat** (Daily). LiveKit Agents + `livekit-plugins-nvidia` is "swappable" but the LiveKit example is
  roadmap only. The local `nemotron-voice-agent-builder` skill confirms: Cascaded on Pipecat or LiveKit, **Omni on
  Pipecat only**; code must be generated from the Pipecat docs MCP, never from memory (**Confirmed** local).
- Transports: browser WebRTC (+ TURN for remote clients), RTVI at `/api/ws`, and an **OpenAI-Realtime-compatible
  gateway `WS /v1/realtime`** (**Confirmed** README).
- Two shapes: **Cascaded** ASR → LLM → TTS, and **Omni** (one audio-in LLM replaces ASR+LLM; TTS still separate; uses
  NVIDIA's `NvidiaOmniLLMService` copied from `src/examples/omni_assistant/`, Smart Turn stop strategy with
  `wait_for_transcript=False`; **Confirmed** local `frameworks/omni.md`).
- Default models (build.nvidia.com slugs, **Confirmed** README): ASR `nemotron-asr-streaming` (alt
  `parakeet-ctc-1_1b-asr`, `parakeet-1_1b-rnnt-multilingual-asr`), LLM `nemotron-3.5-lightning-30b-a3b` (alt
  `nemotron-3.5-super-vl-120b-a12b`, `nemotron-3-nano-omni-30b-a3b-reasoning`), TTS `magpie-tts-multilingual` (alt
  `magpie-tts-zeroshot`, `chatterbox-multilingual-tts`). The "Multilingual Assistant" example = Parakeet 1.1B RNNT
  Multilingual + Magpie/Chatterbox, **one fixed language per session**; the Generic Assistant is English-only.
- Pipecat service for NVIDIA ASR: `NvidiaSTTService` (`pipecat-ai[nvidia]`), default server
  `grpc.nvcf.nvidia.com:443`, local = `localhost:50051` with `use_ssl=False`; default model `nemotron-asr-streaming`,
  function id in `model_function_map` (**Confirmed** docs.pipecat.ai 2026-10-25).
- Deployment profiles: `generic-assistant` (NVIDIA cloud endpoints), `generic-assistant/server` (local NIM sidecars,
  ~80 GB for the all-on-one-GPU layout), `generic-assistant/single-gpu` (**vLLM + NeMo-Speech.cpp**, no NIM, needs an
  HF token not an NVIDIA key; Nemotron 3.5 Lightning needs >=28 GiB usable VRAM; DGX Spark and Jetson Thor supported).
  Local skill sizing hints: Nemotron ASR Streaming ~6 GB (batch 32) / ~15 GB (64); Magpie batch 8 ~13 GB, batch 32
  ~41 GB (**Confirmed** local, matches the NIM matrices within rounding).
- **Published latency** (build.nvidia.com blueprint page, **Confirmed** 2026-10-25; units not printed, "sub-second"
  implies seconds; measured on 4x B200: one ASR, one TTS, two for Nemotron 3.5 Lightning):

  | Parallel streams | E2E latency | ASR + turn-taking | TTS TTFB | LLM TTFT | LLM tok/s |
  | --- | --- | --- | --- | --- | --- |
  | 1 | 0.93 | 0.47 | 0.08 | 0.23 | 144 |
  | 4 | 0.86 | 0.49 | 0.07 | 0.17 | 170 |
  | 16 | 0.86 | 0.49 | 0.08 | 0.13 | 154 |
  | 64 | 0.93 | 0.49 | 0.10 | 0.13 | 141 |

  Turn-taking (Full-Duplex-Bench 1.0): Pipecat Smart Turn with 1 s timeout vs Silero VAD 500 ms (table on the same
  page). The v2.3.0 release note says streaming ASR is finalised after 320 ms trailing silence and a per-turn
  tool-call reminder removal saved ~220-320 ms at 16-32 clients (**Confirmed** via search snippet of the release).
- "ACE Controller": the Pipecat-based `NVIDIA/voice-agent-examples` (nvidia-pipecat, NAT agents, Riva ASR/TTS,
  BSD-2) was **archived 2026-07-17**, "all future development has moved to nemotron-voice-agent" (**Confirmed**
  GitHub). Treat ACE as superseded.
- Full-duplex alternative: NeMo-Speech.cpp lists VoiceChat-11B as a served model; its interactive mode is NVIDIA's
  CUDA/Triton/vLLM container with a bidirectional WebSocket (**Confirmed**). English only.

**NeMo-Speech.cpp** (`github.com/NVIDIA/NeMo-Speech.cpp`, Apache 2.0, **Confirmed**): ggml C++ runtime, no Triton,
no Python, GGUF models, CPU/CUDA/Metal/Vulkan, amd64 + arm64 container on NGC (`nemo-speech.cpp`), separate
`riva_server` binary exposing Riva-compatible ASR/TTS/NMT gRPC. Benchmarks (Q8_0): ASR 160 ms chunks 2.3 ms/chunk
on RTX 4090 (67x real time), 27 ms on CPU; TTS 9 ms first audio / 3 ms inter-chunk on RTX 4090, 203 ms / 64 ms on
CPU. Local skill adds: Magpie tokenizer lives in the `.nemo` archive, text-normalisation grammars are a GitHub release
asset, some Magpie languages are build-time options so `GetRivaSynthesisConfig` is the authority (**Confirmed** local).

---

## 4. Nebius Token Factory + Nebius AI Cloud

**Naming.** Nebius AI Studio became **Nebius Token Factory** on 2025-11-05 ("next evolution of Nebius AI Studio",
automatic upgrade; **Confirmed** nebius.com newsroom via search). `studio.nebius.com` is the old name; use
`tokenfactory.nebius.com` / `api.tokenfactory.nebius.com`.

**Serverless catalogue (live, 2026-10-25, `GET https://api.tokenfactory.nebius.com/v1/models`, Confirmed):** 30
ids, no audio: `nvidia/nemotron-3-super-120b-a12b`, `nvidia/Nemotron-3.5-Super-VL`, `nvidia/Nemotron-3_5-Lightning`,
`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/Nemotron-3-Ultra-550b-a55b`, `Qwen/Qwen3-Embedding-8B`,
`Qwen/Qwen3-235B-A22B-Instruct-2507`, `Qwen/Qwen3-30B-A3B-Instruct-2507`, `Qwen/Qwen3.5-397B-A17B`, `Qwen/Qwen3.8-27B`,
`deepseek-ai/DeepSeek-V4-Pro`, `-V4-Pro-0813`, `-V4-Flash-0731`, `-V4.1-Flash`, `-V4.1-Flash-1017`, `google/gemma-3-27b-it`,
`openai/gpt-oss-120b`, `moonshotai/Kimi-K2.6`, `Kimi-K2.7-Code`, `Kimi-K3`, `zai-org/GLM-5.1`, `-5.2`, `-5.3`, `-5.3-Flash`,
`MiniMaxAI/MiniMax-M3`, `-M3.1-Flash`, `NousResearch/Hermes-4-405B`, `openbmb/MiniCPM-V-4_5`, `meta-models/muse-spark-open`,
`reflection/beam`. The list response carries no modality field; the absence of speech is by id and by the docs index.
A WebSearch (OpenRouter provider page, Nebius deprecation notice) found no speech model either.

**Realtime / WebSocket API:** none. `docs.tokenfactory.nebius.com/llms.txt` (~300 pages) has no realtime, WebSocket,
audio or speech page; the only "streaming" pages are Sandboxes server-sent events (**Confirmed** 2026-10-25). The
OpenAI-compatible chat endpoint streams tokens (local skill + docs home).

**Dedicated endpoints** (`docs.tokenfactory.nebius.com/ai-models-inference/dedicated-endpoints`, **Confirmed**):
- Catalogue templates only: live `GET /v0/dedicated_endpoints/templates` = 58 templates, types `text2text` 40,
  `image2text` 14, `embedding` 4; GPU types `gpu-h100-sxm`, `gpu-h200-sxm`, `gpu-b300-sxm`, `gpu-l40s-d`; regions
  `eu-north1`, `eu-west2`, `us-central1`, `us-north1`; flavors `base` (throughput) and `fast` (speculative decoding).
  NVIDIA entries: `nvidia/Nemotron-3.5-Lightning` (1x H200), `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (1-4x H100 /
  1-8x H200), `nvidia/Nemotron-3-Nano-Omni` (typed `text2text`, 1-8 GPUs), `nvidia/Nemotron-Nano-V2-12b`,
  `nvidia/Cosmos3-Super-Reasoner`, `nvidia/Llama-3_1-Nemotron-Ultra-253B-v1`. **No ASR/TTS template.**
- Pricing: "Per GPU/hour, billed with per-minute granularity"; billable only while >=1 replica is ready; provisioning,
  restarts and graceful shutdowns are not billed; scale-to-zero stops charges. **Rates are not published** in the
  docs, the templates API has no price field, and `nebius.com/token-factory` shows no numbers (**Confirmed**, 4 pages).
  Minimum replicas are reserved/non-preemptible; no formal SLA for self-service (historical ~99.9% success).
- Bring-your-own: "Custom model weights ... currently in beta and available on request" via Support (fine-tuned
  weights of an eligible base model). No mention of custom containers, vLLM or NIM images. **Assumption:** a speech
  model cannot be deployed as a dedicated endpoint today.
- Fine-tuning (`nebius-finetune` skill, **Confirmed** local + docs): LoRA / full SFT on text LLMs via the OpenAI
  fine-tuning API (Llama 3.1 8B, Llama 3.3 70B listed). Not applicable to ASR/TTS.
- Observability (`nebius-observability` skill, **Confirmed** local): Prometheus endpoint
  `monitoring.tokenfactory.nebius.com/v1/projects/{PROJECT_ID}/prometheus/...` with `nebius_time_to_first_token_ms_bucket`,
  `nebius_e2e_latency_ms_bucket`, `nebius_requests_total`, `nebius_active_replicas`; 15 s minimum scrape.
- Billing: $1 trial credit for 30 days on new accounts (**Confirmed** billing page).

**Nebius AI Cloud GPU VMs (what speech would run on).** `nebius.com/prices`, on-demand per GPU-hour, USD, taxes
excluded, no region shown (**Confirmed** 2026-10-25):

| GPU | On-demand $/GPU-h | Smallest 1-GPU preset (docs.nebius.com/compute, Confirmed) | Regions |
| --- | --- | --- | --- |
| L40S (Intel) | from $1.55 | `gpu-l40s-a` 1gpu-8vcpu-32gb | eu-north1 |
| L40S (AMD) | from $1.82 | `gpu-l40s-d` 1gpu-16vcpu-96gb | eu-north1 |
| RTX PRO 6000 | $1.80 | `gpu-rtx6000` 1gpu-24vcpu-218gb | us-central1 (`-a`: uk-south2, eu-south1) |
| H100 SXM | $4.50 | `gpu-h100-sxm` 1gpu-16vcpu-200gb | eu-north1 |
| H200 SXM | $5.40 | `gpu-h200-sxm` 1gpu-16vcpu-200gb | eu-north1, eu-west1, us-central1 (+ eu-north2 private) |
| B200 | $8.50 | `gpu-b200-sxm` 1gpu-20vcpu-224gb | us-central1 (`-a`: me-west1) |
| B300 | $9.50 | `gpu-b300-sxm` 1gpu-24vcpu-346gb | uk-south1, eu-west2, us-north1 |
| GB200 / GB300 NVL72 | contact sales | — | — |

Spot/preemptible is dynamic and capped one cent below on-demand (prices page); third-party trackers quote H100 from
$0.79 and H200 from $0.95 spot and say Hopper on-demand rose from $3.85/$4.50 to $4.50/$5.40 on 2026-10-01
(**Hypothesis**: secondary sources gpufinder.dev / usagepricing.com, not verified on nebius.com). No Nebius region
is in Southeast Asia (closest to Bangkok: none listed; eu/us/uk/me only) — add ~150-250 ms RTT (**Assumption**).

---

## 5. Thai ASR options

CER/WER figures are only comparable inside one row's source. Thai is scored by CER (no word boundaries).

| Model | Thai quality (source) | Streaming | Size / licence | How to host | Verdict for Dory |
| --- | --- | --- | --- | --- | --- |
| **Typhoon ASR Realtime** (`scb10x/typhoon-asr-realtime`, SCB10X) | CER 9.99 TVSpeech, 6.81 Gigaspeech2, 13.87 FLEURS-orig / 9.68 normalised (arXiv 2601.13044 Table 6); HF card CER 0.0984, RTFx 4,097; "45x less compute than Whisper large-v3" | Yes (FastConformer-Transducer, built for streaming; hosted API labelled "Streaming ASR") | 114-115M, CC-BY-4.0 + OpenTyphoon T&C; NeMo checkpoint; ~10-11k h Thai | NeMo (`ASRModel.from_pretrained`), `pip install typhoon-asr`; hosted `https://api.opentyphoon.ai/v1` model `typhoon-asr-realtime`, 100 req/min, free key, OpenAI-compatible. **Hypothesis:** convertible to NeMo-Speech.cpp GGUF / Riva since it is a stock NeMo FastConformer-Transducer | Best streaming Thai option, tiny GPU footprint (fits beside other services on one L40S) | 
| **Typhoon Whisper Large-v3 / Turbo** (SCB10X, offline Whisper fine-tunes) | 6.32 / 4.69 / 9.98 (5.69) and 6.85 / 4.79 / 10.52 (7.08) — best offline rows in Table 6 | No (offline) | ~1.55B / ~0.8B; licence not fetched (**Open question**) | Transformers / vLLM Whisper path | Best accuracy for meeting transcription (`meeting.py` segments), not for live turns |
| **Pathumma-Whisper Large-v3** (NECTEC) | 10.36 / 5.84 / 6.29 (7.88) | No | ~1.55B | as Whisper | Strong on FLEURS read speech |
| **Thonburian Whisper** (`biodatlab/whisper-th-large-v3-combined`) | WER 6.59 Common Voice 13 (deepcut tokeniser, self-reported); in Table 6 "Biodatlab Whisper Large" 18.96 / 13.22 / 16.50 (15.26), Distil 13.82 / 8.24 / 6.77 (8.63) | No | ~1.55B, Apache-2.0 | as Whisper | Older; the distil variant is the interesting one |
| **OpenAI Whisper large-v3 / v3-turbo** (zero-shot) | CER 6.56 FLEURS / 8.01 CV25 normalised (BuzzASR card, secondary); Fleurs† incl. Thai WER 6.85 (Qwen3-ASR table) | No ("cannot be used for real-time out of the box") | 1.55B Apache-2.0 / 809M MIT (4 decoder layers) | vLLM `WhisperForConditionalGeneration`; NVIDIA NIM `whisper-large-v3` offline 12.5 GB | Baseline; NIM path gives an "NVIDIA-served" Thai ASR for files |
| **Qwen3-ASR-1.7B / 0.6B** (`Qwen/Qwen3-ASR-1.7B`) | No Thai-only row; Fleurs† (8 extra langs incl. Thai) WER 6.62 vs Whisper-v3 6.85; MLC-SLM 12.74; News-Multilingual 12.80 | Yes, **streaming only through vLLM** (`vllm serve Qwen/Qwen3-ASR-1.7B`; vLLM lists `Qwen3ASRRealtimeGeneration` under "Realtime Transcription" via `/v1/realtime` WebSocket) | 1.7B / 0.6B, Apache-2.0, 30 languages + 22 Chinese dialects (Thai listed) | vLLM on any Nebius GPU VM; OpenAI transcriptions endpoint | Second streaming candidate; same vLLM you would run anyway |
| **NVIDIA Parakeet 1.1B RNNT Multilingual** (NIM) | **No published Thai WER** (HF card gated) | Yes (`mode=str`) | 1.1B; NIM licence; 12.8-50 GB | Speech NIM container, `type=default` (auto-detect; Thai not in `prompt` type) | The only NVIDIA ASR that transcribes Thai today; accuracy unknown → probe before relying on it |
| **NVIDIA Nemotron 3.5 ASR Streaming** | Thai = adaptation-ready, **needs fine-tuning** | Yes, 80 ms | 0.6B OpenMDW-1.1 | NIM / NeMo-Speech.cpp | Not usable for Thai without a NeMo fine-tune (Typhoon's ~10k h corpus is not public as a whole) |
| **Gemini** (current Dory path) | Gemini 3 Pro 10.95 / 12.50 / 11.35 (6.91) in Table 6; Gemini 2.5 Flash Thai 0.05 on SEA-SpeechBench (metric unclear) | Gemini Live API lists `th-TH` (Google doc fetched this session) | cloud | API | Works today; keep as fallback / Live voice |
| **Voxtral Mini 4B Realtime** (Mistral) | 13 languages, **no Thai** | Yes (<500 ms, vLLM `/v1/realtime`) | 4B Apache-2.0 | vLLM | Not for Thai |
| **Qwen3-Omni-30B-A3B** (open) | speech input 18-19 languages, **Thai not listed** on the card (the tech report lists th; card does not) | Yes | 35B Apache-2.0, ~79 GB BF16 | vLLM (thinker only) | Not for Thai; Qwen3.5-Omni adds Thai in and out but is **API-only, no open weights** (search, 2026-10-25) |

---

## 6. Thai TTS options

| Model | Thai quality claim (source) | Streaming / latency | Licence | Notes |
| --- | --- | --- | --- | --- |
| **F5-TTS-THAI** (`VIZINTZOR/F5-TTS-THAI`, `pip install f5-tts-th`) | Card: "long texts and some words are not yet pronounced correctly"; v2 uses IPA (GitHub VYNCX/F5-TTS-THAI) | No streaming API; flow-matching, 32 steps; 24 kHz; no latency claim | weights **CC-BY-4.0**; code licence unstated (upstream F5-TTS code MIT, upstream weights CC-BY-NC per search) | ~500 h (Common Voice ~160 h + Porjai ~300 h + CV-EN ~40 h). Needs a 2-8 s Thai reference clip |
| **ThonburianTTS** (`biodatlab/ThonburianTTS`, F5-TTS Thai-script + IPA variants) | Paper: CER 8.70, SylER 14.17, WER 25.72, MOSNet 3.95, SIM-O 88.3 (ISAI-NLP 2025); CER 6.26 / SIM 0.48 in the JaiTTS comparison | RTF 0.115 (JaiTTS table) | **CC-BY-NC-SA 4.0** | Non-commercial |
| **OpenJaiTTS-v1.0** (`JTS-AI/OpenJaiTTS-v1.0`, F5-TTS) | CER 4.78 short / 12.63 long, SIM 0.60 / 0.80; closed JaiTTS-v1.0 (VoxCPM-based) 1.94 / 2.55 | RTF 0.11 | **CC-BY-NC-4.0**, gated | Best open Thai numbers found; licence blocks commercial use |
| **Typhoon2-Audio** (`scb10x/llama3.1-typhoon2-audio-8b-instruct`, speech-to-speech) | SpeechIF-Th CER 8.67, UTMOS 2.35; ASR-th WER 14.04 | end-to-end speech out; no latency claim | LLM Llama 3.1 Community; **speech output CC-BY-NC** | Only Thai speech-to-speech model found; 8B, Dec 2024, no realtime story |
| **Google Cloud TTS / Gemini Live** (current) | production Thai voices | yes | API | What Dory ships today |
| Magpie TTS (NVIDIA) | **no Thai** (12 languages) | 35 ms TTFA on H100 | NVIDIA OML | — |
| Qwen3-TTS | **no Thai** (10 languages: zh en ja ko de fr ru pt es it) | streaming via vLLM-Omni `/v1/audio/speech` + WS | Apache 2.0 | JaiTTS paper notes Thai pronunciation errors anyway |
| Kokoro-82M | **no Thai** (9 lang codes) | fast | Apache 2.0 | — |
| Fish Audio S2-Pro / Drama 3 | "about a hundred languages", Thai not named | S2-Pro ~100 ms first audio, RTF 0.195 on H200 | Fish Audio Community / Research licence | **Hypothesis** Thai works; licence restricts commercial use |
| "Typhoon TTS" | does not exist for Thai (only "Typhoon Isan TTS (Demo)", Nov 2025) | — | — | **Confirmed** absent via docs.opentyphoon.ai + search |

---

## 7. What Dory could realistically run on Nebius for the hackathon

Constraints: 5 days; Dory's text brain already on Token Factory; Thai first; one person deploying; Nebius has no
SEA region. Prices are Nebius on-demand list prices from section 4 (**Confirmed**); everything else in this section is
**Assumption** unless marked.

### Option A — "Thai-native open stack" on one L40S (48 GB) VM, ~$1.55-1.82/GPU-h (~$37-44/day)

- ASR: Typhoon ASR Realtime (NeMo, 114M) streaming, or Qwen3-ASR-1.7B on vLLM with `/v1/realtime`.
- LLM: unchanged, Nemotron 3 Super on Token Factory (RoutedClient already in `llm.py`).
- TTS: F5-TTS-THAI (CC-BY-4.0) sentence-chunked behind a small FastAPI; Google Cloud TTS stays as fallback.
- Thai coverage: full. NVIDIA content: FastConformer-Transducer architecture + Nemotron brain, no NVIDIA speech model.
- Risk: F5-TTS is not streaming and 32 diffusion steps per sentence on an L40S will likely cost >1 s to first audio
  (**Hypothesis**, no published latency); Thai TTS quality below Google's; VM in eu-north1 adds RTT.

### Option B — "NVIDIA speech showcase" on one H100 ($4.50/h, ~$108/day) or L40S

- NeMo-Speech.cpp container (Apache 2.0, no NVAIE) serving `nemotron-3.5-asr-streaming-0.6b` (32 usable locales = 19
  transcription-ready + 13 broad-coverage; Thai is not one of them) and `magpie_tts_multilingual_357m` over Riva gRPC; Pipecat `NvidiaSTTService` or Dory's own WebSocket.
- Thai: route Thai audio to Parakeet 1.1B RNNT Multilingual **NIM** (`type=default`, streaming, 13-50 GB; free under
  the Developer Program for dev/test, NVAIE for production) or to Option A's Typhoon ASR; Thai TTS still Google.
- Risk: two ASR engines and a language switch per session (the blueprint itself fixes one language per session);
  Parakeet's Thai accuracy is unpublished; NIM pulls are 10-30 GB and need an NGC key; H100 budget.

### Option C — "Minimal change, measurable win" (recommended for 5 days)

- Keep Gemini Live for the web/Discord live voice (Thai confirmed) and Google TTS for Thai speech.
- Add ONE Nebius VM (L40S, $1.55/h) running Typhoon ASR Realtime (+ Typhoon Whisper Large-v3 for offline accuracy)
  and point `meeting.py`'s per-segment transcription and the Discord voice path at it instead of Gemini per segment;
  measure CER vs Gemini on a stored meeting (`scripts/resummarize_dry_run.py`-style, read-only).
- Optionally run `nemotron-3.5-asr-streaming-0.6b` via NeMo-Speech.cpp on the same VM for the **English** live path to
  show a Nemotron Speech component end to end.
- Thai coverage: unchanged (Google) for TTS, open-source for ASR. Cost ~$37/day. Risk: lowest; the judging story is
  "Nemotron brain + NVIDIA-architecture Thai ASR on Nebius", not "all-NVIDIA speech".

### Not viable before 2026-10-30

- Thai on Nemotron 3.5 ASR Streaming: adaptation-ready tier = fine-tune first. The local `nemotron-asr-finetune` skill
  sets the floor at ">=10 h of real transcribed target-domain audio" and routes "new language, no suitable checkpoint"
  to cross-language transfer "rare" (**Confirmed** local); Common Voice Thai + FLEURS exist but a tokenizer-ready
  40-locale model fine-tune plus NIM/GGUF export plus evaluation is more than a hackathon week (**Assumption**).
- Any NVIDIA TTS or full-duplex model for Thai: none exists (section 2).
- Nebius dedicated endpoint for speech: no template, custom weights beta/text only (section 4).

---

## 8. Open questions

1. Parakeet 1.1B RNNT Multilingual Thai WER/CER — HF card is gated (HTTP 401); needs an NGC/HF login or a probe on
   Thai audio (`tests/fixtures/thai_meeting.json` audio if kept).
2. Nebius dedicated-endpoint $/GPU-hour — not in docs or API; visible only in the console UI or a work order.
3. Whether Typhoon ASR Realtime (`.nemo` FastConformer-Transducer) converts to NeMo-Speech.cpp GGUF or a Riva RMIR
   (`nemo2riva` / `riva-build`, local `asr-custom.md`); would make it servable from the same Riva gRPC as Magpie.
4. Real time-to-first-audio of F5-TTS-THAI on an L40S (no published number).
5. Typhoon Whisper Large-v3 licence and HF id (seen only in the paper table and on friendli.ai).
6. Riva Translate / NMT NIM: does any language pair include Thai (NMT support matrix not fetched).
7. Nebius spot pricing and the 2026-10-01 price rise — only secondary sources.
8. Nemotron voice-agent latency units (table prints 0.93 etc. without "s"); and whether the single-GPU recipe's
   NeMo-Speech.cpp build enables all 12 Magpie languages by default (some are build-time options per local skill).
9. Whether Gemini Live `th-TH` latency from Bangkok beats an eu-north1 Nebius hop for Thai turns (measure, do not assume).

---

## Sources (all seen 2026-10-25 unless noted)

NVIDIA: NIM ASR support matrix https://docs.nvidia.com/nim/speech/latest/reference/support-matrix/asr.html (page
"Last updated on Oct 07, 2026"); TTS matrix .../support-matrix/tts.html; ASR perf
.../performances/asr/performance.html; TTS perf .../performances/tts/performance.html;
https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b; https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b;
https://huggingface.co/nvidia/magpie_tts_multilingual_357m; https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3;
https://huggingface.co/nvidia/canary-1b-v2; https://huggingface.co/nvidia/canary-qwen-2.5b; https://huggingface.co/nvidia/canary-1b-flash;
https://huggingface.co/nvidia/personaplex-7b-v1; https://huggingface.co/nvidia/NVIDIA-NemotronLabs-VoiceChat-11B;
https://huggingface.co/nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-BF16; https://huggingface.co/nvidia/parakeet-tdt-1.1b-rnnt-multilingual (401);
https://github.com/NVIDIA-AI-Blueprints/nemotron-voice-agent (+ raw README, releases v2.3.0 2026-10-19 via search);
https://build.nvidia.com/nvidia/nemotron-voice-agent (benchmark tables); https://github.com/NVIDIA/NeMo-Speech.cpp;
https://github.com/NVIDIA/voice-agent-examples (archived 2026-07-17); https://docs.pipecat.ai/server/services/stt/nvidia;
NIM free for dev via Developer Program: https://developer.nvidia.com/blog/access-to-nvidia-nim-now-available-free-to-developer-program-members (via search).
Nebius: live `GET https://api.tokenfactory.nebius.com/v1/models` and `GET /v0/dedicated_endpoints/templates`;
https://docs.tokenfactory.nebius.com/ (+ /llms.txt index, dedicated-endpoints overview, billing-policy, custom-weights,
capacity-and-scaling, faq, api-reference list-templates, other-capabilities/billing-new); https://nebius.com/prices;
https://docs.nebius.com/compute/virtual-machines/types; https://dev.nebius.com/token-factory; rename:
https://nebius.com/newsroom/nebius-launches-nebius-token-factory-to-deliver-production-ai-inference-at-scale (2025-11-05).
Thai ASR: https://arxiv.org/html/2601.13044v1 (Typhoon ASR Real-time, Table 6); https://huggingface.co/scb10x/typhoon-asr-realtime;
https://docs.opentyphoon.ai/en/asr; https://huggingface.co/biodatlab/whisper-th-large-v3-combined; https://huggingface.co/BuzzASR/thai;
https://huggingface.co/Qwen/Qwen3-ASR-1.7B; https://github.com/QwenLM/Qwen3-ASR; https://huggingface.co/openai/whisper-large-v3;
https://huggingface.co/openai/whisper-large-v3-turbo; https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602;
https://huggingface.co/Qwen/Qwen3-Omni-30B-A3B-Instruct; https://arxiv.org/html/2604.15804v1 (Qwen3.5-Omni report);
https://docs.vllm.ai/en/latest/models/supported_models/; Gemini Live languages
https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/configure-language-voice (fetched earlier this session).
Thai TTS: https://huggingface.co/VIZINTZOR/F5-TTS-THAI; https://huggingface.co/biodatlab/ThonburianTTS; https://huggingface.co/JTS-AI/OpenJaiTTS-v1.0;
https://arxiv.org/abs/2604.27607 (JaiTTS); https://huggingface.co/scb10x/llama3.1-typhoon2-audio-8b-instruct;
https://huggingface.co/hexgrad/Kokoro-82M (+ VOICES.md); https://github.com/fishaudio/fish-speech; https://github.com/QwenLM/Qwen3-TTS (via search);
https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/; ThonburianTTS paper (Mahidol repository, via search);
Typhoon Isan TTS demo: https://www.scbx.com/en/news/scb-10x-unveils-typhoon-isan/ (via search).
