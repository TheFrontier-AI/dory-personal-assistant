"""Smoke test for a running GLM-4-Voice server (deploy/glm_voice/server.py): one turn, timings only.

    GLM_VOICE_TOKEN=... uv run python deploy/glm_voice/smoke.py ws://204.12.189.216:8765/voice [utterance.wav]

Sends a typed turn (or a 16 kHz mono PCM16 WAV as the person's speech, then {"type": "end"}) and
prints time to ready, time to first audio, seconds of audio received and what the model said.
Never prints the token; audio is not saved.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import wave

import websockets

IN_RATE, OUT_RATE = 16_000, 24_000
GREETING = "Say hello to the person in one short sentence."
CASCADE_SAY = "Hello. This is the cascade voice test: two in policy, take the eight o'clock?"


async def main(url: str, wav: str | None) -> int:
    token = os.environ.get("GLM_VOICE_TOKEN", "")
    if not token:
        print("set GLM_VOICE_TOKEN")
        return 2
    t0 = time.monotonic()
    headers = {"Authorization": f"Bearer {token}"}
    # websockets >= 13 (asyncio client) vs the legacy client gradio pins the VM to (< 13)
    kw = (
        "additional_headers" if int(websockets.__version__.split(".")[0]) >= 13 else "extra_headers"
    )
    async with websockets.connect(url, max_size=None, **{kw: headers}) as ws:
        first = json.loads(await ws.recv())
        print(f"ready after {time.monotonic() - t0:.2f}s: {first}")
        if first.get("type") != "ready":
            return 1
        if wav:
            with wave.open(wav, "rb") as w:
                assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (IN_RATE, 1, 2), (
                    "need 16 kHz mono PCM16"
                )
                pcm = w.readframes(w.getnframes())
            for i in range(0, len(pcm), 1280):  # 40 ms frames, paced like a microphone
                await ws.send(pcm[i : i + 1280])
                await asyncio.sleep(0.04)
            await ws.send(json.dumps({"type": "end"}))
        else:
            await ws.send(json.dumps({"type": "text", "text": GREETING}))
        sent = time.monotonic()
        first_audio = None
        audio_bytes, said = 0, []
        while True:
            msg = await asyncio.wait_for(ws.recv(), 120)
            if isinstance(msg, bytes | bytearray):
                if first_audio is None:
                    first_audio = time.monotonic() - sent
                audio_bytes += len(msg)
                continue
            ev = json.loads(msg)
            if ev.get("type") == "heard":  # the cascade sidecar: Dory's brain would answer here
                print(f"heard after {time.monotonic() - sent:.2f}s: {ev.get('text', '')!r}")
                sent = time.monotonic()
                await ws.send(json.dumps({"type": "say", "text": CASCADE_SAY, "final": True}))
            elif ev.get("type") == "said":
                said.append(ev.get("text", ""))
            elif ev.get("type") == "turn":
                break
            elif ev.get("type") == "error":
                print("server error:", ev.get("text"))
                return 1
        await ws.send(json.dumps({"type": "close"}))
    total = time.monotonic() - sent
    print(
        f"first audio {first_audio if first_audio is None else round(first_audio, 2)} s, "
        f"turn done {total:.2f} s, audio {audio_bytes / (OUT_RATE * 2):.1f} s"
    )
    print("said:", "".join(said).strip()[:300])
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)))
