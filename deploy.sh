#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# EcoQuest — Idempotent GCP Deployment Script
# Run: bash deploy.sh
# Prerequisites: gcloud CLI authenticated, PROJECT_ID set
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Configuration — edit these before first deploy ───────────────────────────
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-ecoquest2}"
REGION="${REGION:-asia-south1}"
FIRESTORE_REGION="${FIRESTORE_REGION:-asia-south1}"
AR_REPO="ecoquest-registry"
BACKEND_SERVICE="ecoquest-backend"
FRONTEND_SERVICE="ecoquest-frontend"
GCS_BUCKET="${PROJECT_ID}-ecoquest-uploads"
SCHEDULER_JOB="ecoquest-challenge-rotation"
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[✓]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fatal()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Guard: require project ────────────────────────────────────────────────────
[[ -z "${PROJECT_ID}" ]] && fatal "Set GOOGLE_CLOUD_PROJECT or run: gcloud config set project YOUR_PROJECT_ID"
info "Deploying EcoQuest to project: ${PROJECT_ID} (region: ${REGION})"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Enable required APIs
# ══════════════════════════════════════════════════════════════════════════════
info "STEP 1 — Enabling GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudscheduler.googleapis.com \
  aiplatform.googleapis.com \
  --project="${PROJECT_ID}" --quiet
success "APIs enabled."

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Firestore (native mode)
# ══════════════════════════════════════════════════════════════════════════════
info "STEP 2 — Setting up Firestore..."
if ! gcloud firestore databases list --project="${PROJECT_ID}" 2>/dev/null | grep -q "(default)"; then
  gcloud firestore databases create \
    --project="${PROJECT_ID}" \
    --location="${FIRESTORE_REGION}" \
    --type=firestore-native --quiet
  success "Firestore database created."
else
  warn "Firestore (default) already exists — skipping create."
fi

# Deploy indexes if file exists
INDEXES_FILE="$(dirname "$0")/firestore.indexes.json"
if [[ -f "${INDEXES_FILE}" ]]; then
  info "Deploying Firestore composite indexes via python script..."
  python3 -c "
import json, subprocess, sys
with open('${INDEXES_FILE}') as f:
    data = json.load(f)
for idx in data.get('indexes', []):
    cg = idx['collectionGroup']
    fields = idx['fields']
    cmd = ['gcloud', 'firestore', 'indexes', 'composite', 'create', '--project=' + sys.argv[1], '--collection-group=' + cg, '--async']
    for field in fields:
        path = field['fieldPath']
        order = field['order'].lower()
        cmd.append(f'--field-config=field-path={path},order={order}')
    print(f'Requesting index for {cg}...')
    res = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if res.returncode != 0:
        if 'ALREADY_EXISTS' in res.stderr or 'already exists' in res.stderr:
            print(f'Index for {cg} already exists — skipping.')
        else:
            print(f'Error requesting index for {cg}: {res.stderr.strip()}')
    else:
        print(f'Index creation requested for {cg}.')
" "${PROJECT_ID}"
  success "Firestore indexes request processed."
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Artifact Registry
# ══════════════════════════════════════════════════════════════════════════════
info "STEP 3 — Creating Artifact Registry repository..."
if ! gcloud artifacts repositories describe "${AR_REPO}" \
    --project="${PROJECT_ID}" --location="${REGION}" &>/dev/null; then
  gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="EcoQuest Docker images" \
    --project="${PROJECT_ID}" --quiet
  success "Artifact Registry created: ${AR_REPO}"
else
  warn "Artifact Registry '${AR_REPO}' already exists — skipping."
fi

# Configure Docker to use Artifact Registry
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Cloud Storage bucket for uploads
# ══════════════════════════════════════════════════════════════════════════════
info "STEP 4 — Setting up Cloud Storage bucket..."
if ! gcloud storage buckets describe "gs://${GCS_BUCKET}" &>/dev/null; then
  gcloud storage buckets create "gs://${GCS_BUCKET}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}"
  success "GCS bucket created: ${GCS_BUCKET}"
else
  warn "GCS bucket '${GCS_BUCKET}' already exists — skipping."
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Secret Manager
# ══════════════════════════════════════════════════════════════════════════════
info "STEP 5 — Configuring Secret Manager..."

if ! gcloud secrets describe gemini-api-key --project="${PROJECT_ID}" &>/dev/null; then
  gcloud secrets create gemini-api-key \
    --replication-policy="automatic" \
    --project="${PROJECT_ID}"
  echo ""
  echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}ACTION REQUIRED: Paste your Gemini API key below:${NC}"
  echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  read -rsp "Gemini API Key: " GEMINI_KEY
  echo ""
  echo -n "${GEMINI_KEY}" | gcloud secrets versions add gemini-api-key \
    --data-file=- --project="${PROJECT_ID}"
  success "gemini-api-key secret created and populated."
else
  warn "Secret 'gemini-api-key' already exists — skipping creation."
fi

# Internal auth token for Cloud Scheduler
if ! gcloud secrets describe ecoquest-internal-token --project="${PROJECT_ID}" &>/dev/null; then
  INTERNAL_TOKEN=$(openssl rand -hex 32)
  echo -n "${INTERNAL_TOKEN}" | gcloud secrets create ecoquest-internal-token \
    --data-file=- --replication-policy="automatic" --project="${PROJECT_ID}"
  success "Internal auth token secret created."
else
  warn "Internal token secret already exists — skipping."
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — IAM: Cloud Run Service Account
# ══════════════════════════════════════════════════════════════════════════════
info "STEP 6 — Configuring IAM..."
SA_NAME="ecoquest-backend-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" &>/dev/null; then
  gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="EcoQuest Backend Service Account" \
    --project="${PROJECT_ID}"
fi

for ROLE in roles/datastore.user roles/storage.objectCreator roles/secretmanager.secretAccessor roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" --quiet
done
success "IAM roles bound to ${SA_EMAIL}"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 7 — Cloud Build: Backend image
# ══════════════════════════════════════════════════════════════════════════════
info "STEP 7 — Building and pushing Docker images via Cloud Build..."
BACKEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/backend:${GIT_SHA}"
FRONTEND_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/frontend:${GIT_SHA}"

gcloud builds submit backend/ \
  --tag="${BACKEND_IMAGE}" \
  --project="${PROJECT_ID}"
success "Backend image built: ${BACKEND_IMAGE}"

# Frontend: Nginx-served static files
gcloud builds submit frontend/ \
  --tag="${FRONTEND_IMAGE}" \
  --project="${PROJECT_ID}"
success "Frontend image built: ${FRONTEND_IMAGE}"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 8 — Cloud Run: Deploy backend & frontend
# ══════════════════════════════════════════════════════════════════════════════
info "STEP 8 — Deploying to Cloud Run..."

gcloud run deploy "${BACKEND_SERVICE}" \
  --image="${BACKEND_IMAGE}" \
  --region="${REGION}" \
  --platform=managed \
  --service-account="${SA_EMAIL}" \
  --min-instances=1 \
  --max-instances=10 \
  --memory=512Mi \
  --cpu=1 \
  --concurrency=80 \
  --timeout=300 \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},GCS_BUCKET_NAME=${GCS_BUCKET},ENVIRONMENT=production,FRONTEND_ORIGIN=https://${FRONTEND_SERVICE}-${PROJECT_ID}.a.run.app" \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,INTERNAL_AUTH_TOKEN=ecoquest-internal-token:latest" \
  --allow-unauthenticated \
  --project="${PROJECT_ID}" --quiet

BACKEND_URL=$(gcloud run services describe "${BACKEND_SERVICE}" \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format="value(status.url)")
success "Backend deployed: ${BACKEND_URL}"

# Deploy frontend (with BACKEND_URL injected at startup by entrypoint script)
gcloud run deploy "${FRONTEND_SERVICE}" \
  --image="${FRONTEND_IMAGE}" \
  --region="${REGION}" \
  --platform=managed \
  --min-instances=0 \
  --max-instances=5 \
  --memory=256Mi \
  --cpu=1 \
  --set-env-vars="BACKEND_URL=${BACKEND_URL}" \
  --allow-unauthenticated \
  --project="${PROJECT_ID}" --quiet

FRONTEND_URL=$(gcloud run services describe "${FRONTEND_SERVICE}" \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format="value(status.url)")
success "Frontend deployed: ${FRONTEND_URL}"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 9 — Cloud Scheduler: Challenge rotation
# ══════════════════════════════════════════════════════════════════════════════
info "STEP 9 — Setting up Cloud Scheduler..."

SCHEDULER_SA="ecoquest-scheduler-sa"
SCHEDULER_SA_EMAIL="${SCHEDULER_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "${SCHEDULER_SA_EMAIL}" --project="${PROJECT_ID}" &>/dev/null; then
  gcloud iam service-accounts create "${SCHEDULER_SA}" \
    --display-name="EcoQuest Scheduler SA" \
    --project="${PROJECT_ID}"
fi
gcloud run services add-iam-policy-binding "${BACKEND_SERVICE}" \
  --region="${REGION}" \
  --member="serviceAccount:${SCHEDULER_SA_EMAIL}" \
  --role="roles/run.invoker" \
  --project="${PROJECT_ID}" --quiet

INTERNAL_TOKEN=$(gcloud secrets versions access latest \
  --secret="ecoquest-internal-token" --project="${PROJECT_ID}")

if ! gcloud scheduler jobs describe "${SCHEDULER_JOB}" \
    --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
  # Create temporary flags file to avoid exposing token in process list
  cat <<EOF > temp_scheduler.yaml
--location: ${REGION}
--schedule: "0 0 * * 1"
--time-zone: "Asia/Kolkata"
--uri: ${BACKEND_URL}/internal/challenges/rotate
--http-method: POST
--headers:
  Authorization: "Bearer ${INTERNAL_TOKEN}"
  Content-Type: "application/json"
--message-body: '{"auth_token":"${INTERNAL_TOKEN}"}'
--oidc-service-account-email: ${SCHEDULER_SA_EMAIL}
--project: ${PROJECT_ID}
EOF
  chmod 600 temp_scheduler.yaml

  gcloud scheduler jobs create http "${SCHEDULER_JOB}" --flags-file=temp_scheduler.yaml
  rm -f temp_scheduler.yaml
  success "Cloud Scheduler job created: ${SCHEDULER_JOB}"
else
  warn "Scheduler job already exists — skipping."
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 10 — Seed initial challenges into Firestore
# ══════════════════════════════════════════════════════════════════════════════
info "STEP 10 — Seeding challenges via rotation endpoint..."

info "Waiting for backend service to become healthy..."
for i in {1..6}; do
  if curl -sSf "${BACKEND_URL}/health" &>/dev/null; then
    success "Backend is healthy."
    break
  else
    warn "Backend not ready yet (attempt $i/6) — retrying in 5s..."
    sleep 5
  fi
  if [ $i -eq 6 ]; then
    fatal "Backend health check failed after 30 seconds."
  fi
done

# Create temporary Python script to run seed request securely
cat <<EOF > temp_seed.py
import urllib.request
import json
import sys
from google.cloud import secretmanager

backend_url = sys.argv[1]
project = sys.argv[2]

client = secretmanager.SecretManagerServiceClient()
name = f"projects/{project}/secrets/ecoquest-internal-token/versions/latest"
try:
    response = client.access_secret_version(request={"name": name})
    token = response.payload.data.decode("utf-8").strip()
except Exception as e:
    print(f"Error fetching token from Secret Manager: {e}")
    sys.exit(1)

req = urllib.request.Request(
    f"{backend_url}/internal/challenges/rotate",
    data=json.dumps({"auth_token": token}).encode(),
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    },
    method="POST"
)
try:
    with urllib.request.urlopen(req) as f:
        print(f"Seed Response: {f.read().decode()}")
except Exception as e:
    print(f"Seed endpoint error: {e}")
    sys.exit(1)
EOF
chmod 600 temp_seed.py

python3 temp_seed.py "${BACKEND_URL}" "${PROJECT_ID}" || warn "Challenge seed failed"
rm -f temp_seed.py

# ══════════════════════════════════════════════════════════════════════════════
# STEP 11 — Summary
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  🌍 EcoQuest deployed successfully!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  🌐 Frontend:  ${CYAN}${FRONTEND_URL}${NC}"
echo -e "  🔧 Backend:   ${CYAN}${BACKEND_URL}${NC}"
echo -e "  ❤️  Health:    ${CYAN}${BACKEND_URL}/health${NC}"
echo ""
echo -e "  💰 Estimated monthly GCP cost:"
echo -e "     Cloud Run (backend, min=1):  ~\$15–25/month"
echo -e "     Cloud Run (frontend, min=0): ~\$2–5/month"
echo -e "     Firestore:                   ~\$5–15/month"
echo -e "     Vertex AI (Gemini 2.5 Flash):~\$10–30/month (usage-based)"
echo -e "     Cloud Storage + Scheduler:   ~\$1–3/month"
echo -e "     TOTAL estimate:              ~\$33–78/month"
echo ""
echo -e "  Run health check: curl ${BACKEND_URL}/health"
echo ""
