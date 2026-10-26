#!/usr/bin/env bash
# Idempotent deploy of the web service (Meeting Scribe + the Dory command center) to Cloud Run,
# with the Pub/Sub push subscription, the Firestore database, the buckets and the secrets a FRESH
# project needs. Usage: GCP_PROJECT=<project> scripts/deploy.sh   (gcloud logged in as an owner).
# Secrets come from the environment, else from .env, and are never echoed: DISCORD_WEBHOOK_URL
# (optional, Meeting Scribe's Discord post), DORY_NEBIUS_API_KEY (Nemotron on Token Factory),
# DORY_SESSION_SECRET (generated when absent), DORY_DISCORD_CLIENT_SECRET (optional, Sign in with
# Discord; secret dory-discord-client-secret). A Secret Manager version is added only when the
# secret has none yet. Optional env passed to the service: HUB_GOOGLE_CLIENT_ID, HUB_ADMIN_EMAILS,
# DORY_DISCORD_CLIENT_ID, DORY_HUB_URL (environment, else .env, else the service URL). Env vars and
# secrets are UPDATED, never replaced: anything else already on the service is kept (remove a stale
# one by hand with `gcloud run services update --remove-env-vars`).
# No Vertex AI: the models run on Nebius Token Factory (README "NVIDIA Nemotron on Nebius Token
# Factory"); enable aiplatform.googleapis.com by hand if a project is meant to use Gemini too.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck disable=SC1090
[ -f "$HOME/google-cloud-sdk/path.bash.inc" ] && source "$HOME/google-cloud-sdk/path.bash.inc"

PROJECT="${GCP_PROJECT:-dory-personal-assistant}"
REGION="${GCP_REGION:-asia-southeast1}"
BUCKET="${AUDIO_BUCKET:-$PROJECT-audio}"          # Meeting Scribe audio chunks
FILES_BUCKET="${DORY_RECEIPT_BUCKET:-$PROJECT-files}"  # Dory documents, receipts, originals
TOPIC="meeting-finalize"
SERVICE="meeting-scribe"
SUBSCRIPTION="meeting-finalize-push"
SECRET="discord-webhook-url"
RUN_SA_NAME="meeting-scribe-run"
PUSHER_SA_NAME="meeting-scribe-pusher"
RUN_SA="$RUN_SA_NAME@$PROJECT.iam.gserviceaccount.com"
PUSHER_SA="$PUSHER_SA_NAME@$PROJECT.iam.gserviceaccount.com"

gcloud config set project "$PROJECT" >/dev/null
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"

echo "==> Enabling APIs"
gcloud services enable secretmanager.googleapis.com run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com pubsub.googleapis.com firestore.googleapis.com iam.googleapis.com \
  cloudresourcemanager.googleapis.com compute.googleapis.com

echo "==> Firestore database, buckets, topic"
gcloud firestore databases describe --database='(default)' >/dev/null 2>&1 \
  || gcloud firestore databases create --database='(default)' --location "$REGION" \
       --type firestore-native >/dev/null
for b in "$BUCKET" "$FILES_BUCKET"; do
  gcloud storage buckets describe "gs://$b" >/dev/null 2>&1 \
    || gcloud storage buckets create "gs://$b" --location "$REGION" --uniform-bucket-level-access >/dev/null
done
gcloud pubsub topics describe "$TOPIC" >/dev/null 2>&1 || gcloud pubsub topics create "$TOPIC" >/dev/null

ensure_sa() {  # name, display name
  gcloud iam service-accounts describe "$1@$PROJECT.iam.gserviceaccount.com" >/dev/null 2>&1 \
    || gcloud iam service-accounts create "$1" --display-name "$2"
}

echo "==> Service accounts"
ensure_sa "$RUN_SA_NAME" "Meeting Scribe (Cloud Run runtime)"
ensure_sa "$PUSHER_SA_NAME" "Meeting Scribe (Pub/Sub push identity)"
# Newly created service accounts can take a few seconds to become visible to IAM.
for _ in 1 2 3 4 5 6; do gcloud iam service-accounts describe "$PUSHER_SA" >/dev/null 2>&1 && break; sleep 5; done

for role in roles/datastore.user roles/pubsub.publisher roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$RUN_SA" --role "$role" \
    --condition=None >/dev/null
done
# A fresh project builds as the Compute Engine default service account; without the builder role
# the source upload cannot even be read ("does not have storage.objects.get access").
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member "serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role roles/cloudbuild.builds.builder --condition=None >/dev/null
for b in "$BUCKET" "$FILES_BUCKET"; do
  gcloud storage buckets add-iam-policy-binding "gs://$b" --member "serviceAccount:$RUN_SA" \
    --role roles/storage.objectAdmin >/dev/null
done

echo "==> Secrets"
from_env_file() {  # value of a key from the environment, else from .env; never printed
  local v="${!1:-}"
  if [ -z "$v" ] && [ -f .env ]; then
    v="$(grep "^$1=" .env | head -n1 | cut -d= -f2- | tr -d '\r"'"'" | tr -d '\n')"
  fi
  printf '%s' "$v"
}
SECRET_REFS=()
ensure_secret() {  # secret name, env var, "required" | "optional": add a version only when none exists
  local name="$1" var="$2" value
  gcloud secrets describe "$name" >/dev/null 2>&1 \
    || gcloud secrets create "$name" --replication-policy automatic >/dev/null
  if ! gcloud secrets versions list "$name" --limit 1 --format='value(name)' | grep -q .; then
    value="$(from_env_file "$var")"
    if [ -z "$value" ] && [ "$var" = DORY_SESSION_SECRET ]; then value="$(openssl rand -hex 32)"; fi
    if [ -z "$value" ]; then
      if [ "$3" = required ]; then echo "ERROR: no $var in the environment or .env" >&2; exit 1; fi
      echo "    $name: no value and no version, left out"; return 0
    fi
    # The value goes via stdin only; it is never echoed or placed on a command line.
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
    echo "    stored the first version of $name"
  fi
  gcloud secrets add-iam-policy-binding "$name" --member "serviceAccount:$RUN_SA" \
    --role roles/secretmanager.secretAccessor >/dev/null
  SECRET_REFS+=("$var=$name:latest")
}
ensure_secret "$SECRET" DISCORD_WEBHOOK_URL optional
ensure_secret dory-nebius-api-key DORY_NEBIUS_API_KEY required
ensure_secret dory-session-secret DORY_SESSION_SECRET required
ensure_secret dory-discord-client-secret DORY_DISCORD_CLIENT_SECRET optional  # Sign in with Discord
SECRETS_JOINED="$(IFS=,; echo "${SECRET_REFS[*]}")"

# Expected Cloud Run URL, so the OIDC audience can be set in the same deploy.
# On re-runs the service already reports its canonical URL.
URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)' 2>/dev/null || true)"
URL="${URL:-https://$SERVICE-$PROJECT_NUMBER.$REGION.run.app}"
HUB_URL="$(from_env_file DORY_HUB_URL)"; HUB_URL="${HUB_URL:-$URL}"   # the custom domain once mapped

echo "==> Deploying Cloud Run service $SERVICE"
ENV_PAIRS=("USE_PUBSUB=true" "PUBSUB_VERIFY_AUDIENCE=$URL/pubsub/finalize" "PUSHER_SA_EMAIL=$PUSHER_SA"
           "GCP_PROJECT=$PROJECT" "AUDIO_BUCKET=$BUCKET" "DORY_STORE=firestore"
           "DORY_GCP_PROJECT=$PROJECT" "DORY_RECEIPT_BUCKET=$FILES_BUCKET"
           "DORY_HUB_URL=$HUB_URL")
for k in HUB_GOOGLE_CLIENT_ID HUB_ADMIN_EMAILS DORY_DISCORD_CLIENT_ID; do
  v="$(from_env_file "$k")"; [ -z "$v" ] || ENV_PAIRS+=("$k=$v")   # environment, else .env
done
ENV_JOINED="$(IFS='|'; echo "${ENV_PAIRS[*]}")"   # '|' delimiter: HUB_ADMIN_EMAILS has commas
# --update-*, not --set-*: values set on the service by hand (and not passed here) survive a redeploy
gcloud run deploy "$SERVICE" --quiet --source . --region "$REGION" \
  --service-account "$RUN_SA" \
  --update-env-vars "^|^$ENV_JOINED" \
  --update-secrets "$SECRETS_JOINED" \
  --allow-unauthenticated --timeout 900 --memory 1Gi --cpu 1 --concurrency 20 --max-instances 1

ACTUAL_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
if [ "$ACTUAL_URL" != "$URL" ]; then
  echo "    URL differs from the expected one; updating the OIDC audience to $ACTUAL_URL"
  URL="$ACTUAL_URL"
  gcloud run services update "$SERVICE" --region "$REGION" \
    --update-env-vars "^|^PUBSUB_VERIFY_AUDIENCE=$URL/pubsub/finalize|DORY_HUB_URL=$HUB_URL"
fi

echo "==> Pub/Sub push subscription"
gcloud run services add-iam-policy-binding "$SERVICE" --region "$REGION" \
  --member "serviceAccount:$PUSHER_SA" --role roles/run.invoker >/dev/null
# Pub/Sub's service agent must be able to mint OIDC tokens for the pusher identity.
gcloud iam service-accounts add-iam-policy-binding "$PUSHER_SA" \
  --member "serviceAccount:service-$PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com" \
  --role roles/iam.serviceAccountTokenCreator >/dev/null

SUB_ARGS=(--push-endpoint "$URL/pubsub/finalize" --push-auth-service-account "$PUSHER_SA"
          --push-auth-token-audience "$URL/pubsub/finalize" --ack-deadline 600 --min-retry-delay 10s)
if gcloud pubsub subscriptions describe "$SUBSCRIPTION" >/dev/null 2>&1; then
  gcloud pubsub subscriptions update "$SUBSCRIPTION" "${SUB_ARGS[@]}" >/dev/null
else
  gcloud pubsub subscriptions create "$SUBSCRIPTION" --topic "$TOPIC" "${SUB_ARGS[@]}" >/dev/null
fi

echo
echo "Deployed: $URL"
