# Phase 4 — Code & Tools for a production Thai/English voice-to-voice agent

Research date: **2026-10-25**. Consumer: Dory (Python 3.12 via uv, FastAPI, discord.py-family voice,
google-genai, google-adk, NVIDIA Nemotron on Nebius Token Factory). Audience: the team deciding what to build on.

## How to read this file

- Every number in the tables was read by script on 2026-10-25 from the source named in the URL column:
  GitHub GraphQL API (stars, licence SPDX id, primary language, `latestRelease`, newest tag, last push /
  default-branch commit), Hugging Face JSON API (`cardData.language`, `license`, likes, 30-day downloads),
  PyPI JSON API (version, upload date, `requires_python`, classifiers, wheel tags), plus the README /
  model card text of each repo. Treat every un-tagged cell as **Confirmed (URL in the row, 2026-10-25)**.
- Cells tagged **[A]** are **Assumptions** (inferred, not read from a source today). Nothing in this file is
  quoted from memory.
- "Stars" are GitHub stargazers. "Release" is the GitHub `latestRelease` (tag @ date); when a repo has no
  release the newest tag or last commit date is given instead.
- "Thai" = Thai is in the model's documented training / supported-language list (Y), not (N), or the item is a
  language-agnostic framework whose Thai support depends on the plugged-in models (partial).
- "Streaming / barge-in" = for frameworks: handles interruptions; for models: streams output / is full-duplex;
  for ASR: has a true streaming mode; for TTS: streams audio chunks.

---

## A. Voice-agent orchestration frameworks

| Repo | What it does | Stars | Latest release + date | Licence | Thai | Streaming / barge-in | Notes | URL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pipecat-ai/pipecat | Python pipeline framework for voice / multimodal agents (Daily) | 16,799 | v1.14.0 @ 2026-10-24 (PyPI `pipecat-ai` 1.14.0 same day) | BSD-2-Clause | partial (framework is language-agnostic; its own turn model has no Thai) | Y — VAD + Smart Turn, interruption handling | Python ≥3.11. Transports: Daily WebRTC, FastAPI WebSocket, LiveKit, SmallWebRTC; telephony serialisers (Twilio, Plivo, Exotel, Genesys). Last push 2026-10-25. | https://github.com/pipecat-ai/pipecat |
| pipecat-ai/smart-turn (v3.2) | Semantic end-of-turn model on raw audio (not transcript) | 1,632 | no release; last commit 2026-01-29; HF `smart-turn-v3` updated 2026-01-07 | BSD-2-Clause | **N** — v3: 23 languages = Arabic, Bengali, Chinese, Danish, Dutch, German, English, Finnish, French, Hindi, Indonesian, Italian, Japanese, Korean, Marathi, Norwegian, Polish, Portuguese, Russian, Spanish, Turkish, Ukrainian, Vietnamese. v2: 14 (EN FR DE ES PT ZH JA HI IT KO NL PL RU TR) | n/a (it IS the turn detector) | v3 = Whisper-Tiny encoder + linear head, 8M params, 8 MB int8 ONNX; "as little as 10 ms on some CPUs", ~65 ms on Pipecat Cloud 1x instance. v2 ≈360 MB, 12 ms on L40S. Training data: pipecat-ai/datasets (synthetic Chirp3 for non-EN). | https://github.com/pipecat-ai/smart-turn · https://huggingface.co/pipecat-ai/smart-turn-v3 |
| livekit/agents | Python (+Node) realtime voice-agent framework over LiveKit WebRTC | 14,935 | livekit-agents@1.8.9 @ 2026-10-24 (PyPI 1.8.9) | Apache-2.0 | partial (STT/TTS plugin-dependent; turn detector has no Thai) | Y — VAD + semantic turn detector, interruptions | PyPI `requires_python >=3.10,<3.15`. Turn detector (text, `MultilingualModel`): en es fr de it pt nl zh ja ko id tr ru hi (14). Audio turn detector: English, Arabic, German, Spanish, French, Hindi, Indonesian, Italian, Japanese, Korean, Dutch, Portuguese, Turkish, Chinese (14). HF `livekit/turn-detector` licence "other", 1.22M downloads/30d. With no STT the detector falls back to English thresholds. | https://github.com/livekit/agents · https://docs.livekit.io/agents/build/turns/turn-detector/ |
| TEN-framework/ten-framework | Open framework for conversational voice agents (TEN Agent, TEN VAD, TEN Turn Detection) | 11,198 | 0.11.74 @ 2026-10-21 | "Apache-2.0 with additional conditions" (GitHub: NOASSERTION) | partial (pluggable STT/TTS; TEN Turn Detection languages not read today — [A] en/zh only) | Y — TEN VAD + TEN Turn Detection "full-duplex dialogue" | Min CPU ≥2 cores, RAM ≥4 GB. `TEN-framework/ten-turn-detection` 620 stars, last push 2025-12-26, licence NOASSERTION. | https://github.com/TEN-framework/ten-framework |
| vocodedev/vocode-core | Modular Python voice-LLM agent library (telephony, Zoom dial-in) | 3,806 | v0.1.113 @ 2024-06-18 | MIT | provider-dependent | Y — streaming conversations | **Dormant**: last commit 2024-11-15. | https://github.com/vocodedev/vocode-core |
| kyutai-labs/unmute | "Make text LLMs listen and speak": Kyutai STT → any text LLM → Kyutai TTS | 1,530 | no release; last commit 2026-09-09 | MIT | **N** (Kyutai STT/TTS are en/fr) | Y — low-latency cascade; Docker compose | GPU ≥16 GB VRAM, x86_64 only. | https://github.com/kyutai-labs/unmute |
| NVIDIA/ace-controller → **archived**, now `NVIDIA/voice-agent-examples` | Pipecat-based orchestrator with NVIDIA Riva/NIM services ("nvidia-pipecat") | 66 | v0.4.0 @ 2026-03-03; PyPI `nvidia-pipecat` 0.4.0 (2026-03-03) | BSD-2-Clause | partial (Riva/NIM ASR; Nemotron ASR Streaming has Thai only as "adaptation-ready", see C/F) | Y (Pipecat; "speculative speech processing" doc) | `isArchived: true`, last push 2026-07-17. `nvidia-pipecat` requires Python ≥3.12. | https://github.com/NVIDIA/ace-controller |
| fixie-ai/ultravox | Audio-in → text-out multimodal LLM (Llama 3.x backbones) for realtime voice | 4,583 | v0.6 @ 2025-08-18 | MIT (repo and HF weights) | **Y** — HF cards for v0.5-8B and v0.6-70B list 42 languages incl. `th` | partial — streams text; no speech output (pair with TTS) | Served by vLLM (`UltravoxModel`). Last commit 2025-12-12. Training: adapter only, 8xH100 2-3 h (v0.4). | https://github.com/fixie-ai/ultravox · https://huggingface.co/fixie-ai/ultravox-v0_5-llama-3_1-8b |
| Hume (HumeAI/hume-python-sdk; EVI) | Managed empathic S2S API + Python SDK | 181 | v0.14.0 @ 2026-06-17 | MIT (SDK); service is commercial | **N** — FAQ: "EVI 3 only supports English and Spanish"; EVI 4-mini: English, Japanese, Korean, Spanish, French, Portuguese, Italian, German, Russian, Hindi, Arabic | Y (managed S2S) [A] | Managed only; no self-hosting. | https://github.com/HumeAI/hume-python-sdk · https://dev.hume.ai/docs/speech-to-speech-evi/faq |
| bolna-ai/bolna | Conversational voice agents, telephony-first (provider STT/LLM/TTS) | 802 | 0.11.3 @ 2026-10-24 | MIT | provider-dependent | Y — `agent_flow_type="streaming"` | Telephony via `local_setup/`. | https://github.com/bolna-ai/bolna |

---

## B. Full-duplex / speech-to-speech open models with code

GPU memory figures are from the READMEs where present; "[A]" figures are bf16 weight-size estimates.

| Repo | What it does | Stars | Latest release + date | Licence | Thai | Streaming / barge-in | GPU memory · notes | URL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kyutai-labs/moshi | Full-duplex speech-text foundation model + Mimi streaming codec (PyTorch / MLX / Rust) | 11,297 | newest tag moshi-v0.2.12; PyPI `moshi` 0.2.13 (2026-02-12) | code Apache-2.0; weights CC-BY-4.0 | **N** — English only (HF `kyutai/moshiko-pytorch-bf16`: en) | **Y full-duplex**; 160 ms theoretical, ~200 ms on an L4 | 24 GB GPU for the PyTorch bf16 version. Last commit 2026-05-16. (NVIDIA's PersonaPlex-7B on HF is a Moshi-derived full-duplex model with Full-Duplex-Bench scores; metadata not collected here.) | https://github.com/kyutai-labs/moshi |
| QwenLM/Qwen2.5-Omni | End-to-end omni model (text/image/audio/video in, text+speech out), 3B and 7B | 4,084 | no release; last commit 2025-06-12 | Apache-2.0 (repo); HF card licence "other" | **N** [A] — speech output en/zh; HF card language tag `en` | Y streaming speech out (Thinker-Talker); vLLM audio output since 2025-04 | README has a "Minimum GPU memory requirements" table (not captured). vLLM `Qwen2_5OmniThinkerForConditionalGeneration`. | https://github.com/QwenLM/Qwen2.5-Omni |
| QwenLM/Qwen3-Omni | Natively end-to-end omni MoE (30B-A3B Instruct / Thinking) | 4,075 | no release; last commit 2026-04-23 | Apache-2.0 (repo); HF "other" | **N** — speech **input** 19: English, Chinese, Korean, Japanese, German, Russian, Italian, French, Spanish, Portuguese, Malay, Dutch, Indonesian, Turkish, Vietnamese, Cantonese, Arabic, Urdu (+1 unlisted); speech **output** 10: English, Chinese, French, German, Russian, Italian, Spanish, Portuguese, Japanese, Korean. Text: 119 languages (Thai text yes) | Y — "real-time streaming responses", natural turn-taking | BF16 min 78.85 GB (Instruct, 15 s video) / 68.74 GB (Thinking) with FlashAttention-2 → multi-GPU or vLLM. | https://github.com/QwenLM/Qwen3-Omni |
| VITA-MLLM/Freeze-Omni | S2S dialogue with a frozen text LLM (Qwen2-7B-Instruct) | 403 | none; last commit 2025-05-27 | NOASSERTION (no LICENSE file found; HF weights Apache-2.0) | **N** [A] (zh/en) | Y — chunk-wise streaming input, AR streaming speech decoder | 7B backbone → ~16 GB bf16 [A]. Python 3.10 env. | https://github.com/VITA-MLLM/Freeze-Omni |
| ictnlp/LLaMA-Omni | Speech-in/speech-out on Llama-3.1-8B-Instruct | 3,145 | none; last commit 2025-05-19 | code Apache-2.0; **model non-commercial** ("academic research only") | **N** (en) | Y — 226 ms latency, streaming synthesis | 8B → ~16 GB bf16 [A]. | https://github.com/ictnlp/LLaMA-Omni |
| ictnlp/LLaMA-Omni2 | Series on Qwen2.5 0.5B–32B with autoregressive streaming TTS (CosyVoice2 decoder) | 282 | none; last commit 2025-05-19 | code Apache-2.0; model non-commercial | **N** [A] (en/zh) | Y — streaming speech synthesis | 0.5B–32B sizes. | https://github.com/ictnlp/LLaMA-Omni2 |
| stepfun-ai/Step-Audio | 130B speech LLM (Step-Audio-Chat) + tokenizer + TTS-3B | 44 (repo now nearly empty; last push 2026-03-16) | none | Apache-2.0 | **N** [A] (zh/en) | Y — real-time pipeline with speculative response | Step-Audio-Chat weights 265 GB; tokenizer 1.5 GB. Python ≥3.10. | https://github.com/stepfun-ai/Step-Audio |
| stepfun-ai/Step-Audio2 | End-to-end audio LLM for understanding + speech conversation; open "mini" variants | 1,526 | none; last commit 2026-03-16 | Apache-2.0 (code + HF Step-Audio-2-mini) | **N** — HF tags en/zh; README evaluates zh, Cantonese, ja, ar, en | Y — vLLM backend "faster and streaming inference" | Size of "mini" not stated in the lines read [A ~8B class]. Python ≥3.10. | https://github.com/stepfun-ai/Step-Audio2 |
| MoonshotAI/Kimi-Audio | Audio foundation model (understanding, generation, conversation), 7B on Qwen2.5-7B | 4,744 | none; last commit 2025-06-03 | code MIT (Qwen-derived parts Apache-2.0); HF weights MIT | **N** (en/zh) | Y — chunk-wise streaming flow-matching detokenizer | 7B → ~16 GB bf16 [A]. vLLM `KimiAudioForConditionalGeneration`. | https://github.com/MoonshotAI/Kimi-Audio |
| zai-org/GLM-4-Voice | End-to-end zh/en spoken dialogue, 9B | 3,240 | none; last commit 2024-12-05 | Apache-2.0 (repo); HF card has no licence tag | **N** (zh/en) | Y — streaming | `--dtype int4` option in `model_server.py`; 9B → ~18 GB bf16 [A]. Dormant since 2024-12. | https://github.com/zai-org/GLM-4-Voice |
| SesameAILabs/csm | Conversational Speech Model (CSM-1B): contextual speech generation | 14,733 | none; last commit 2025-05-27 | Apache-2.0 | **N** — "some capacity for non-English … but it likely won't do well" | N (generation model, not a duplex agent) | CUDA GPU required; Python 3.10 recommended. | https://github.com/SesameAILabs/csm |
| baichuan-inc/Baichuan-Audio | End-to-end speech interaction on Qwen2.5-7B | 220 | none; last commit 2025-02-28 | Apache-2.0 | **N** [A] (zh) | Y [A] | 7B → ~16 GB bf16 [A]. | https://github.com/baichuan-inc/Baichuan-Audio |
| VITA-MLLM/VITA (VITA-1.5) | Real-time vision + speech interaction (NeurIPS 2025) | 2,538 | none; last commit 2025-03-28 | NOASSERTION (no LICENSE file at root) | **N** [A] (zh/en) | partial — e2e speech latency ~1.5 s (down from ~4 s) | 7B LLM + InternViT-300M. Python 3.10. | https://github.com/VITA-MLLM/VITA |

**Takeaway for Thai:** no open full-duplex / S2S model lists Thai for speech output; the only open audio-LLM with Thai
*input* is Ultravox (text out). SCB10X's `llama3.1-typhoon2-audio-8b-instruct` (HF, th+en, speech in/out) is the one
Thai S2S checkpoint, but its speech-output component is CC-BY-NC and the LLM is under the Llama 3.1 licence
(https://huggingface.co/scb10x/llama3.1-typhoon2-audio-8b-instruct) — not usable commercially.

---

## C. Streaming ASR

| Repo | What it does | Stars | Latest release + date | Licence | Thai | Streaming | Notes | URL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NVIDIA-NeMo/NeMo → now **NVIDIA-NeMo/Speech** (redirect) | NeMo speech toolkit: FastConformer, Parakeet, Canary, cache-aware streaming | 18,613 | v3.0.0 @ 2026-08-07 (PyPI `nemo_toolkit` 3.0.0, classifiers only up to 3.10) | Apache-2.0 | **partial**: `parakeet-tdt-0.6b-v3` = 25 European languages (no th); `canary-1b-v2` = 25 European (no th); `stt_en_fastconformer_hybrid_large_streaming_multi` = en; **Nemotron-3.5-ASR-Streaming-0.6B** (2026-06, 40 locales) lists Thai `th-TH` only in the **"Adaptation-ready" tier** (recognised by the tokenizer, meant for fine-tuning) — the HF repo is gated (401) | Y — cache-aware streaming FastConformer; Parakeet-unified-en-0.6b (2026-04) offline+streaming; Nemotron ASR Streaming | NIM support matrix: Parakeet 0.6b TDT NIM 13.75 GB GPU, offline, batch 1024. Thai in NeMo today = fine-tune the streaming model, or use **Typhoon ASR Realtime**, which is a NeMo FastConformer-Transducer. | https://github.com/NVIDIA-NeMo/NeMo · https://docs.nvidia.com/nim/speech/latest/reference/support-matrix/asr.html |
| openai/whisper | Reference Whisper (99 languages) | 111,239 | v20250625 @ 2025-06-26 (PyPI openai-whisper, sdist only) | MIT | **Y** (th in 99) | N — offline; chunked | Python ≥3.8, classifiers to 3.13. Last push 2026-08-31. | https://github.com/openai/whisper |
| SYSTRAN/faster-whisper | Whisper on CTranslate2 (int8/fp16, batched) | 26,127 | v1.2.1 @ 2025-10-31 (PyPI 1.2.1) | MIT | **Y** (Whisper weights) | N native; pair with whisper_streaming / SimulStreaming | `ctranslate2` 4.8.3 (2026-10-13) ships cp310–cp314 + cp314t wheels. RTX 3070 Ti 8 GB benchmarks in README. | https://github.com/SYSTRAN/faster-whisper |
| ufal/whisper_streaming (→ successor `ufal/SimulStreaming`) | LocalAgreement streaming wrapper for Whisper backends | 3,676 (SimulStreaming 691) | none; last commit 2025-11-12 (SimulStreaming last push 2026-07-12, MIT) | MIT | **Y** (Whisper) | **Y** — simulated/real streaming, sentence segmenters | PyPI `whisper-streaming` 0.1.0 requires `<3.13`. | https://github.com/ufal/whisper_streaming · https://github.com/ufal/SimulStreaming |
| openai/whisper-large-v3-turbo (HF) | Pruned-decoder (4 layers) large-v3, ~8x faster | 3,477 likes; 5.82M downloads/30d | model 2024-10-04 | MIT | **Y** (99 languages incl. th) | N — offline | vLLM `WhisperForConditionalGeneration` lists it. Thai WER on Whisper is weak vs fine-tunes (see Thonburian). | https://huggingface.co/openai/whisper-large-v3-turbo |
| k2-fsa/sherpa-onnx | On-device ASR/TTS/VAD/diarisation runtime (C++ with Python, Android, iOS, Node, WASM) | 15,505 | v2.0.0 @ 2026-10-23 (PyPI sherpa-onnx 2.0.0, cp37–cp315 wheels) | Apache-2.0 | **Y** — `sherpa-onnx-zipformer-thai-2024-06-20` (Zipformer transducer trained on GigaSpeech2; RTF 0.040 fp32 / 0.033 int8 on 2 CPU threads) — **offline** (non-streaming) model; streaming Zipformer models exist for zh/en, none for Thai in the docs read | Y streaming engine (zh/en models); Thai model is offline → chunk with VAD | Also integrates Qwen3-ASR 0.6B (~1 GB). Last push 2026-10-25. | https://github.com/k2-fsa/sherpa-onnx · https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/zipformer-transducer-models.html |
| alphacep/vosk-api | Offline Kaldi-based ASR, 20+ languages | 15,200 | v0.3.50 @ 2024-04-22 (PyPI vosk 0.3.45, 2022) | Apache-2.0 | **N** — model list has Vietnamese, Filipino … no Thai | Y — "zero-latency response with streaming API" | Last push 2026-10-15. | https://github.com/alphacep/vosk-api · https://alphacephei.com/vosk/models |
| speechbrain/speechbrain | PyTorch conversational-AI toolkit (ASR, speaker, enhancement, SLU) | 11,902 | v1.1.2 @ 2026-10-14 (PyPI 1.1.2) | Apache-2.0 | partial — recipes; no Thai streaming checkpoint read [A] | partial — streaming Conformer recipes | Research toolkit; Python ≥3.8.1. | https://github.com/speechbrain/speechbrain |
| moonshine-ai/moonshine | Very-low-latency on-device streaming STT (+ intent, TTS) | 11,287 | v0.1.5 @ 2026-08-24 (tag v0.1.6) | MIT (code except `core/third-party`; models MIT by default) | **N** — HF org `moonshine-ai` models: en, es, ja, zh, ar, uk, ko, vi, de, tl (streaming tiny/small/medium) | **Y** — "optimized for live streaming … while the user is still talking" | PyPI `useful-moonshine-onnx` 20251121. | https://github.com/moonshine-ai/moonshine · https://huggingface.co/moonshine-ai |
| kyutai-labs/delayed-streams-modeling (Kyutai STT) | Streaming STT 1B/2.6B + TTS 1.6B via Delayed Streams Modeling | 3,040 | none; last commit 2026-01-26 | Python MIT, Rust Apache-2.0; weights CC-BY-4.0 | **N** (`stt-1b-en_fr`: en, fr) | **Y** — true streaming; "an H100 can process 400 streams" | — | https://github.com/kyutai-labs/delayed-streams-modeling |
| **Typhoon ASR Realtime** (SCB10X, HF only — no GitHub repo found) | Thai streaming ASR: NeMo FastConformer-Transducer, 114M params, 10,000 h Thai | 30 likes; 1,528 downloads/30d | model updated 2026-06-11; tech report Jan 2026 | **CC-BY-4.0** | **Y** (th) | **Y** — "built for real-world streaming applications" (RNNT; cache-aware mode not stated [A]) | CER 0.0984; RTFx 4097 ("6x throughput over the next fastest model", Open-ASR-Leaderboard method). Runs in NeMo / can export to sherpa-onnx [A]. | https://huggingface.co/scb10x/typhoon-asr-realtime |
| biodatlab/thonburian-whisper | Whisper fine-tuned for Thai (medium, large-v3, distilled) | 208 | none; last commit 2026-04-02 | repo MIT; HF models Apache-2.0 | **Y** | N — offline Whisper | `whisper-th-large-v3-combined`: WER 6.59 on Common Voice 13 test (Deepcut tokenizer); trained on CV13 th + FLEURS + curated sets; last model update 2024-02-20. | https://github.com/biodatlab/thonburian-whisper · https://huggingface.co/biodatlab/whisper-th-large-v3-combined |

---

## D. VAD / turn detection

| Repo | What it does | Stars | Latest release + date | Licence | Thai | Latency / notes | URL |
| --- | --- | --- | --- | --- | --- | --- | --- |
| snakers4/silero-vad (v6) | Enterprise-grade VAD, ONNX/JIT, 8/16 kHz | 10,522 | v6.2.3 @ 2026-09-23 (PyPI silero-vad 6.2.3, classifiers to 3.15) | MIT ("no telemetry, no keys") | **Y** — trained on corpora covering 6,000+ languages | <1 ms per 30 ms+ chunk on one CPU thread. The default choice for Thai end-pointing. | https://github.com/snakers4/silero-vad |
| pipecat-ai/smart-turn v3 | Semantic end-of-turn (audio) | 1,632 | see A | BSD-2-Clause | **N** (23 langs, no th) | ~12 ms CPU. Falls back to plain VAD behaviour for unsupported languages [A]. | https://github.com/pipecat-ai/smart-turn |
| livekit/turn-detector | Text (transformer on transcript) + audio end-of-turn models | HF 167 likes, 1.22M dl/30d | HF updated 2026-02-11 | "other" (LiveKit model licence) | **N** (14 langs, no th) | Needs STT language; English thresholds otherwise. | https://huggingface.co/livekit/turn-detector |
| wiseman/py-webrtcvad | Python binding to the WebRTC GMM VAD | 2,501 | tag 2.0.10 (PyPI 2017-01-07, sdist only) | NOASSERTION (WebRTC BSD-style) | Y (language-agnostic energy/GMM) | 10/20/30 ms frames. Last code commit 2021-02-15; compiles from source on modern Python [A]. | https://github.com/wiseman/py-webrtcvad |
| TEN-framework/ten-vad | Low-latency frame-level VAD (C, ONNX; Python package) | 2,292 | v1.0-ONNX @ 2025-07-11 (PyPI ten-vad 1.0.6.9, 2026-10-09) | Apache-2.0 **with additional conditions** | Y (language-agnostic) [A] | README: faster speech→non-speech transitions than Silero ("several hundred ms" delay in Silero). | https://github.com/TEN-framework/ten-vad |
| Krisp (commercial SDK) | Noise cancellation, background-voice cancellation, server-side voice isolation, **Turn-Taking** model | n/a | n/a | commercial | "language independent" (vendor claim) | Vendor claims WER cut 46 % average in front of VAD/STT. Paid, closed. | https://krisp.ai/developers/ |

---

## E. Streaming TTS

| Repo | What it does | Stars | Latest release + date | Licence | Thai | Streaming | Notes | URL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hexgrad/kokoro (Kokoro-82M) | 82M-param TTS, CPU-friendly | 9,659 (HF 7,275 likes, 10.3M dl/30d) | none; last commit 2025-08-06; PyPI kokoro 0.9.4 (2025-04-05) | Apache-2.0 | **N** — lang codes a/b (en-US/GB), e es, f fr, h hi, i it, j ja, p pt-BR, z zh | Y (phrase-level chunks) | **PyPI `kokoro` requires Python `>=3.10,<3.13`** — blocks 3.13+. | https://github.com/hexgrad/kokoro |
| canopyai/Orpheus-TTS | Llama-3B-based TTS "towards human-sounding speech" | 6,374 | none; last commit 2025-12-05 | Apache-2.0 | **N** (HF `orpheus-3b-0.1-ft`: en; multilingual research checkpoints exist, Thai not among them [A]) | **Y** — ~200 ms streaming, ~100 ms with input streaming; vLLM serving | 3B → ~7 GB bf16 [A]. | https://github.com/canopyai/Orpheus-TTS |
| FunAudioLLM/CosyVoice (CosyVoice 2 / Fun-CosyVoice 3) | LLM-based zero-shot TTS, 0.5B | 24,127 | tag v2.0; last commit 2026-05-25; HF Fun-CosyVoice3-0.5B-2512 updated 2026-02-03 | Apache-2.0 | **N** — 9 languages (zh en ja ko de es fr it ru) + 18 Chinese dialects | **Y** — bi-streaming (text-in, audio-out), ~150 ms | Python 3.10 env. | https://github.com/FunAudioLLM/CosyVoice |
| fishaudio/fish-speech (S1 / S2 / Drama 3) | SOTA open TTS with voice cloning and inline emotion tags | 33,398 | v1.5.1 @ 2025-05-31 (tag v3.0.0-beta); last commit 2026-10-14 | **Fish Audio Community License v1.0 (2026-10-13)**; S2-Pro under Research Licence; HF s1-mini CC-BY-NC-SA-4.0 | **N** — HF cards list 13 languages (zh en de ja fr es ko ar nl ru it pl pt) | Y — production streaming, RTF 0.195 on H200, ~100 ms to first audio | Commercial use only within the Community Licence limits — read it. | https://github.com/fishaudio/fish-speech |
| SWivid/F5-TTS | Flow-matching zero-shot TTS | 15,449 | 1.1.22 @ 2026-07-23 (PyPI f5-tts 1.1.22) | code MIT; **pre-trained models CC-BY-NC** (Emilia data) | N (base); **Thai via fork below** | partial — chunked inference (253 ms RTF figures) | Python 3.11 env. | https://github.com/SWivid/F5-TTS |
| VYNCX/F5-TTS-THAI (model VIZINTZOR/F5-TTS-THAI) | F5-TTS fine-tuned for Thai (~160 h Common Voice th + ~300 h Porjai + ~40 h CV-en) | 166 (HF 55 likes) | 1.0.3 @ 2025-08-08; last commit 2026-01-04; HF updated 2025-10-08 | repo MIT; **HF model CC-BY-4.0** | **Y** | partial (chunked) | README warns it may skip or repeat words. GPU recommended [A]. | https://github.com/VYNCX/F5-TTS-THAI · https://huggingface.co/VIZINTZOR/F5-TTS-THAI |
| resemble-ai/chatterbox (Multilingual V3, Turbo) | 0.5B multilingual TTS; Turbo 350M English for voice agents | 27,231 (HF 1,866 likes, 1.9M dl/30d) | v0.1.2 @ 2025-06-13; last commit 2026-07-21; PyPI chatterbox-tts 0.1.7 (2026-03-26) | MIT | **N** — 23 languages (ar da de el en es fi fr he hi it ja ko ms nl no pl pt ru sv sw tr zh) | Y (Turbo: low latency, paralinguistic tags) | Python ≥3.10. | https://github.com/resemble-ai/chatterbox |
| nari-labs/dia (Dia-1.6B) | Dialogue TTS, one pass, non-verbal tags | 19,405 | none; last commit 2025-11-19 | Apache-2.0 | **N** (en) | N (whole-utterance) | RTX 4090 benchmarks in README. | https://github.com/nari-labs/dia |
| idiap/coqui-ai-TTS (XTTS v2 fork) | Maintained fork of Coqui TTS | 2,340 | v0.28.0 @ 2026-10-19 (PyPI coqui-tts 0.28.0, `<3.15`) | MPL-2.0 (code); **XTTS-v2 weights CPML non-commercial** (HF "other") | **N** — XTTS v2: 17 languages, no th | Y — XTTS streaming | "+1100 languages" refers to MMS/VITS single-speaker models (Thai MMS-TTS exists on HF, e.g. `VIZINTZOR/MMS-TTS-THAI-MALEV1` [A quality]). | https://github.com/idiap/coqui-ai-TTS |
| Kyutai TTS (`kyutai/tts-1.6b-en_fr`) | Streaming TTS from delayed-streams-modeling | 3,040 (repo) | HF updated 2025-09-11 | weights CC-BY-4.0 | **N** (en, fr) | **Y** | See C. | https://huggingface.co/kyutai/tts-1.6b-en_fr |
| PyThaiNLP/PyThaiTTS | Open Thai TTS library (loads KhanomTan, VachanaTTS, FastThaiG2P pipeline) | 112 | v0.8.0 @ 2026-10-11 (PyPI pythaitts 0.8.0) | Apache-2.0 (library; model licences differ) | **Y** | **Y** — "Real-time / Streaming TTS (FastThaiG2P)" for LLM streaming | Python ≥3.6. Thai number/text normalisation built in. | https://github.com/PyThaiNLP/PyThaiTTS |
| VYNCX/VachanaTTS (HF VIZINTZOR/VachanaTTS) | VITS-based Thai TTS, 4 voices (th_f_1, th_m_1, th_f_2, th_m_2), CPU or GPU, fine-tune UI | 27 | no release; last push 2025-09-14; HF updated 2025-09-18 | **repo has no LICENSE (null)**; HF model tagged MIT | **Y** | N (VITS, whole utterance; fast enough to chunk by sentence [A]) | Loadable via `pythaitts.TTS(pretrained="vachana")`. | https://github.com/VYNCX/VachanaTTS · https://huggingface.co/VIZINTZOR/VachanaTTS |
| wannaphong/khanomtan-tts-v1.0 | YourTTS multilingual (Thai + English) | 15 likes | 2022-08-25 | **CC-BY-NC-SA-3.0** (non-commercial) | **Y** | N | Old; non-commercial. | https://huggingface.co/wannaphong/khanomtan-tts-v1.0 |
| Typhoon TTS | **No standalone Typhoon TTS exists** (HF `scb10x` search for tts: none). Speech output only inside `llama3.1-typhoon2-audio-8b-instruct` (speech-output part CC-BY-NC). | — | — | — | Y | — | — | https://huggingface.co/scb10x |

---

## F. Inference serving

| Repo | What it does | Stars | Latest release + date | Licence | Audio-model support | Streaming | Notes | URL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vllm-project/vllm | High-throughput LLM / multimodal serving | 95,451 | v0.32.0 @ 2026-10-18 (PyPI vllm 0.32.0, `>=3.11,<3.15`, cp38-abi3 wheel) | Apache-2.0 | Audio-text: Ultravox, Qwen2-Audio, Qwen2.5-Omni, Qwen3-Omni, Kimi-Audio, Gemma 3n, MiniCPM-O, Voxtral; Transcription: Whisper, Qwen3-ASR, GLM-ASR, Voxtral, FunASR, Cohere-Transcribe … | Y (token streaming; Qwen2.5-Omni audio output) | The path for self-hosting Ultravox (Thai audio-in). | https://github.com/vllm-project/vllm · https://docs.vllm.ai/en/latest/models/supported_models/ |
| sgl-project/sglang | Fast serving framework (LLM / VLM / diffusion), RL rollouts | 38,138 | v0.5.22 @ 2026-10-19 (PyPI cp311–cp313 only) | Apache-2.0 | VLM yes; audio models not checked [A] | Y | No cp314 wheel yet. | https://github.com/sgl-project/sglang |
| NVIDIA/TensorRT-LLM | TensorRT-based LLM inference | 14,942 | v1.2.1 @ 2026-04-20 (tag v1.4.0rc1; PyPI tensorrt_llm 1.2.1, sdist, classifier 3.12) | NOASSERTION (Apache-2.0 + NVIDIA terms) | Whisper examples exist [A] | Y | Heavy toolchain; NIMs wrap it. | https://github.com/NVIDIA/TensorRT-LLM |
| NVIDIA Speech NIM (Riva ASR/TTS containers) | Prebuilt ASR/TTS microservices | n/a | docs "latest" (2026-10-25) | NVIDIA AI Enterprise licence | **Nemotron ASR Streaming NIM**: 40 locales, `language_code=auto`; tiers: 19 transcription-ready, 13 broad-coverage, 8 adaptation-ready — **Thai is adaptation-ready** (fine-tune first). Parakeet 0.6b TDT NIM: 25 European. | Y (streaming ASR, diarisation via Sortformer) | Parakeet 0.6b TDT NIM 13.75 GB GPU. FP8 builds need compute capability ≥8.9. | https://docs.nvidia.com/nim/speech/latest/reference/support-matrix/asr.html |
| triton-inference-server/server | Multi-framework inference server (ensembles, dynamic batching) | 11,111 | v2.73.0 @ 2026-09-30 | BSD-3-Clause | Any ONNX/TensorRT/PyTorch model (ASR/TTS as ensembles) | Y (gRPC streaming) | — | https://github.com/triton-inference-server/server |
| ggml-org/llama.cpp | CPU/GPU LLM inference in C/C++ (GGUF) | 132,315 | GitHub release v0.7.0 @ 2026-10-15 (build tag b11879) | MIT | Text LLMs; audio via separate projects | Y | — | https://github.com/ggml-org/llama.cpp |
| ggml-org/whisper.cpp | Whisper in C/C++ (CPU-only works; Metal/CUDA) | 54,657 | v1.9.5 @ 2026-10-06 | MIT | Whisper (99 langs incl. Thai) | partial ("stream" example, chunked) | medium model 1.5 GiB disk / ~2.1 GB RAM. | https://github.com/ggml-org/whisper.cpp |

---

## G. Transport

| Repo | What it does | Stars | Latest release + date | Licence | Voice receive | Notes | URL |
| --- | --- | --- | --- | --- | --- | --- | --- |
| aiortc/aiortc | WebRTC / ORTC in Python (asyncio) | 5,122 | tag 1.15.0 (PyPI 1.15.0, 2026-07-13) | BSD-3-Clause | Y (RTP in/out, Opus) | Python ≥3.10, pure-Python wheel (+ `av`, `pylibsrtp`). | https://github.com/aiortc/aiortc |
| Rapptz/discord.py | Discord API wrapper | 16,200 | tag v2.7.1 (PyPI 2.7.1, 2026-03-03) | MIT | **N in core** — RFC #1094 "Voice Receive API" open since 2018-02-20, 92 comments, last updated 2024-12-06 | v2.7.0 added **DAVE (E2EE) protocol support for voice connections** (`davey` dependency shown in `python -m discord --version` since 2.7.1). PyPI `>=3.8`, classifiers to 3.12 (pure Python, runs on newer [A]). | https://github.com/Rapptz/discord.py · https://github.com/Rapptz/discord.py/issues/1094 |
| imayhaveborkedit/discord-ext-voice-recv | Voice-receive extension for discord.py (`VoiceRecvClient`, `AudioSink`, Opus or PCM, `get_speaking()`) | 232 | PyPI 0.5.2a179 (2025-06-18, alpha); last commit 2025-06-18 | MIT | **Y** (the only discord.py option) | **Risk:** last commit predates discord.py 2.7's DAVE E2EE support; README has no DAVE mention — receive may break on DAVE-enabled channels until updated [A]. Dory's `meeting.py` depends on this family. | https://github.com/imayhaveborkedit/discord-ext-voice-recv |
| Pycord-Development/pycord | discord.py fork with built-in `Sinks` (`VoiceClient.start_recording`) | 2,963 | v2.8.1 @ 2026-07-25 (PyPI py-cord 2.8.1, `>=3.10,<3.15`) | MIT | **Y** (Sinks) | Docs warning: "Recording may not work as expected due to the new DAVE (End-to-End Encryption) for voice calls." | https://github.com/Pycord-Development/pycord · https://docs.pycord.dev/en/stable/api/voice.html |
| python-websockets/websockets | WebSocket client/server library | 5,738 | 17.3 @ 2026-10-19 (PyPI 17.3, cp311–cp315 + cp314t/cp315t) | BSD-3-Clause | n/a | `>=3.11`. Dory's `/live` socket. | https://github.com/python-websockets/websockets |
| livekit/livekit | Self-hostable WebRTC SFU + realtime stack (Go) | 21,802 | v1.13.11 @ 2026-10-25 | Apache-2.0 | Y (SFU) | Pair with livekit/agents or Pipecat's LiveKit transport. | https://github.com/livekit/livekit |

---

## H. Benchmarks, datasets and evaluation tools

| Item | What it measures | Stars / likes | Status (2026-10-25) | Licence | Thai | Notes | URL |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DanielLin94144/Full-Duplex-Bench | Turn-taking of full-duplex spoken dialogue models: v1 = Pause Handling, Backchanneling, Smooth Turn-Taking, User Interruption (metrics: Takeover Rate, latency, GPT-4o judge); v1.5 adds overlap (listener backchannel, side conversation, ambient speech); v2, v3 interactive | 330 | last commit 2026-05-20 | NOASSERTION | N (English) [A] | The benchmark NVIDIA PersonaPlex reports on. | https://github.com/DanielLin94144/Full-Duplex-Bench |
| MatthewCYM/VoiceBench (TACL'26) | LLM-based voice assistants: alpacaeval, commoneval, wildvoice, openbookqa, mmsu, sd-qa, mtbench, ifeval, bbh, advbench (speech-in, text judged) | 406 | last commit 2026-09-28 | Apache-2.0 | N (English) [A] | Python 3.10 env. | https://github.com/MatthewCYM/VoiceBench |
| Open ASR Leaderboard (hf-audio) | WER + RTFx on English short-form, long-form (earnings21/22, CORAAL) and a Multilingual set (FLEURS, MCV, MLS; Hindi via Voice Arena; Armenian via Metric-AI) | HF Space 1,509 likes; repo 271 stars | repo last commit 2026-10-21; runs on HF Jobs (H200) | Apache-2.0 | **N** — Thai is not in the multilingual set read today [A: not covered]; Typhoon ASR reports RTFx with its method | — | https://huggingface.co/spaces/hf-audio/open_asr_leaderboard · https://github.com/huggingface/open_asr_leaderboard |
| TTS Arena V2 (TTS-AGI) | Crowd-sourced blind A/B TTS preference | HF Space 983 likes | live | — | N (English-centric) [A] | — | https://huggingface.co/spaces/TTS-AGI/TTS-Arena-V2 |
| Artificial Analysis Speech Arena | Blind A/B TTS arena + provider/controlled-voice leaderboards | — | live (JS app; not scrapeable) | — | not stated | — | https://artificialanalysis.ai/text-to-speech/arena |
| Common Voice (Thai) | Crowd ASR corpus | — | **Moved**: "Effective October 2025, Mozilla Common Voice datasets are now exclusively available through Mozilla Data Collective" (HF `mozilla-foundation/common_voice_17_0` is empty) | CC0 (dataset) [A] | **Y** | Processed mirrors exist (e.g. `Porameht/processed-voice-th-169k`, used by F5-TTS-THAI). | https://datacollective.mozillafoundation.org · https://huggingface.co/datasets/mozilla-foundation/common_voice_17_0 |
| google/fleurs | 102-language read-speech benchmark | 493 likes | updated 2026-05-15 | CC-BY-4.0 | **Y** (`th_th` config) | Standard Thai eval set; used in Thonburian and Parakeet evaluations. | https://huggingface.co/datasets/google/fleurs |
| ekapolc/gowajee_corpus | Thai smart-home command corpus with "Gowajee" hotword (incl. a "ภาษาลู" slang set) | 21 | last commit 2023-07-30 | MIT | **Y** | Small, domain-specific. | https://github.com/ekapolc/gowajee_corpus |
| Thai elderly speech | `SEACrowd/thai_elderly_speech` (CC-BY-SA-4.0, 2024-06) and `Phonsiri/thai-elderly-speech` (2026-07, no licence tag; Healthcare + Smarthome domains, viewer errors) | 2 / 0 likes | available | CC-BY-SA-4.0 / unknown | **Y** | Pathumma-whisper cards report CER on it. | https://huggingface.co/datasets/SEACrowd/thai_elderly_speech · https://huggingface.co/datasets/Phonsiri/thai-elderly-speech |
| Porjai (CMKL) | ~300 h Thai central-dialect voice dataset (used by F5-TTS-THAI) | — | available | not read [A] | **Y** | — | https://huggingface.co/datasets/CMKL/Porjai-Thai-voice-dataset-central |
| jitsi/jiwer | WER / CER / MER / WIL | 939 | v4.0.0 @ 2025-06-19 (PyPI 4.0.0) | Apache-2.0 | n/a | **Thai has no word spaces**: tokenise with PyThaiNLP (newmm) or Deepcut before WER, and always report CER too (Thonburian uses Deepcut WER; Typhoon reports CER). | https://github.com/jitsi/jiwer |
| sarulab-speech/UTMOS22 | MOS prediction (SSL-based, VoiceMOS 2022 winner) | 314 | last commit 2024-04-11 | MIT | n/a (English-trained) | HF Space `sarulab-speech/UTMOS-demo`; PyPI `speechmos` 0.0.1.1 wraps it. | https://github.com/sarulab-speech/UTMOS22 |
| gabrielmittag/NISQA | Non-intrusive speech quality (v2.0: MOS + noisiness, coloration, discontinuity, loudness) and **NISQA-TTS naturalness** | 981 | last commit 2024-12-01 | MIT | n/a | — | https://github.com/gabrielmittag/NISQA |
| microsoft/DNS-Challenge (DNSMOS) | DNSMOS P.835 non-intrusive quality (SIG/BAK/OVRL) | 1,473 | last commit 2024-03-29 | CC-BY-4.0 | n/a | Use for the noise-suppression / capture-chain side. | https://github.com/microsoft/DNS-Challenge |

---

## Python compatibility (2026-10-25)

### CPython status (python.org/downloads, devguide, PEP 790)

| Version | Status | First released | Notes |
| --- | --- | --- | --- |
| 3.16 | pre-release (`main`) | planned 2027-10-06 (PEP 826) | — |
| **3.15** | bugfix | **3.15.0 final 2026-10-09** (PEP 790); **3.15.1** tarball is already on python.org/ftp (the PEP's "expected" 3.15.1 date was 2026-12-01, so an early point release shipped) | Two weeks old. |
| 3.14 | bugfix | 2025-10-07; latest on FTP **3.14.9** | — |
| 3.13 | security | 2024-10-07; 3.13.12 exists on FTP | security-only since Oct 2026 |
| **3.12** | security | 2023-10-02; 3.12.13 exists on FTP; EOL 2028-10 | Dory's current pin |
| 3.11 | security | EOL 2027-10 | — |
| 3.10 | **end-of-life 2026-10-01** (last 3.10.22) | — | — |

### Highest CPython each package supports (PyPI JSON, 2026-10-25)

"Wheels" = ABI tags on the latest release; "cls" = highest `Programming Language :: Python :: 3.x` classifier; "rp" = `requires_python`.

| Package | Latest (upload) | rp | cls max | Wheels | Free-threaded wheels | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| torch | 2.14.1 (2026-09-30) | ≥3.10 | 3.14 | cp310–cp314 | **cp314t** | ≤3.14 |
| torchaudio | 2.11.0 (2026-03-23) | — | 3.14 | cp310–cp314 | — | ≤3.14 (note: lags torch 2.14 by two releases) |
| numpy | 2.5.4 (2026-10-10) | ≥3.12 | 3.15 | cp312–cp315 | cp314t, cp315t | 3.12–3.15 |
| onnxruntime | 1.31.0 (2026-10-09) | ≥3.11 | 3.14 | cp311–cp314 | cp313t, cp314t | ≤3.14 |
| discord.py | 2.7.1 (2026-03-03) | ≥3.8 | 3.12 | py3 | n/a | pure Python; classifiers stop at 3.12 |
| py-cord | 2.8.1 (2026-07-25) | ≥3.10,<3.15 | 3.14 | py3 | n/a | ≤3.14 |
| discord-ext-voice-recv | 0.5.2a179 (2025-06-18) | ≥3.8 | 3.12 | py3 | n/a | alpha |
| PyNaCl | 1.6.2 (2026-01-01) | ≥3.8 | 3.14 | cp38-abi3, cp314 | cp314t | ≤3.14 |
| google-genai | 2.33.0 (2026-10-23) | ≥3.10 | 3.14 | py3 | n/a | ok |
| google-adk | 2.13.0 (2026-10-23) | ≥3.11 | 3.15 | py3 | n/a | ok |
| fastapi / uvicorn | 0.162.0 / 0.54.0 | ≥3.10 | 3.14 | py3 | n/a | ok |
| websockets | 17.3 (2026-10-19) | ≥3.11 | 3.15 | cp311–cp315 | cp314t, cp315t | ok |
| aiortc | 1.15.0 (2026-07-13) | ≥3.10 | 3.14 | py3 | n/a | ok |
| vllm | 0.32.0 (2026-10-18) | **≥3.11,<3.15** | 3.14 | cp38-abi3 | — | ≤3.14 |
| sglang | 0.5.22 (2026-10-16) | ≥3.11 | — | **cp311–cp313** | — | ≤3.13 |
| tensorrt_llm | 1.2.1 (2026-04-20) | ≥3.10,<4 | 3.12 | sdist | — | effectively 3.12 |
| nemo_toolkit | 3.0.0 (2026-08-07) | ≥3.10 | **3.10** | py3 | n/a | classifier only 3.10; works on 3.12 in practice [A] |
| faster-whisper / ctranslate2 | 1.2.1 (2025-10-31) / 4.8.3 (2026-10-13) | ≥3.9 | 3.11 / 3.14 | py3 / cp39–cp314 | ctranslate2 cp314t | ≤3.14 |
| silero-vad | 6.2.3 (2026-09-23) | ≥3.8 | 3.15 | py3 | n/a | ok (needs torch or onnxruntime) |
| sherpa-onnx | 2.0.0 (2026-10-23) | ≥3.7 | — | cp37–cp315 | none | ok |
| pipecat-ai | 1.14.0 (2026-10-24) | ≥3.11 | 3.14 | py3 | n/a | ok |
| livekit-agents | 1.8.9 (2026-10-24) | **≥3.10,<3.15** | 3.14 | py3 | n/a | ≤3.14 |
| nvidia-pipecat | 0.4.0 (2026-03-03) | **≥3.12** | — | py3 | n/a | ≥3.12 |
| kokoro | 0.9.4 (2025-04-05) | **≥3.10,<3.13** | — | py3 | n/a | **3.12 max** |
| whisper-streaming | 0.1.0 (2025-06-16) | ≥3.9,<3.13 | 3.12 | py3 | n/a | 3.12 max |
| moshi | 0.2.13 (2026-02-12) | ≥3.10,<3.15 | — | py3 | n/a | ≤3.14 |
| coqui-tts | 0.28.0 (2026-10-19) | ≥3.10,<3.15 | 3.14 | py3 | n/a | ≤3.14 |
| transformers | 5.20.2 (2026-10-19) | ≥3.10 | 3.14 | py3 | n/a | ok |

### Which Python to pin, and why

- **Pin 3.12 for the production voice stack today** (Dory already does, via uv). It is the only version where
  *every* package above has a wheel or an explicit range: `kokoro` and `whisper-streaming` stop at `<3.13`,
  `sglang` has no cp314 wheel, `tensorrt_llm` classifies only 3.12, `nvidia-pipecat` needs ≥3.12, and the big
  frameworks (`vllm`, `livekit-agents`, `py-cord`, `moshi`, `coqui-tts`) all exclude 3.15. 3.12 is in security-only
  maintenance (EOL 2028-10), which is acceptable for a pinned service image.
- **3.13** costs you Kokoro (pip) and whisper-streaming; **3.14** additionally costs sglang and TensorRT-LLM and is
  only two weeks into torch cp314 support; **3.15** (released 2026-10-09) has no torch/onnxruntime/vllm wheels yet.
  Plan the move 3.12 → 3.13/3.14 when Kokoro publishes a `>=3.13` release (or switch to `kokoro-onnx` /
  sherpa-onnx Kokoro, which has no such pin) and when vLLM lifts `<3.15`.
- **Free-threaded builds (3.13t/3.14t/3.15t): not yet for audio pipelines.** torch, numpy, onnxruntime, PyNaCl,
  ctranslate2, websockets, pillow, aiohttp and pydantic-core now publish `cp314t` wheels, but sherpa-onnx does
  not, and the CPython HOWTO states the GIL is **re-enabled automatically** when any extension not marked
  free-threading-safe is imported — so a mixed voice stack silently runs with the GIL anyway. Real-time audio in
  Python is best served by asyncio plus separate processes (ASR / TTS workers), which is how Pipecat and
  LiveKit Agents already work. Track https://py-free-threading.github.io/tracking/ and
  https://hugovk.github.io/free-threaded-wheels/ before reconsidering.

---

## Recommended open-source bill of materials for a Thai/English voice agent

Common constraints from the tables: (1) **no open end-of-turn model understands Thai** (Smart Turn v3, LiveKit
turn-detector, TEN Turn Detection all lack `th`), so Thai end-pointing must come from VAD + silence timing or
from the S2S model's own activity detection; (2) **no open S2S model speaks Thai**, so Thai output is always
TTS; (3) Thai WER needs a word segmenter — report CER.

### Tier 1 — Minimal-managed (what Dory ships today, hardened)

| Layer | Pick | Licence | Why |
| --- | --- | --- | --- |
| Brain + S2S | Gemini Live API (managed; `web_live.py` already) with its built-in `automatic_activity_detection`; text brain Nemotron 3 Super on Nebius Token Factory | commercial APIs | Thai in/out works today; zero GPU ops. |
| Client-side VAD | **silero-vad v6.2.3** (MIT, 6,000+ languages, <1 ms/chunk) in the browser-side/edge gate or bot | MIT | Cuts dead air sent to the API; language-agnostic so Thai is safe. |
| Transport | browser WebSocket (`websockets` 17.3) / WebRTC via **aiortc**; Discord via **discord.py 2.7.1 + discord-ext-voice-recv** | BSD-3 / MIT | Already in the codebase; watch the DAVE-E2EE compatibility of voice-recv (risk flagged in G). |
| Eval | **jiwer** + PyThaiNLP tokenisation, CER; FLEURS `th_th`; UTMOS/NISQA on TTS samples | Apache-2.0 / MIT | Cheap regression gate. |

### Tier 2 — Hybrid (open orchestration + open Thai STT/TTS, managed or Token-Factory LLM)

| Layer | Pick | Licence | Why |
| --- | --- | --- | --- |
| Orchestration | **Pipecat 1.14** (Python ≥3.11; BSD-2) — or LiveKit Agents 1.8.9 if you adopt a LiveKit SFU | BSD-2 / Apache-2.0 | Interruption handling, VAD, transports, telephony serialisers already built. |
| Streaming STT (Thai) | **Typhoon ASR Realtime** (NeMo FastConformer-Transducer 114M, 10k h Thai, CER 0.098, CC-BY-4.0); fallback **faster-whisper large-v3-turbo** (MIT) or **Thonburian whisper-large-v3** (Apache-2.0) for accuracy on long form | CC-BY-4.0 / MIT / Apache-2.0 | The only open *streaming* Thai ASR with a permissive licence. English: same Whisper or Nemotron ASR Streaming NIM. |
| Turn-taking | **silero-vad v6** end-pointing (tuned silence 400–700 ms for Thai [A]) + optional Smart Turn v3 **for English turns only** | MIT / BSD-2 | Nothing semantic exists for Thai; Krisp (paid) is the only "language-independent" turn-taking vendor claim. |
| LLM | Nemotron on Nebius Token Factory (existing) streaming tokens → sentence chunker | API | Keeps GPU-free. |
| TTS (Thai) | **PyThaiTTS 0.8.0** streaming path (Apache-2.0 lib; check each model's licence) with **VachanaTTS** (VITS, CPU-fast; HF MIT, repo licence missing) for latency, **F5-TTS-THAI** (CC-BY-4.0, GPU) for quality | Apache-2.0 / MIT / CC-BY-4.0 | Only permissive Thai voices found; KhanomTan is NC, Typhoon2-Audio speech-out is NC. |
| TTS (English) | **Kokoro-82M** (Apache-2.0, CPU; pin Python 3.12 or use kokoro-onnx) or **Chatterbox-Turbo 350M** (MIT, GPU) | Apache-2.0 / MIT | Low latency, permissive. |
| Serving | sherpa-onnx 2.0 (CPU ONNX for VAD/ASR/TTS) | Apache-2.0 | One runtime for edge + server; cp312–cp315 wheels. |

### Tier 3 — Fully self-hosted (one GPU, no external AI APIs)

| Layer | Pick | Licence | GPU | Why |
| --- | --- | --- | --- | --- |
| Speech understanding + brain | **Ultravox v0.5 (Llama-3.1-8B)** served by **vLLM 0.32** — audio in (42 languages incl. **Thai**), streaming text out | MIT / Apache-2.0 | ~16 GB bf16, 24 GB card comfortable [A] | The only open audio-LLM with Thai input and a commercial licence; skips a separate ASR hop. Alternative: Typhoon ASR Realtime → text LLM (Nemotron GGUF via llama.cpp or a vLLM-served open LLM). |
| Full-duplex option (English only) | **Moshi** (Apache-2.0 code / CC-BY-4.0 weights, 24 GB, ~200 ms) or **Unmute** (MIT, 16 GB, STT→LLM→TTS en/fr) | Apache-2.0 / MIT | 16–24 GB | For an English-only demo of true barge-in; **not Thai**. |
| VAD / turn | silero-vad v6 (+ TEN VAD for faster speech→silence transitions; Apache-2.0 with conditions) | MIT | CPU | — |
| TTS | Thai: F5-TTS-THAI (CC-BY-4.0) or VachanaTTS (VITS); English: Orpheus-3B (Apache-2.0, ~200 ms streaming, vLLM) or Chatterbox | mixed | 4–8 GB | Keep Thai and English voices separate; no open multilingual model covers Thai. |
| Transport | LiveKit server v1.13 (Apache-2.0, Go) + livekit/agents, or aiortc for a pure-Python WebRTC path; Discord via discord.py + voice-recv | Apache-2.0 / BSD-3 / MIT | — | — |
| Serving / runtime | vLLM (LLM + Ultravox), sherpa-onnx (ASR/VAD/TTS on CPU), Triton if you need ensembles | Apache-2.0 / BSD-3 | — | — |
| Eval | jiwer (+PyThaiNLP) CER/WER on FLEURS th_th + Gowajee + Thai-elderly; VoiceBench (English) for the brain; Full-Duplex-Bench only for the Moshi demo; UTMOS / NISQA-TTS / DNSMOS for audio quality | Apache-2.0 / MIT / CC-BY-4.0 | — | — |

**Runtime:** Python **3.12** for all three tiers (see above). Budget one 24 GB GPU (L4/A10/4090-class) for Tier 3;
Tier 2 runs on CPU plus a small GPU for F5-TTS-THAI; Tier 1 needs no GPU.

---

## What was not verified today

- Qwen2.5-Omni GPU table rows, Step-Audio-2-mini parameter count, TEN Turn Detection and Baichuan-Audio language
  lists, Open ASR Leaderboard's exact multilingual language set, Porjai licence, discord-ext-voice-recv behaviour
  with DAVE E2EE, and whether Typhoon ASR Realtime uses cache-aware (chunked) streaming — all marked [A].
- `nvidia/nemotron-3.5-asr-streaming-0.6b` on HF returned 401 (gated); its Thai tier comes from the NIM support
  matrix instead. `scb10x/typhoon-asr` has no GitHub repo (GraphQL: MISSING); the HF card is the source.
- `stepfun-ai/Step-Audio` shows 44 stars and an empty description, suggesting the original repo was moved or
  emptied; the number is what the API returned.
