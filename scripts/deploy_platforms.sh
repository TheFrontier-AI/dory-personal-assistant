#!/usr/bin/env bash
# Deploy `python -m dory.platforms` (LINE / WhatsApp webhooks + Slack / Telegram) as the Cloud Run
# SERVICE dory-platforms, on the dory-bot image (cloudbuild.dory.yaml).
# Usage: scripts/deploy_platforms.sh [--dry-run|--apply]
#   (default)  --dry-run: echo the mutating commands only (nothing is built or changed)
#   --apply    build a new image tag and deploy
# Secrets are NEVER passed here: create them first in Secret Manager (names below) and this script
# only references them with --update-secrets. Plain env is read from the local environment:
#   DORY_WHATSAPP_PHONE_NUMBER_ID, GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_REDIRECT_URI and the
#   optional pass-through DORY_GEMINI_MODEL, DORY_GEMINI_LOCATION, DORY_GUILD_COLLECTION,
#   DORY_FIRESTORE_COLLECTION, DORY_HUB_URL, DORY_SLACK_EXEC_USER_IDS, DORY_LINE_EXEC_USER_IDS,
#   DORY_TELEGRAM_EXEC_USER_IDS, DORY_WHATSAPP_EXEC_NUMBERS, DORY_LINE_ORG_LINKING, DORY_RECEIPT_BUCKET.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck disable=SC1090
[ -f "$HOME/google-cloud-sdk/path.bash.inc" ] && source "$HOME/google-cloud-sdk/path.bash.inc"

APPLY=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) APPLY=false ;;
    --apply) APPLY=true ;;
    -h|--help) sed -n 2,12p "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

PROJECT="${GCP_PROJECT:-dory-personal-assistant}"
REGION="${GCP_REGION:-asia-southeast1}"
SERVICE="dory-platforms"
SA="dory-bot@$PROJECT.iam.gserviceaccount.com"
AR_REPO="cloud-run-source-deploy"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)}"
IMAGE="$REGION-docker.pkg.dev/$PROJECT/$AR_REPO/dory-bot:$IMAGE_TAG"

if $APPLY; then echo "MODE: APPLY (changes will be made in project $PROJECT)"
else echo "MODE: DRY-RUN (nothing is changed; pass --apply to execute)"; fi

run() {
  printf '    $'; printf ' %q' "$@"; printf '\n'
  if $APPLY; then "$@"; fi
}

echo "==> Building image $IMAGE (Cloud Build, Dockerfile.dory)"
run gcloud builds submit . --project "$PROJECT" --region "$REGION" \
  --config cloudbuild.dory.yaml --substitutions "_IMAGE=$IMAGE"

# Non-secret env. '|' is the pair delimiter because values may contain commas.
ENV_PAIRS=("DORY_STORE=firestore" "DORY_GCP_PROJECT=$PROJECT"
           "DORY_GEMINI_LOCATION=${DORY_GEMINI_LOCATION:-global}" "DORY_TZ=Asia/Bangkok")
for k in DORY_WHATSAPP_PHONE_NUMBER_ID GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_REDIRECT_URI \
         DORY_GEMINI_MODEL DORY_GUILD_COLLECTION DORY_FIRESTORE_COLLECTION DORY_HUB_URL \
         DORY_SLACK_EXEC_USER_IDS DORY_LINE_EXEC_USER_IDS DORY_TELEGRAM_EXEC_USER_IDS \
         DORY_WHATSAPP_EXEC_NUMBERS DORY_LINE_ORG_LINKING DORY_RECEIPT_BUCKET; do
  [ -z "${!k:-}" ] || ENV_PAIRS+=("$k=${!k}")
done
ENV_JOINED="$(IFS='|'; echo "${ENV_PAIRS[*]}")"

SECRET_PAIRS=(
  "DORY_SLACK_BOT_TOKEN=dory-platforms-slack-bot-token:latest"
  "DORY_SLACK_APP_TOKEN=dory-platforms-slack-app-token:latest"
  "DORY_LINE_CHANNEL_SECRET=dory-platforms-line-channel-secret:latest"
  "DORY_LINE_CHANNEL_ACCESS_TOKEN=dory-platforms-line-channel-access-token:latest"
  "DORY_TELEGRAM_BOT_TOKEN=dory-platforms-telegram-bot-token:latest"
  "DORY_WHATSAPP_ACCESS_TOKEN=dory-platforms-whatsapp-access-token:latest"
  "DORY_WHATSAPP_APP_SECRET=dory-platforms-whatsapp-app-secret:latest"
  "DORY_WHATSAPP_VERIFY_TOKEN=dory-platforms-whatsapp-verify-token:latest"
  "GOOGLE_OAUTH_CLIENT_SECRET=dory-google-oauth-secret:latest"
  "DORY_TOKEN_KEY=dory-token-key:latest"
)
SECRETS_JOINED="$(IFS=','; echo "${SECRET_PAIRS[*]}")"

# One always-on instance (Slack Socket Mode and Telegram polling must not run twice), CPU always
# allocated (background work after a webhook returns). Unauthenticated: LINE and WhatsApp call it
# from the internet and every webhook verifies its own signature.
echo "==> Deploying Cloud Run service $SERVICE"
run gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" \
  --image "$IMAGE" --service-account "$SA" \
  --command python --args=-m,dory.platforms \
  --min-instances 1 --max-instances 1 --no-cpu-throttling --memory 1Gi \
  --allow-unauthenticated \
  --update-env-vars "^|^$ENV_JOINED" --update-secrets "$SECRETS_JOINED" --quiet

echo
if $APPLY; then
  URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" \
    --format='value(status.url)')"
else URL="https://<service-url>"; fi
echo "LINE webhook:     $URL/line/webhook"
echo "WhatsApp webhook: $URL/whatsapp/webhook"
echo "Health:           $URL/health"
$APPLY || echo "Dry run finished. Secrets must already exist in Secret Manager and be readable by $SA."
