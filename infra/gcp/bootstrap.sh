#!/usr/bin/env bash
# One-time (idempotent) GCP setup for Tristhana. Specs: docs/specs/NF-02-cloud-run-deploy.md,
# docs/specs/ID-01-accounts.md (database). ADR-0011, ADR-0014.
#
#   infra/gcp/bootstrap.sh --dry-run   # print every command, change nothing (no credentials needed)
#   infra/gcp/bootstrap.sh             # apply (creates resources; the owner approves first)
#
# Re-running is safe: each step checks whether its resource exists before creating it.
# Secret VALUES are never handled here; add them later with:
#   gcloud secrets versions add NAME --data-file=- --project "$PROJECT_ID"
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-braided-trees-444417-u6}"
PROJECT_NUMBER="${PROJECT_NUMBER:-189568791437}"
REGION="${REGION:-europe-west3}"
BILLING_ACCOUNT="${BILLING_ACCOUNT:-01CBF7-6E2154-3A850B}"
GITHUB_REPO="${GITHUB_REPO:-airy-beam/tristhana}"
GITHUB_REPO_ID="${GITHUB_REPO_ID:-1424252113}" # numeric id survives repo renames
SERVICE="tristhana-api"
AR_REPO="tristhana"
RUN_SA="tristhana-run"
DEPLOY_SA="tristhana-deploy"
MIGRATE_SA="tristhana-migrate" # runs the migrations job (ADR-0014)
WIF_POOL="github"
WIF_PROVIDER="github-actions"
BUDGET_NAME="tristhana-monthly"
KEEPWARM_JOB="tristhana-keepwarm"
HOSTING_SITE="tristhana" # https://tristhana.web.app (Mini App, UI-03)
BACKUP_SA="tristhana-backup"
BACKUP_JOB="tristhana-backup"
BACKUP_SCHEDULE="tristhana-backup-weekly"
BACKUP_BUCKET="${PROJECT_ID}-tristhana-backups"
# Official image, pinned by digest (it runs with the backup credentials).
BACKUP_IMAGE="docker.io/library/postgres@sha256:aa90e97ee862e558111d34cfb8b2c4bec768c2b039fb791341686928560263b3"
# Read by the service. database-url: the tristhana_app role via the Supabase session pooler.
# field-encryption-keys: the keyring for private fields such as ladies' holiday (ADR-0016).
SECRETS=(telegram-bot-token telegram-webhook-secret database-url field-encryption-keys)
# Read only by the migrations job: the postgres role (DDL).
MIGRATE_SECRET="database-url-migrate"

RUN_SA_EMAIL="${RUN_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_SA_EMAIL="${DEPLOY_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
MIGRATE_SA_EMAIL="${MIGRATE_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
BACKUP_SA_EMAIL="${BACKUP_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WIF_POOL_ID="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# run: execute (or print in dry-run) a command that changes something.
run() {
  if $DRY_RUN; then
    printf '+'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

# exists: true if a read-only describe succeeds. In dry-run, assume nothing exists.
exists() {
  if $DRY_RUN; then return 1; fi
  "$@" >/dev/null 2>&1
}

step() { printf '\n== %s\n' "$*"; }

gc=(gcloud --project "$PROJECT_ID" --quiet)

step "APIs"
run "${gc[@]}" services enable \
  iam.googleapis.com cloudresourcemanager.googleapis.com run.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com iamcredentials.googleapis.com \
  sts.googleapis.com billingbudgets.googleapis.com cloudscheduler.googleapis.com \
  firebase.googleapis.com firebasehosting.googleapis.com

step "Artifact Registry repo ${AR_REPO} (${REGION}) with cleanup policy"
if ! exists "${gc[@]}" artifacts repositories describe "$AR_REPO" --location "$REGION"; then
  run "${gc[@]}" artifacts repositories create "$AR_REPO" --location "$REGION" \
    --repository-format docker --description "Tristhana images"
fi
policy="$(mktemp)"
trap 'rm -f "$policy"' EXIT
cat >"$policy" <<'JSON'
[
  {"name": "keep-newest-5", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 5}},
  {"name": "delete-old", "action": {"type": "Delete"}, "condition": {"olderThan": "604800s"}}
]
JSON
run "${gc[@]}" artifacts repositories set-cleanup-policies "$AR_REPO" --location "$REGION" \
  --policy "$policy" --no-dry-run

step "Service accounts"
if ! exists "${gc[@]}" iam service-accounts describe "$RUN_SA_EMAIL"; then
  run "${gc[@]}" iam service-accounts create "$RUN_SA" --display-name "Tristhana runtime (Cloud Run)"
fi
if ! exists "${gc[@]}" iam service-accounts describe "$DEPLOY_SA_EMAIL"; then
  run "${gc[@]}" iam service-accounts create "$DEPLOY_SA" --display-name "Tristhana deployer (GitHub Actions)"
fi
if ! exists "${gc[@]}" iam service-accounts describe "$MIGRATE_SA_EMAIL"; then
  run "${gc[@]}" iam service-accounts create "$MIGRATE_SA" --display-name "Tristhana DB migrations (Cloud Run Job)"
fi

step "Deployer permissions (least privilege)"
run "${gc[@]}" projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${DEPLOY_SA_EMAIL}" --role roles/run.developer --condition None
run "${gc[@]}" iam service-accounts add-iam-policy-binding "$RUN_SA_EMAIL" \
  --member "serviceAccount:${DEPLOY_SA_EMAIL}" --role roles/iam.serviceAccountUser
# The deploy job creates and runs the migrations job as the migrate SA.
run "${gc[@]}" iam service-accounts add-iam-policy-binding "$MIGRATE_SA_EMAIL" \
  --member "serviceAccount:${DEPLOY_SA_EMAIL}" --role roles/iam.serviceAccountUser
run "${gc[@]}" artifacts repositories add-iam-policy-binding "$AR_REPO" --location "$REGION" \
  --member "serviceAccount:${DEPLOY_SA_EMAIL}" --role roles/artifactregistry.writer

step "Workload Identity Federation (GitHub, ${GITHUB_REPO} main only)"
# Only these workflows on main may deploy: backend (Cloud Run) and miniapp (Firebase Hosting).
WIF_CONDITION="assertion.repository_id == '${GITHUB_REPO_ID}' && assertion.ref == 'refs/heads/main' && (assertion.workflow_ref.startsWith('${GITHUB_REPO}/.github/workflows/backend.yml@') || assertion.workflow_ref.startsWith('${GITHUB_REPO}/.github/workflows/miniapp.yml@'))"
if ! exists "${gc[@]}" iam workload-identity-pools describe "$WIF_POOL" --location global; then
  run "${gc[@]}" iam workload-identity-pools create "$WIF_POOL" --location global \
    --display-name "GitHub Actions"
fi
if ! exists "${gc[@]}" iam workload-identity-pools providers describe "$WIF_PROVIDER" \
  --location global --workload-identity-pool "$WIF_POOL"; then
  run "${gc[@]}" iam workload-identity-pools providers create-oidc "$WIF_PROVIDER" \
    --location global --workload-identity-pool "$WIF_POOL" \
    --display-name "GitHub Actions OIDC" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref,attribute.workflow_ref=assertion.workflow_ref" \
    --attribute-condition "$WIF_CONDITION"
else
  # Keep the condition current (e.g. a newly allowed workflow).
  run "${gc[@]}" iam workload-identity-pools providers update-oidc "$WIF_PROVIDER" \
    --location global --workload-identity-pool "$WIF_POOL" --attribute-condition "$WIF_CONDITION"
fi
run "${gc[@]}" iam service-accounts add-iam-policy-binding "$DEPLOY_SA_EMAIL" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/${WIF_POOL_ID}/attribute.repository_id/${GITHUB_REPO_ID}"

step "Secret containers (no values) + runtime access per secret"
for secret in "${SECRETS[@]}"; do
  if ! exists "${gc[@]}" secrets describe "$secret"; then
    run "${gc[@]}" secrets create "$secret" --replication-policy automatic
  fi
  run "${gc[@]}" secrets add-iam-policy-binding "$secret" \
    --member "serviceAccount:${RUN_SA_EMAIL}" --role roles/secretmanager.secretAccessor
done
if ! exists "${gc[@]}" secrets describe "$MIGRATE_SECRET"; then
  run "${gc[@]}" secrets create "$MIGRATE_SECRET" --replication-policy automatic
fi
run "${gc[@]}" secrets add-iam-policy-binding "$MIGRATE_SECRET" \
  --member "serviceAccount:${MIGRATE_SA_EMAIL}" --role roles/secretmanager.secretAccessor

step "Cloud Run service ${SERVICE} (placeholder image; CI deploys the real one)"
if ! exists "${gc[@]}" run services describe "$SERVICE" --region "$REGION"; then
  run "${gc[@]}" run deploy "$SERVICE" --region "$REGION" \
    --image us-docker.pkg.dev/cloudrun/container/hello \
    --service-account "$RUN_SA_EMAIL" \
    --min-instances 0 --max-instances 2 --cpu 1 --memory 512Mi --concurrency 80 \
    --timeout 60s --cpu-boost --cpu-throttling --ingress all --port 8080 \
    --allow-unauthenticated
fi

step "Keep-warm ping (Cloud Scheduler, every 10 min; free tier: 3 jobs per billing account)"
# An instance kept alive by pings already has aiogram loaded (~3 s import, UI-01 spec).
# /health/db also keeps the Supabase free project active (it pauses after ~1 week idle).
service_url="https://SERVICE_URL"
if ! $DRY_RUN; then
  service_url="$("${gc[@]}" run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)')"
fi
if ! exists "${gc[@]}" scheduler jobs describe "$KEEPWARM_JOB" --location "$REGION"; then
  run "${gc[@]}" scheduler jobs create http "$KEEPWARM_JOB" --location "$REGION" \
    --schedule "*/10 * * * *" --time-zone "Etc/UTC" --uri "${service_url}/api/v1/health/db" \
    --http-method GET --attempt-deadline 30s --description "Keep one tristhana-api instance warm"
else
  run "${gc[@]}" scheduler jobs update http "$KEEPWARM_JOB" --location "$REGION" \
    --uri "${service_url}/api/v1/health/db"
fi

step "Weekly database backup (Cloud Run Job ${BACKUP_JOB} → gs://${BACKUP_BUCKET}; infra/backup/README.md)"
# Private bucket in the same region; dumps expire after 90 days.
if ! exists gcloud storage buckets describe "gs://${BACKUP_BUCKET}" --project "$PROJECT_ID"; then
  run gcloud storage buckets create "gs://${BACKUP_BUCKET}" --project "$PROJECT_ID" \
    --location "$REGION" --default-storage-class STANDARD \
    --uniform-bucket-level-access --public-access-prevention
fi
lifecycle="$(mktemp)"
trap 'rm -f "$policy" "$lifecycle"' EXIT
echo '{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 90}}]}' >"$lifecycle"
run gcloud storage buckets update "gs://${BACKUP_BUCKET}" --project "$PROJECT_ID" \
  --lifecycle-file "$lifecycle"
if ! exists "${gc[@]}" iam service-accounts describe "$BACKUP_SA_EMAIL"; then
  run "${gc[@]}" iam service-accounts create "$BACKUP_SA" --display-name "Tristhana DB backup (Cloud Run Job)"
fi
# Create and read objects (the mount needs list/get), never delete or overwrite.
for role in roles/storage.objectCreator roles/storage.objectViewer; do
  run gcloud storage buckets add-iam-policy-binding "gs://${BACKUP_BUCKET}" --project "$PROJECT_ID" \
    --member "serviceAccount:${BACKUP_SA_EMAIL}" --role "$role"
done
# database-url-backup: role tristhana_backup (read-only, infra/supabase/backup_role.sql), value
# added by the owner via stdin. supabase-ca: the public CA cert, added from the repo here.
for secret in database-url-backup supabase-ca; do
  if ! exists "${gc[@]}" secrets describe "$secret"; then
    run "${gc[@]}" secrets create "$secret" --replication-policy automatic
  fi
  run "${gc[@]}" secrets add-iam-policy-binding "$secret" \
    --member "serviceAccount:${BACKUP_SA_EMAIL}" --role roles/secretmanager.secretAccessor
done
if $DRY_RUN || [[ -z "$("${gc[@]}" secrets versions list supabase-ca --format 'value(name)' --limit 1)" ]]; then
  run "${gc[@]}" secrets versions add supabase-ca --data-file "$REPO_ROOT/infra/supabase/certs/supabase-ca.crt"
fi
# The script travels base64-encoded: gcloud splits --args on commas.
script_b64="$(base64 -w0 "$REPO_ROOT/infra/backup/backup.sh")"
run "${gc[@]}" run jobs deploy "$BACKUP_JOB" --region "$REGION" --image "$BACKUP_IMAGE" \
  --service-account "$BACKUP_SA_EMAIL" --execution-environment gen2 \
  --cpu 1 --memory 512Mi --max-retries 1 --task-timeout 600s \
  --command sh --args "-c,echo ${script_b64} | base64 -d | sh" \
  --set-env-vars "BACKUP_DIR=/backups,PGSSLMODE=verify-full,PGSSLROOTCERT=/ca/supabase-ca.crt" \
  --set-secrets "DATABASE_URL=database-url-backup:latest,/ca/supabase-ca.crt=supabase-ca:latest" \
  --clear-volumes --clear-volume-mounts \
  --add-volume "name=backups,type=cloud-storage,bucket=${BACKUP_BUCKET}" \
  --add-volume-mount "volume=backups,mount-path=/backups"
run "${gc[@]}" run jobs add-iam-policy-binding "$BACKUP_JOB" --region "$REGION" \
  --member "serviceAccount:${BACKUP_SA_EMAIL}" --role roles/run.invoker
if ! exists "${gc[@]}" scheduler jobs describe "$BACKUP_SCHEDULE" --location "$REGION"; then
  run "${gc[@]}" scheduler jobs create http "$BACKUP_SCHEDULE" --location "$REGION" \
    --schedule "0 3 * * 0" --time-zone "Etc/UTC" --http-method POST \
    --uri "https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${BACKUP_JOB}:run" \
    --oauth-service-account-email "$BACKUP_SA_EMAIL" \
    --description "Weekly pg_dump of schema tristhana (Sundays 03:00 UTC)"
fi

step "Firebase Hosting for the Mini App (site ${HOSTING_SITE})"
# No gcloud commands exist for these, so they use the REST APIs with the caller's token.
firebase_api() { # METHOD URL [JSON]
  local token
  token="$(gcloud auth print-access-token)"
  curl -sS --fail-with-body -X "$1" "$2" -H "Authorization: Bearer ${token}" \
    -H "x-goog-user-project: ${PROJECT_ID}" -H "Content-Type: application/json" ${3:+-d "$3"}
}
if $DRY_RUN || ! firebase_api GET "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}" >/dev/null 2>&1; then
  run firebase_api POST "https://firebase.googleapis.com/v1beta1/projects/${PROJECT_ID}:addFirebase" "{}"
  $DRY_RUN || sleep 30 # addFirebase is a long-running operation
fi
if $DRY_RUN || ! firebase_api GET \
  "https://firebasehosting.googleapis.com/v1beta1/projects/${PROJECT_ID}/sites/${HOSTING_SITE}" >/dev/null 2>&1; then
  run firebase_api POST \
    "https://firebasehosting.googleapis.com/v1beta1/projects/${PROJECT_ID}/sites?siteId=${HOSTING_SITE}" "{}"
fi
run "${gc[@]}" projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${DEPLOY_SA_EMAIL}" --role roles/firebasehosting.admin --condition None

step "Budget \$5/month (alerts only; it does not cap spend)"
existing_budget=""
if ! $DRY_RUN; then
  # Fails loudly (set -e) instead of treating an error as "no budget" and creating a duplicate.
  existing_budget="$(gcloud billing budgets list --billing-account "$BILLING_ACCOUNT" \
    --billing-project "$PROJECT_ID" --filter "displayName=${BUDGET_NAME}" --format "value(name)")"
fi
if [[ -z "$existing_budget" ]]; then
  run gcloud billing budgets create --billing-account "$BILLING_ACCOUNT" --billing-project "$PROJECT_ID" \
    --display-name "$BUDGET_NAME" --budget-amount 5USD \
    --filter-projects "projects/${PROJECT_NUMBER}" \
    --threshold-rule percent=0.5 --threshold-rule percent=0.9 \
    --threshold-rule percent=1.0 --threshold-rule percent=1.0,basis=forecasted-spend
fi

step "GitHub repository variables (not secrets: nothing here is sensitive)"
run gh variable set GCP_PROJECT_ID --repo "$GITHUB_REPO" --body "$PROJECT_ID"
run gh variable set GCP_REGION --repo "$GITHUB_REPO" --body "$REGION"
run gh variable set GCP_WIF_PROVIDER --repo "$GITHUB_REPO" --body "${WIF_POOL_ID}/providers/${WIF_PROVIDER}"
run gh variable set GCP_DEPLOY_SA --repo "$GITHUB_REPO" --body "$DEPLOY_SA_EMAIL"
run gh variable set GCP_RUN_SA --repo "$GITHUB_REPO" --body "$RUN_SA_EMAIL"
run gh variable set GCP_MIGRATE_SA --repo "$GITHUB_REPO" --body "$MIGRATE_SA_EMAIL"

step "Done"
echo "Service URL: gcloud run services describe ${SERVICE} --region ${REGION} --format 'value(status.url)' --project ${PROJECT_ID}"
