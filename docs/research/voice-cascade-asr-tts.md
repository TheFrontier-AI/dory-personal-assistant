# Voice cascade on the GLM VM: ASR and TTS options (27 Oct 2026)

Scope: the booking demo needs tools, GLM-4-Voice has none, so the same Nebius H200 VM gets a
CASCADE path: ASR -> GLM-5.3 on Token Factory (exists) -> TTS, streamed sentence by sentence as
PCM16 24 kHz over the WebSocket protocol `glm_voice.py` already speaks. English first, Thai
nice-to-have. Everything below was checked against the current model cards, docs and sources on
2026-10-27; numbers marked *estimate* were not measured.

## Recommendation

- **ASR: `nvidia/parakeet-tdt-0.6b-v3` through NeMo** — NVIDIA open model (CC-BY-4.0), 600M,
  English + 24 European languages with auto language detection, loads with two lines, takes a
  numpy array, and needs no NIM/NVAIE licence. Swap-in for Thai: `faster-whisper large-v3-turbo`
  (same venv) or `typhoon-ai/typhoon-asr-realtime` (NeMo, Thai, CC-BY-4.0).
- **TTS: Kokoro-82M first, Magpie TTS behind the same function second** — Kokoro is a pip
  package, Apache-2.0, 24 kHz native (matches the protocol), yields audio per chunk; it gets the
  demo speaking in an afternoon. `nvidia/magpie_tts_multilingual_357m` (NVIDIA Open Model
  License, open weights since Aug 2026, NeMo `do_tts` per sentence, 22.05 kHz) is the NVIDIA
  story for the judges: put it behind the same `synth(sentence) -> int16 24 kHz` function once
  `do_tts` is measured on the VM. Neither speaks Thai.
- **Layout: one new venv (Python 3.12, torch >= 2.7) and one sidecar process** on another
  port, same wire protocol. The GLM venv is pinned to torch 2.3 / transformers 4.44.1 / Python
  3.11; NeMo 3.0 needs torch >= 2.7 and its install docs assume Python >= 3.12, so they cannot
  share a venv. The GPU is shared by both processes; VRAM is not a constraint (section 4).
- **Zero-install fallback:** build.nvidia.com hosts Parakeet ASR and Magpie TTS behind
  `grpc.nvcf.nvidia.com:443` with `nvidia-riva-client`; free key, 40 requests/min reported.

## 1. Comparison

| Option | Kind | Langs (Thai?) | Licence | Install | In / out | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `nvidia/parakeet-tdt-0.6b-v3` | ASR, offline per utterance | 25 European, auto-detect (no) | CC-BY-4.0, "ready for commercial/non-commercial use" | `nemo-toolkit[asr]` (PyPI 3.0.0, 2026-08-07) | 16 kHz mono float32 numpy -> text + punctuation | Open ASR leaderboard avg WER 6.34%; also loadable with Transformers from source (`AutoModelForTDT`) |
| `nvidia/nemotron-3.5-asr-streaming-0.6b` | ASR, cache-aware streaming RNNT | 40 locales; 32 out of the box; **Thai is "adaptation-ready" = needs fine-tuning** | OpenMDW-1.1 | NeMo from git `main` (card), or Transformers `AutoModelForRNNT` | 16 kHz; chunk 80 ms – 1.12 s; `language="en-US"` or `"auto"` | The "Nemotron" name; streaming partials. Not needed for an utterance-level cascade |
| `nvidia/nemotron-speech-streaming-en-0.6b` | ASR streaming | English only | NVIDIA Open Model License | NeMo, or NeMo-Speech.cpp GGUF | 16 kHz | Predecessor of the above |
| `nvidia/canary-1b-v2` | ASR + translation | 25 European (no) | CC-BY-4.0 | NeMo / Transformers | 16 kHz; RTFx 749 | Bigger, slower; only if translation is wanted |
| `typhoon-ai/typhoon-asr-realtime` | ASR | **Thai** | CC-BY-4.0 + OpenTyphoon terms | NeMo (`ASRModel.from_pretrained`) or `pip install typhoon-asr` | 16 kHz; CER 0.098, RTFx 4097 | 114M FastConformer-Transducer; same venv as Parakeet |
| `faster-whisper` 1.2.1, `large-v3-turbo` | ASR | 99 Whisper langs (**Thai yes**) | MIT (code); Whisper weights MIT | `pip install faster-whisper` + cuBLAS 12 / cuDNN 9 | `transcribe(np.ndarray float32 16 kHz)` | CTranslate2 4.8.4; the general fallback |
| `openai-whisper` 20231117 in the GLM venv | ASR | Whisper langs (Thai yes) | MIT | already installed | `whisper.load_model("large-v3").transcribe(np.float32)` | Zero install, but torch 2.3 and that old version have no `turbo`; slowest |
| Kokoro-82M (`kokoro` 0.9.4) | TTS | en (US/GB), es, fr, hi, it, ja, pt-br, zh (no) | Apache-2.0 (weights and code) | `pip install kokoro soundfile` + `apt install espeak-ng`; Python >= 3.10, < 3.13 | text -> 24 kHz float per chunk (generator) | 54 voices (`af_heart`...); split on `\n` by default, feed one sentence per call |
| `nvidia/magpie_tts_multilingual_357m` (v2607) | TTS | ar zh en fr de hi it ja ko pt es vi (no) | NVIDIA Open Model License, "ready for commercial use" | `nemo_toolkit[tts]@main` + `kaldialign` | `do_tts(text, language, speaker_index)` -> 22.05 kHz; 5 English voices (Aria, Jason, John, Leo, Sofia) | 364M. Zero-shot cloning removed. No streaming API in the open checkpoint; NIM measures 47 ms TTFA on H100 |
| Chatterbox Multilingual (NIM community) | TTS | 24 locales (no Thai) | MIT | NIM container only in NVIDIA's matrix | — | Not better for this demo; skipped |
| build.nvidia.com hosted Parakeet / Magpie | cloud ASR / TTS | as above | NVIDIA API trial terms | `pip install nvidia-riva-client` | gRPC + function id, or HTTP for Magpie | 40 RPM free tier (forum reports) |

Thai in one line: none of the NVIDIA open speech models transcribe or speak Thai out of the box
today (Nemotron 3.5 ASR lists `th-TH` only as fine-tune-to-enable). Thai ASR = faster-whisper or
Typhoon; Thai TTS is out of scope for this VM.

## 2. Install (fresh venv on the VM, Ubuntu + CUDA 12)

NeMo's "bring your own PyTorch" path: install torch first (>= 2.7), then NeMo; never
`uv sync --locked` (it replaces torch with NVIDIA's pinned build). One venv holds ASR, both TTS
engines, the Whisper fallback and the cloud client.

```bash
sudo apt-get install -y libsndfile1 ffmpeg espeak-ng          # espeak-ng is Kokoro's G2P
uv venv --python 3.12 ~/cascade/.venv && source ~/cascade/.venv/bin/activate
uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
uv pip install 'nemo-toolkit[asr,tts]' kaldialign              # Parakeet, Typhoon, Magpie
uv pip install kokoro soundfile                                # Kokoro (needs Python < 3.13)
uv pip install faster-whisper                                  # Thai fallback (CTranslate2)
uv pip install nvidia-riva-client                              # cloud fallback (gRPC)
# faster-whisper on GPU wants cuBLAS 12 + cuDNN 9 on LD_LIBRARY_PATH; the torch cu126 wheels
# already bring nvidia-cublas-cu12 / nvidia-cudnn-cu12 9.x, so only the path is needed:
export LD_LIBRARY_PATH=$(python -c 'import os, nvidia.cublas.lib, nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__)+":"+os.path.dirname(nvidia.cudnn.lib.__file__))')
```

- `nemo_toolkit` 3.0.0 on PyPI (2026-08-07) declares `torch>=2.6.0`, Python >= 3.10; the docs
  say torch >= 2.7 and test Python 3.13 / PyTorch 2.12 / CUDA 12.6 or 13.2. Parakeet v3's card
  installs `pip install -U nemo_toolkit['asr']`; the Nemotron 3.5 and Magpie cards install from
  git `main` (`pip install git+https://github.com/NVIDIA/NeMo.git@main#egg=nemo_toolkit[asr]`,
  `pip install nemo_toolkit[tts]@main`). If 3.0.0 refuses a checkpoint newer than Aug 2026,
  switch that one line to `@main`.
- *Estimate*: torch cu126 wheels ~3 GB, NeMo and its deps (lightning, lhotse, hydra, numba) a
  further ~1 GB, Parakeet weights 2.4 GB, Kokoro ~0.3 GB, Magpie ~1.5 GB, Whisper turbo ~1.6 GB.
- Magpie's recommended inference knobs from NVIDIA's post: `cfg_scale=2.5, temperature=0.6,
  top_k=80, apply_attention_prior=True, prior_epsilon=0.1`.

## 3. Minimal Python

All snippets take `np.int16` at 16 kHz in and return `np.int16` at 24 kHz out, so they drop into
the sidecar untouched. Load once at process start and run one warm-up call: the first NeMo /
CTranslate2 call is seconds slower than the rest (*estimate; measure with `StageTimer`*).

### (a) ASR: Parakeet, int16 16 kHz numpy -> text

NeMo's `transcribe()` accepts "file paths (strings), lists of paths, numpy arrays, or PyTorch
tensors"; "audio must be 16 kHz mono-channel" and float32 (the mixin does not resample).

```python
import numpy as np
import nemo.collections.asr as nemo_asr

asr = nemo_asr.models.ASRModel.from_pretrained(model_name="nvidia/parakeet-tdt-0.6b-v3")
asr.eval()  # cuda is picked automatically


def transcribe(pcm16: np.ndarray) -> str:  # pcm16: int16, 16 kHz, mono
    audio = pcm16.astype(np.float32) / 32768.0
    out = asr.transcribe([audio], batch_size=1, verbose=False)
    return out[0].text  # punctuated, capitalised


# Thai with the same venv and call shape:
# asr = nemo_asr.models.ASRModel.from_pretrained("typhoon-ai/typhoon-asr-realtime")
```

Nemotron 3.5 ASR, if the name matters: `ASRModel.from_pretrained(model_name="nvidia/nemotron-3.5-asr-streaming-0.6b")`
and the same `transcribe([...])`; streaming partials need NeMo's
`speech_to_text_cache_aware_streaming_infer.py` or the Transformers `AutoModelForRNNT` +
`processor.set_num_lookahead_tokens(6)` path. Not worth it for an utterance-level cascade.

faster-whisper fallback (`transcribe(audio: Union[str, BinaryIO, np.ndarray], ...)`; an ndarray
is used as-is at the model's 16 kHz, so pass float32 16 kHz):

```python
from faster_whisper import WhisperModel

fw = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")


def transcribe_whisper(pcm16: np.ndarray, lang: str | None = None) -> str:
    segments, _info = fw.transcribe(pcm16.astype(np.float32) / 32768.0, language=lang, beam_size=1)
    return " ".join(s.text.strip() for s in segments)
```

Zero-install option in the GLM venv (torch 2.3, `openai-whisper` 20231117 is already there for
the GLM tokenizer): `whisper.load_model("large-v3").transcribe(audio_f32)["text"]`; that version
has no `turbo`, so it is the slowest of the three and only for a smoke test.

### (b) TTS: sentence -> int16 24 kHz, streamed per chunk

Kokoro: `KPipeline(lang_code, repo_id, device)` and
`pipeline(text, voice, speed=1, split_pattern=r'\n+')` is a generator of `Result` with
`.graphemes`, `.phonemes` and `.audio` (a torch float tensor at 24 kHz). Feed one sentence per
call and yield each chunk as it comes.

```python
import numpy as np, torch
from kokoro import KPipeline

tts = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", device="cuda")  # 'a' = US English
TTS_RATE = 24000  # native


def synth(sentence: str, voice: str = "af_heart"):
    """Yields np.int16 24 kHz chunks; Kokoro splits on split_pattern, one sentence = one chunk."""
    for r in tts(sentence, voice=voice, split_pattern=None):
        if r.audio is None:
            continue
        yield (r.audio.clamp(-1, 1).numpy() * 32767).astype(np.int16)
```

Magpie behind the same function (NeMo; 22.05 kHz, so resample 147:160 to 24 kHz; no streaming
inside one call, which is fine because the cascade already streams per sentence):

```python
import torchaudio
from nemo.collections.tts.models import MagpieTTSModel

magpie = MagpieTTSModel.from_pretrained("nvidia/magpie_tts_multilingual_357m").cuda().eval()
SPEAKERS = {"Aria": 0, "Jason": 1, "John": 2, "Leo": 3, "Sofia": 4}


def synth_magpie(sentence: str, speaker: str = "Sofia"):
    audio, audio_len = magpie.do_tts(
        sentence, language="en", apply_TN=True, speaker_index=SPEAKERS[speaker]
    )
    wav = audio[0, : int(audio_len[0])].float().cpu()  # 22.05 kHz
    wav24 = torchaudio.functional.resample(wav, 22050, 24000)
    yield (wav24.clamp(-1, 1).numpy() * 32767).astype(np.int16)
```

`do_tts(transcript, language, apply_TN, use_cfg, speaker_index)` "returns the generated audio and
the length of the audio" (card). The exact tensor shape of `audio` is the one thing to check on
the first run; the card does not print it.

### (c) NVIDIA cloud fallback (build.nvidia.com, no install on the GPU)

Sign in at build.nvidia.com, press **Get API Key** on any model page (an NGC personal key with
the Cloud Functions scope also works), export `NVIDIA_API_KEY=nvapi-...`. Server
`grpc.nvcf.nvidia.com:443` with SSL; the model is selected by a `function-id` metadata entry.
Function ids rotate per release: resolve them instead of hard-coding (the Magpie id below is the
one printed on its card today).

```python
import io, os, wave, numpy as np, requests, riva.client
from riva.client import AudioEncoding

KEY = os.environ["NVIDIA_API_KEY"]


def function_id(pattern: str) -> str:  # e.g. "parakeet-tdt-0.6b-v3", "magpie-tts-multilingual"
    r = requests.get(
        "https://api.nvcf.nvidia.com/v2/nvcf/functions?visibility=public,authorized",
        headers={"Authorization": f"Bearer {KEY}"},
        timeout=20,
    ).json()
    return next(f["id"] for f in r["functions"] if f["status"] == "ACTIVE" and pattern in f["name"])


def auth(fid: str) -> riva.client.Auth:
    return riva.client.Auth(
        uri="grpc.nvcf.nvidia.com:443",
        use_ssl=True,
        metadata_args=[["function-id", fid], ["authorization", f"Bearer {KEY}"]],
    )


# ASR: Parakeet (English on parakeet-tdt-0.6b-v2 / -v3, 25 languages on parakeet-1.1b-rnnt-multilingual)
asr = riva.client.ASRService(auth(function_id("parakeet")))


def cloud_transcribe(pcm16: np.ndarray) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:  # 16-bit mono WAV, what the hosted ASR expects
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm16.tobytes())
    cfg = riva.client.RecognitionConfig(
        encoding=AudioEncoding.LINEAR_PCM,
        sample_rate_hertz=16000,
        language_code="en-US",
        audio_channel_count=1,
        max_alternatives=1,
        enable_automatic_punctuation=True,
    )
    resp = asr.offline_recognize(buf.getvalue(), cfg)
    return " ".join(r.alternatives[0].transcript for r in resp.results)


# TTS: Magpie multilingual (card's current function id 877104f7-e885-42b9-8de8-f6e4c6303969)
tts = riva.client.SpeechSynthesisService(auth("877104f7-e885-42b9-8de8-f6e4c6303969"))


def cloud_synth(sentence: str) -> np.ndarray:  # int16 24 kHz
    resp = tts.synthesize(
        sentence,
        "Magpie-Multilingual.EN-US.Sofia",
        "en-US",
        sample_rate_hz=24000,
        encoding=AudioEncoding.LINEAR_PCM,
    )
    return np.frombuffer(resp.audio, dtype=np.int16)
```

Magpie also has a plain HTTP form:
`POST https://877104f7-e885-42b9-8de8-f6e4c6303969.invocation.api.nvcf.nvidia.com/v1/audio/synthesize`
with form fields `text`, `language=en-US`, `voice=Magpie-Multilingual.EN-US.Aria`,
`encoding=LINEAR_PCM`, `sample_rate_hz` (the page shows 44100; the model is 22.05 kHz native), and
`GET .../v1/audio/list_voices`. Expect ~100–300 ms per short request from Bangkok to NVCF
(*estimate*: NVIDIA's own 47 ms TTFA on H100 plus a trans-Pacific round trip); it is a fallback,
not the demo path. Limits: NVIDIA Developer Forum threads consistently report **40 requests per
minute** on a free key and "1,000 credits" at sign-up (one credit per call), with NVIDIA staff
answering that the free tier gets no increase; a third-party tracker (June 2026) says the credit
cap was dropped and only 40 RPM remains. No official page states either, so budget for 40 RPM.
`nvidia-riva-client` 2.27.0 (MIT) depends only on `grpcio`.

## 4. VRAM and process layout

| Resident on the H200 (141 GB) | VRAM |
| --- | --- |
| GLM-4-Voice-9B bf16 (`model_server.py`) + KV cache | ~18 GB weights, ~20–24 GB in use (*estimate*: 9B × 2 bytes) |
| GLM tokenizer (Whisper-VQ encoder) + CosyVoice decoder (`server.py`) | ~3–5 GB (*estimate*) |
| Parakeet-TDT-0.6b-v3 fp32 | ~2.4 GB weights, ~4 GB in use (*estimate*) |
| Kokoro-82M | < 1 GB (*estimate*) |
| Magpie 357M + NanoCodec (NeMo, batch 1) | ~2–3 GB (*estimate*; NVIDIA's NIM profile at batch 8 is 12.6 GiB, an upper bound) |
| faster-whisper large-v3-turbo fp16 | ~2–3 GB (*estimate*) |

Everything together stays under ~40 GB; more than 100 GB remains free, so no quantisation,
offloading or scheduling is needed. Read the real figures off `nvidia-smi` after the first
warm-up call and put them in this table.

Run the cascade as a **sidecar**, not inside `server.py`:

- Different venv is forced (torch 2.3 vs >= 2.7, Python 3.11 vs 3.12), so it is a separate
  process anyway: `~/cascade/.venv/bin/python cascade_server.py --port 8766`, a third systemd
  unit next to `glm-model` / `glm-voice`, same bearer token, same `--idle-shutdown-min` hook.
- Same wire protocol as `deploy/glm_voice/server.py` (up: PCM16 16 kHz frames + `{type: end}` /
  `{type: text}`; down: PCM16 24 kHz + `ready` / `said` / `interrupted` / `turn` / `error`), so
  `glm_voice.py` switches paths by URL and nothing in `center.py` or `glm_room.py` changes.
  `said` can now carry the real sentence text, and barge-in = stop the TTS generator and drop
  the queue.
- Two CUDA contexts on one GPU are fine; the only shared resource is compute, and the ASR / TTS
  calls are tens of milliseconds next to the LLM round trip (GLM-5.3 at 5–9 s a turn is the
  latency to attack, not the speech models).
- The text brain call is the existing Token Factory client with tools; the cascade server only
  needs an HTTP hook to it (or runs the ADK agent in-process if the Dory package is installed in
  the same venv — avoid: that drags torch-free Dory deps onto the GPU box; call the web service).

## Sources

- Parakeet TDT 0.6b v3 model card: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 (languages, licence, NeMo and Transformers usage, leaderboard WER)
- Nemotron 3.5 ASR: https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b (40 locales, Thai adaptation-ready, OpenMDW-1.1, chunk sizes, NeMo/Transformers code)
- Nemotron ASR streaming (English): https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b
- Canary 1B v2: https://huggingface.co/nvidia/canary-1b-v2
- Typhoon ASR real-time: https://huggingface.co/scb10x/typhoon-asr-realtime (served as `typhoon-ai/typhoon-asr-realtime`)
- NeMo-Speech install (bring-your-own PyTorch >= 2.7, `uv pip`, no `uv sync --locked`): https://docs.nvidia.com/nemo/speech/latest/starthere/install.html ; tested baseline: https://docs.nvidia.com/nemo/speech/3.0.0/starthere/install.html ; repo README: https://github.com/NVIDIA-NeMo/Speech
- NeMo ASR inference (numpy input, 16 kHz mono): https://docs.nvidia.com/nemo/speech/latest/asr/inference.html ; mixin source: https://raw.githubusercontent.com/NVIDIA-NeMo/Speech/main/nemo/collections/asr/parts/mixins/transcription.py
- PyPI metadata (versions, Python ranges, deps): https://pypi.org/pypi/nemo_toolkit/json , https://pypi.org/project/kokoro/ , https://pypi.org/pypi/faster-whisper/json , https://pypi.org/pypi/ctranslate2/json , https://pypi.org/pypi/nvidia-riva-client/json , https://pypi.org/pypi/misaki/json
- Kokoro: https://huggingface.co/hexgrad/Kokoro-82M , https://raw.githubusercontent.com/hexgrad/kokoro/main/README.md , https://raw.githubusercontent.com/hexgrad/kokoro/main/kokoro/pipeline.py
- faster-whisper: https://raw.githubusercontent.com/SYSTRAN/faster-whisper/master/README.md , https://raw.githubusercontent.com/SYSTRAN/faster-whisper/master/faster_whisper/transcribe.py
- Magpie TTS open checkpoint: https://huggingface.co/nvidia/magpie_tts_multilingual_357m ; NVIDIA post with NIM latency table: https://huggingface.co/blog/nvidia/magpie-tts-multilingual-voice-agents ; NIM model card (22.05 kHz, zero-shot variant): https://build.nvidia.com/nvidia/magpie-tts-multilingual/modelcard ; hosted API page: https://build.nvidia.com/nvidia/magpie-tts-multilingual/api ; NIM TTS support matrix (VRAM profiles, Chatterbox): https://docs.nvidia.com/nim/speech/latest/reference/support-matrix/tts.html
- NVIDIA Open Model License (24 Oct 2025; commercial use, derivatives, notice file): https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/
- Hosted Parakeet: https://build.nvidia.com/nvidia/parakeet-tdt-0_6b-v2/api , https://build.nvidia.com/nvidia/parakeet-1_1b-rnnt-multilingual-asr/api ; Riva client script and proto: https://raw.githubusercontent.com/nvidia-riva/python-clients/main/scripts/asr/transcribe_file_offline.py , https://raw.githubusercontent.com/nvidia-riva/common/main/riva/proto/riva_asr.proto ; LiteLLM's NVCF notes: https://docs.litellm.ai/docs/providers/nvidia_riva.md
- Free-tier limits (unofficial): https://forums.developer.nvidia.com/t/request-for-nvidia-build-api-rate-limit-increase-40-rpm-200-rpm/378450 , https://forums.developer.nvidia.com/t/is-nim-free/369368 , https://yangmao.ai/en/providers/nvidia-build/free-tier/
- GLM-4-Voice: https://raw.githubusercontent.com/zai-org/GLM-4-Voice/main/README.md ; this repo's `deploy/glm_voice/install.sh` and `server.py` (torch 2.3 pin, `openai-whisper` 20231117, protocol)
- HF model listings used to confirm what NVIDIA has published (2026-10-27): https://huggingface.co/api/models?author=nvidia&pipeline_tag=automatic-speech-recognition , https://huggingface.co/api/models?author=nvidia&pipeline_tag=text-to-speech

Not checked: nothing here was installed or run on the VM, so every latency and VRAM figure
marked *estimate* is arithmetic, not a measurement; the faster-whisper `"large-v3-turbo"` model
name and Magpie's `do_tts` output tensor shape were read from docs, not executed; the NVIDIA
AI Enterprise requirement applies to the NIM containers only and was not re-read on the NIM
prerequisites page.
