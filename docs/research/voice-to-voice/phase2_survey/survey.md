# Phase 2 — Survey (2022–2026): real-time voice-to-voice conversational AI

Scope: end-to-end speech-to-speech and full-duplex spoken dialogue models vs modular ASR → LLM → TTS pipelines; streaming ASR; streaming TTS; turn-taking / end-of-turn detection; barge-in; latency and evaluation benchmarks; Thai / Southeast Asian speech. Date: 2026-10-25.

## How this database was built

- Sources: arXiv API searches for Phase 1 (2025-01-01 →, 9 queries) and Phase 2 (2022–2024 window, 10 queries), targeted arXiv id fetches of seminal works and of papers surfaced by WebSearch over accepted-paper lists (Interspeech 2025/2026, ICASSP 2026, ICLR 2025/2026, ICML 2025, ACL 2025/2026, ASRU 2025, SLT 2026, SIGDIAL 2025/2026, NeurIPS 2025). Raw files: `phase1_frontier/search_results/*.jsonl`, `phase2_survey/search_results/*.jsonl`.
- Merge + dedupe with the skill's `paper_db.py merge` (title Jaccard ≥ 0.8): 503 records → 361 unique (`paper_db_all_unfiltered.jsonl`). Curated to the **80** most relevant (`paper_db.jsonl`), tagged `e2e_s2s`, `full_duplex`, `streaming_asr`, `streaming_tts`, `turn_taking`, `benchmark`, `thai_lowresource`, `architecture_survey`.
- Venue / peer-review: from the arXiv record's comment field ("Accepted to …"), from proceedings pages found by WebSearch, or (5 records, marked "per OpenAlex") from OpenAlex's primary location. "Submitted to" counts as preprint. A technical report is a preprint even when a companion demo paper exists (MERaLiON is marked by its ACL 2025 demo).
- Citation counts: Semantic Scholar's unauthenticated API answered HTTP 429 to every request during the run (search and batch endpoints), so counts are **OpenAlex `cited_by_count`** matched on title (Jaccard ≥ 0.8), `citation_source: openalex`; 5 records had no match and keep `null`. OpenAlex undercounts arXiv-only preprints relative to Semantic Scholar, so treat small numbers as lower bounds, not rankings.

## Taxonomy

```
Real-time voice-to-voice conversational AI
├── Architecture
│   ├── Modular cascade  ASR → LLM → TTS   (+ VAD / EOT / barge-in controller)        C4, C5, C6, DuplexCascade (C3)
│   ├── Hybrid           speech encoder → LLM with text trace → streaming TTS        Stream-Omni, Freeze-Omni, LLaMA-Omni (C2)
│   └── End-to-end       speech tokens in / speech tokens out
│       ├── half-duplex (turn-based, external VAD)                                    C2
│       └── full-duplex (listens while speaking)                                      C3
│           ├── learned synchronisation in one LM     Moshi, SyncLLM, NTPP, BayLing-Duplex
│           ├── converted from half-duplex / text LLM  SALM-Duplex, D2, LSLM
│           └── engineered synchronisation (modular)   Duplex Conversation 2022, DuplexCascade
├── Streaming components      streaming ASR (C4) · streaming TTS (C5) · turn-taking / EOT / barge-in (C6)
├── Evaluation                assistant quality · turn-taking dynamics · overlap / barge-in · multi-round · tool use (C7)
└── Language coverage         Thai / SEA / low-resource data, encoders, LLMs, TTS (C8)
```

## C1 · Foundations: spoken language models and audio-understanding LLMs (2022–2023)

Where the vocabulary comes from: discrete speech units, textless dialogue generation, and the first LLMs that take audio tokens. Whisper is here because it is the encoder every later Thai system (Thonburian Whisper, Typhoon-Audio, MERaLiON) starts from.

| key | title | year | venue | peer-reviewed | citations (OpenAlex) | one-line finding |
|---|---|---|---|---|---|---|
| 2212.04356 | Robust Speech Recognition via Large-Scale Weak Supervision | 2022 | ICML 2023 | yes | 1953 | 680k h of weakly supervised multilingual data gives robust zero-shot ASR; offline encoder-decoder, so streaming needs a wrapper (C4) and Thai needs fine-tuning. |
| 2203.16502 | Generative Spoken Dialogue Language Modeling | 2022 | TACL 2023 | yes | 58 | dGSLM: first textless model generating two-channel naturalistic dialogue (dual-tower transformer, 2k h Fisher), learning overlaps and backchannels without text. |
| 2305.11000 | SpeechGPT: Empowering Large Language Models with Intrinsic Cross-Modal Conversational Abilities | 2023 | Findings of EMNLP 2023 | yes | 189 | Discrete speech units + LLM with modality-adaptation → cross-modal instruction → chain-of-modality training; argues cascades block inter-modal knowledge transfer. |
| 2306.12925 | AudioPaLM: A Large Language Model That Can Speak and Listen | 2023 | arXiv (preprint) | no (preprint) | 81 | Fuses PaLM-2 and AudioLM into one decoder over text and audio tokens; text-LLM knowledge transfers to speech translation / ASR. |
| 2310.13289 | SALMONN: Towards Generic Hearing Abilities for Large Language Models | 2023 | ICLR 2024 | yes | 67 | Whisper + BEATs encoders into an LLM give 'generic hearing' (speech, audio events, music) with emergent abilities. |

## C2 · Half-duplex end-to-end speech-to-speech assistants (2024–2025)

The GPT-4o-inspired wave: speech encoder → LLM → streaming speech decoder, mostly *text-anchored* (text tokens generated in parallel or interleaved with speech tokens so the LLM keeps its knowledge). Turn-taking is still handled by an external VAD in most of these; MOSS-Speech is the text-free counter-position.

| key | title | year | venue | peer-reviewed | citations (OpenAlex) | one-line finding |
|---|---|---|---|---|---|---|
| 2408.16725 | Mini-Omni: Language Models Can Hear, Talk While Thinking in Streaming | 2024 | arXiv (preprint) | no (preprint) | 4 | Parallel text + audio token generation ('talk while thinking') so an LLM speaks in streaming; text-guided batch decoding keeps reasoning. |
| 2409.06666 | LLaMA-Omni: Seamless Speech Interaction with Large Language Models | 2024 | ICLR 2025 | yes | 4 | Speech encoder → Llama-3.1-8B → streaming CTC speech decoder; a low-latency recipe for building S2S on an open LLM (ICLR 2025). |
| 2411.00774 | Freeze-Omni: A Smart and Low Latency Speech-to-speech Dialogue Model with Frozen LLM | 2024 | arXiv (preprint) | no (preprint) | 4 | Trains speech input/output around a *frozen* LLM so the text model's intelligence is untouched; the design to copy when the LLM must stay as is. |
| 2412.02612 | GLM-4-Voice: Towards Intelligent and Human-Like End-to-End Spoken Chatbot | 2024 | arXiv (preprint) | no (preprint) | 4 | Chinese/English e2e chatbot on a 175 bps single-codebook tokenizer; instruction-controlled emotion, intonation, rate and dialect. |
| 2502.11946 | Step-Audio: Unified Understanding and Generation in Intelligent Speech Interaction | 2025 | arXiv (preprint) | no (preprint) | 2 | Open production framework: unified speech-text model, real-time pipeline and a voice-data generation engine to cut data cost. |
| 2502.17239 | Baichuan-Audio: A Unified Framework for End-to-End Speech Interaction | 2025 | arXiv (preprint) | no (preprint) | 2 | Text-guided aligned speech generation with a pre-trained-ASR-based tokenizer; real-time comprehension + generation. |
| 2504.18425 | Kimi-Audio Technical Report | 2025 | arXiv (preprint) | no (preprint) | 2 | Open audio foundation model on a 12.5 Hz tokenizer covering understanding, generation and conversation; details the deployment recipe. |
| 2501.01957 | VITA-1.5: Towards GPT-4o Level Real-Time Vision and Speech Interaction | 2025 | NeurIPS 2025 | yes | 11 | Three-stage training adds speech to a vision-language MLLM for real-time vision + speech interaction (NeurIPS 2025 spotlight). |
| 2501.06282 | MinMo: A Multimodal Large Language Model for Seamless Voice Interaction | 2025 | arXiv (preprint) | no (preprint) | n/a | Frames the field as 'native' vs 'aligned' voice models and builds an aligned (text-LLM-centred) model for seamless voice interaction. |
| 2503.20215 | Qwen2.5-Omni Technical Report | 2025 | arXiv (preprint) | no (preprint) | n/a | Thinker–Talker split with block-wise streaming encoders: text and speech responses stream simultaneously from one omni model. |
| 2505.02707 | Voila: Voice-Language Foundation Models for Real-Time Autonomous Interaction and Voice Role-Play | 2025 | arXiv (preprint) | no (preprint) | 2 | Autonomous voice agent that continuously listens, reasons and responds proactively rather than waiting for commands. |
| 2506.13642 | Stream-Omni: Simultaneous Multimodal Interactions with Large Language-Vision-Speech Model | 2025 | arXiv (preprint) | no (preprint) | n/a | Aligns speech to the LLM along the *layer* dimension (CTC) so speech interaction yields intermediate text, a hybrid between cascade and e2e. |
| 2510.00499 | MOSS-Speech: Towards True Speech-to-Speech Models Without Text Guidance | 2025 | arXiv (preprint) | no (preprint) | 0 | True speech-to-speech without text intermediates; argues text guidance is a bottleneck for paralinguistics and expressivity. |

## C3 · Full-duplex spoken dialogue: listen while speaking (2022–2026)

From engineered duplex behaviour in a production call agent (2022) to learned synchronisation in one LM (Moshi, SyncLLM, NTPP) and, in 2025–2026, to converting existing half-duplex / text LLMs into duplex ones (SALM-Duplex, D2, BayLing-Duplex). DuplexCascade is the cascade answer to the same problem; two surveys organise the space.

| key | title | year | venue | peer-reviewed | citations (OpenAlex) | one-line finding |
|---|---|---|---|---|---|---|
| 2205.15060 | Duplex Conversation: Towards Human-like Interaction in Spoken Dialogue Systems | 2022 | KDD 2022 | yes | 16 | Alibaba's telephone agent engineers full-duplex behaviour (user-state detection, backchannels, barge-in) from modular parts, KDD 2022. |
| 2408.02622 | Language Model Can Listen While Speaking | 2024 | AAAI (per OpenAlex) | yes | 8 | LSLM adds a listening channel to a speaking LM and fuses them (early / middle / late) to detect interruptions while talking. |
| 2409.15594 | Beyond Turn-Based Interfaces: Synchronous LLMs as Full-Duplex Dialogue Agents | 2024 | EMNLP 2024 | yes | 10 | SyncLLM: a text LLM predicts time-synchronised interleaved speech units, trained on synthetic duplex data (EMNLP 2024). |
| 2410.00037 | Moshi: a speech-text foundation model for real-time dialogue | 2024 | arXiv (preprint) | no (preprint) | 9 | Dual user / assistant audio streams plus an 'Inner Monologue' text stream over the 12.5 Hz Mimi codec; 160 ms theoretical, ~200 ms practical latency. |
| 2506.00975 | NTPP: Generative Speech Language Modeling for Dual-Channel Spoken Dialogue via Next-Token-Pair Prediction | 2025 | ICML 2025 | yes | 0 | Next-token-*pair* prediction models both dialogue channels per step, exploiting dual-channel data (ICML 2025). |
| 2505.15670 | SALM-Duplex: Efficient and Direct Duplex Modeling for Speech-to-Speech Language Model | 2025 | Interspeech 2025 | yes | 0 | Continuous user input + codec agent output fused per channel; described as the first open duplex S2S model with training and inference code (Interspeech 2025). |
| 2510.05150 | Chronological Thinking in Full-Duplex Spoken Dialogue Language Models | 2025 | SIGDIAL 2026 | yes | 1 | Uses the listening phase to reason incrementally so the answer is ready at turn end, recovering thinking time without added latency (SIGDIAL 2026). |
| 2510.02066 | Chain-of-Thought Reasoning in Streaming Full-Duplex End-to-End Spoken Dialogue Systems | 2025 | arXiv (preprint) | no (preprint) | 0 | Adds chain-of-thought to a streaming duplex E2E SDS; states that duplex models drop VAD via silence tokens but lag cascades in reasoning. |
| 2606.14528 | BayLing-Duplex: Native Full-Duplex Speech Dialogue with a Single Autoregressive LLM | 2026 | arXiv (preprint) | no (preprint) | 0 | Native duplex in a single autoregressive LLM, no external VAD; handles overlap, hesitation and barge-in; code released. |
| 2610.17124 | D2: High-Capability Full-Duplex Spoken Language Models from Half-Duplex Backbones | 2026 | arXiv (preprint) | no (preprint) | 0 | Dialogue-to-Duplex converts a pretrained half-duplex SLM into a full-duplex one via decoder-free distillation of a streaming encoder. |
| 2603.09180 | DuplexCascade: Full-Duplex Speech-to-Speech Dialogue with VAD-Free Cascaded ASR-LLM-TTS Pipeline and Micro-Turn Optimization | 2026 | arXiv (preprint) | no (preprint) | 1 | VAD-free cascaded ASR-LLM-TTS with micro-turn optimisation: keeps LLM intelligence while reaching full-duplex behaviour. |
| 2509.14515 | From Turn-Taking to Synchronous Dialogue: A Survey of Full-Duplex Spoken Language Models | 2025 | arXiv (preprint) | no (preprint) | 0 | Survey: engineered (modular) vs learned (e2e) synchronisation; evaluation along temporal, behavioural, semantic and acoustic axes. |
| 2606.19453 | A Survey of Full-Duplex Spoken Dialogue Systems: Architectural Hierarchy, Interaction Ontology, and Decision State Machine | 2026 | arXiv (preprint) | no (preprint) | 0 | Survey: 'full-duplex' names different capabilities; proposes an architectural hierarchy, interaction ontology and decision state machine for builders. |

## C4 · Streaming ASR: encoders, transducers and LLM decoders

What a modular pipeline uses for the ear. NVIDIA's FastConformer + TDT (Parakeet / Canary) and k2's Zipformer define the efficient streaming encoder; the transducer loss family controls emission latency; 2025–2026 work streams decoder-only LLM ASR. Typhoon ASR Real-time is the Thai instance of exactly this recipe.

| key | title | year | venue | peer-reviewed | citations (OpenAlex) | one-line finding |
|---|---|---|---|---|---|---|
| 2305.05084 | Fast Conformer with Linearly Scalable Attention for Efficient Speech Recognition | 2023 | ASRU 2023 | yes | 96 | Redesigned downsampling gives a Conformer 2.8x faster with linearly scalable attention; backbone of Parakeet and Canary (ASRU 2023). |
| 2304.06795 | Efficient Sequence Transduction by Jointly Predicting Tokens and Durations | 2023 | ICML 2023 | yes | 12 | Token-and-Duration Transducer predicts a token and how many frames it covers, skipping frames for faster streaming decoding (ICML 2023). |
| 2406.19674 | Less is More: Accurate Speech Recognition & Translation without Web-Scale Data | 2024 | Interspeech 2024 | yes | 33 | Canary (FastConformer + Transformer decoder) beats Whisper / OWSM / Seamless on ASR + AST with far less than web-scale data (Interspeech 2024). |
| 2310.11230 | Zipformer: A faster and better encoder for automatic speech recognition | 2023 | ICLR 2024 | yes | 52 | U-Net-style temporally downsampled encoder stacks: faster, lighter and more accurate than Conformer; streaming variants in k2 (ICLR 2024). |
| 2211.00490 | Delay-penalized transducer for low-latency streaming ASR | 2022 | ICASSP 2023 | yes | 7 | A simple delay penalty in the transducer loss trades emission latency for accuracy without external alignments (ICASSP 2023). |
| 2307.14743 | Turning Whisper into Real-Time Transcription System | 2023 | IJCNLP-AACL 2023 | yes | 30 | Whisper-Streaming: LocalAgreement policy turns offline Whisper into a real-time transcriber, at the cost of seconds of latency. |
| 2509.08753 | Streaming Sequence-to-Sequence Learning with Delayed Streams Modeling | 2025 | arXiv (preprint) | no (preprint) | 1 | Delayed Streams Modeling: a general streaming seq2seq formulation (delay the output stream relative to the input) behind Kyutai's STT/TTS. |
| 2601.22779 | Streaming Speech Recognition with Decoder-Only Large Language Models and Latency Optimization | 2026 | ICASSP 2026 | yes | 0 | Read/write policy network + monotonic chunkwise attention make a decoder-only LLM ASR streaming, with explicit latency optimisation (ICASSP 2026). |
| 2510.00982 | Spiralformer: Low Latency Encoder for Streaming Speech Recognition with Circular Layer Skipping and Early Exiting | 2025 | ASRU 2025 | yes | 0 | Circular layer skipping and early exiting cut *encoding* latency of block processing with small chunk shifts (ASRU 2025). |
| 2601.13044 | Typhoon ASR Real-time: FastConformer-Transducer for Thai Automatic Speech Recognition | 2026 | arXiv (preprint) | no (preprint) | 0 | 115M FastConformer-Transducer for Thai: ~45x less compute than Whisper-large-v3 at comparable accuracy; Thai normalisation, Isan curriculum, public benchmark. |

## C5 · Streaming TTS that starts on partial text

Utterance-level TTS adds a full sentence of delay after the LLM's first token. The fix is TTS trained on interleaved text/speech streams (IST-LM, SpeakStream), LLM-agnostic streaming decoders (LLMVoX), chunk-aware flow matching (CosyVoice 2) and alignment-free dual streaming (CTC-TTS).

| key | title | year | venue | peer-reviewed | citations (OpenAlex) | one-line finding |
|---|---|---|---|---|---|---|
| 2412.10117 | CosyVoice 2: Scalable Streaming Speech Synthesis with Large Language Models | 2024 | arXiv (preprint) | no (preprint) | 5 | FSQ speech tokens + chunk-aware causal flow matching give one model for streaming and non-streaming synthesis with minimal first-packet delay. |
| 2406.02897 | LiveSpeech: Low-Latency Zero-shot Text-to-Speech via Autoregressive Modeling of Audio Discrete Codes | 2024 | Interspeech (per OpenAlex) | yes | 7 | Fully autoregressive codec LM for low-latency zero-shot TTS (adaptive codebook loss weights, grouped parallel codebooks). |
| 2412.16102 | Interleaved Speech-Text Language Models for Simple Streaming Text-to-Speech Synthesis | 2024 | arXiv (preprint) | no (preprint) | 0 | Trains on fixed-ratio interleaved text/speech tokens, so streaming TTS needs no forced alignment or special design. |
| 2505.19206 | SpeakStream: Streaming Text-to-Speech with Interleaved Data | 2025 | arXiv (preprint) | no (preprint) | 0 | Decoder-only streaming TTS on interleaved data that starts speaking from partial LLM output; names utterance-level TTS as the latency bottleneck. |
| 2503.04724 | LLMVoX: Autoregressive Streaming Text-to-Speech Model for Any LLM | 2025 | ACL 2025 | yes | 0 | 30M-parameter LLM-agnostic streaming TTS: no LLM fine-tuning, low latency, keeps the LLM's text quality (ACL 2025). |
| 2502.11094 | SyncSpeech: Efficient and Low-Latency Text-to-Speech based on Temporal Masked Transformer | 2025 | ICASSP (per OpenAlex) | yes | 0 | Temporal Masked Transformer bridges slow AR and high-first-packet-latency NAR TTS for efficient low-latency synthesis. |
| 2602.19574 | CTC-TTS: LLM-based dual-streaming text-to-speech with CTC alignment | 2026 | INTERSPEECH 2026 | yes | 0 | CTC alignment replaces MFA-style forced alignment for LLM-based dual-streaming TTS (Interspeech 2026); useful where no aligner exists (Thai). |

## C6 · Turn-taking, end-of-turn detection and barge-in

The component both camps still need. Text-only (TurnGPT) → self-supervised audio (VAP, real-time and multilingual VAP) → semantic endpointing (Semantic VAD) → 2025–2026 production EOT models that fuse acoustic, prosodic and lexical cues, handle multi-speaker rooms and classify interruptions vs backchannels.

| key | title | year | venue | peer-reviewed | citations (OpenAlex) | one-line finding |
|---|---|---|---|---|---|---|
| 2010.10874 | TurnGPT: a Transformer-based Language Model for Predicting Turn-taking in Spoken Dialog | 2020 | Findings of EMNLP 2020 | yes | 54 | Transformer LM predicts turn shifts from syntactic / pragmatic completeness of the transcript; text-only turn-taking. |
| 2205.09812 | Voice Activity Projection: Self-supervised Learning of Turn-taking Events | 2022 | Interspeech 2022 | yes | 44 | Voice Activity Projection: self-supervised prediction of both speakers' future voice activity from stereo audio, no labels. |
| 2401.04868 | Real-time and Continuous Turn-taking Prediction Using Voice Activity Projection | 2024 | IWSDS 2024 | yes | 4 | Real-time, continuous CPU demo of VAP (CPC + transformers) usable as a drop-in turn-taking module (IWSDS 2024). |
| 2403.06487 | Multilingual Turn-taking Prediction Using Voice Activity Projection | 2024 | LREC-COLING 2024 | yes | 13 | Tests whether one VAP model transfers across English, Mandarin and Japanese dialogue data (LREC-COLING 2024). |
| 2305.12450 | Semantic VAD: Low-Latency Voice Activity Detection for Speech Interaction | 2023 | Interspeech 2023 | yes | 8 | Replaces fixed tail-silence endpointing with semantic completeness to cut end-of-turn latency (Interspeech 2023). |
| 2503.23439 | Speculative End-Turn Detector for Efficient Speech Chatbot Assistant | 2025 | ACL 2026 | yes | 0 | Speculative end-turn detector separates turn completion from hesitation; releases the OpenETD dataset (ACL 2026). |
| 2603.13379 | A Hierarchical End-of-Turn Model with Primary Speaker Segmentation for Real-Time Conversational AI | 2026 | IEEE CAI 2026 | yes | 0 | Meta's production front end: primary-speaker segmentation plus a causal hierarchical EOT model over user and bot features. |
| 2609.11066 | Less can be More: What Aspects of Speech Drive End-of-Turn Detection | 2026 | arXiv (preprint) | no (preprint) | 0 | Controlled ablation of acoustic / prosodic / semantic cues in a streaming trimodal EOT classifier; acoustic + prosodic gives the best accuracy–latency balance. |
| 2601.13835 | The Role of Prosodic and Lexical Cues in Turn-Taking with Self-Supervised Speech Representations | 2026 | ICASSP 2026 | yes | 0 | Vocoder-based control of prosody vs lexical content probes what S3R-based VAP models rely on (ICASSP 2026). |
| 2603.26515 | JAL-Turn: Joint Acoustic-Linguistic Modeling for Real-Time and Robust Turn-Taking Detection in Full-Duplex Spoken Dialogue Systems | 2026 | NCMMSC 2026 | yes | 0 | Lightweight speech-only joint acoustic–linguistic turn-taking for industrial agents, avoiding a full-duplex LLM. |
| 2506.21191 | Prompt-Guided Turn-Taking Prediction | 2025 | SIGdial 2025 | yes | n/a | VAP-style turn-taking prediction controlled by textual prompts (wait longer / respond faster) (SIGDIAL 2025). |
| 2603.24144 | Semantic-Aware Interruption Detection in Spoken Dialogue Systems: Benchmark, Metric, and Model | 2026 | ICME 2026 | yes | 0 | Benchmark, metric and model for semantic interruption detection: VAD is 'trigger-happy' on backchannels, e2e models too slow (ICME 2026). |

## C7 · Benchmarks and evaluation of voice assistants and duplex behaviour

Assistant-level quality (VoiceBench, URO-Bench, ParaS2S) and interaction-level behaviour (Talking Turns, TurnBench, Full-Duplex-Bench v1 / v1.5 / v3, FD-Bench, MTR-DuplexBench). Note the two unrelated 'FDB' series.

| key | title | year | venue | peer-reviewed | citations (OpenAlex) | one-line finding |
|---|---|---|---|---|---|---|
| 2410.17196 | VoiceBench: Benchmarking LLM-Based Voice Assistants | 2024 | TACL (per OpenAlex) | yes | 12 | First multi-facet benchmark for LLM-based voice assistants: knowledge, instruction following and safety under speaker / environment / content variation. |
| 2502.17810 | URO-Bench: Towards Comprehensive Evaluation for End-to-End Spoken Dialogue Models | 2025 | arXiv (preprint) | no (preprint) | 7 | Evaluates e2e spoken dialogue models on cognitive (reasoning, knowledge) and speech (paralinguistics, audio quality) dimensions. |
| 2511.08723 | ParaS2S: Benchmarking and Aligning Spoken Language Models for Paralinguistic-aware Speech-to-Speech Interaction | 2025 | ICLR 2026 | yes | 0 | Benchmark + RL alignment for paralinguistic-aware speech-to-speech responses (ICLR 2026). |
| 2503.01174 | Talking Turns: Benchmarking Audio Foundation Models on Turn-Taking Dynamics | 2025 | ICLR 2025 | yes | 1 | Protocol to score audio foundation models on fluent turn succession and overlap (ICLR 2025). |
| 2608.25218 | TurnBench: A Multi-Domain Benchmark for Turn-Taking Dynamics in Spoken Dialogue | 2026 | SLT 2026 | yes | 0 | 30-hour hand-labelled multi-domain corpus and protocol for take / hold / yield decisions (SLT 2026). |
| 2503.04721 | Full-Duplex-Bench: A Benchmark to Evaluate Full-duplex Spoken Dialogue Models on Turn-taking Capabilities | 2025 | ASRU 2025 | yes | 8 | Automatic metrics for pause handling, backchannelling, turn-taking and interruption in full-duplex models (ASRU 2025). |
| 2507.23159 | Full-Duplex-Bench v1.5: Evaluating Overlap Handling for Full-Duplex Speech Models | 2025 | ICASSP 2026 | yes | 0 | Overlap handling (interruption, backchannel, side talk, ambient speech) with stop / response latency; finds 'responsive' vs 'floor-holding' strategies (ICASSP 2026). |
| 2604.04847 | Full-Duplex-Bench-v3: Benchmarking Tool Use for Full-Duplex Voice Agents Under Real-World Disfluency | 2026 | arXiv (preprint) | no (preprint) | 0 | Real human audio with five disfluency types plus chained tool calls; evaluates GPT-Realtime and Gemini Live among six configurations. |
| 2507.19040 | FD-Bench: A Full-Duplex Benchmarking Pipeline Designed for Full Duplex Spoken Dialogue Systems | 2025 | Interspeech 2025 | yes | 2 | LLM-simulated multi-round conversations + TTS/ASR/Silero-VAD to score interruption handling and response quality of Moshi, Freeze-Omni, VITA-1.5 (Interspeech 2025). |
| 2511.10262 | MTR-DuplexBench: Towards a Comprehensive Evaluation of Multi-Round Conversations for Full-Duplex Speech Language Models | 2025 | ACL 2026 | yes | 1 | Multi-round evaluation of full-duplex SLMs (turn segmentation, quality, instruction following, safety); models drift across rounds (Findings of ACL 2026). |

## C8 · Thai, Southeast Asian and low-resource speech

Data (MMS, GigaSpeech 2), Thai LLM / audio-LLM families (Typhoon 2, Typhoon-Audio, SeaLLMs-Audio, MERaLiON for Singapore), diagnosis of why speech LLMs fail on Thai (Thai-SUP / XLSR-Thai), speech-instruction training without TTS (Speechless) and the 2025–2026 Thai TTS work (JaiTTS, fixed-voice distillation). Typhoon ASR Real-time (C4) belongs here too.

| key | title | year | venue | peer-reviewed | citations (OpenAlex) | one-line finding |
|---|---|---|---|---|---|---|
| 2305.13516 | Scaling Speech Technology to 1,000+ Languages | 2023 | JMLR 2024 | yes | n/a | MMS: ASR, TTS and LID for 1,000+ languages from wav2vec 2.0 pretraining; includes Thai models (JMLR 2024). |
| 2406.11546 | GigaSpeech 2: An Evolving, Large-Scale and Multi-domain ASR Corpus for Low-Resource Languages with Automated Crawling, Transcription and Refinement | 2024 | ACL 2025 | yes | 8 | Large multi-domain ASR corpus for low-resource languages built from unlabelled audio with an automatic pipeline (ACL 2025). |
| 2412.13702 | Typhoon 2: A Family of Open Text and Multimodal Thai Large Language Models | 2024 | arXiv (preprint) | no (preprint) | 1 | Open Thai LLM family (text, vision, audio); Typhoon2-Audio is an end-to-end speech-to-speech model with simultaneous text and speech output. |
| 2409.10999 | Enhancing Low-Resource Language and Instruction Following Capabilities of Audio Language Models | 2024 | Interspeech 2025 | yes | 3 | Audio LMs lack emergent cross-lingual ability on Thai despite multilingual parts; builds Typhoon-Audio to fix it (Interspeech 2025). |
| 2412.09818 | MERaLiON-AudioLLM: Bridging Audio and Language with Large Language Models | 2024 | ACL 2025 System Demonstrations (companion paper) | yes | 0 | Singapore-centric audio LLM (localised Whisper encoder + LLM) for Singlish, Malay, Tamil, Mandarin; regional precedent. |
| 2511.01670 | SeaLLMs-Audio: Large Audio-Language Models for Southeast Asia | 2025 | arXiv (preprint) | no (preprint) | 0 | First audio LLM for Indonesian, Thai and Vietnamese (+ en, zh) with voice interaction, plus the SeaBench-Audio benchmark. |
| 2509.14804 | Towards Building Speech Large Language Models for Multitask Understanding in Low-Resource Languages | 2025 | ICASSP (per OpenAlex) | yes | 1 | Whisper-family encoders underperform on Thai and no Thai SLU data exists; builds XLSR-Thai, the Thai-SUP synthetic pipeline and U-Align. |
| 2505.17417 | Speechless: Speech Instruction Training Without Speech for Low Resource Languages | 2025 | INTERSPEECH 2025 | yes | 1 | Speech-instruction training without TTS by aligning text to semantic speech tokens, for languages with weak TTS (Interspeech 2025). |
| 2604.27607 | JaiTTS: A Thai Voice Cloning Model | 2026 | arXiv (preprint) | no (preprint) | 0 | Thai voice-cloning TTS adapted from VoxCPM; handles numerals and Thai–English code-switching without text normalisation. |
| 2609.03502 | Building and Evaluating Fixed-Voice Thai TTS from Synthetic Speech | 2026 | arXiv (preprint) | no (preprint) | 0 | Distils a voice-cloning teacher into a compact fixed-voice Thai student from a 15 s reference, trained only on synthetic speech. |

## Cross-cutting observations for a Thai/English assistant

1. **The cascade is not dead, it is being de-VAD-ed.** The newest work on both sides (DuplexCascade, CoT-duplex, Chronological Thinking, the two surveys) agrees on the trade: e2e duplex models win on timing and paralinguistics, cascades win on reasoning, tool use and language coverage. The convergent design is a cascade whose turn controller is a learned EOT / interruption model (C6) and whose TTS streams on partial text (C5).
2. **Turn-taking is a separable, cheap component.** VAP-family models run on CPU in real time; 2026 ablations find acoustic + prosodic cues carry most of the signal, which matters for Thai, where lexical EOT models trained on English (OpenETD) will not transfer.
3. **Thai e2e options exist but are thin.** Typhoon2-Audio is the only open Thai speech-to-speech model found; SeaLLMs-Audio covers Thai understanding and voice interaction; nothing full-duplex for Thai was found. The Thai component papers (Typhoon ASR Real-time, JaiTTS, fixed-voice TTS, Thai-SUP) all come from 2025–2026 and are preprints.
4. **Benchmarks to adopt:** VoiceBench (assistant quality), Full-Duplex-Bench v1.5 (overlap and latency), FDB-v3 (tool use under disfluency), TurnBench / Talking Turns (turn-taking). None has Thai data; SeaBench-Audio (SeaLLMs-Audio) is the only SEA-language audio-LLM benchmark seen.
5. **Latency anchors reported in abstracts:** Moshi 160 ms theoretical / ~200 ms practical; Whisper-Streaming on the order of seconds; Typhoon ASR Real-time ~45x less compute than Whisper-large-v3. Component-level numbers for TTS first-packet latency are in the papers but were not extracted at this phase.

## Reading list for the deep dive (15)

| # | arXiv | paper | why |
|---|---|---|---|
| 1 | 2410.00037 | Moshi | The reference native full-duplex design (dual audio streams + Inner Monologue, Mimi codec); every 2025–2026 duplex paper positions itself against it, and it reports concrete latency numbers. |
| 2 | 2505.15670 | SALM-Duplex (Interspeech 2025) | Peer-reviewed, open code; the most practical open duplex S2S baseline to actually run. |
| 3 | 2610.17124 | D2 | Answers the team's build question directly: convert an existing capable half-duplex SLM into a duplex one instead of pretraining. |
| 4 | 2606.14528 | BayLing-Duplex | Single autoregressive LLM, no external VAD, code released; lineage from LLaMA-Omni / Stream-Omni makes the half → full-duplex delta readable. |
| 5 | 2603.09180 | DuplexCascade | The modular counter-proposal: VAD-free cascade with micro-turns. For a Thai/English assistant that needs a strong text LLM and tools this is the most directly applicable architecture. |
| 6 | 2411.00774 | Freeze-Omni | Keeps the LLM frozen; the pattern to use if the Thai LLM (Typhoon) must stay untouched and only speech adapters are trained. |
| 7 | 2506.13642 | Stream-Omni | Layer-dimension CTC alignment yields intermediate text during speech interaction, a hybrid that keeps a text trace for logging, tools and translation. |
| 8 | 2507.23159 | Full-Duplex-Bench v1.5 (ICASSP 2026) | The evaluation protocol for overlap / barge-in with latency metrics; read with v1 (2503.04721) and v3 (2604.04847, tool use, real disfluent audio). |
| 9 | 2410.17196 | VoiceBench | Assistant-level benchmark (knowledge, instruction following, safety under acoustic variation) to compare cascade vs e2e on what users actually ask. |
| 10 | 2503.23439 | Speculative End-Turn Detector (ACL 2026) | Current peer-reviewed EOT method plus a public dataset; the component a cascade needs most. |
| 11 | 2603.13379 | Hierarchical EOT with primary-speaker segmentation (Meta) | Production EOT for noisy multi-speaker rooms (offices, meetings), which is the deployment context here. |
| 12 | 2401.04868 | Real-time VAP (+ multilingual VAP 2403.06487) | Runnable self-supervised turn-taking model; the multilingual follow-up is the closest evidence on whether it transfers to a tonal language like Thai. |
| 13 | 2503.04724 | LLMVoX (ACL 2025) | LLM-agnostic 30M streaming TTS: the pattern for streaming speech from a hosted LLM's partial output without touching the LLM. |
| 14 | 2601.13044 | Typhoon ASR Real-time | The Thai streaming ASR: FastConformer-Transducer recipe, Thai normalisation and a public benchmark; the ear of the modular pipeline. |
| 15 | 2409.10999 | Typhoon-Audio (Interspeech 2025) + Typhoon 2 (2412.13702) | Why off-the-shelf audio LLMs fail on Thai and the only open Thai speech-to-speech model family; defines the e2e option for Thai. |

Also worth skimming (not in the 15): NTPP 2506.00975 (ICML 2025 formulation), SyncLLM 2409.15594, CosyVoice 2 2412.10117, Qwen2.5-Omni 2503.20215, the two surveys 2509.14515 / 2606.19453, SeaLLMs-Audio 2511.01670, fixed-voice Thai TTS 2609.03502.

## `paper_db.py stats`

```json
{
  "total": 80,
  "peer_reviewed": 49,
  "preprint_only": 31,
  "sources": {
    "arxiv": 80
  },
  "years": {
    "2020": 1,
    "2022": 5,
    "2023": 9,
    "2024": 18,
    "2025": 31,
    "2026": 16
  },
  "top_venues": {
    "Interspeech 2025": 3,
    "ICASSP 2026": 3,
    "ICML 2023": 2,
    "ICLR 2024": 2,
    "ACL 2025": 2,
    "ICLR 2025": 2,
    "ICASSP (per OpenAlex)": 2,
    "ASRU 2025": 2,
    "ACL 2026": 2,
    "Findings of EMNLP 2020": 1
  },
  "with_abstract": 80,
  "with_pdf": 80,
  "total_citations": 2839,
  "avg_citations": 35.5,
  "tags": {
    "turn_taking": 13,
    "e2e_s2s": 18,
    "full_duplex": 14,
    "streaming_asr": 11,
    "thai_lowresource": 11,
    "streaming_tts": 9,
    "benchmark": 11,
    "architecture_survey": 2
  }
}
```

✅ Phase 2 complete
