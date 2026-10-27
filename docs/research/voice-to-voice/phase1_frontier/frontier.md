# Phase 1 — Frontier (2025–2026): real-time voice-to-voice conversational AI

Topic: end-to-end speech-to-speech / full-duplex spoken dialogue models vs modular ASR → LLM → TTS
pipelines; streaming ASR; streaming TTS; turn-taking / end-of-turn detection; barge-in; latency and
evaluation benchmarks. Consumer: an engineering team building a Thai/English voice assistant.
Date of search: 2026-10-25.

Status labels: **peer-reviewed** = venue stated in the arXiv record's comment field or found in the
venue's proceedings during the web search; **(preprint)** = no venue found. Citation counts were not
retrieved in this phase (Semantic Scholar unauthenticated API returned HTTP 429 during the run); they are
added in `paper_db.jsonl` where the Phase 2 batch lookup succeeded.

## Searches run (raw results kept in `search_results/`)

| # | Query (arXiv API, cs.CL / cs.SD / eess.AS, 2025-01-01 →) | File | Hits |
|---|---|---|---|
| 1 | full-duplex spoken dialogue model | `arxiv_full_duplex.jsonl` | 38 |
| 2 | speech-to-speech large language model end-to-end spoken dialogue | `arxiv_s2s_llm.jsonl` | 15 |
| 3 | benchmark evaluation spoken dialogue models speech interaction | `arxiv_benchmark.jsonl` | 29 |
| 4 | streaming speech recognition low latency | `arxiv_streaming_asr.jsonl` | 13 |
| 5 | turn-taking prediction end-of-turn detection spoken dialogue (+cs.HC) | `arxiv_turn_taking.jsonl` | 32 |
| 6 | barge-in interruption handling spoken dialogue system (+cs.HC) | `arxiv_barge_in.jsonl` | 10 |
| 7 | streaming text-to-speech low latency language model | `arxiv_streaming_tts.jsonl` | 25 |
| 8 | Thai speech recognition (2024-01-01 →) | `arxiv_thai_speech.jsonl` | 15 |
| 9 | Southeast Asian languages speech large language model (2024-06-01 →) | `arxiv_sea_speech.jsonl` | 25 |
| 10 | Targeted id fetches of papers surfaced by WebSearch of accepted-paper lists (Interspeech 2025, ICASSP 2026, ICLR 2025/2026, ACL 2026, ASRU 2025, SLT 2026, SIGDIAL 2026) | `arxiv_targeted_websearch{,2,3}.jsonl` | 62 |
| 11 | Semantic Scholar, same queries, year 2025-2026 | none | unauthenticated API returned HTTP 429 throughout |

Semantic Scholar unauthenticated search returned HTTP 429 for every query at first; a slower retry
runner (`s2_fetch.py`, 20–125 s backoff) was used. It never got through either (HTTP 429 on every attempt), so no `s2_*.jsonl` files exist; citation counts are added in Phase 2 from a different source.

---

## Trending direction A — Native full-duplex speech LMs built from half-duplex / text backbones

The 2025–2026 frontier moved from "turn-based S2S chatbots with an external VAD" (LLaMA-Omni,
GLM-4-Voice, Freeze-Omni) to models that listen while they speak. The common recipe: keep a strong
pretrained (text or half-duplex speech) LLM, add a continuous user stream (codec or encoder features,
~80–200 ms frames), and let the model emit speech, silence or "keep listening" tokens on its own stream.

- **D2: High-Capability Full-Duplex Spoken Language Models from Half-Duplex Backbones** — Chang, Liu,
  Kingsbury et al., 2026, arXiv 2610.17124 **(preprint)**. Converts a pretrained half-duplex speech LM
  into a full-duplex one "at fine temporal granularity": the audio encoder is made streaming through
  decoder-free representation distillation, so the general capabilities of the half-duplex model are kept.
  Directly relevant to the build-vs-adapt decision: it argues you do not need to pretrain a duplex model
  from scratch, you can adapt an existing capable one.
- **BayLing-Duplex: Native Full-Duplex Speech Dialogue with a Single Autoregressive LLM** — Fang, Guo,
  Feng (ICT/CAS), 2026, arXiv 2606.14528 **(preprint)**, code released. Explicitly positions itself
  against LLaMA-Omni / GLM-4-Voice ("still turn-based, rely on an external VAD") and models overlap,
  hesitation and barge-in in a single autoregressive LLM. Same group as LLaMA-Omni / Stream-Omni, so the
  lineage from turn-based to native duplex is traceable in one codebase.
- **SALM-Duplex: Efficient and Direct Duplex Modeling for Speech-to-Speech Language Model** — Hu,
  Hosseini-Asl, Chen et al. (NVIDIA), **Interspeech 2025, peer-reviewed**, arXiv 2505.15670. Continuous user
  input + codec agent output with channel fusion directly modelling both streams; the web search
  describes it as the first openly available duplex S2S model with training and inference code. A
  practical starting point for an open duplex baseline.
- **NTPP: Generative Speech Language Modeling for Dual-Channel Spoken Dialogue via Next-Token-Pair
  Prediction** — Wang, Meng, Cui et al., **ICML 2025, peer-reviewed** (PMLR 267), arXiv 2506.00975.
  Models dual-channel speech by predicting token *pairs* (one per speaker) per step, exploiting the
  structure of two-channel conversational data. The cleanest formulation of "both channels in one LM".
- **MOSS-Speech: Towards True Speech-to-Speech Models Without Text Guidance** — Zhao, Xu, Cheng et al.,
  2025, arXiv 2510.00499 **(preprint)**. Argues that even end-to-end systems that keep a text
  intermediate have a bottleneck, and trains a speech-in / speech-out LLM without text guidance. The
  counter-position to text-anchored designs (Mini-Omni, LLaMA-Omni2); important for the paralinguistics
  argument, less so for a knowledge-heavy assistant.
- **Chronological Thinking in Full-Duplex Spoken Dialogue Language Models** — Wu, Zhang, Chen et al.,
  **SIGDIAL 2026, peer-reviewed**, arXiv 2510.05150. Uses the listening phase (while the user is still
  speaking) to reason incrementally, so the answer is ready when the turn ends: a way to recover
  "thinking time" without adding response latency.
- **Chain-of-Thought Reasoning in Streaming Full-Duplex End-to-End Spoken Dialogue Systems** — Arora,
  Tian, Futami et al. (CMU/ESPnet), 2025, arXiv 2510.02066 **(preprint)**. Notes that duplex models drop
  VAD by emitting silence tokens but "lag behind cascaded models in semantic reasoning", and adds CoT to a
  streaming duplex E2E system. Relevant evidence for the e2e-vs-cascade trade-off on reasoning.
- **How Should LLMs Listen While Speaking? A Study of User-Stream Routing in Full-Duplex Spoken
  Dialogue** — Lu, Chen, Wang et al., 2026, arXiv 2605.10199 **(preprint)**. A controlled study of *where*
  the user stream enters the LLM during generation, the key architectural choice behind every design
  above. Useful as a design-space map.
- Also seen (preprints, 2026): **F-Actor** (controllable conversational behaviour in full-duplex models,
  2601.11329), **DuplexSLA** (full-duplex with synchronized speech, language and action, 2605.20755),
  **TASTE2** (text-aligned speech modelling and deployment toward full-duplex, 2609.08956, reports
  Full-Duplex-Bench latency), **What Did I Just Say? Self-Listening for Full-Duplex Speech Models**
  (2609.05592), **Omni-DuplexEval** (2605.17360).

## Trending direction B — VAD-free cascades and latency engineering of the modular pipeline

A parallel line keeps ASR → LLM → TTS (for LLM intelligence, tool use and language coverage) but removes
the turn-based VAD gate and overlaps the stages. For a Thai/English assistant that needs a strong text
LLM and tool calls, this is the most directly applicable direction.

- **DuplexCascade: Full-Duplex Speech-to-Speech Dialogue with VAD-Free Cascaded ASR-LLM-TTS Pipeline
  and Micro-Turn Optimization** — Yang, Fujita, Sudo (SB Intuitions), 2026, arXiv 2603.09180 **(preprint,
  submitted to Interspeech 2026)**. States the trade-off exactly: cascades keep LLM intelligence but VAD
  "forces half-duplex turns and brittle control", VAD-free end-to-end models are "hard to maintain
  conversational intelligence"; proposes a VAD-free streaming cascade with micro-turn optimisation.
- **i-LAVA: Insights on Low Latency Voice-2-Voice Architecture for Agents** — Purwar, Choudhary, 2025,
  arXiv 2509.20971 **(preprint)**. An engineering analysis of where time goes in ASR / TTS / dialogue
  management of a V2V agent and which levers cut it; practitioner-oriented, directly useful for a
  latency budget.
- **Stream-Omni: Simultaneous Multimodal Interactions with Large Language-Vision-Speech Model** —
  Zhang, Guo, Fang et al. (ICT/CAS), 2025, arXiv 2506.13642 **(preprint)**, code and model released.
  Aligns speech to the LLM along the *layer* dimension (CTC-based) instead of concatenating tokens, which
  yields intermediate text transcripts during speech interaction, a bridge design between cascades and
  e2e that keeps a text trace for logging and tool use.
- **ESPnet-SDS: Unified Toolkit and Demo for Spoken Dialogue Systems** — Arora et al., **NAACL 2025
  Demo, peer-reviewed**, arXiv 2503.08533. An open toolkit that runs cascaded and end-to-end SDS behind
  one interface with on-the-fly latency and quality metrics; the natural harness for comparing both
  families on the team's own Thai data.

## Trending direction C — Turn-taking, end-of-turn detection and barge-in as separate, cheap models

Even e2e-duplex papers concede VAD-only endpointing is the weak point. 2025–2026 work builds small
streaming end-of-turn (EOT) models from acoustic + prosodic + lexical cues, and studies what cues matter.

- **Speculative End-Turn Detector for Efficient Speech Chatbot Assistant** — Ok, Yoo, Lee, **ACL 2026,
  peer-reviewed**, arXiv 2503.23439. Frames ETD as separating turn completion from hesitation, which
  "leads to premature or delayed responses"; proposes a speculative detector plus the OpenETD dataset
  (English-focused, per its limitations section).
- **A Hierarchical End-of-Turn Model with Primary Speaker Segmentation for Real-Time Conversational
  AI** — Helwani, Do, Luan et al. (Meta), 2026, arXiv 2603.13379, comment says **accepted at an IEEE
  conference** (peer-reviewed). A production-style front end: track the primary speaker in a multi-speaker
  room, then a causal hierarchical EOT model over per-speaker features of both the user and the bot.
  Addresses the "side conversation / background talk" failure that matters in offices.
- **Less can be More: What Aspects of Speech Drive End-of-Turn Detection** — Sharon, A, Hacioglu et al.,
  2026, arXiv 2609.11066 **(preprint)**. Controlled ablation of acoustic, prosodic and semantic signals in
  a lightweight trimodal streaming EOT classifier; the web summary reports the acoustic+prosodic
  combination gives the best accuracy/latency balance, which, if it holds for Thai, means the EOT model
  can be language-light.
- **The Role of Prosodic and Lexical Cues in Turn-Taking with Self-Supervised Speech Representations**
  — O'Connor Russell, Charuau, Harte, **ICASSP 2026, peer-reviewed**, arXiv 2601.13835. Vocoder-based
  control of prosody vs lexical content to probe what Voice Activity Projection (VAP) models rely on.
- **JAL-Turn: Joint Acoustic-Linguistic Modeling for Real-Time and Robust Turn-Taking Detection in
  Full-Duplex Spoken Dialogue Systems** — Pan, Yang, Huzaifah et al., **NCMMSC 2026 oral, peer-reviewed**,
  arXiv 2603.26515. "Industrial-grade" speech-only, lightweight turn-taking that avoids giving the LLM
  full duplex capability (too costly to deploy), i.e. the pragmatic middle path.
- **Prompt-Guided Turn-Taking Prediction** — Inoue, Elmers, Fu et al. (Kyoto), **SIGDIAL 2025,
  peer-reviewed**, arXiv 2506.21191. Turn-taking prediction (VAP family) steered by textual prompts, so
  the same model can be told to wait longer or respond faster; a controllability knob for an assistant.
- **Semantic-Aware Interruption Detection in Spoken Dialogue Systems: Benchmark, Metric, and Model** —
  Xia, Mu, Shi et al., **ICME 2026, peer-reviewed**, arXiv 2603.24144. The barge-in paper of the set:
  "trigger-happy" VAD methods misread backchannels, robust e2e models respond too slowly; proposes a
  benchmark, a metric and a model for semantic interruption detection.
- **HiThink Turn: An Intent-Aware Turn-Taking Control Module for Full-Duplex Dialogue** — 2026, arXiv
  2609.34096 **(preprint)**: intent-aware turn control as a plug-in module.

## Trending direction D — Streaming TTS that starts speaking on partial LLM output

- **SpeakStream: Streaming Text-to-Speech with Interleaved Data** — Bai, Gu, Likhomanenko et al. (Apple),
  2025, arXiv 2505.19206 **(preprint)**. Trains a decoder-only TTS on text–speech *interleaved* data so it
  can synthesise while the LLM is still generating; names the latency bottleneck of utterance-level TTS.
- **LLMVoX: Autoregressive Streaming Text-to-Speech Model for Any LLM** — Shikhar, Kurpath, Mullappilly
  et al., 2025, arXiv 2503.04724 (web search lists it as **ACL 2025**; the arXiv comment is empty, so treat
  as peer-reviewed-unverified). A 30M-parameter LLM-agnostic streaming TTS that avoids fine-tuning the LLM,
  which is attractive when the LLM is a hosted Thai model you cannot modify.
- **CTC-TTS: LLM-based dual-streaming text-to-speech with CTC alignment** — Liu, Yusuyin, Huang et al.,
  **Interspeech 2026, peer-reviewed**, arXiv 2602.19574. Dual-streaming (text in, speech out, both
  streaming) with CTC alignment instead of MFA forced alignment, which matters for languages without a
  good forced aligner (Thai has no spaces between words).
- **SyncSpeech: Efficient and Low-Latency Text-to-Speech based on Temporal Masked Transformer** —
  Sheng, Du, Zhang et al. (Alibaba/CosyVoice group), 2025, arXiv 2502.11094 **(preprint)**. Bridges AR
  (slow) and NAR (high first-packet latency) with a temporal masked transformer.
- Also: **LLM2Speech / "Speak while you think"** (IBM, Interspeech 2025, found via web search only, no
  arXiv record retrieved) and Samsung's Mamba streaming TTS acoustic model (Interspeech 2025).

## Trending direction E — Streaming ASR: chunked encoders and LLM decoders

- **Streaming Speech Recognition with Decoder-Only Large Language Models and Latency Optimization** —
  Wan, Zhang, Zhang et al., **ICASSP 2026, peer-reviewed**, arXiv 2601.22779. Read/write policy network +
  monotonic chunkwise attention segments speech embeddings for a decoder-only LLM; relevant when the ASR
  and the LLM are to be fused.
- **Spiralformer: Low Latency Encoder for Streaming Speech Recognition with Circular Layer Skipping and
  Early Exiting** — Tsunoo, Futami, Kashiwagi et al. (Sony), **ASRU 2025, peer-reviewed**, arXiv
  2510.00982. Attacks *encoding* latency of block processing (small chunk shifts without the compute
  blow-up), complementary to transducer emission-latency work.
- **Chunkwise Aligners for Streaming Speech Recognition** — Teo, Moriya, Mimura (NTT), 2026, arXiv
  2605.11422 **(preprint)**. Makes the alignment-free "Aligner" loss streamable, a cheaper-to-train
  alternative to the transducer that remains the standard for streaming ASR.
- **Typhoon ASR Real-time: FastConformer-Transducer for Thai Automatic Speech Recognition** —
  Sirichotedumrong, Na-Thalang, Manakul et al. (SCB 10X), 2026, arXiv 2601.13044 **(preprint)**, models and
  datasets public. 115M-parameter FastConformer-Transducer for low-latency Thai; claims a 45x compute
  reduction vs Whisper Large-v3 at comparable accuracy, Thai-specific text normalisation and Isan dialect
  curriculum, plus a human-labelled Typhoon ASR Benchmark. The single most relevant paper for the Thai ASR
  stage.
- **Zipper-LoRA: Dynamic Parameter Decoupling for Speech-LLM based Multilingual Speech Recognition** —
  Mei, Qiu, Liu et al., **IEEE/ACM TASLP 2026, peer-reviewed**, arXiv 2603.17558. Speech-LLM ASR under
  imbalanced multilingual data (the Thai/English situation): shared PEFT causes negative transfer,
  decoupled adapters fix it.

## Trending direction F — Benchmarks for duplex behaviour, latency and S2S quality

Two benchmark families with confusingly similar names exist: **Full-Duplex-Bench** (Lin et al., v1 → v3)
and **FD-Bench** (Peng et al.). Cite team and version.

- **Full-Duplex-Bench** — Lin, Lian, Li et al., **ASRU 2025, peer-reviewed**, arXiv 2503.04721: pause
  handling, backchanneling, turn-taking, interruption with automatic metrics.
  **Full-Duplex-Bench v1.5** — **ICASSP 2026, peer-reviewed**, arXiv 2507.23159: overlap handling (user
  interruption, backchannel, side conversation, ambient speech) with stop- and response-latency; finds
  two divergent strategies, "responsive" vs "floor-holding".
  **Full-Duplex-Bench-v3** — 2026, arXiv 2604.04847 **(preprint)**: real human audio with five
  disfluency categories plus chained tool calls; evaluates GPT-Realtime and Gemini Live among six
  configurations, so it is the closest thing to a production assistant benchmark.
- **FD-Bench: A Full-Duplex Benchmarking Pipeline Designed for Full Duplex Spoken Dialogue Systems** —
  Peng, Chao, Ng et al., **Interspeech 2025, peer-reviewed**, arXiv 2507.19040. LLM-simulated multi-round
  conversations + TTS + ASR + Silero-VAD timestamps to score interruption handling and response quality
  (Moshi, Freeze-Omni, VITA-1.5 evaluated).
- **MTR-DuplexBench** — Zhang, Cui, Xu et al., **Findings of ACL 2026, peer-reviewed**, arXiv 2511.10262.
  Multi-round evaluation of full-duplex SLMs (turn segmentation, dialogue quality, instruction following,
  safety); finds current models struggle to stay consistent across rounds.
- **Talking Turns: Benchmarking Audio Foundation Models on Turn-Taking Dynamics** — Arora, Lu, Chiu et
  al., **ICLR 2025, peer-reviewed**, arXiv 2503.01174. Measures whether audio FMs take turns fluently
  without excessive overlap.
- **TurnBench: A Multi-Domain Benchmark for Turn-Taking Dynamics in Spoken Dialogue** — Jiang,
  Sanabria, Deshmukh et al., **IEEE SLT 2026, peer-reviewed**, arXiv 2608.25218. 30-hour hand-labelled
  multi-domain corpus with a linguistically grounded protocol for take / hold / yield decisions.
- **URO-Bench** — Yan, Li, Chen et al., 2025, arXiv 2502.17810 **(preprint)**: cognitive (reasoning,
  knowledge) and speech-related (paralinguistics, audio quality) dimensions for end-to-end SDMs.
- **ParaS2S** — Yang, Tu, Liu et al., **ICLR 2026, peer-reviewed**, arXiv 2511.08723: benchmark + RL
  alignment for paralinguistic-aware S2S responses.
- **SPEARBench** — Thebaud, Wang, Zhang et al., 2026, arXiv 2607.05365 **(preprint)**: naturalness of
  streaming S2S LMs including timing, turn-taking, prosody and *language/dialect consistency*, the last of
  which is a live concern for Thai/English code-switching.
- **FLEXI** — 2025, arXiv 2509.22243 **(preprint)**: full-duplex human–LLM interaction benchmark that
  reports interaction latency and model-initiated interruption in emergencies.
- Surveys: **From Turn-Taking to Synchronous Dialogue: A Survey of Full-Duplex Spoken Language Models**
  (Chen, Yu, 2025, arXiv 2509.14515, preprint) — taxonomy "Engineered Synchronization (modular) vs Learned
  Synchronization (e2e)" and four evaluation axes (temporal dynamics, behavioural arbitration, semantic
  coherence, acoustic performance); **A Survey of Full-Duplex Spoken Dialogue Systems: Architectural
  Hierarchy, Interaction Ontology, and Decision State Machine** (Lu, Wang, Luo et al., 2026, arXiv
  2606.19453, preprint) — argues "full-duplex" is used for substantially different capabilities and
  proposes a decision-state-machine ontology for builders.

## Consumer-specific — Thai and Southeast Asian speech (2024–2026)

- **Typhoon 2: A Family of Open Text and Multimodal Thai Large Language Models** — Pipatanakul, Manakul,
  Nitarach et al. (SCB 10X), 2024, arXiv 2412.13702 **(preprint, technical report)**. Includes
  Typhoon2-Audio, described as an end-to-end speech-to-speech model with simultaneous text and speech
  output; the only open Thai S2S model found.
- **Enhancing Low-Resource Language and Instruction Following Capabilities of Audio Language Models**
  (Typhoon-Audio) — Manakul, Sun, Sirichotedumrong et al., **Interspeech 2025, peer-reviewed**, arXiv
  2409.10999. Finds audio LMs "lack emergent cross-lingual abilities" on Thai despite multilingual
  components; trains Typhoon-Audio; the HF card reports ~14% WER on Thai ASR for Typhoon2-Audio.
- **SeaLLMs-Audio: Large Audio-Language Models for Southeast Asia** — Liu, Aljunied, Chen et al.
  (Alibaba DAMO), 2025, arXiv 2511.01670 **(preprint)**. First LALM for Indonesian, Thai and Vietnamese
  (+ en, zh) with voice-based interaction, plus the SeaBench-Audio benchmark.
- **Towards Building Speech Large Language Models for Multitask Understanding in Low-Resource
  Languages** (XLSR-Thai, Thai-SUP, U-Align) — Shao, Mu, Wang et al., 2025, arXiv 2509.14804
  **(preprint)**. Diagnoses why speech LLMs degrade on Thai (Whisper-family encoders underperform, no Thai
  SLU data) and builds a Thai SSL encoder plus a synthetic Thai spoken-understanding pipeline.
- **MERaLiON-AudioLLM** — 2024, arXiv 2412.09818 (tech report) with an **ACL 2025 System Demo,
  peer-reviewed** version: Singapore-centric audio LLM (Singlish, Malay, Tamil, Mandarin); SEA regional
  precedent for a localised speech encoder + LLM.
- Thai TTS: **JaiTTS: A Thai Voice Cloning Model** (2026, arXiv 2604.27607, preprint; VoxCPM-based, handles
  numerals and Thai–English code-switching without text normalisation, 1.94% CER reported in the web
  summary); **Building and Evaluating Fixed-Voice Thai TTS from Synthetic Speech** (Pipatanakul et al.,
  2026, arXiv 2609.03502, preprint; distil a 15 s reference through a voice-cloning teacher into a compact
  fixed-voice student, names Thai word-boundary, tone and numeral issues); **Empowering Global Voices**
  (Geng et al., ACL 2025 Industry per web search, arXiv 2504.07858; data-efficient Thai TTS with zero-shot
  cloning). **Thonburian Whisper** (Aung et al., ICNLSP 2024, peer-reviewed, no arXiv) is the standard
  fine-tuned/distilled Whisper for Thai.
- **Speechless: Speech Instruction Training Without Speech for Low Resource Languages** — Dao, Vu, Ha
  et al., **Interspeech 2025, peer-reviewed**, arXiv 2505.17417. Trains speech-instruction following
  without TTS by aligning to semantic speech tokens; a recipe when Thai TTS quality is the bottleneck for
  synthetic data.
- **THAI-SER corpus** (2025, arXiv 2507.09618, preprint): Thai speech emotion recognition corpus, useful
  for paralinguistic evaluation.

## Active groups (from authorship above)

ICT/CAS (ictnlp: LLaMA-Omni, Stream-Omni, BayLing-Duplex); NVIDIA (SALM-Duplex, Full-Duplex-Bench-v3
co-authors); CMU/ESPnet (Talking Turns, ESPnet-SDS, CoT duplex); NTU/Lin et al. (Full-Duplex-Bench
series); Kyoto/Inoue (VAP, prompt-guided turn-taking); Apple (SpeakStream); Alibaba (SyncSpeech,
CosyVoice, SeaLLMs-Audio); SCB 10X Typhoon (Thai ASR / TTS / audio LLM); Meta (hierarchical EOT);
Sony and NTT (streaming ASR encoders).

## Web sources consulted for venue status

- https://arxiv.org/abs/2505.15670 (Interspeech 2025), https://www.isca-archive.org/interspeech_2025/peng25b_interspeech.html (FD-Bench),
  https://www.isca-archive.org/interspeech_2025/ohashi25_interspeech.html (J-Moshi)
- https://proceedings.mlr.press/v267/wang25by.html (NTPP, ICML 2025)
- https://aclanthology.org/2026.acl-long.2094.pdf (Speculative End-Turn Detector, ACL 2026)
- https://arxiv.org/abs/2601.13835 (ICASSP 2026), https://arxiv.org/abs/2601.13044 (Typhoon ASR Real-time)
- https://arxiv.org/abs/2412.09818 and https://preview.aclanthology.org/setup/2025.acl-demo.3 (MERaLiON)
- https://arxiv.org/abs/2511.01670 (SeaLLMs-Audio), https://arxiv.org/abs/2409.10999 (Typhoon-Audio)
- https://aclanthology.org/2024.icnlsp-1.17 (Thonburian Whisper), https://arxiv.org/abs/2509.14804 (Thai-SUP)
- https://research.ibm.com/publications/speak-while-you-think-streaming-speech-synthesis-during-text-generation (LLM2Speech)
- https://arxiv.org/pdf/2507.19040, https://arxiv.org/pdf/2511.10262, https://arxiv.org/pdf/2606.19453

✅ Phase 1 complete
