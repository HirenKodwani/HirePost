#!/usr/bin/env bash
set -euo pipefail

# AutoVideoFactory - Cloud Run Deployment Script
# Run this from Google Cloud Shell (https://shell.cloud.google.com)
#
# Prerequisites:
#   1. A GCP project with billing enabled
#   2. Run: gcloud auth login && gcloud config set project YOUR_PROJECT_ID
#   3. A Cloud SQL PostgreSQL instance (or let this script create one)
#
# Usage: bash scripts/deploy.sh

PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
SERVICE_NAME="autovideofactory"
GCS_BUCKET="${SERVICE_NAME}-${PROJECT_ID}"
CLOUD_SQL_INSTANCE="${SERVICE_NAME}-db"
CLOUD_SQL_CONNECTION="${PROJECT_ID}:${REGION}:${CLOUD_SQL_INSTANCE}"
DB_NAME="autovideofactory"
DB_USER="autovideofactory"
DB_PASS=$(openssl rand -base64 18)
GROQ_API_KEY="${AVF_OPENAI_API_KEY:-}"

echo "=== Deploying AutoVideoFactory to Cloud Run ==="
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
    sqladmin.googleapis.com \
    storage.googleapis.com \
    secretmanager.googleapis.com

# Create GCS bucket
echo "=== Creating GCS bucket ==="
gsutil ls "gs://${GCS_BUCKET}" 2>/dev/null || \
    gcloud storage buckets create "gs://${GCS_BUCKET}" --location="${REGION}"

# Create Cloud SQL PostgreSQL instance
echo "=== Creating Cloud SQL PostgreSQL instance ==="
gcloud sql instances describe "${CLOUD_SQL_INSTANCE}" 2>/dev/null || \
    gcloud sql instances create "${CLOUD_SQL_INSTANCE}" \
        --database-version=POSTGRES_16 \
        --region="${REGION}" \
        --tier=db-f1-micro \
        --storage-size=10GB \
        --storage-type=SSD

gcloud sql databases describe "${DB_NAME}" --instance="${CLOUD_SQL_INSTANCE}" 2>/dev/null || \
    gcloud sql databases create "${DB_NAME}" --instance="${CLOUD_SQL_INSTANCE}"

gcloud sql users describe "${DB_USER}" --instance="${CLOUD_SQL_INSTANCE}" 2>/dev/null || \
    gcloud sql users create "${DB_USER}" --instance="${CLOUD_SQL_INSTANCE}" --password="${DB_PASS}"

# Store Groq API key in Secret Manager
echo "=== Storing secrets ==="
echo -n "${GROQ_API_KEY}" | gcloud secrets create groq-api-key --data-file=- 2>/dev/null || \
    echo -n "${GROQ_API_KEY}" | gcloud secrets versions add groq-api-key --data-file=-

# Grant Cloud Run access to secrets and Cloud SQL
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud secrets add-iam-policy-binding groq-api-key \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${COMPUTE_SA}" \
    --role="roles/cloudsql.client"

# Build and push Docker image
echo "=== Building Docker image ==="
COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")
IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${SERVICE_NAME}:${COMMIT_SHA}"

gcloud builds submit \
    --config=cloudbuild.yaml \
    --substitutions="_REGION=${REGION},_CLOUD_SQL_CONNECTION=${CLOUD_SQL_CONNECTION},_DB_PASSWORD=${DB_PASS},_SERVICE_ACCOUNT=${COMPUTE_SA}" \
    .

# Get the deployed URL
DEPLOY_URL=$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --format="value(status.url)" 2>/dev/null || echo "")

if [ -z "$DEPLOY_URL" ]; then
    # Deploy directly if Cloud Build didn't auto-deploy
    echo "=== Deploying to Cloud Run ==="
    gcloud run deploy "${SERVICE_NAME}" \
        --image="${IMAGE_NAME}" \
        --region="${REGION}" \
        --platform=managed \
        --allow-unauthenticated \
        --memory=4Gi \
        --cpu=2 \
        --timeout=600 \
        --set-env-vars="\
AVF_ENVIRONMENT=production,\
AVF_DEBUG=false,\
AVF_CONTAINER_MODE=true,\
AVF_LLM_PROVIDER=openai,\
AVF_OPENAI_BASE_URL=https://api.groq.com/openai/v1,\
AVF_OPENAI_DEFAULT_MODEL=llama-3.3-70b-versatile,\
AVF_LLM_TEMPERATURE=0.7,\
AVF_LLM_MAX_TOKENS=8192,\
AVF_STORAGE_PROVIDER=gcs,\
AVF_GCS_BUCKET_NAME=${GCS_BUCKET},\
AVF_DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASS}@//cloudsql/${CLOUD_SQL_CONNECTION}/${DB_NAME}" \
        --set-secrets="AVF_OPENAI_API_KEY=groq-api-key:latest" \
        --add-cloudsql-instances="${CLOUD_SQL_CONNECTION}" \
        --service-account="${COMPUTE_SA}"

    DEPLOY_URL=$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --format="value(status.url)")
fi

# Update redirect URI
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
echo "5. To run a batch pipeline:"
echo "   gcloud run jobs create batch-pipeline --image=${IMAGE_NAME} --command=python,run_batch.py"
echo "   (Or trigger via the FastAPI endpoint)"
