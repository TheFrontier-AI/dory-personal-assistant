#!/usr/bin/env bash
# Runs ON the GPU VM (copied there by `vm.sh provision`, as the SSH user with passwordless sudo).
# Idempotent: GLM-4-Voice checkout + Python 3.11 venv + weights, the Nebius CLI with the VM's own
# stop/start service account, the voice token, and three systemd units:
#   glm-model.service   model_server.py on localhost:10000 (bf16)
#   glm-voice.service   server.py on :8765 with --idle-shutdown-min 30 -> `nebius compute instance stop`
#   glm-cascade.service cascade.py on :8766 (Parakeet ASR -> Dory's brain -> Kokoro TTS; own venv ~/cascade)
#   glm-stop.timer      nightly safety net: stop the VM at 16:30 UTC (23:30 Bangkok) whatever happened
# Prints the voice token ONCE, at the first run; nothing else secret.
set -euo pipefail
cd "$HOME"
SA_ID="" VM_ID="" PROJECT=""
# shellcheck disable=SC1091
[ -f "$HOME/glm_voice/vm.env" ] && . "$HOME/glm_voice/vm.env"   # SA_ID VM_ID PROJECT (vm.sh sa)

sudo apt-get update -qq
sudo apt-get install -y -qq git git-lfs libsndfile1 ffmpeg jq >/dev/null
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

[ -d GLM-4-Voice ] || git clone --recurse-submodules https://github.com/zai-org/GLM-4-Voice
cd GLM-4-Voice
# the repo pins torch 2.3.0 / numpy 1.24.4 / transformers 4.44.1: Python 3.11, not the OS 3.12
[ -d .venv ] || uv venv --python 3.11 .venv
# shellcheck disable=SC1091
. .venv/bin/activate
# openai-whisper 20231117 builds with `pkg_resources`, gone from current setuptools: build it with
# the venv's own older setuptools instead of an isolated build environment
uv pip install -q "setuptools<80" wheel
uv pip install -q --no-build-isolation -r requirements.txt -r "$HOME/glm_voice/requirements-extra.txt"
[ -f glm-4-voice-decoder/flow.pt ] || huggingface-cli download THUDM/glm-4-voice-decoder --local-dir ./glm-4-voice-decoder >/dev/null
# weights on the disk, so a start after a stop needs no download
huggingface-cli download THUDM/glm-4-voice-9b >/dev/null
huggingface-cli download THUDM/glm-4-voice-tokenizer >/dev/null
cp "$HOME/glm_voice/server.py" "$HOME/glm_voice/cascade.py" .
python server.py --selftest
deactivate

# The cascade sidecar: its own venv (NeMo wants a current torch; the GLM venv is pinned to 2.3).
# Parakeet-TDT 0.6B v3 (CC-BY-4.0) + Kokoro-82M (Apache-2.0); weights cached on the disk.
sudo apt-get install -y -qq espeak-ng >/dev/null   # Kokoro's G2P
mkdir -p "$HOME/cascade"
[ -d "$HOME/cascade/.venv" ] || uv venv --python 3.12 "$HOME/cascade/.venv"
# shellcheck disable=SC1091
. "$HOME/cascade/.venv/bin/activate"
uv pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cu126
uv pip install -q "nemo-toolkit[asr]" kokoro soundfile fastapi "uvicorn[standard]" "websockets>=12"
python - <<'PYEOF'
import nemo.collections.asr as nemo_asr
nemo_asr.models.ASRModel.from_pretrained(model_name="nvidia/parakeet-tdt-0.6b-v3")
from kokoro import KPipeline
KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
print("cascade weights cached")
PYEOF
python cascade.py --selftest
deactivate
# shellcheck disable=SC1091
. .venv/bin/activate

# The stop command: the VM's attached service account, whose token the metadata service hands out
# (http://metadata.nebius.internal/v1/iam/sa/token/access_token); the CLI reads it from a file that
# the script refreshes first. Without an attached identity the stop only logs: a Linux shutdown would
# be rebooted and billed, so it is never used.
STOP_CMD=""
ATTACHED=$(curl -sf -m 3 -H 'Metadata: true' http://metadata.nebius.internal/v1/instance-data/service_account_id 2>/dev/null || true)
if [ -n "$ATTACHED" ] && [ -n "$VM_ID" ]; then
  [ -x "$HOME/.nebius/bin/nebius" ] || curl -sSL https://artifacts.nebius.cloud/cli/install.sh | bash
  TOK="$HOME/glm_voice/iam-token"
  install -m 600 /dev/null "$TOK"
  "$HOME/.nebius/bin/nebius" profile list 2>/dev/null | grep -q '^vm' || \
    "$HOME/.nebius/bin/nebius" profile create --profile vm --endpoint api.nebius.cloud \
      --token-file "$TOK" --parent-id "$PROJECT" --skip-auth
  cat >"$HOME/glm_voice/stop_vm.sh" <<EOF
#!/usr/bin/env bash
# refresh the identity token from the metadata service, then stop THIS VM through the API
set -euo pipefail
curl -sf -m 5 -H 'Metadata: true' http://metadata.nebius.internal/v1/iam/sa/token/access_token | jq -r .token.access_token > "$TOK"
exec "$HOME/.nebius/bin/nebius" --profile vm compute instance stop --id "$VM_ID"
EOF
  chmod 700 "$HOME/glm_voice/stop_vm.sh"
  STOP_CMD="$HOME/glm_voice/stop_vm.sh"
  echo "identity $ATTACHED attached: the idle stop and the nightly timer stop the VM through the API"
else
  echo "no attached service account: idle stop and nightly timer only log (vm.sh sa, then recreate the VM)"
fi

if [ ! -f /etc/glm-voice.env ]; then
  TOKEN=$(openssl rand -hex 24)
  printf 'GLM_VOICE_TOKEN=%s\n' "$TOKEN" | sudo tee /etc/glm-voice.env >/dev/null
  sudo chmod 600 /etc/glm-voice.env
  echo "GLM_VOICE_TOKEN written to /etc/glm-voice.env (read it on the VM: sudo cat /etc/glm-voice.env; never printed here)"
fi
# the stop command is (re)written on every run, so a later `vm.sh sa` + provision completes it
sudo sed -i '/^GLM_IDLE_SHUTDOWN_CMD=/d' /etc/glm-voice.env
printf 'GLM_IDLE_SHUTDOWN_CMD=%s\n' "$STOP_CMD" | sudo tee -a /etc/glm-voice.env >/dev/null

REPO="$HOME/GLM-4-Voice"
sudo tee /etc/systemd/system/glm-model.service >/dev/null <<EOF
[Unit]
Description=GLM-4-Voice language model server
After=network-online.target
[Service]
User=$USER
WorkingDirectory=$REPO
ExecStart=$REPO/.venv/bin/python model_server.py --host localhost --model-path THUDM/glm-4-voice-9b --port 10000 --dtype bfloat16 --device cuda:0
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
sudo tee /etc/systemd/system/glm-voice.service >/dev/null <<EOF
[Unit]
Description=Dory GLM-4-Voice socket (tokenizer + decoder), idle stop through the Nebius API
After=glm-model.service
Requires=glm-model.service
[Service]
User=$USER
WorkingDirectory=$REPO
EnvironmentFile=/etc/glm-voice.env
ExecStart=$REPO/.venv/bin/python server.py --port 8765 --idle-shutdown-min 30
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
sudo tee /etc/systemd/system/glm-cascade.service >/dev/null <<EOF
[Unit]
Description=Dory cascade voice sidecar (Parakeet ASR -> Dory brain -> Kokoro TTS), idle stop through the Nebius API
After=network-online.target
[Service]
User=$USER
WorkingDirectory=$REPO
EnvironmentFile=/etc/glm-voice.env
ExecStart=$HOME/cascade/.venv/bin/python cascade.py --port 8766 --idle-shutdown-min 30
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
sudo tee /etc/systemd/system/glm-stop.service >/dev/null <<EOF
[Unit]
Description=Nightly safety net: stop this VM through the Nebius API
[Service]
Type=oneshot
User=$USER
ExecStart=${STOP_CMD:-/bin/echo no service account: nightly stop skipped}
EOF
sudo tee /etc/systemd/system/glm-stop.timer >/dev/null <<EOF
[Unit]
Description=Stop the GLM-4-Voice VM at 16:30 UTC (23:30 Bangkok) every day
[Timer]
OnCalendar=*-*-* 16:30:00 UTC
Persistent=false
[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now glm-model.service glm-voice.service glm-cascade.service glm-stop.timer
echo "services enabled; first model load takes a few minutes: curl -s localhost:8765/health"
