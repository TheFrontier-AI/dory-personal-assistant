#!/usr/bin/env bash
# Idempotent deploy of the Dory Discord bot as a Cloud Run worker pool.
# Usage: scripts/deploy_dory.sh [--dry-run|--apply] [--rotate-token] [--configure-hub]
#   (default)       --dry-run: only echo the mutating commands (read-only gcloud checks still run)
#   --apply         execute for real
#   --rotate-token  add a new Secret Manager version even if one exists
#   --configure-hub ONLY update env vars on the existing meeting-scribe service (hub settings)
# Reads from the local environment (never from .env, never echoed): DORY_DISCORD_TOKEN.
# Optional pass-through: DORY_RECEIPT_CHANNEL_IDS, DORY_ASK_CHANNEL_IDS, DORY_EXEC_ROLE_NAMES,
# DORY_EXEC_USER_IDS, DORY_DIGEST_TIME, DORY_DIGEST_CHANNEL_ID, DORY_RECEIPT_BUCKET,
# DORY_FIRESTORE_COLLECTION, DORY_TEAM_COLLECTION, DORY_TEAM_ID, DORY_GEMINI_MODEL,
# DORY_DEEP_TASK_TIMEOUT, DORY_DEEP_TASK_MODEL. For --configure-hub: HUB_GOOGLE_CLIENT_ID,
# HUB_ADMIN_EMAILS, DORY_DISCORD_CLIENT_ID.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck disable=SC1090
[ -f "$HOME/google-cloud-sdk/path.bash.inc" ] && source "$HOME/google-cloud-sdk/path.bash.inc"

APPLY=false ROTATE=false HUB=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) APPLY=false ;;
    --apply) APPLY=true ;;
    --rotate-token) ROTATE=true ;;
    --configure-hub) HUB=true ;;
    -h|--help) sed -n 2,13p "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

PROJECT="${GCP_PROJECT:-dory-personal-assistant}"
REGION="${GCP_REGION:-asia-southeast1}"
POOL="dory-bot"
SA_NAME="dory-bot"
SA="$SA_NAME@$PROJECT.iam.gserviceaccount.com"
SECRET="dory-discord-token"
AR_REPO="cloud-run-source-deploy"   # existing repo created by `gcloud run deploy --source`
HUB_SERVICE="meeting-scribe"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"
IMAGE="$REGION-docker.pkg.dev/$PROJECT/$AR_REPO/$POOL:$IMAGE_TAG"
BUCKET="${DORY_RECEIPT_BUCKET:-}"

if $APPLY; then echo "MODE: APPLY (changes will be made in project $PROJECT)"
else echo "MODE: DRY-RUN (nothing is changed; pass --apply to execute)"; fi

# run CMD...: print the command, execute it only with --apply.
run() {
  printf '    $'; printf ' %q' "$@"; printf '\n'
  if $APPLY; then "$@"; fi
}

# Read-only probes work in both modes; if gcloud is unusable they report "missing".
gc() { gcloud --project "$PROJECT" "$@"; }

configure_hub() {
  echo "==> Hub settings on existing service $HUB_SERVICE (update only; max-instances untouched)"
  local pairs=("DORY_STORE=firestore") missing=()
  for k in HUB_GOOGLE_CLIENT_ID HUB_ADMIN_EMAILS DORY_DISCORD_CLIENT_ID; do
    if [ -n "${!k:-}" ]; then pairs+=("$k=${!k}"); else missing+=("$k"); fi
  done
  [ ${#missing[@]} -eq 0 ] || echo "    not set locally, skipped: ${missing[*]}"
  # '^|^' makes '|' the pair delimiter, because HUB_ADMIN_EMAILS contains commas.
  local joined; joined="$(IFS='|'; echo "${pairs[*]}")"
  run gcloud run services update "$HUB_SERVICE" --project "$PROJECT" --region "$REGION" \
    --update-env-vars "^|^$joined"
  echo "    meeting-scribe-run needs roles/datastore.user for Firestore (it already has it for meetings)."
}

if $HUB; then configure_hub; echo "Done."; exit 0; fi

if [ -z "${DORY_DISCORD_TOKEN:-}" ] && $APPLY; then
  echo "WARNING: DORY_DISCORD_TOKEN is not set; only an existing secret version can be used." >&2
fi

echo "==> Enabling APIs (only missing ones)"
ENABLED="$(gc services list --enabled --format='value(config.name)' 2>/dev/null || true)"
MISSING_APIS=()
for api in run artifactregistry cloudbuild secretmanager firestore aiplatform; do
  grep -qx "$api.googleapis.com" <<<"$ENABLED" || MISSING_APIS+=("$api.googleapis.com")
done
if [ ${#MISSING_APIS[@]} -gt 0 ]; then run gcloud services enable --project "$PROJECT" "${MISSING_APIS[@]}"
else echo "    all enabled"; fi

echo "==> Service account $SA"
if gc iam service-accounts describe "$SA" >/dev/null 2>&1; then echo "    exists"
else run gcloud iam service-accounts create "$SA_NAME" --project "$PROJECT" \
       --display-name "Dory bot (Cloud Run worker pool)"
  if $APPLY; then  # new service accounts can take a few seconds to become visible to IAM
    for _ in 1 2 3 4 5 6; do gc iam service-accounts describe "$SA" >/dev/null 2>&1 && break; sleep 5; done
  fi
fi
for role in roles/datastore.user roles/aiplatform.user roles/logging.logWriter; do
  run gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" \
    --role "$role" --condition=None --quiet
done
if [ -n "$BUCKET" ]; then
  run gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
    --member "serviceAccount:$SA" --role roles/storage.objectAdmin
else echo "    DORY_RECEIPT_BUCKET not set: no storage role granted (receipt archive off)"; fi

echo "==> Secret $SECRET"
if gc secrets describe "$SECRET" >/dev/null 2>&1; then echo "    exists"
else run gcloud secrets create "$SECRET" --project "$PROJECT" --replication-policy automatic; fi
HAS_VERSION=false
if gc secrets versions list "$SECRET" --limit 1 --format='value(name)' 2>/dev/null | grep -q .; then
  HAS_VERSION=true
fi
if ! $HAS_VERSION || $ROTATE; then
  if [ -z "${DORY_DISCORD_TOKEN:-}" ] && $APPLY; then
    echo "ERROR: need DORY_DISCORD_TOKEN in the environment to add a secret version" >&2; exit 1
  fi
  # The token goes via stdin only; it is never echoed or placed on a command line.
  echo '    $ printf %s "$DORY_DISCORD_TOKEN" | gcloud secrets versions add' \
       "$SECRET --project $PROJECT --data-file=-   # value hidden"
  if $APPLY; then
    printf '%s' "$DORY_DISCORD_TOKEN" | gcloud secrets versions add "$SECRET" \
      --project "$PROJECT" --data-file=- >/dev/null
    echo "    stored a new version of $SECRET"
  fi
else echo "    a version exists; keeping it (use --rotate-token to add a new one)"; fi
run gcloud secrets add-iam-policy-binding "$SECRET" --project "$PROJECT" \
  --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor

echo "==> Building image $IMAGE (Cloud Build, Dockerfile.dory)"
run gcloud builds submit . --project "$PROJECT" --region "$REGION" \
  --config cloudbuild.dory.yaml --substitutions "_IMAGE=$IMAGE"

echo "==> Deploying Cloud Run worker pool $POOL (1 fixed instance)"
ENV_PAIRS=("DORY_STORE=firestore" "DORY_GCP_PROJECT=$PROJECT"
           "DORY_GEMINI_LOCATION=${DORY_GEMINI_LOCATION:-global}" "DORY_TZ=Asia/Bangkok")
for k in DORY_RECEIPT_CHANNEL_IDS DORY_ASK_CHANNEL_IDS DORY_EXEC_ROLE_NAMES DORY_EXEC_USER_IDS \
         DORY_DIGEST_TIME DORY_DIGEST_CHANNEL_ID DORY_RECEIPT_BUCKET DORY_FIRESTORE_COLLECTION \
         DORY_TEAM_COLLECTION DORY_TEAM_ID DORY_GEMINI_MODEL DORY_DEEP_TASK_TIMEOUT \
         DORY_DEEP_TASK_MODEL; do
  [ -z "${!k:-}" ] || ENV_PAIRS+=("$k=${!k}")
done
ENV_JOINED="$(IFS='|'; echo "${ENV_PAIRS[*]}")"   # '|' delimiter: values contain commas
# --instances=1 = manual scaling with a fixed count: the Discord gateway needs exactly one
# always-on connection (two would answer every message twice). 1 vCPU / 2 GiB: the Gemini CLI
# (Node) runs next to the Python bot during deep tasks.
run gcloud run worker-pools deploy "$POOL" --project "$PROJECT" --region "$REGION" \
  --image "$IMAGE" --service-account "$SA" --instances 1 --cpu 1 --memory 2Gi \
  --set-env-vars "^|^$ENV_JOINED" --set-secrets "DORY_DISCORD_TOKEN=$SECRET:latest" --quiet

echo
if $APPLY; then echo "Deployed worker pool $POOL ($IMAGE)."
else echo "Dry run finished: nothing was changed. Re-run with --apply to deploy $POOL ($IMAGE)."; fi
echo "Logs:  gcloud logging read 'resource.type=cloud_run_worker_pool' --project $PROJECT --limit 20"
echo "Stop:  gcloud run worker-pools update $POOL --region $REGION --instances 0"
echo "Hub:   scripts/deploy_dory.sh --configure-hub   (optional, separate step)"
