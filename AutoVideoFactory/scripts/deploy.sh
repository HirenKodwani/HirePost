#!/usr/bin/env bash
set -euo pipefail

# AutoVideoFactory - Cloud Run Deployment Script (SQLite free tier)
# Run this from Google Cloud Shell (https://shell.cloud.google.com)
#
# Prerequisites:
#   1. A GCP project with billing enabled
#   2. Run: gcloud auth login && gcloud config set project YOUR_PROJECT_ID
#
# Usage: bash scripts/deploy.sh

PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
SERVICE_NAME="autovideofactory"
GCS_BUCKET="${SERVICE_NAME}-${PROJECT_ID}"
GROQ_API_KEY="${AVF_OPENAI_API_KEY:-}"
GROQ_API_KEY_BACKUP="${AVF_OPENAI_API_KEY_BACKUP:-}"

echo "=== Deploying AutoVideoFactory to Cloud Run (free tier) ==="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"

# Check required variables
if [ -z "$GROQ_API_KEY" ]; then
    echo "ERROR: Set AVF_OPENAI_API_KEY env var with your Groq API key"
    echo "  export AVF_OPENAI_API_KEY='gsk_...'"
    exit 1
fi

# Enable APIs
echo "=== Enabling GCP APIs ==="
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    storage.googleapis.com \
    secretmanager.googleapis.com

# Create GCS bucket
echo "=== Creating GCS bucket ==="
gsutil ls "gs://${GCS_BUCKET}" 2>/dev/null || \
    gcloud storage buckets create "gs://${GCS_BUCKET}" --location="${REGION}"

# Store Groq API keys in Secret Manager
echo "=== Storing secrets ==="
echo -n "${GROQ_API_KEY}" | gcloud secrets create groq-api-key --data-file=- 2>/dev/null || \
    echo -n "${GROQ_API_KEY}" | gcloud secrets versions add groq-api-key --data-file=-

if [ -n "$GROQ_API_KEY_BACKUP" ]; then
    echo -n "${GROQ_API_KEY_BACKUP}" | gcloud secrets create groq-api-key-backup --data-file=- 2>/dev/null || \
        echo -n "${GROQ_API_KEY_BACKUP}" | gcloud secrets versions add groq-api-key-backup --data-file=-
fi

# Grant Cloud Run access to secrets and GCS
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud secrets add-iam-policy-binding groq-api-key \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/secretmanager.secretAccessor" 2>/dev/null || true

if [ -n "$GROQ_API_KEY_BACKUP" ]; then
    gcloud secrets add-iam-policy-binding groq-api-key-backup \
        --member="serviceAccount:${COMPUTE_SA}" \
        --role="roles/secretmanager.secretAccessor" 2>/dev/null || true
fi

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/storage.objectAdmin" 2>/dev/null || true

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/logging.logWriter" 2>/dev/null || true

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/artifactregistry.writer" 2>/dev/null || true

# Build using Cloud Build with explicit Dockerfile
echo "=== Building Docker image via Cloud Build ==="
gcloud artifacts repositories describe cloud-run-source-deploy \
    --location="${REGION}" 2>/dev/null || \
    gcloud artifacts repositories create cloud-run-source-deploy \
        --repository-format=docker \
        --location="${REGION}" \
        --description="Cloud Run source deploy"

gcloud builds submit \
    --tag="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${SERVICE_NAME}:latest" \
    .

# Deploy to Cloud Run (SQLite in /tmp/data, CPU throttled for free tier)
echo "=== Deploying to Cloud Run ==="
gcloud run deploy "${SERVICE_NAME}" \
    --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${SERVICE_NAME}:latest" \
    --region="${REGION}" \
    --platform=managed \
    --allow-unauthenticated \
    --memory=4Gi \
    --cpu=2 \
    --timeout=600 \
    --cpu-throttling \
    --update-env-vars="\
AVF_ENVIRONMENT=production,\
AVF_DEBUG=false,\
AVF_CONTAINER_MODE=true,\
AVF_HOST=0.0.0.0,\
AVF_LLM_PROVIDER=openai,\
AVF_OPENAI_BASE_URL=https://api.groq.com/openai/v1,\
AVF_OPENAI_DEFAULT_MODEL=llama-3.3-70b-versatile,\
AVF_LLM_TEMPERATURE=0.7,\
AVF_LLM_MAX_TOKENS=8192,\
AVF_STORAGE_PROVIDER=gcs,\
AVF_GCS_BUCKET_NAME=${GCS_BUCKET},\
AVF_DATA_DIR=/tmp/data,\
AVF_SESSIONS_DIR=/tmp/sessions,\
AVF_OUTPUT_DIR=/tmp/output,\
AVF_TEMP_DIR=/tmp/temp,\
AVF_LOGS_DIR=/tmp/logs" \
    --remove-env-vars="AVF_DATABASE_URL" \
    --set-secrets="AVF_OPENAI_API_KEY=groq-api-key:latest" \
    --set-secrets="AVF_OPENAI_API_KEY_BACKUP=groq-api-key-backup:latest" \
    --service-account="${COMPUTE_SA}"

DEPLOY_URL=$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --format="value(status.url)")

# Update redirect URI for YouTube OAuth
CALLBACK_URL="${DEPLOY_URL}/api/v1/auth/youtube/callback"
gcloud run services update "${SERVICE_NAME}" \
    --region="${REGION}" \
    --update-env-vars="AVF_GOOGLE_REDIRECT_URI=${CALLBACK_URL}"

echo ""
echo "=========================================="
echo "  DEPLOYMENT COMPLETE!"
echo "  URL: ${DEPLOY_URL}"
echo "=========================================="
echo ""
echo "=== IMPORTANT: YouTube tokens are ephemeral on SQLite ==="
echo "  The app auto-restores tokens from GCS backup on startup."
echo "  After first OAuth auth, tokens are persisted in GCS."
echo ""
echo "=== NEXT STEPS ==="
echo ""
echo "1. ADD CALLBACK URL to Google Cloud Console OAuth:"
echo "   https://console.cloud.google.com/apis/credentials"
echo "   Add this to both OAuth clients:"
echo "   ${CALLBACK_URL}"
echo ""
echo "2. AUTHORIZE FIRST YOUTUBE CHANNEL:"
echo "   ${DEPLOY_URL}/api/v1/auth/youtube/login"
echo ""
echo "3. AUTHORIZE SECOND YOUTUBE CHANNEL:"
echo "   ${DEPLOY_URL}/api/v1/auth/youtube/login?oauth_config=secondary"
echo ""
echo "4. ADD PIXABAY API KEY (optional):"
echo "   gcloud run services update ${SERVICE_NAME} --region=${REGION} --update-env-vars=AVF_PIXABAY_API_KEY=your_key"
echo ""
echo "5. TEST PIPELINE:"
echo "   curl -X POST ${DEPLOY_URL}/api/v1/agents/run-full-pipeline \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"style\":\"comedy\",\"duration\":45,\"language\":\"hinglish\"}'"
echo "   curl ${DEPLOY_URL}/api/v1/agents/pipeline-status/PIPELINE_ID"
echo ""
echo "6. SET UP SCHEDULED DAILY JOB (recommended):"
echo "   bash scripts/deploy_job.sh"
echo ""
echo "7. TRIGGER A JOB MANUALLY FOR TESTING:"
echo "   gcloud run jobs execute ${SERVICE_NAME}-pipeline --region=${REGION}"
echo ""
echo "8. (Optional) Delete old Cloud SQL instance to save money:"
echo "   gcloud sql instances delete ${SERVICE_NAME}-db --project=${PROJECT_ID}"
