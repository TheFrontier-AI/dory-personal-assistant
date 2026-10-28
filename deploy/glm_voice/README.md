# GLM-4-Voice server for Dory's web Live call

English small talk on a self-hosted GPU, by the owner's decision of 26 Oct 2026 (design note:
`docs/superpowers/specs/2026-10-26-dory-glm-voice-design.md`). GLM-4-Voice speaks Chinese and
English, has no tool calling (so no company data, no `ask_dory`) and no input transcript.

## 1. The machine: `vm.sh` (Nebius AI Cloud CLI, profile `dory`, project `Dory`)

```bash
deploy/glm_voice/vm.sh create          # preemptible H200 (spot, capped) + static IP; --on-demand for the judged demo
deploy/glm_voice/vm.sh provision       # install everything over SSH (20-40 min, detached on the VM; prints the token once)
deploy/glm_voice/vm.sh sa              # once: the VM's service account; prints the role grant for a tenant admin
deploy/glm_voice/vm.sh provision       # again: writes the stop command the idle stop and the nightly timer run
deploy/glm_voice/vm.sh status | start | stop | ip | ssh
```

`sa` makes the VM's identity: a service account `glm-voice-power` that `create` ATTACHES to the VM
(`--service-account-id`), so the metadata service hands out its tokens inside the VM and no key file
exists anywhere (`http://metadata.nebius.internal/v1/iam/sa/token/access_token`). What `sa` cannot do
from this account is the role: creating a tenant group and an access permit needs the tenant `admin`
role, and the owner is an `editor`. `sa` therefore prints the admin's three commands (custom group,
membership, `compute.instance-power-operator` on this one instance), or the admin simply adds the
owner to the `admins` group and `sa` finishes on its own. A VM created before the service account
existed has no identity attached: recreate it afterwards (`vm.sh delete`, `vm.sh create [--on-demand]`,
`vm.sh provision`; the weights download again, about 10 minutes).

Nebius access keys (an id plus a secret, made for Object Storage and other AWS-compatible services)
authenticate nothing in the control API and are never what this needs.

## "Live call failed" on the website: what it means

The web call and the Discord room both open ONE WebSocket to `DORY_GLM_VOICE_URL`; nothing else is
involved (no WebRTC, no third-party relay). The error the page shows names the cause:

| Page says | Cause | Fix |
| --- | --- | --- |
| voice server not running (`voice_server_down`, 27 Oct 2026; before that the raw `ConnectionRefusedError`) | the VM is stopped (idle stop, nightly timer, spot preemption) or still installing, or the URL's port has no server (8765 = GLM-4-Voice, 8766 = cascade) | `vm.sh status`; `vm.sh start` then wait for `curl :8766/health`; `vm.sh provision` if the install never finished. With the Nebius identity settings Dory starts the box herself (`nebius_vm.VmWaker`, "Waking the voice server") |
| the room or panel stays at "waking the voice server" and the bot log repeats `nebius.aio.token.renewable: Failed refresh token ... Invalid nid format` (28 Oct 2026) | `DORY_NEBIUS_SA_KEY_ID` is not the `publickey-…` id of a key registered on the service account (an S3-style access-key id looks like `NAK…`); the SDK retries for ever, so the waker gives up after `API_TIMEOUT_S` (60 s) per call and the person gets `voice_server_down` | register `~/.config/dory-glm-vm/sa-public.pem` with the `auth-public-key create` line `vm.sh sa` prints, put the id it returns on the bot (`--update-env-vars DORY_NEBIUS_SA_KEY_ID=...`), and have a tenant admin grant `compute.instance-power-operator` on the CURRENT instance id (a recreated VM needs a new permit) |
| `busy` | one call at a time per server: a Discord room or another browser tab holds it | end the other call |
| `Agent Platform API has not been used in project` (log) | the service has NO `DORY_GLM_VOICE_URL`, so it fell back to Gemini Live, which this project does not have | set the URL on the service (`.env` + `scripts/deploy.sh`, or `gcloud run services update --update-env-vars`) |
| 4401 in the server log | token mismatch between Secret Manager `dory-glm-voice-token` and the box's `/etc/glm-voice.env` | copy the secret to the box before `install.sh` reaches its token step (a fresh box mints a new token otherwise) |

Root cause of the 27 Oct 2026 failure: the website was deployed with the cascade URL (:8766) while the
box was still being provisioned (and the spot VM had been preempted three times mid-install), so the
connect was refused. Prevention: provision on an ON-DEMAND VM for demo days, check `/health` on the
port named in `DORY_GLM_VOICE_URL` before announcing voice, and keep the Mac watchdog's install grace.

## The box on spot, on a disk that survives (28 Oct 2026)

The owner chose spot ("the most cost-effective option") and accepted preemption: `glm-voice` is
`computeinstance-u00ktbbsgedmfdt3k7`, preemptible under the `glm-voice-spot-cap` policy ($2 per GPU-hour cap;
H200 spot was $1.09 against $5.40 on demand that day), on the EXISTING boot disk `glm-voice-boot`
(`computedisk-u00c85z65rzvsssyyc`, 120 GiB) with the static IP. Consequences:

- A preemption or a `vm.sh stop` leaves it STOPPED; nothing self-heals (the start-on-demand waker is inert
  until the tenant admin acts, and that admin command now names the new instance id). Before a judged
  demo: `vm.sh start` 20 minutes early, then `curl http://204.12.189.216:8766/health`.
- `vm.sh delete` keeps the disk (the weights, both venvs and the services live on it) and `vm.sh create`
  boots from it in about 2 minutes with no provision, no cloud-init. Cost while everything is off: the disk,
  about $8.52 a month. Zero means deleting the disk too (`nebius compute disk delete --id <id>`), and the
  next create then provisions from scratch (40 minutes).
- Unverified: SSH to the recreated instance (its `/health` was checked, `vm.sh ssh` / `update` /
  `provision` were not tried on it yet).

## The cascade sidecar: voice WITH tools (booking, calendar, ledger)

GLM-4-Voice cannot call tools, so `cascade.py` (27 Oct 2026) runs next to it on the same VM, port
8766, same `GLM_VOICE_TOKEN`, same idle stop: NVIDIA Parakeet-TDT 0.6B v3 (NeMo, CC-BY-4.0) turns
the utterance into text, the text goes to Dory as `{"type": "heard"}`, Dory's own agent answers (the
`ask_dory` brain with every tool, GLM-5.3 on Token Factory), a filler line is spoken at once and the
answer comes back as `{"type": "say", "final": true}` for Kokoro-82M (Apache-2.0, 24 kHz) to speak
sentence by sentence. `install.sh` builds its venv (`~/cascade/.venv`, Python 3.12, torch cu126,
`nemo-toolkit[asr]`, `kokoro`; weights cached on the disk) and the unit `glm-cascade.service`.
Point Dory at it with `DORY_GLM_VOICE_URL=ws://<ip>:8766/voice` in `.env` (8765 = GLM-4-Voice small
talk, no tools); the web call (`center.py`) and the Discord room (`glm_room.py`) both switch by URL, and
both deploy scripts carry the URL from `.env` and mount the token secret `dory-glm-voice-token`
(`scripts/deploy.sh` for the website, `scripts/deploy_dory.sh` for the bot).
Switches: `CASCADE_ASR=parakeet|whisper` (faster-whisper large-v3-turbo for Thai),
`CASCADE_TTS=kokoro|magpie` (`nvidia/magpie_tts_multilingual_357m`), `CASCADE_VOICE` (Kokoro: one
voice or a comma blend, default `af_heart,af_nicole` = the A-grade voice softened; Magpie `Sofia`),
`CASCADE_SPEED` (0.95; 0.9-0.95 is calm, under 0.85 drags), `CASCADE_SENTENCE_GAP_MS` (250 of silence
after each sentence), `CASCADE_MAX_CALLS` (4), in `/etc/glm-voice.env`; restart `glm-cascade` after a change.
The behaviour rules (who she answers in a room, follow-ups without the name, hush, barge-in, fillers,
history) are in `docs/voice_behaviour.md`, section "Cascade path". Offline tests: `tests/dory/test_glm_cascade.py`
(FastAPI test client + fake engines), `test_glm_voice.py`, `test_glm_room.py`;
`python cascade.py --selftest` for the pure parts. Research: `docs/research/voice-cascade-asr-tts.md`.

`vm.sh watch-install` is the no-IAM fallback on your Mac: a launchd agent runs `vm.sh idle-check`
every 5 minutes while the Mac is awake, polls the voice server's `/health`, remembers when a call was
last active (`~/.config/dory-glm-vm/last_busy`) and stops the VM through YOUR profile after
`GLM_IDLE_MIN` (30) idle minutes or past `GLM_STOP_AT` (23:30). While the voice server answers no
health check (booting, or a fresh install, ~40 min) the idle clock waits, up to `GLM_INSTALL_GRACE_MIN`
(90) after the VM came up, so a stop never kills an install (it did once, 27 Oct). `vm.sh watch` does
the same in a terminal, `vm.sh watch-uninstall` removes the agent; after editing `vm.sh`, run
`watch-install` again (it copies the script). A sleeping or closed laptop means no stop: run
`vm.sh stop` before you leave.

Until one of those is in place, the idle stop and the nightly timer on the VM only log. SSH and SCP go through `nc` as a ProxyCommand (`GLM_SSH_PROXY`), because the Claude Code
sandbox lets `nc` open sockets but not `ssh` itself; it changes nothing on the VM.

- **Where and what (decided 26 Oct 2026 from live prices and capacity)**: the tenant's `us-central1`
  project (`project-u00amh34kc00p6ym5tjd0e`), platform `gpu-h200-sxm`, preset `1gpu-16vcpu-200gb`
  (one H200, 141 GB), image family `ubuntu24.04-cuda13.0`, 120 GiB boot disk (the weights stay on
  it across stop / start). The L40S exists only in `eu-north1`, where this account may not create a
  project; the RTX PRO 6000 (spot $1.34, on-demand $1.80) is Blackwell, and GLM-4-Voice pins
  `torch==2.3.0` (CUDA 12.1 wheels, no Blackwell kernels), so it would need an untested torch upgrade.
  The H200 (Hopper) runs the pinned stack unchanged.
- **Preemptible by default with a price cap**: the price calculator gave the H200 preset at $1.40/h
  spot vs $5.40/h on-demand (RTX PRO 6000 $1.34 / $1.80, B200 $5.70 / $8.50; capacity advisor:
  H200 high availability for both, RTX PRO 6000 low for on-demand). `vm.sh create` makes a pricing
  policy `glm-voice-spot-cap` with `GLM_SPOT_MAX` (default $2.000 per GPU-hour): above it Compute
  stops the VM instead of billing more; you pay the spot price, not the cap. Compute may also stop a
  preemptible VM for capacity (`on_preemption=stop`: stopped, never deleted); `vm.sh start` brings it
  back. For the judged demo window create with `--on-demand` ($5.40/h for the few hours it runs).
- **Static public IP** (a VPC allocation named `glm-voice-ip`), so `DORY_GLM_VOICE_URL` survives
  stop / start.
- The VM's own Nebius identity (`vm.sh sa`) is a service account in a custom group with the
  `compute.instance-power-operator` role on this instance only; its private key lives in
  `~/.config/dory-glm-vm/` locally and `~/glm_voice/` on the VM, never in the repo.
- Python 3.11 for the venv (`uv venv --python 3.11`): the repo pins `torch==2.3.0`, `numpy==1.24.4`,
  `transformers==4.44.1`, which do not install on the OS Python 3.12.

## 2. What `provision` installs (install.sh, idempotent)

GLM-4-Voice checkout with submodules, the venv and requirements (+ `websockets`), the decoder, the
9B model and the tokenizer pre-downloaded, `server.py` (self-test run), the Nebius CLI with the
`vm` profile, `/etc/glm-voice.env` (token + the stop command, root-only) and three systemd units:
`glm-model.service` (model_server.py, localhost:10000, bf16), `glm-voice.service` (server.py on
:8765, `--idle-shutdown-min 30`) and `glm-stop.timer` (16:30 UTC = 23:30 Bangkok daily).

```bash
deploy/glm_voice/vm.sh ssh curl -s localhost:8765/health      # {"ok": true, "busy": false}
deploy/glm_voice/vm.sh ssh journalctl -u glm-voice -n 50 --no-pager
```

The first model load after a start takes a few minutes (CUDA warm-up).

## Cost: automated, three layers

1. **Idle stop**: 30 minutes without a call and `server.py` runs `GLM_IDLE_SHUTDOWN_CMD`, which
   install.sh sets to `stop_vm.sh` (metadata-service token, then `nebius compute instance stop`). NEVER a Linux
   `shutdown`: Nebius treats that as a failure, reboots the VM and keeps billing (stop-start docs
   and the CLI's `--recovery-policy` help, read 2026-10-26). A stopped VM bills the disk and the
   static IP only (Assumption from the pricing page's structure; verify on the first invoice).
2. **Nightly safety net**: `glm-stop.timer` stops the VM at 23:30 Bangkok whatever happened.
3. **Spot pricing with a cap** (above): about a quarter of the on-demand hour today.

Starting is the one manual step: `vm.sh start` (or the console) a few minutes before a demo. A
start-on-demand from Dory (the web service starting the VM when a call arrives and telling the
person to wait) needs the service-account key in Secret Manager and a 3-5 minute wait: not built.

Also: `MAX_NEW_TOKENS` is 600 (a spoken answer), not web_demo's 2000, and the server takes one call
at a time, so one GPU is all this ever needs.

## 4. Point Dory at it

The box created on 26 Oct 2026 answers at the static IP `204.12.189.216`. Web service env:
`DORY_GLM_VOICE_URL=ws://204.12.189.216:8765/voice` and `DORY_GLM_VOICE_TOKEN` from Secret Manager
(never on a command line). The token is printed once by `provision`; store it and wire it in:

```bash
# in the web service's GCP project, with the token in the clipboard or a file, never as an argument
pbpaste | gcloud secrets create dory-glm-voice-token --data-file=-            # first time
gcloud run services update meeting-scribe --region asia-southeast1 \
  --update-env-vars DORY_GLM_VOICE_URL=ws://204.12.189.216:8765/voice \
  --update-secrets DORY_GLM_VOICE_TOKEN=dory-glm-voice-token:latest
```

With the URL set, the Live panel's call runs on GLM-4-Voice instead of Gemini Live: same browser,
same events. Remove the env var (`--remove-env-vars DORY_GLM_VOICE_URL`) to go back. A Cloud Run
update is a deploy: a person approves it (CLAUDE.md).

The Discord bot (worker pool `dory-bot`) takes the same two plus `DORY_VOICE_MODE=glm`;
`scripts/deploy_dory.sh` carries all three on every deploy once they are in the environment and the
secret exists:

```bash
export DORY_VOICE_MODE=glm DORY_GLM_VOICE_URL=ws://204.12.189.216:8765/voice
scripts/deploy_dory.sh            # dry run: prints what it would do
scripts/deploy_dory.sh --apply    # builds the current tree and deploys it (human approval)
```

Audio between Cloud Run and the VM is plain `ws://` unless you front the port with Caddy (TLS) or an
SSH tunnel: acceptable for the demo, not for production.

## Scale-to-zero: stop when idle, start when a call arrives

Two halves, two identities:

- **Stop** runs on the VM: `server.py --idle-shutdown-min 30` and the nightly `glm-stop.timer` call
  `nebius compute instance stop` with the VM's attached service account (metadata-service token).
  Until a tenant admin grants that role, the owner's Mac watchdog (`vm.sh watch-install`) stops it.
- **Start** runs in Dory (`dory.nebius_vm.VmWaker`, used by `GlmVoice`, so both the web panel and
  Discord rooms wake the box): when a call arrives and `/health` does not answer, Dory starts the VM
  through the Nebius API, tells the person ("waking the voice server, about two minutes": panel
  status `live_waking`, room notice `glm_waking`), polls `/health` every 5 s up to 5 minutes, then
  connects. One wake at a time per process; at most one start request per minute. Measured cold path
  on 26 Oct 2026: boot about 45 s, model load about 75 s, so the first answer comes roughly two
  minutes after the first call; every later call is instant until the next idle stop.

Dory needs the Nebius identity (settings on the web service and the bot):

| Setting | Value |
| --- | --- |
| `DORY_NEBIUS_VM_ID` | `vm.sh status` id (`computeinstance-...`) |
| `DORY_NEBIUS_SA_ID` | `glm-voice-power` (`vm.sh sa` prints it) |
| `DORY_NEBIUS_SA_KEY_ID` | the authorized key's id, from the admin's `auth-public-key create` output |
| `DORY_NEBIUS_SA_PRIVATE_KEY` | Secret Manager `dory-nebius-vm-key` = `~/.config/dory-glm-vm/sa-private.pem` |
| `DORY_NEBIUS_PROJECT` | the VM's project (optional) |

```bash
gcloud secrets create dory-nebius-vm-key --project dory-personal-assistant --data-file=$HOME/.config/dory-glm-vm/sa-private.pem
export DORY_NEBIUS_VM_ID=... DORY_NEBIUS_SA_ID=... DORY_NEBIUS_SA_KEY_ID=... DORY_NEBIUS_PROJECT=project-u00amh34kc00p6ym5tjd0e
scripts/deploy_dory.sh --apply      # mounts the key as DORY_NEBIUS_SA_PRIVATE_KEY and carries the ids
```

The same role (`compute.instance-power-operator` on the VM) covers start and stop, and the same
tenant-admin step unlocks both halves; nothing here works until it is granted.

## Discord voice rooms on this server (`DORY_VOICE_MODE=glm`)

The bot's rooms can run on the same box: set `DORY_VOICE_MODE=glm` plus `DORY_GLM_VOICE_URL` and
`DORY_GLM_VOICE_TOKEN` on the `dory-bot` worker pool. `/เข้าประชุม` then joins with `glm_room.GlmRoom`:
the room's mixed audio goes to the server, GLM's voice plays back in the room, and nothing in the room
calls Google: no per-segment transcription, no minutes, no TTS lines, no wake word (Dory answers
whoever talks). The server takes one connection at a time, so a room blocks the web Live panel and
vice versa; a connected room keeps `/health` busy, so the idle stop waits for it.

## Limits (by design, today)

- One call at a time per GPU (`busy` error for a second caller).
- English answers only; the person's words are not transcribed, so the panel shows only Dory's text.
- No tools: receipts, tasks, documents and reminders are not reachable from this voice.
- A cancelled turn (barge-in) stops streaming at once, but `model_server.py` keeps generating up to
  `MAX_NEW_TOKENS` on the GPU; the next turn shares the GPU with that tail.
