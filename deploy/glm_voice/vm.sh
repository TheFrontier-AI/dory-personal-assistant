#!/usr/bin/env bash
# Nebius AI Cloud lifecycle of Dory's GLM-4-Voice box: one H200 in us-central1, PREEMPTIBLE by default
# (spot $1.40/h vs $5.40 on-demand on 2026-10-26, capped by a pricing policy; Compute may stop it,
# never deletes it), a static public IP so Dory's URL
# survives stop / start, and stops ONLY through the API: a Linux `shutdown` is treated as a failure,
# the VM is rebooted and billed on (docs.nebius.com/compute/virtual-machines/stop-start, 2026-10-26).
#
#   vm.sh sa                    once: the VM's service account (tokens from the metadata service, no key file);
#                               the role grant itself needs a tenant admin (printed)
#   vm.sh create [--on-demand]  VM + static IP (preemptible unless --on-demand); prints id and ip
#   vm.sh update               copy server.py + cascade.py to a running box and restart (after a code change)
#   vm.sh provision             install GLM-4-Voice + the services over SSH (idempotent, 20-40 min)
#   vm.sh idle-check | watch | watch-install | watch-uninstall
#                               no-IAM idle stop from THIS machine with your profile (launchd every 5 min)
#   vm.sh start | stop | status | ip | ssh [cmd...] | delete
#
# Needs: the `nebius` CLI with a signed-in active profile (or NEBIUS_PROFILE), jq, openssl, an SSH key.
# State (ids) lives in $GLM_VM_STATE, never in the repo. Prints ids and IPs only, never tokens.
set -euo pipefail

PROFILE=${NEBIUS_PROFILE:-}   # empty = the active profile (the owner named it "Dory")
PROJECT=${GLM_VM_PROJECT:-project-u00amh34kc00p6ym5tjd0e}   # the tenant's us-central1 project (the H200 lives there)
NAME=${GLM_VM_NAME:-glm-voice}
PLATFORM=${GLM_VM_PLATFORM:-gpu-h200-sxm}
PRESET=${GLM_VM_PRESET:-1gpu-16vcpu-200gb}
IMAGE=${GLM_VM_IMAGE:-ubuntu24.04-cuda13.0}
DISK_GIB=${GLM_VM_DISK_GIB:-120}
SSH_USER=${GLM_SSH_USER:-glm}
SSH_PUB=${GLM_SSH_PUB:-$HOME/.ssh/id_ed25519.pub}
STATE=${GLM_VM_STATE:-$HOME/.config/dory-glm-vm}
SPOT_MAX=${GLM_SPOT_MAX:-2.000}   # USD per GPU-hour cap for the preemptible VM (pricing policy)
N=${NEBIUS_CLI:-$HOME/.nebius/bin/nebius}
# ssh through nc: some sandboxes (Claude Code's) let nc open sockets but not ssh itself; harmless elsewhere
SSH_OPTS=(-o "ProxyCommand=${GLM_SSH_PROXY:-nc %h %p}" -o StrictHostKeyChecking=accept-new -o BatchMode=yes)
HERE=$(cd "$(dirname "$0")" && pwd)

nb() { "$N" ${PROFILE:+--profile "$PROFILE"} --format json "$@"; }
die() { echo "vm.sh: $*" >&2; exit 1; }
mkdir -p "$STATE"
chmod 700 "$STATE"

vm_json() { nb compute instance get-by-name --parent-id "$PROJECT" --name "$NAME" 2>/dev/null || true; }
vm_id() { local j; j=$(vm_json); [ -n "$j" ] && jq -r '.metadata.id // empty' <<<"$j"; }
vm_state() { vm_json | jq -r '.status.state // "ABSENT"'; }
vm_ip() { vm_json | jq -r '.status.network_interfaces[0].public_ip_address.address // empty' | cut -d/ -f1; }

subnet_id() {
  nb vpc subnet list --parent-id "$PROJECT" | jq -r '.items[0].metadata.id // empty'
}

alloc_id() {
  local j
  j=$(nb vpc allocation get-by-name --parent-id "$PROJECT" --name "${NAME}-ip" 2>/dev/null || true)
  if [ -z "$j" ]; then
    nb vpc allocation create --parent-id "$PROJECT" --name "${NAME}-ip" \
      --ipv4-public-subnet-id "$(subnet_id)" >/dev/null
    j=$(nb vpc allocation get-by-name --parent-id "$PROJECT" --name "${NAME}-ip")
  fi
  jq -r '.metadata.id' <<<"$j"
}

policy_id() {
  # The spot cap: above SPOT_MAX per GPU-hour Compute stops the VM instead of billing more.
  local j
  j=$(nb billing pricing-policy list --parent-id "$PROJECT" | jq -r --arg n "${NAME}-spot-cap" '.items[]? | select(.metadata.name==$n) | .metadata.id' | head -1)
  if [ -z "$j" ]; then
    nb billing pricing-policy create --parent-id "$PROJECT" --name "${NAME}-spot-cap" \
      --compute-instance-spec-v1-platform "$PLATFORM" --pricing-max-price-v1-max-price "$SPOT_MAX" >/dev/null
    j=$(nb billing pricing-policy list --parent-id "$PROJECT" | jq -r --arg n "${NAME}-spot-cap" '.items[]? | select(.metadata.name==$n) | .metadata.id' | head -1)
  fi
  echo "$j"
}

user_data() {
  [ -f "$SSH_PUB" ] || die "no SSH public key at $SSH_PUB (set GLM_SSH_PUB)"
  cat <<EOF
#cloud-config
users:
  - name: $SSH_USER
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - $(cat "$SSH_PUB")
EOF
}

cmd_create() {
  [ -z "$(vm_id)" ] || die "$NAME exists: $(vm_id) ($(vm_state))"
  local pricing=(--recovery-policy fail --preemptible-on-preemption stop --spot-pricing-policy-id "$(policy_id)")
  [ "${1:-}" = "--on-demand" ] && pricing=(--on-demand)
  local subnet alloc sa
  subnet=$(subnet_id); [ -n "$subnet" ] || die "no subnet in $PROJECT"
  alloc=$(alloc_id)
  # the VM's identity: tokens come from the metadata service, no key ever touches a disk
  sa=${GLM_SA_ID:-$(sa_id)}
  if [ -n "$sa" ] && ! instance_create --service-account-id "$sa" 2>"$STATE/create.err"; then
    # attaching an identity needs a grant the owner (tenant editor) lacks until the admin acts
    echo "vm.sh: create with identity $sa refused ($(grep -m1 -o 'PermissionDenied' "$STATE/create.err" || echo error)); creating without it: the on-VM idle stop stays log-only" >&2
    sa=""
  fi
  [ -n "$sa" ] || instance_create
  echo "id=$(vm_id) state=$(vm_state) ip=$(vm_ip) pricing=${pricing[*]} identity=${sa:-none}"
}
instance_create() {  # pricing / subnet / alloc are cmd_create's locals (bash dynamic scope); $@ = identity
  nb compute instance create \
    --parent-id "$PROJECT" --name "$NAME" \
    --resources-platform "$PLATFORM" --resources-preset "$PRESET" \
    --boot-disk-managed-disk-name "${NAME}-boot" --boot-disk-managed-disk-type network_ssd \
    --boot-disk-managed-disk-size-gibibytes "$DISK_GIB" \
    --boot-disk-managed-disk-source-image-family-image-family "$IMAGE" \
    --boot-disk-attach-mode READ_WRITE \
    --network-interfaces "[{\"name\":\"eth0\",\"ip_address\":{},\"public_ip_address\":{\"static\":true,\"allocation_id\":\"$alloc\"},\"subnet_id\":\"$subnet\"}]" \
    --cloud-init-user-data "$(user_data)" \
    "$@" "${pricing[@]}" >/dev/null
}

sa_id() { nb iam service-account get-by-name --parent-id "$PROJECT" --name "${NAME}-power" 2>/dev/null | jq -r '.metadata.id // empty' || true; }

cmd_sa() {
  # The VM's own identity for the idle stop and the nightly timer: a service account ATTACHED to the
  # VM (`create` passes --service-account-id; the metadata service hands out its tokens, so no key
  # file exists anywhere) plus the role compute.instance-power-operator on this one instance, granted
  # through a custom group. Creating groups and permits needs the tenant `admin` role, which the owner
  # does not hold: this prints the admin's commands and writes the identity file for `provision`.
  local id tenant sa group
  sa=$(sa_id)
  if [ -z "$sa" ]; then
    nb iam service-account create --parent-id "$PROJECT" --name "${NAME}-power" >/dev/null
    sa=$(sa_id)
  fi
  id=$(vm_id); tenant=$(nb iam v2 project get --id "$PROJECT" | jq -r '.metadata.parent_id')
  printf 'SA_ID=%s\nVM_ID=%s\nPROJECT=%s\n' "$sa" "${id:-}" "$PROJECT" >"$STATE/vm.env"
  echo "service account $sa (project $PROJECT)"
  # Dory on Cloud Run starts the stopped box through the Nebius API (scale-to-zero): that needs an
  # authorized key on the account. The pair is made here; the PUBLIC half is registered by the admin,
  # the PRIVATE half goes to Secret Manager (deploy/glm_voice/README.md), never into the repo.
  if [ ! -f "$STATE/sa-private.pem" ]; then
    (umask 077; openssl genrsa -out "$STATE/sa-private.pem" 4096 2>/dev/null)
    openssl rsa -in "$STATE/sa-private.pem" -pubout -out "$STATE/sa-public.pem" 2>/dev/null
  fi
  echo "key pair for Dory's start-on-demand: $STATE/sa-public.pem (share) / sa-private.pem (Secret Manager)"
  group=$(nb iam group get-by-name --parent-id "$tenant" --name "${NAME}-power" 2>/dev/null | jq -r '.metadata.id // empty' || true)
  if [ -z "$group" ] && nb iam group create --parent-id "$tenant" --name "${NAME}-power" >/dev/null 2>&1; then
    group=$(nb iam group get-by-name --parent-id "$tenant" --name "${NAME}-power" | jq -r '.metadata.id')
  fi
  if [ -n "$group" ]; then
    nb iam group-membership create --parent-id "$group" --member-id "$sa" >/dev/null 2>&1 || true
    [ -n "$id" ] && nb iam access-permit create --parent-id "$group" --resource-id "$id" --role compute.instance-power-operator >/dev/null 2>&1 || true
    echo "role compute.instance-power-operator on ${id:-<vm>} via group $group"
  else
    {
      echo "vm.sh: the role needs a tenant admin. Ask them to run (one time):"
      echo "  nebius iam group create --parent-id $tenant --name ${NAME}-power"
      echo "  nebius iam group-membership create --parent-id <group_id> --member-id $sa"
      echo "  nebius iam access-permit create --parent-id <group_id> --resource-id ${id:-<vm_id>} --role compute.instance-power-operator"
      echo "  nebius iam auth-public-key create --parent-id $PROJECT --account-service-account-id $sa --data \"\$(cat sa-public.pem)\"   # Dory's start-on-demand key"
      echo "  (or simply add your account to the tenant 'admins' group and re-run vm.sh sa)"
      echo "A VM created BEFORE the service account existed has no identity attached: recreate it afterwards"
      echo "  (vm.sh delete; vm.sh create [--on-demand]; vm.sh provision) so the metadata service serves its tokens."
    } >&2
  fi
}

cmd_idle_check() {
  # One pass of the no-IAM idle stop (your own profile, this machine): remember when the voice server
  # was last busy, and stop the VM after GLM_IDLE_MIN minutes without a call or past GLM_STOP_AT.
  local idle_min=${GLM_IDLE_MIN:-30} stop_at=${GLM_STOP_AT:-23:30} ip now last idle state
  state=$(vm_state)
  [ "$state" = "RUNNING" ] || { echo "$(date '+%F %T') VM is $state"; rm -f "$STATE/last_busy" "$STATE/up_since"; return 0; }
  ip=$(vm_ip); now=$(date +%s)
  [ -f "$STATE/up_since" ] || echo "$now" >"$STATE/up_since"
  [ -f "$STATE/last_busy" ] || echo "$now" >"$STATE/last_busy"
  local health; health=$(curl -sf -m 5 "http://$ip:8765/health" || true)
  # no voice server yet = booting or installing (a fresh disk takes ~40 min): the idle clock starts
  # at its first answer, or after GLM_INSTALL_GRACE_MIN, so a stop never kills an install
  if [ -z "$health" ] && [ $(( (now - $(cat "$STATE/up_since")) / 60 )) -lt "${GLM_INSTALL_GRACE_MIN:-90}" ]; then
    echo "$now" >"$STATE/last_busy"
    echo "$(date '+%F %T') running, voice server not up yet: idle clock waits (grace ${GLM_INSTALL_GRACE_MIN:-90} min)"
    return 0
  fi
  grep -q '"busy": *true' <<<"$health" && echo "$now" >"$STATE/last_busy"
  last=$(cat "$STATE/last_busy"); idle=$(( (now - last) / 60 ))
  if [ "$idle" -ge "$idle_min" ] || [[ "$(date +%H:%M)" > "$stop_at" ]]; then
    echo "$(date '+%F %T') idle ${idle} min or past $stop_at: stopping $(vm_id)"
    nb compute instance stop --id "$(vm_id)" >/dev/null && rm -f "$STATE/last_busy"
    echo "$(date '+%F %T') state=$(vm_state)"
  else
    echo "$(date '+%F %T') running, idle ${idle}/${idle_min} min"
  fi
}

cmd_watch() { echo "Ctrl-C to leave"; while cmd_idle_check; do sleep 60; done; }

PLIST=$HOME/Library/LaunchAgents/com.dory.glm-voice-watch.plist
cmd_watch_install() {
  # macOS launchd agent: idle-check every 5 minutes while this Mac is awake, log in $STATE.
  # launchd may not read ~/Documents (macOS folder protection), so the agent runs a copy of this
  # script from $STATE; re-run watch-install after changing vm.sh.
  mkdir -p "$(dirname "$PLIST")"
  install -m 700 "$HERE/vm.sh" "$STATE/vm.sh"
  cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.dory.glm-voice-watch</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$STATE/vm.sh</string><string>idle-check</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$HOME/.nebius/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$STATE/watch.log</string>
  <key>StandardErrorPath</key><string>$STATE/watch.log</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "installed: every 5 min while awake; log $STATE/watch.log; remove with vm.sh watch-uninstall"
}
cmd_watch_uninstall() { launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true; rm -f "$PLIST"; echo "removed"; }

cmd_ssh() { ssh "${SSH_OPTS[@]}" "$SSH_USER@$(vm_ip)" "$@"; }

cmd_update() {
  # Ship a changed server.py / cascade.py to a RUNNING box and restart its service (no reinstall)
  [ "$(vm_state)" = "RUNNING" ] || die "VM is $(vm_state): run vm.sh start"
  local ip; ip=$(vm_ip)
  scp -q "${SSH_OPTS[@]}" "$HERE/server.py" "$HERE/cascade.py" "$SSH_USER@$ip:glm_voice/"
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$ip" 'cp glm_voice/server.py glm_voice/cascade.py GLM-4-Voice/ && cd GLM-4-Voice \
    && ~/cascade/.venv/bin/python cascade.py --selftest && sudo systemctl restart glm-cascade glm-voice \
    && sleep 45 && systemctl is-active glm-cascade glm-voice | tr "\n" " " && curl -s localhost:8766/health && echo'
}

cmd_provision() {
  [ "$(vm_state)" = "RUNNING" ] || die "VM is $(vm_state): run vm.sh start"
  [ -f "$STATE/vm.env" ] || echo "vm.sh: no identity file yet (vm.sh sa): the idle stop will only log until provision runs again" >&2
  local ip; ip=$(vm_ip)
  for _ in $(seq 1 30); do
    ssh "${SSH_OPTS[@]}" -o ConnectTimeout=10 "$SSH_USER@$ip" true 2>/dev/null && break
    sleep 10
  done
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$ip" mkdir -p glm_voice
  scp -q "${SSH_OPTS[@]}" "$HERE/server.py" "$HERE/cascade.py" "$HERE/install.sh" "$HERE/requirements-extra.txt" "$HERE/smoke.py" "$SSH_USER@$ip:glm_voice/"
  [ -f "$STATE/vm.env" ] && scp -q "${SSH_OPTS[@]}" "$STATE/vm.env" "$SSH_USER@$ip:glm_voice/"
  # detached on the VM (a dropped local session must not kill a 30-minute install); tail its log
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$ip" 'nohup bash glm_voice/install.sh > glm_voice/install.log 2>&1 < /dev/null & echo started'
  local last="" out
  while :; do
    sleep 30
    out=$(ssh "${SSH_OPTS[@]}" "$SSH_USER@$ip" 'tail -n 3 glm_voice/install.log; pgrep -f "bash glm_voice/install.sh" >/dev/null && echo RUNNING || echo DONE' 2>/dev/null) || continue
    [ "$out" != "$last" ] && { echo "$out" | grep -v -E '^(RUNNING|DONE)$'; last=$out; }
    echo "$out" | grep -q '^DONE$' && break
  done
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$ip" 'grep -E "services enabled|identity|no attached|error|Error" glm_voice/install.log | tail -5'
  echo "install.log is at $SSH_USER@$ip:glm_voice/install.log (vm.sh ssh tail -f glm_voice/install.log)"
}

case "${1:-}" in
  create) shift; cmd_create "$@" ;;
  sa) cmd_sa ;;
  idle-check) cmd_idle_check ;;
  watch) cmd_watch ;;
  watch-install) cmd_watch_install ;;
  watch-uninstall) cmd_watch_uninstall ;;
  provision) cmd_provision ;;
  update) cmd_update ;;
  start) nb compute instance start --id "$(vm_id)" >/dev/null; echo "state=$(vm_state) ip=$(vm_ip)" ;;
  stop) nb compute instance stop --id "$(vm_id)" >/dev/null; echo "state=$(vm_state)" ;;
  status) echo "id=$(vm_id) state=$(vm_state) ip=$(vm_ip)" ;;
  ip) vm_ip ;;
  ssh) shift; cmd_ssh "$@" ;;
  delete) ip=$(vm_ip); nb compute instance delete --id "$(vm_id)" >/dev/null
          ssh-keygen -R "$ip" >/dev/null 2>&1 || true   # the next VM reuses the IP with a new host key
          echo "deleted (the static IP ${NAME}-ip is kept)" ;;
  *) sed -n '2,13p' "$0"; exit 2 ;;
esac
