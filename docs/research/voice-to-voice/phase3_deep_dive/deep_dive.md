# Phase 3 Deep Dive — real-time voice-to-voice conversational AI

Date: 2026-10-25. 12 papers read in full text (PDF from arxiv.org, text extracted with PyMuPDF). Every number below is copied from the paper's own tables or text; "not reported" means the paper gives no figure. Venue status: `(preprint)` = no peer-reviewed venue named by arXiv or Semantic Scholar on 2026-10-25. Selection rationale: `selection.md`.

---

### [@defossez2024moshi] Moshi: a speech-text foundation model for real-time dialogue

**Metadata**
- Authors: Alexandre Défossez, Laurent Mazaré, Manu Orsini, Amélie Royer, Patrick Pérez, Hervé Jégou, Edouard Grave, Neil Zeghidour (Kyutai)
- Year: 2024 | Venue: Kyutai technical report, arXiv only **(preprint)**
- arXiv: 2410.00037 | Citations: 859 (Semantic Scholar, 2026-10-25)
- Code: https://github.com/kyutai-labs/moshi (weights released)

**Problem**
Cascaded VAD → ASR → LLM → TTS pipelines have multi-second latency, lose paralinguistic information through the text bottleneck, and assume clean speaker turns; Moshi casts spoken dialogue as streaming speech-to-speech generation over two parallel audio streams so that overlap, interruption and backchannels need no explicit turn logic.

**Key Contributions**
1. Helium, a 7B text LLM pretrained on 2.1T tokens of public English data (MMLU 54.3, Table 2).
2. Mimi, a causal neural codec: 24 kHz audio → 12.5 Hz frames, 8 codebooks of 2048 (1.1 kbps), a *split RVQ* where one VQ is distilled from WavLM for semantics and a 7-level RVQ carries acoustics; 80 ms frame size and stride, so the first 80 ms of audio yields the first decodable frame.
3. A multi-stream RQ-Transformer (7B Temporal Transformer + 6-layer Depth Transformer with per-codebook parameters) that models Moshi's text, Moshi's audio and the user's audio jointly at every 80 ms step.
4. *Inner Monologue*: time-aligned text tokens (Whisper word timestamps, PAD/EPAD tokens) predicted as a prefix to the audio tokens; changing the text/audio delay turns the same model into a streaming TTS or ASR.

**Methodology**
- Approach type: architecture + training recipe for a full-duplex speech LM.
- Streaming/latency: every component is causal; the "acoustic delay" τ between the semantic token and the acoustic tokens is 2 frames in pretraining and 1 in fine-tuning, giving a theoretical latency of 80 ms (frame) + 80 ms (delay) = **160 ms, 200 ms in practice** (abstract; hardware for the practical figure is not stated in the text).
- Training stages (Table 1): Helium pretraining (500k steps); Moshi audio pretraining on single-stream audio with 30 % text masking and random text/audio delay (1M steps, half of the batches text-only to avoid forgetting); post-training on a simulated two-stream split made with PyAnnote diarization (100k steps); fine-tuning on the Fisher telephone corpus for real overlap (10k steps); instruct fine-tuning on >20k hours of synthetic dialogues rendered by their own multi-stream TTS with one actor's voice (70+ styles). The user stream is augmented with gain (−24…+15 dB), DNS noise, a 100–500 ms scaled echo of Moshi's own output and reverb, which is what makes barge-in work on real microphones.

**Experiments**
- Codec: MUSHRA 81.0 with adversarial-only training vs 58.8 with Encodec-style losses; ABX 8.1 % (Table 3/4). The authors note objective metrics (VisQOL, MOSNet) were decorrelated from human ratings.
- Spoken QA (Table 8, 0-shot, audio in): Moshi 26.6 Web Questions / 62.3 LLaMA-Questions / 22.8 Audio TriviaQA, vs SpeechGPT 6.5 / 21.6 / 14.8 and Spectron 6.1 / 22.9 / –; without Inner Monologue 9.2 / 21.0 / 7.3; the Helium text topline is 32.3 / 75.0 / 56.4.
- Derived streaming systems (Section 5.7): streaming TTS with 2 s lookahead gets **4.7 % WER** on LibriSpeech test-clean (VALL-E 5.9 %, NaturalSpeech 3 1.81 % non-streaming); streaming ASR gets **5.7 % WER** vs 3.6 % for a streaming FastConformer with similar look-ahead, with 80 ms alignment precision.
- Compression (Section 5.8): post-training quantization hurts Moshi's MMLU more than Helium's (Tables 10–11).
- Latency: 160 ms theoretical / 200 ms practical; no per-stage breakdown.

**Limitations**
- Acknowledged: ASR behind a dedicated streaming FastConformer; "thorough evaluation of streaming TTS" left to future work; objective audio-quality metrics unreliable; textless-NLP metrics did not guide dialogue quality; quantization degrades the speech model.
- Observed by reader: English-only training; Full-Duplex-Bench measures a takeover rate of 0.98 on pauses (it interrupts), and VoiceBench scores it 27.5 overall, far below pipelines — the price of a 7B model that must also be the TTS and ASR.

**Relevance to a Thai/English production voice assistant**
Moshi is the cleanest statement of what an end-to-end duplex model buys (≈200 ms, native barge-in, no VAD) and what it costs (a bespoke 7B model, English only, weaker knowledge than a text LLM of the same size). For Thai it is a design reference, not a deployable component: Mimi and Inner Monologue would need Thai data and Whisper-quality Thai timestamps to retrain.

---

### [@lin2025fullduplexbench] Full-Duplex-Bench: A Benchmark to Evaluate Full-duplex Spoken Dialogue Models on Turn-taking Capabilities

**Metadata**
- Authors: Guan-Ting Lin, Jiachen Lian, Tingle Li, Qirui Wang, Gopala Anumanchipalli, Alexander H. Liu, Hung-yi Lee (NTU, UC Berkeley, UW, MIT)
- Year: 2025 | Venue: IEEE ASRU 2025 (peer-reviewed)
- arXiv: 2503.04721 | Citations: 146
- Code/data: released with the paper (benchmark + evaluation pipeline)

**Problem**
Existing spoken-dialogue evaluations are turn-based or corpus-level; nothing measures whether a full-duplex model waits through a pause, backchannels at the right time, takes the turn quickly, or recovers from a user interruption.

**Key Contributions**
1. Four scenario-driven dimensions with automatic metrics: pause handling (Takeover Rate, TOR ↓), backchanneling (TOR ↓, frequency, Jensen–Shannon divergence of timing vs human), smooth turn-taking (TOR ↑, response latency ↓), user interruption (TOR ↑, GPT-4o quality 0–5, latency after interruption ↓).
2. A reproducible pipeline: user audio in, time-synchronous model audio out, both transcribed and aligned.
3. First like-for-like comparison of dGSLM, Moshi, Freeze-Omni and a commercial API (Gemini Live, gemini-2.0-flash-live-001).

**Methodology**
- Approach type: benchmark.
- Data (Table II): Candor two-channel conversations — 216 pause-handling and 119 smooth-turn-taking samples (gaps < 0.4 s, since human transitions are typically 200–250 ms; 5 s of silence appended); ICC — 55 backchannel samples; 200 synthetic interruptions (GPT-4o text, ChatTTS with 10 voices, interruption ≈ 7 s in, 15 s silence appended). A backchannel is < 1 s and < 2 words.
- Latency is computed only on samples where the model did take over (TOR = 1), to avoid averaging silence.

**Experiments** (Table III, latency in seconds)
- Pause handling TOR (synthetic / Candor): dGSLM 0.934 / 0.935; Moshi 0.985 / 0.980; Freeze-Omni 0.642 / 0.481; Gemini Live 0.255 / 0.310.
- Backchannel (TOR, Freq, JSD): dGSLM 0.691, 0.015, 0.934; Moshi 1.000, 0.001, 0.957; Freeze-Omni 0.636, 0.001, 0.997; Gemini Live 0.091, 0.012, 0.896.
- Smooth turn-taking (TOR, latency): dGSLM 0.975, **0.352 s**; Moshi 0.941, **0.265 s**; Freeze-Omni 0.336, **0.953 s**; Gemini Live 0.655, **1.301 s**.
- User interruption (TOR, GPT-4o score, latency): dGSLM 0.917, 0.201, 2.531 s; Moshi 1.000, 0.765, **0.257 s**; Freeze-Omni 0.867, **3.615**, 1.409 s; Gemini Live 0.891, 3.376, 1.183 s.
- Findings: end-to-end models (dGSLM, Moshi) respond fastest but interrupt pauses constantly and give incoherent answers after an interruption; the cascaded Freeze-Omni, with an explicit speak/listen state classifier, interrupts less and answers coherently but is ~0.7 s slower; even Gemini Live misses the turn 35 % of the time on real Candor data.

**Limitations**
- Acknowledged: metrics are automatic proxies (TOR, ASR alignment, GPT-4o judge); latency is only defined when the model takes over; backchannel detection is a duration/word-count heuristic.
- Observed by reader: English only; small sets (55–216 items); synthetic interruptions from one TTS; no human preference study.

**Relevance to a Thai/English production voice assistant**
This is the evaluation template to copy: TOR on pauses and latency after turn end are exactly the two numbers that decide whether a Thai meeting assistant feels polite or rude. The results also show that an explicit turn-taking module (Freeze-Omni style) is what keeps a system from talking over people — a cascade can win on manners while losing ~0.7 s.

---

### [@chen2024voicebench] VoiceBench: Benchmarking LLM-Based Voice Assistants

**Metadata**
- Authors: Yiming Chen, Xianghu Yue, Chen Zhang, Xiaoxue Gao, Robby T. Tan, Haizhou Li (NUS)
- Year: 2024 | Venue: Semantic Scholar lists TACL (peer-reviewed); arXiv v3 (Dec 2024) still says "work in progress"
- arXiv: 2410.17196 | Citations: 263
- Code/data: https://github.com/MatthewCYM/VoiceBench

**Problem**
Voice assistants were being judged by ASR WER or TTS-synthesised QA on clean speech; nobody measured knowledge, instruction following and safety under real speaker, environment and content variation, or compared end-to-end audio LLMs against a plain ASR + LLM pipeline on the same inputs.

**Key Contributions**
1. Seven sub-benchmarks: AlpacaEval and CommonEval (open QA, GPT-judged 1–5), SD-QA (real accented speech, accuracy), MMSU and OpenBookQA (multiple choice), IFEval (instruction following), AdvBench (refusal rate).
2. Robustness probes: speaker (pitch, speed, volume, age), environment (noise, reverberation, far-field), content (disfluency, grammar errors, mispronunciation).
3. The first systematic pipeline-vs-end-to-end comparison.

**Methodology**
- Approach type: benchmark. Text instructions are normalised with GPT-4o into a spoken-friendly form and synthesised with Google TTS (shown to give the same model ranking as other TTS); CommonEval and SD-QA are real recordings; inputs capped at 30 s.
- Evaluated systems (Table 2): Naive (Whisper-large-v3 + LLaMA-3.1-8B-Instruct), Naive-4o (Whisper + GPT-4o), DiVA, LLaMA-Omni, Mini-Omni/Mini-Omni2, Qwen2-Audio, VITA, Moshi, GPT-4o-Audio. Only the text of the answer is scored, so latency and speech quality are outside scope.

**Experiments** (Table 3, Overall, speech input)
- Naive pipeline **79.06** (text input 81.43; gap 4.37 points, attributed to ASR errors); Naive-4o 87.23; GPT-4o-Audio 86.42; DiVA 55.70; LLaMA-Omni 37.51 (its text score is 74.26); VITA 34.68; Moshi 27.47.
- Findings: open end-to-end models trail the 8B pipeline by > 20 points; VITA's text→speech gap exceeds 35 points and most end-to-end models are at chance on multiple-choice; LLaMA-Omni lost > 11 points of *text* ability after speech tuning; LLaMA-Omni's AdvBench refusal rate on speech is 11.35 % (text 98.46 %) — speech tuning broke safety; end-to-end models degrade below 0.5x or above 1.5x speaking rate while the pipeline is stable from 0.25x to 2.0x; low-resource accents (Indian, Philippine English) hurt every model, more on real accents than synthetic ones.
- Latency: not measured.

**Limitations**
- Acknowledged: text-only scoring (no speech output quality), synthetic speech for most sets, English only.
- Observed by reader: Whisper-large-v3 is both the pipeline's ASR and the encoder inside most end-to-end systems, so the comparison isolates the fusion method rather than the acoustic front end.

**Relevance to a Thai/English production voice assistant**
For a product that must answer correctly and refuse harmful requests, VoiceBench is the strongest evidence that a Whisper + strong-LLM cascade is still the safer default in 2024–25; the accent results also predict that Thai-accented English will be a weak spot for every off-the-shelf model, which argues for Thai-specific ASR (see Typhoon-Audio).

---

### [@veluri2024beyond] Beyond Turn-Based Interfaces: Synchronous LLMs as Full-Duplex Dialogue Agents

**Metadata**
- Authors: Bandhav Veluri, Benjamin N. Peloquin, Bokai Yu, Hongyu Gong, Shyamnath Gollakota (Meta AI, University of Washington)
- Year: 2024 | Venue: EMNLP 2024 main conference (peer-reviewed)
- arXiv: 2409.15594 | Citations: 115
- Code: project page https://syncllm.cs.washington.edu/

**Problem**
Pretrained text LLMs have no notion of wall-clock time, so they cannot decide *when* to speak, backchannel or overlap; and a cloud agent receives the user's audio late, so it must act on delayed input.

**Key Contributions**
1. SyncLLM: Llama3-8b post-trained to emit interleaved fixed-duration chunks (160, 200 or 240 ms) of its own and the user's deduplicated HuBERT speech units, with periodic synchronisation tokens that carry timing.
2. Latency tolerance by anticipation: the model predicts the user's current chunk itself, generates its next chunk, then replaces the guess with the real user audio when it arrives (Fig. 1), so one chunk of network delay (up to 240 ms) is hidden.
3. A three-stage recipe using 212k hours of synthetic spoken dialogue generated from text dialogues plus only ~2k hours of real two-channel speech (Fisher).

**Methodology**
- Approach type: fine-tuning of a text LLM into a full-duplex speech LM; standard autoregressive architecture, HiFi-GAN vocoder on the output units.
- Streaming is intrinsic: the model must finish chunk N+1 before chunk N ends; the chunk size is therefore both the generation deadline and the maximum tolerated delay.

**Experiments**
- Semantic quality: median perplexity of transcribed continuations drops ≈15 vs ground truth for SyncLLM but ≈70 for dGSLM (Fig. 5).
- Turn-taking statistics (Table 2, Pearson correlation of IPU / pause / FTO durations with ground truth): SyncLLM-F (160 ms) average 0.43 in-distribution vs dGSLM 0.33; out-of-distribution Candor 0.23–0.31 vs 0.14.
- Human study (n = 32, Table 4): Meaningfulness MOS **3.74** (SyncLLM-F) vs **1.55** (dGSLM); Naturalness 3.90 vs 3.95; simulated two-agent interaction (SyncLLM-F-F) 3.47 / 3.72; cross-dataset interaction (F-C) 3.39 / 3.78. The abstract's "+2.2 MOS" is the meaningfulness gain.
- Latency: not a measured wall-clock number; the design guarantees operation with Internet latencies up to 240 ms (one chunk).

**Limitations**
- Acknowledged (Section 7): speech quality is limited by the simple HiFi-GAN vocoder; higher-quality synthesis left to future work.
- Observed by reader: the "interaction" evaluation is LLM-to-LLM simulation, not live users; 160–240 ms chunks on an 8B model imply a GPU that can run a full decode step per chunk; English only.

**Relevance to a Thai/English production voice assistant**
SyncLLM is the clearest argument that full-duplex behaviour can be *added* to an existing text LLM rather than requiring a new foundation model, and its chunk-size reasoning (budget one chunk for the network) is directly reusable for a Thai web/Discord deployment. The 212k-hour synthetic recipe is also the only realistic path to Thai duplex data, since no Fisher-like Thai corpus exists.

---

### [@ma2024language] Language Model Can Listen While Speaking

**Metadata**
- Authors: Ziyang Ma, Yakun Song, Chenpeng Du, Jian Cong, Zhuo Chen, Yuping Wang, Yuxuan Wang, Xie Chen (SJTU, ByteDance)
- Year: 2024 | Venue: AAAI 2025 per Semantic Scholar (arXiv Aug 2024)
- arXiv: 2408.02622 | Citations: 91
- Code: demo page only (https://ddlbojack.github.io/LSLM)

**Problem**
Turn-based speech LMs cannot be interrupted; the paper isolates "full duplex modeling" — can a speaking model keep listening and stop when a human cuts in — and asks how to fuse a listening channel without hurting speech generation.

**Key Contributions**
1. LSLM: a token-based decoder-only TTS (12 layers, 768 dims, 106M params) that also consumes a streaming listening channel from vq-wav2vec (34M, fully convolutional, hence streamable) and emits an IRQ token to stop.
2. Three fusion points — early (input embeddings), middle (per-block), late (logits) — with middle fusion the best trade-off.
3. Two test regimes: command-based (a fixed phrase, speaker-dependent) and voice-based (Speech Commands words, unseen speakers), both with MUSAN noise in the listening channel.

**Methodology**
- Approach type: architecture study on a small TTS backbone. Training data: LibriTTS (585 h) for speech; interruption audio inserted at random times; turn-taking success = the model stops within 1 s of the interruption start; interactivity scored as precision / recall / F1 over 500 interrupted + 500 clean utterances; speech quality as Whisper-large-v3 WER on LibriTTS-testsetB.

**Experiments**
- Command-based (Table 2): vanilla TTS WER 4.28 %; middle fusion **4.05 % clean / 4.51 % noisy**, P/R/F1 97.80 / 98.19 / 98.00 (clean) and 97.58 / 97.18 / 97.38 (noise); early fusion wrecks TTS (WER 33.56 %); late fusion is fine on clean audio but F1 falls to 94.89 in noise (precision drops: noise mistaken for speech).
- Voice-based, unseen speakers (Table 3): WER 5.33 % clean / 8.50 % noisy; P/R/F1 95.21 / 95.78 / 95.50 clean and **87.69 / 82.77 / 85.15** in noise.
- Ablation (Table 4): best results when both the TTS backbone and the SSL encoder are initialised from pretrained weights and trained further.
- Latency: not reported beyond the 1 s success window.

**Limitations**
- Acknowledged (conclusion): LSLM is a TTS with a listening channel, not a speech-in/speech-out dialogue system; speaker-following (who interrupted) and audio-visual cues are future work.
- Observed by reader: no language understanding, so it cannot distinguish a backchannel ("uh-huh") from a real interruption; English only; 106M model, so results may not transfer to 7B duplex LMs.

**Relevance to a Thai/English production voice assistant**
The paper quantifies the barge-in problem on its own: even a dedicated listener misses ~17 % of real interruptions in noise with unseen speakers, which is why production stacks still pair a VAD/echo-cancelled interrupt detector with the model. Its noise results argue for the kind of user-stream augmentation Moshi uses, whatever language the assistant speaks.

---

### [@fang2025llamaomni] LLaMA-Omni: Seamless Speech Interaction with Large Language Models

**Metadata**
- Authors: Qingkai Fang, Shoutao Guo, Yan Zhou, Zhengrui Ma, Shaolei Zhang, Yang Feng (ICT/CAS)
- Year: 2025 | Venue: ICLR 2025 (peer-reviewed)
- arXiv: 2409.06666 | Citations: 242
- Code: https://github.com/ictnlp/LLaMA-Omni ; model https://huggingface.co/ICTNLP/Llama-3.1-8B-Omni

**Problem**
Open-source speech interaction either transcribes first (cascade latency) or generates speech tokens from a retrained LLM (quality loss); the goal is low-latency speech-in/speech-out on a stock open LLM with modest training cost.

**Key Contributions**
1. Architecture: Whisper-large-v3 encoder → adaptor (frame concatenation by k, 2-layer MLP) → Llama-3.1-8B-Instruct → a non-autoregressive streaming Transformer speech decoder that reads the LLM's hidden states, upsamples them by λ and predicts HuBERT units (1000 k-means clusters) with CTC, vocoded chunk-by-chunk (Ω units) by a unit HiFi-GAN.
2. InstructS2S-200K: 200K speech instructions/responses rewritten for the spoken register.
3. Training in ~65 hours on 4 L40 GPUs (two stages, 3 epochs each).

**Methodology**
- Approach type: fine-tuning + streaming decoder. Text and speech come out simultaneously; latency is set by the unit chunk size Ω ∈ {10…100}; cascaded baselines (Qwen2-Audio + Orca, SALMONN + Orca) stream TTS every Θ ∈ {1…9} words.
- Evaluation: InstructS2S-Eval; GPT-4o "ChatGPT score" 1–5 on S2TIF (speech→text) and S2SIF (speech→speech, transcribed by Whisper-large-v3); ASR-WER between the text and speech answers; UTMOS; words per second; latency = speech instruction end → first speech, on one NVIDIA L40.

**Experiments**
- Offline (Table 2): LLaMA-Omni ChatGPT score **3.99 (S2TIF) / 3.47 (S2SIF)**, ASR-WER 10.82, UTMOS 3.93; SpeechGPT 2.98 / 2.19, ASR-WER 45.00; SALMONN+Orca 3.44 / 3.40, ASR-WER 3.78; Qwen2-Audio+Orca 3.47 / 3.38, 6.77.
- Streaming (Fig. 3): minimum latency **236 ms at Ω = 10** (the paper compares this with GPT-4o's quoted 320 ms average); at **563 ms (Ω = 100)** all metrics are close to offline; smaller Ω slightly raises the ChatGPT score, slightly lowers ASR-WER, but lowers UTMOS because more, shorter vocoder segments add discontinuities. Cascades reach < 300 ms but their ChatGPT score and ASR-WER fall and words-per-second collapses (frequent pauses) at low latency; SpeechGPT > 4500 ms.
- Human preference: LLaMA-Omni wins 50 vs 24 (helpfulness) against Qwen2-Audio+Orca.

**Limitations**
- Acknowledged: the speech decoder saw only ~1K hours, so ASR-WER is above the industrial TTS cascades; speech quality drops at the lowest Ω.
- Observed by reader: VoiceBench reports a > 11-point loss of text ability and an 11 % AdvBench refusal rate for this model; English-only data; latency excludes network and endpointing.

**Relevance to a Thai/English production voice assistant**
LLaMA-Omni is the best-documented middle path: keep a frozen-ish open LLM, bolt on a streaming unit decoder, and get ~240–560 ms first-speech latency on one mid-range GPU. For Thai the recipe would need a Thai-capable Whisper front end and Thai HuBERT units plus vocoder — the same work as building a Thai TTS — so the gain over a cascade with CosyVoice-style streaming TTS is mostly the removal of word-level TTS chunking artefacts.

---

### [@qwen2025qwen25omni] Qwen2.5-Omni Technical Report

**Metadata**
- Authors: Qwen Team (Alibaba)
- Year: 2025 | Venue: arXiv technical report **(preprint)**
- arXiv: 2503.20215 | Citations: 922
- Code: https://github.com/QwenLM/Qwen2.5-Omni (7B weights released)

**Problem**
One model that perceives text, image, audio and video and *simultaneously* streams text and speech back, without the speech head interfering with text quality and with a small initial-packet delay.

**Key Contributions**
1. Thinker-Talker: the Thinker (LLM) produces text and high-level hidden states; the Talker, a dual-track autoregressive model, turns those states into speech codec tokens in parallel, trained end to end.
2. TMRoPE (time-aligned multimodal RoPE) and 2-second interleaving of audio and video frames.
3. Streaming design: audio and vision encoders use block-wise attention (2 s audio blocks) so inputs can be prefilled in chunks; a sliding-window flow-matching DiT with a receptive field of 4 blocks (2 lookback, 1 lookahead) plus chunked BigVGAN turns codec tokens into waveform with bounded delay.

**Methodology**
- Approach type: architecture + large-scale pretraining (data sizes not detailed here).
- Section 2.4 decomposes initial-packet latency into four parts — multimodal input processing, first text token → first speech token, first speech chunk → audio, and model size/FLOPs — and addresses each architecturally; no millisecond figures are given.

**Experiments**
- ASR (Table 2): LibriSpeech test-clean / test-other **1.8 / 3.4** (Whisper-large-v3 1.8 / 3.6, Qwen2-Audio 1.6 / 3.6); Common Voice 15 en / zh / yue / fr **7.6 / 5.2 / 7.3 / 7.5** vs Whisper-large-v3 9.3 / 12.8 / 10.9 / 10.8; Fleurs zh / en 3.0 / 4.1 vs Whisper 7.7 / 4.1.
- Voice interaction: VoiceBench average **74.12**, the best among similar-size audio/omni models at the time; speech-instruction performance on MMLU/GSM8K-derived sets approaches text input (Table 4).
- Speech generation (streaming Talker, seed-tts-eval): WER **1.42 % test-zh, 2.33 % test-en, 6.54 % test-hard**, better than MaskGCT and CosyVoice 2 as reported by the authors.
- Latency: not reported numerically.

**Limitations**
- Acknowledged: none stated beyond future directions in the conclusion.
- Observed by reader: no Thai evaluation (no Thai rows in any table); no turn-taking or barge-in evaluation; the 7B Thinker plus Talker plus DiT is heavier to serve than a cascade with a small ASR.

**Relevance to a Thai/English production voice assistant**
Qwen2.5-Omni shows that a single open model can now match a Whisper + LLM + TTS cascade on English/Chinese ASR, voice QA and TTS quality while streaming — but it proves nothing about Thai, and its own latency section is qualitative. It is the candidate to benchmark if an end-to-end route is chosen, with Thai WER and first-packet latency measured locally rather than assumed.

---

### [@noroozi2024stateful] Stateful Conformer with Cache-based Inference for Streaming Automatic Speech Recognition

**Metadata**
- Authors: Vahid Noroozi, Somshubra Majumdar, Ankur Kumar, Jagadeesh Balam, Boris Ginsburg (NVIDIA, UCLA)
- Year: 2024 | Venue: IEEE ICASSP 2024 (shorter version; peer-reviewed)
- arXiv: 2312.17279 | Citations: 49
- Code: NVIDIA NeMo (cache-aware streaming FastConformer recipes)
- Companion read: Fast Conformer (Rekesh et al., ASRU 2023, arXiv 2305.05084)

**Problem**
Offline Conformer encoders are run in "buffered" streaming mode with overlapping chunks, which wastes compute, adds 1.5–2 s of latency and creates a train/inference mismatch; the paper wants an encoder trained for a chosen look-ahead and run autoregressively.

**Key Contributions**
1. Constrained past and look-ahead context in every attention and convolution layer, with *chunk-aware* look-ahead so the effective latency does not multiply by depth (regular look-ahead of 2 frames × 17 layers × 40 ms = 1360 ms).
2. An activation cache that lets the non-autoregressive FastConformer encoder run as a recurrent model at inference with no recomputation.
3. A hybrid CTC/RNNT shared encoder and multi-look-ahead training so one model serves several latencies.
4. (Backbone, from the Fast Conformer paper) 8x downsampling to 80 ms frames with depth-wise separable convolutions: encoder 2.8x faster than Conformer at the same WER; limited-context attention plus a global token extends single-pass audio on one A100 from 15 to 675 minutes; on a 25k-hour set the RNNT model reaches 3.79 % WER on LibriSpeech test-other and 1.42 % on WSJ-92.

**Methodology**
- Approach type: architecture / inference method. ~114M-parameter models trained on LibriSpeech (with speed perturbation) and NeMo ASRSET 3.0 (26k hours); SentencePiece tokens; reported "latency" is the algorithmic look-ahead (audio the model waits for), not wall-clock.

**Experiments**
- LibriSpeech test-other (Table 1): offline CTC 5.7 / RNNT 5.0; buffered streaming 8.0 @1500 ms / 11.3 @2000 ms; cache-aware zero look-ahead 10.6 / 9.5 @0 ms; chunk-aware 7.1 / 6.3 @1360 ms.
- Latency sweep (Table 2, RNNT hybrid chunk-aware): **9.5 (0 ms), 9.0 (40 ms), 7.8 (240 ms), 7.5 (520 ms), 7.3 (680 ms), 6.3 (1360 ms)**.
- Multi-domain (Table 3, ASRSET): cache-aware RNNT at 520 ms gets 5.4 / 2.2 on test-other / test-clean and 10.6 averaged over 9 sets, vs 9.4 / 4.8 / 15.0 for the 2000 ms buffered baseline; CTC at 240 ms averages 12.6 vs 12.0 for buffered at 2000 ms.
- Multi-look-ahead (Table 4): one RNNT model gives 6.2 / 5.5 / 5.2 at 40 / 240 / 520 ms vs 6.4 / 5.9 / 5.4 for three single-latency models.

**Limitations**
- Acknowledged: not all latencies are feasible with regular look-ahead; zero look-ahead costs ~2x relative WER.
- Observed by reader: English only; the latency numbers exclude decoder and endpointing time; no Thai or code-switched evaluation.

**Relevance to a Thai/English production voice assistant**
This is the ASR half of a low-latency cascade: a 240–520 ms look-ahead buys most of the offline accuracy, and one model can be switched between latencies at runtime. Thai would need a Thai-trained FastConformer (NeMo supports it), but the architecture-level numbers transfer; they also show why Moshi's 5.7 % streaming ASR trails a dedicated 3.6 % streaming encoder.

---

### [@radford2023robust] Robust Speech Recognition via Large-Scale Weak Supervision (Whisper)

**Metadata**
- Authors: Alec Radford, Jong Wook Kim, Tao Xu, Greg Brockman, Christine McLeavey, Ilya Sutskever (OpenAI)
- Year: 2023 | Venue: ICML 2023 (peer-reviewed)
- arXiv: 2212.04356 | Citations: 9,165
- Code: https://github.com/openai/whisper (models and inference code)

**Problem**
Supervised ASR trained on ~1k-hour academic sets is superhuman in-distribution and brittle out of it; can simple scaling of weakly supervised internet transcripts give a zero-shot, robust, multilingual, multitask recogniser?

**Key Contributions**
1. 680,000 hours of weakly labelled audio, of which 117,000 hours cover 96 non-English languages and 125,000 hours are X→English translation.
2. One encoder–decoder Transformer with task/language tokens doing transcription, translation, language ID and voice-activity detection in 30-second windows; models from tiny (39M) to large.
3. Zero-shot evaluation protocol with a released text normaliser.

**Methodology**
- Approach type: large-scale weak supervision; no streaming — audio is processed in 30 s chunks, and long-form transcription shifts the window using predicted timestamps.
- Decoding heuristics for long-form (Section 4.5): beam 5, temperature fallback (0 → 1.0 in 0.2 steps when average log-prob < −1 or gzip compression ratio > 2.4), previous-text conditioning only below temperature 0.5, no-speech threshold 0.6, initial timestamp constrained to 0–1 s (Table 7).

**Experiments**
- Effective robustness (Table 2): matched on LibriSpeech test-clean, zero-shot Whisper makes **55.2 % fewer errors on average** across 12 other datasets than a supervised LibriSpeech model; the 39M tiny model at 6.7 % test-clean is competitive with the best supervised model out of distribution.
- Long-form (Fig. 6): beats NVIDIA STT Conformer-CTC Large on all seven long-form sets and most commercial APIs.
- Thai: Fleurs WER for large-v2 is **11.5** (Table 13; for Thai, Chinese, Japanese, Lao and Burmese a space is inserted between letters, so this is effectively a character error rate); Thai has 226 hours in the ASR training data (Appendix table), i.e. far below the ~1,000-hour knee the authors identify.
- Latency: not reported; the model is not streaming.

**Limitations**
- Acknowledged (Section 6): repeat loops, dropped first/last words and whole-segment hallucination in long-form; performance on lower-resource languages is poor and predicted by data size; fine-tuning was not studied.
- Observed by reader: 30 s windows and attention over the whole chunk make it unsuitable as a real-time endpointer; most "streaming Whisper" deployments re-run the window, which is what the Phase 3 cascade papers pay for in latency.

**Relevance to a Thai/English production voice assistant**
Whisper is the Thai ASR everybody fine-tunes (Typhoon-Audio's encoder is a Thai-fine-tuned Whisper-large-v3), so its 226 hours of Thai and the loop/hallucination failure modes are the baseline risk. Its robustness to noise and accents is the reason cascades still beat end-to-end models on VoiceBench, but for streaming it must be paired with a VAD or replaced by a cache-aware encoder.

---

### [@wang2024turntaking] Turn-taking and Backchannel Prediction with Acoustic and Large Language Model Fusion

**Metadata**
- Authors: Jinhan Wang, Long Chen, Aparna Khare, Anirudh Raju, Pranav Dheram, Di He, Minhua Wu, Andreas Stolcke, Venkatesh Ravichandran (UCLA, Amazon Alexa AI)
- Year: 2024 | Venue: IEEE ICASSP 2024 (peer-reviewed)
- arXiv: 2401.14717 | Citations: 34
- Code: not released

**Problem**
Silence-threshold endpointing is slow and wrong; the paper predicts continuously, at each word, whether the user will *continue*, is producing a *backchannel*, or is yielding the *turn*, using an LLM for linguistic cues and HuBERT for prosody.

**Key Contributions**
1. Extends TurnGPT-style prediction from two to three classes, adding backchannels.
2. Two fusion schemes (Opt1: acoustic features injected into the LLM branch; Opt2: late combination) over GPT2 (124M, fully fine-tuned) and RedPajama-3B (parameter-efficient fine-tuning).
3. Multi-task instruction fine-tuning with task descriptions and dialogue history.

**Methodology**
- Approach type: fine-tuning / fusion. Data: Switchboard human-human conversations, split by session 2000 : 300 : 138; each sample is a partial utterance labelled by its last word; the majority "continuing" class is downsampled in training. Metrics: per-class AUC and EER (threshold-free). Overlapping turns are excluded (left for future work). 8 V100s.

**Experiments**
- Single modality vs fusion (Table 1): HuBERT alone average AUC 0.7060 (EER 34.87); GPT2 text 0.8292; RedPajama text 0.8351; **RedPajama + HuBERT Opt1 0.8657, EER 20.33** — +22.6 % relative over acoustic-only and +3.67 % over text-only. Turn-taking AUC 0.9116, backchannel 0.7862.
- Instruction tuning (Table 2): RedPajama + HuBERT Opt1 rises to **0.8785 (EER 19.50)**, with the largest gain on backchannels (0.8229); adding dialogue history gives 0.8803 / 19.30 and turn-taking AUC 0.9197.
- Latency: not reported (offline classification on gold transcripts).

**Limitations**
- Acknowledged: overlap not modelled; "a polite AI agent might refrain" from overlapping, so only non-overlapping turns are predicted.
- Observed by reader: uses reference transcripts, not streaming ASR output; no end-to-end latency or deployment study; English; backchannel prediction remains the weakest class (AUC ≈ 0.82).

**Relevance to a Thai/English production voice assistant**
For a cascade, this is the component that decides *when* to stop listening: text cues from a small LLM beat prosody alone, and fusing both buys another ~4 % AUC. A Thai version needs a Thai-capable small LM and a Thai two-channel corpus with backchannel labels (none public), so a practical first step is the text-only variant on streaming ASR partials, accepting the ~0.03 AUC loss the paper measures.

---

### [@du2024cosyvoice] CosyVoice 2: Scalable Streaming Speech Synthesis with Large Language Models

**Metadata**
- Authors: Zhihao Du, Yuxuan Wang, Qian Chen, Xian Shi, Xiang Lv, Tianyu Zhao, Zhifu Gao, Yexin Yang, Changfeng Gao, Hui Wang, Fan Yu, Huadai Liu, Zhengyan Sheng, Yue Gu, Chong Deng, Wen Wang, Shiliang Zhang, Zhijie Yan, Jingren Zhou (Alibaba)
- Year: 2024 | Venue: technical report, "work in progress" **(preprint)**
- arXiv: 2412.10117 | Citations: 496
- Code: https://github.com/FunAudioLLM/CosyVoice (weights released)

**Problem**
Zero-shot LM + flow-matching TTS was offline-only; voice chat needs the first audio packet within a few text tokens, with no quality loss relative to offline synthesis and one model for both modes.

**Key Contributions**
1. Finite scalar quantisation (FSQ) inside the SenseVoice-Large ASR encoder as a supervised semantic tokenizer with full codebook use.
2. A simplified text–speech LM that drops the text encoder and speaker embedding so a pretrained text LLM can be the backbone.
3. Streaming by interleaving: every **N = 5 text tokens followed by M = 15 speech tokens**, with a "filling token" that asks for the next text chunk; the same LM runs offline when all text is given first.
4. Chunk-aware causal flow matching trained with four random masks (non-causal, full-causal, chunk-M, chunk-2M) plus a look-ahead convolution, so one flow model covers every latency setting and the wider masks self-distil into the narrow ones.

**Methodology**
- Approach type: architecture + training recipe. Data: tokenizer on 110,884 h Chinese + 99,918 h English; TTS on 130k h Chinese, 30k h English, 4.6k h Japanese, 2.2k h Korean; 1,500 h of instruction data (emotion, rate, dialect, fine-grained tags).
- Latency (Section 2.5) is given as a formula: first-package latency L_TTS = M·(d_lm + d_fm + d_voc) and, in a chat, L_chat ≤ N·d_llm + L_TTS. **No millisecond figure is reported in the paper.**

**Experiments**
- LibriSpeech test-clean (Table 5): WER **2.47 % offline / 2.45 % streaming** (human 2.66), NMOS 3.96 / 3.90, speaker similarity 0.745 / 0.751; baselines ChatTTS 6.84, F5-TTS not on this set.
- SEED test sets (Table 6): test-zh CER 1.45 (streaming 1.45), test-en WER 2.57 (streaming 2.38), test-hard 6.83 (streaming **8.08**); Seed-TTS 1.12 / 2.25 / 7.59, F5-TTS 1.56 / 1.83 / 8.67, MaskGCT 2.27 / 2.62 / 10.27. Streaming is "nearly lossless" except on hard cases.
- Ablation (Table 7): LLM initialisation −18.5 % relative CER on test-zh; dropping the speaker embedding and adding FSQ take CER from 3.63 to 1.45.
- Japanese/Korean: CER 18.79 / 7.98 — character-set overlap and data imbalance hurt.

**Limitations**
- Acknowledged: limited languages; languages with overlapping character sets degrade; no timbre control from text instructions; English trails Chinese because of data imbalance.
- Observed by reader: Thai is not supported; the only latency evidence is the formula, so first-packet time must be measured per GPU.

**Relevance to a Thai/English production voice assistant**
CosyVoice 2 is the TTS design that makes a cascade competitive on first-packet latency (speak after ~5 text tokens) without the word-level chunking artefacts LLaMA-Omni criticises, but it has no Thai voice or tokenizer data, so a Thai deployment would have to train the FSQ tokenizer and LM on Thai speech or use a different TTS; the chunk-aware flow-matching trick itself is language-agnostic.

---

### [@manakul2025enhancing] Enhancing Low-Resource Language and Instruction Following Capabilities of Audio Language Models (Typhoon-Audio)

**Metadata**
- Authors: Potsawee Manakul, Guangzhi Sun, Warit Sirichotedumrong, Kasima Tharnpipitchai, Kunat Pipatanakul (SCB 10X, University of Cambridge)
- Year: 2025 | Venue: Interspeech 2025 (peer-reviewed; arXiv v1 Sep 2024)
- arXiv: 2409.10999 | Citations: 14
- Code/models: Typhoon-Audio weights on Hugging Face (scb10x)

**Problem**
Audio LLMs built on multilingual Whisper and multilingual LLMs still fail on Thai; the paper measures the collapse and finds a data mixture that gives Thai + English audio understanding and speech instruction following in one model.

**Key Contributions**
1. Diagnosis: Qwen-Audio and SALMONN reach **95.1 % and 98.1 % WER on Thai** (CommonVoice-17) despite 6–7 % on English; DiVA 65.2 %; only Gemini-1.5-Pro holds (13.6 %).
2. Typhoon-Audio: SALMONN-style architecture (Whisper-large-v3 fine-tuned to Thai + BEATs → Q-Former → Typhoon-1.5-8B-Instruct with LoRA r = 8), pretrained on 1.82M examples (LibriSpeech 281K, GigaSpeech-M 900K, CommonVoice-Th 436K, Fleurs-Th 7.8K, Vulcan/Elderly/Gowajee 65.1K, AudioCaps/Clotho translated to Thai) and fine-tuned on 640K examples.
3. Evidence that matching *both* backbones to the target language matters, and that a 90/10 English/Thai prompt mixture plus ~20K generated Thai spoken-QA pairs is enough.

**Methodology**
- Approach type: fine-tuning / data-mixture study on an offline audio LM (audio + text prompt → text). Evaluation: ASR WER (LibriSpeech-other, CommonVoice-17 Thai), translation BLEU, gender accuracy (Fleurs), spoken QA F1, SpeechIF and ComplexIF judged by GPT-4o on a 1–10 scale.

**Experiments**
- Backbones (Table 3, CV subset): Whisper + Llama-3 Thai WER 16.66; Whisper-Th + Typhoon-1.5 **13.52** (English 9.15 vs 6.02 — the Thai gain costs English).
- Main (Table 4): Typhoon-Audio ASR En 8.72 / Th **14.17**, Th→En BLEU 24.14, Thai spoken-QA F1 **64.60** (Gemini-1.5-Pro 62.10), Thai SpeechIF **6.11** (Gemini 3.93), English SpeechIF 5.62; Typhoon2-Audio (same recipe, newer LLM) ASR 5.83 / 14.04, Thai SpQA 70.01, Thai SpeechIF 6.79.
- Mixture ablation (Table 5): SFT on English-only prompts destroys Thai ASR (WER 80.86); 10 % Thai prompts restore it (16.80) and Thai spoken QA improves further with generated Thai QA.
- Latency: not reported (offline model).

**Limitations**
- Acknowledged: conclusion only; the recipe uses ~1.8M + 0.64M examples and the English ASR of the Thai-tuned model is worse than vanilla Whisper.
- Observed by reader: Thai WER depends on word segmentation, which the paper does not specify; no streaming, no speech output, no latency; single Thai test set (CommonVoice-17).

**Relevance to a Thai/English production voice assistant**
This is the paper that sets expectations for Thai: a vanilla multilingual audio LLM is unusable (WER > 90 %), a Thai-matched encoder and LLM reach ~14 % WER and beat Gemini-1.5-Pro on Thai spoken QA and instruction following, and the mixture must keep ≥ 10 % Thai or the ability vanishes. It supports a cascade with a Thai-fine-tuned Whisper (or a Thai audio LLM as the understanding stage) over any English-centric end-to-end S2S model.

---

## Cross-paper synthesis

### Reported end-to-end and component latencies

| Paper | System | Latency reported | What exactly was measured | Hardware / conditions |
| --- | --- | --- | --- | --- |
| Moshi (2410.00037) | Full-duplex S2S, 7B | **160 ms theoretical, 200 ms practical** | Codec frame (80 ms) + acoustic delay τ = 1 frame (80 ms); practical figure is the authors' statement in the abstract | not stated in the text |
| SyncLLM (2409.15594) | Full-duplex S2S on Llama3-8b | **160 / 200 / 240 ms chunks** | Chunk size = generation deadline and maximum tolerated network delay; no wall-clock figure | simulated LLM–LLM interaction |
| LLaMA-Omni (2409.06666) | Speech-in/speech-out on Llama-3.1-8B | **236 ms (Ω = 10) … 563 ms (Ω = 100)** | Speech instruction end → first speech audio; cascaded baselines < 300 ms with quality loss; SpeechGPT > 4,500 ms; GPT-4o 320 ms quoted | 1 × NVIDIA L40 |
| Freeze-Omni (2411.00774, read for the table) | Cascaded-in-one-model S2S, frozen Qwen2-7B | **745 ms avg / 753 ms median / 1,020 ms p90** statistical; + 160–320 ms endpoint detection; **≈ 1.2 s in real use** with 200–300 ms network | LLM interrupted → first PCM chunk (478 ms to first text chunk, 237 ms to first speech chunk, 26 ms prefills/decode) | PyTorch bf16, speech-token chunk 40 |
| Full-Duplex-Bench (2503.04721) | Moshi / dGSLM / Freeze-Omni / Gemini Live | **0.265 / 0.352 / 0.953 / 1.301 s** after user turn end; **0.257 / 2.531 / 1.409 / 1.183 s** after an interruption | Time from end of user speech (or interruption) to start of model speech, only on turns the model took | official implementations, Candor + synthetic |
| Streaming FastConformer (2312.17279) | Streaming ASR encoder, 114M | **0 / 40 / 240 / 520 / 680 / 1,360 ms** look-ahead; buffered baseline 1,500–2,000 ms | Algorithmic look-ahead (audio the encoder waits for) vs WER; excludes decoder and endpointing | — |
| CosyVoice 2 (2412.10117) | Streaming TTS | **formula only**: L_TTS = M·(d_lm + d_fm + d_voc), L_chat ≤ N·d_llm + L_TTS with N = 5, M = 15 | First-package latency as a function of per-token compute; no ms value | — |
| Qwen2.5-Omni (2503.20215) | Omni S2S, 7B | **not reported** numerically | Qualitative four-part decomposition of initial-packet latency; 2 s encoder blocks, DiT lookahead 1 block | — |
| LSLM (2408.02622) | Barge-in detector in a TTS | **not reported**; success = stop within 1 s of interruption | Interruption detection F1 (98.0 clean, 85.2 noisy unseen speakers) | — |
| Turn-taking fusion (2401.14717) | End-of-turn predictor | **not reported** | Offline AUC on Switchboard | 8 × V100 training |
| VoiceBench (2410.17196), Whisper (2212.04356), Typhoon-Audio (2409.10999) | — | **not reported** | Accuracy/robustness only; Whisper is non-streaming (30 s windows) | — |

### Five takeaways for an engineer choosing between end-to-end S2S and a modular cascade

1. **The latency gap is real but smaller than the marketing.** Native duplex models sit at ~200–350 ms (Moshi 160/200 ms by design, 0.265 s measured on Full-Duplex-Bench; LLaMA-Omni 236 ms on an L40). A well-built cascade-in-one-model like Freeze-Omni measures ~0.75 s median and ~1.2 s end to end once endpointing and network are included, and Gemini Live measured 1.3 s. The ~0.5–1 s difference comes from three places a cascade can attack individually: endpoint detection (160–320 ms in Freeze-Omni; replaceable by an LLM/acoustic end-of-turn predictor), LLM time-to-first-text (478 ms in Freeze-Omni), and TTS first packet (CosyVoice 2 starts after 5 text tokens; ASR look-ahead of 240–520 ms costs < 1 WER point on the streaming FastConformer).

2. **Cascades still win on what the assistant says.** VoiceBench: Whisper-large-v3 + LLaMA-3.1-8B scores 79 overall vs 37.5 for LLaMA-Omni and 27.5 for Moshi; GPT-4o-Audio only narrows the gap to its own pipeline. End-to-end tuning damaged text ability (−11 points) and safety (refusal 98 % → 11 %) in LLaMA-Omni. Qwen2.5-Omni (74.1 on VoiceBench) shows the gap closing in 2025, but only for English/Chinese and at 7B+ scale.

3. **Turn-taking manners come from an explicit module, not from being end-to-end.** On Full-Duplex-Bench the two end-to-end models interrupt pauses 93–98 % of the time; Freeze-Omni's chunk-level speak/listen state classifier halves that and gives coherent post-interruption answers (GPT-4o score 3.6 vs 0.77 for Moshi). An LLM + acoustic end-of-turn predictor (AUC 0.88 on Switchboard) is the cascade's equivalent and can be improved independently.

4. **For Thai, only the cascade has evidence.** Every S2S paper in the set is English (plus Chinese for Qwen/CosyVoice); none reports Thai. Whisper large-v2 is at 11.5 Fleurs CER with just 226 training hours; multilingual audio LLMs collapse to > 90 % Thai WER until the encoder *and* LLM are Thai-matched (Typhoon-Audio: 14 % WER, beats Gemini-1.5-Pro on Thai spoken QA). Streaming TTS with Thai voices is not covered by CosyVoice 2 at all. A Thai product therefore needs Thai-specific ASR and TTS components regardless of architecture, which removes most of the "one model" advantage of S2S.

5. **If you go end-to-end, budget for the hidden work; if you go cascade, budget for the glue.** S2S requires a 7B-class model that is simultaneously the ASR, LLM and TTS, duplex training data (Fisher-like two-channel speech, or SyncLLM's 212k synthetic hours), echo/noise augmentation of the user stream (Moshi), and quantization that hurts it more than a text LLM. A cascade requires an endpointer (silence threshold → learned predictor), a streaming ASR with a chosen look-ahead, incremental LLM decoding, a TTS that speaks after a few tokens, and an interruption path (LSLM shows even a dedicated listener misses ~17 % of interruptions in noise) — each piece measurable and swappable, which is why the benchmark papers (VoiceBench, Full-Duplex-Bench) recommend measuring both halves of the problem rather than trusting a single architecture claim.
