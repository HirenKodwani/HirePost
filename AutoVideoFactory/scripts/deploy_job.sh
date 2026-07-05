#!/usr/bin/env bash
set -euo pipefail

# AutoVideoFactory - Cloud Run Job + Scheduler Deployment
# Run from Google Cloud Shell after deploy.sh has been run once.
#
# Usage: bash scripts/deploy_job.sh

PROJECT_ID=$(gcloud config get-value project)
REGION="us-central1"
SERVICE_NAME="autovideofactory"
JOB_NAME="${SERVICE_NAME}-pipeline"
SCHEDULER_NAME="${SERVICE_NAME}-daily"
GCS_BUCKET="${SERVICE_NAME}-${PROJECT_ID}"

echo "=== Deploying AutoVideoFactory Pipeline Job ==="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"

# Build OAuth env vars from environment
echo "=== Creating/Updating Cloud Run Job ==="
gcloud run jobs delete "${JOB_NAME}" --region="${REGION}" --quiet 2>/dev/null || true
OAUTH_ENV_VARS=""
OAUTH_ENV_VARS+="AVF_PIXABAY_API_KEY=${AVF_PIXABAY_API_KEY:-56515038-180ae2cbb9fdbd51f8ccb3806},"
if [ -n "${AVF_GOOGLE_CLIENT_ID:-}" ]; then OAUTH_ENV_VARS+="AVF_GOOGLE_CLIENT_ID=${AVF_GOOGLE_CLIENT_ID},"; fi
if [ -n "${AVF_GOOGLE_CLIENT_SECRET:-}" ]; then OAUTH_ENV_VARS+="AVF_GOOGLE_CLIENT_SECRET=${AVF_GOOGLE_CLIENT_SECRET},"; fi
if [ -n "${AVF_GOOGLE_CLIENT_ID_2:-}" ]; then OAUTH_ENV_VARS+="AVF_GOOGLE_CLIENT_ID_2=${AVF_GOOGLE_CLIENT_ID_2},"; fi
if [ -n "${AVF_GOOGLE_CLIENT_SECRET_2:-}" ]; then OAUTH_ENV_VARS+="AVF_GOOGLE_CLIENT_SECRET_2=${AVF_GOOGLE_CLIENT_SECRET_2},"; fi

gcloud run jobs create "${JOB_NAME}" \
    --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/cloud-run-source-deploy/${SERVICE_NAME}:latest" \
    --region="${REGION}" \
    --memory=4Gi \
    --cpu=2 \
    --task-timeout=1800 \
    --max-retries=2 \
    --set-secrets="AVF_OPENAI_API_KEY=groq-api-key:latest,AVF_OPENAI_API_KEY_BACKUP=groq-api-key-backup:latest" \
    --update-env-vars="\
AVF_ENVIRONMENT=production,\
AVF_CONTAINER_MODE=true,\
AVF_LLM_PROVIDER=openai,\
AVF_OPENAI_BASE_URL=https://api.groq.com/openai/v1,\
AVF_OPENAI_DEFAULT_MODEL=llama-3.3-70b-versatile,\
AVF_LLM_TEMPERATURE=0.7,\
AVF_LLM_MAX_TOKENS=8192,\
AVF_STORAGE_PROVIDER=gcs,\
AVF_GCS_BUCKET_NAME=${GCS_BUCKET},\
${OAUTH_ENV_VARS}\
AVF_DATA_DIR=/tmp/data,\
AVF_SESSIONS_DIR=/tmp/sessions,\
AVF_OUTPUT_DIR=/tmp/output,\
AVF_TEMP_DIR=/tmp/temp,\
AVF_LOGS_DIR=/tmp/logs,\
JOB_STYLE=comedy,\
JOB_DURATION=60,\
JOB_LANGUAGE=hinglish,\
JOB_PUBLISH=true,\
JOB_PLATFORMS=youtube" \
    --command="python" \
    --args="run_job.py"

echo ""
echo "=== Cloud Run Job created ==="

PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")

# Schedule daily execution via Cloud Scheduler
echo "=== Creating/Updating Cloud Scheduler ==="
gcloud scheduler jobs delete "${SCHEDULER_NAME}" --location="${REGION}" --quiet 2>/dev/null || true

gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
    --location="${REGION}" \
    --schedule="0 6 * * *" \
    --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB_NAME}:run" \
    --http-method=POST \
    --oauth-service-account-email="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --description="Daily AutoVideoFactory pipeline run"

echo "Scheduler created: runs daily at 06:00 UTC"
echo ""

echo "=========================================="
echo "  JOB DEPLOYMENT COMPLETE!"
echo "=========================================="
echo ""
echo "Test the job manually:"
echo "  gcloud run jobs execute ${JOB_NAME} --region=${REGION}"
echo ""
echo "View job logs:"
echo "  gcloud logging read \"resource.type=cloud_run_job AND resource.labels.job_name=${JOB_NAME}\" --limit 20"
echo ""
echo "To update job env vars (e.g., change topic style):"
echo "  gcloud run jobs update ${JOB_NAME} --region=${REGION} --update-env-vars=JOB_STYLE=story"
echo ""
echo "To trigger immediately for testing:"
echo "  curl -X POST https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB_NAME}:run \\"
echo "    -H \"Authorization: Bearer \$(gcloud auth print-access-token)\" \\"
echo "    -H \"Content-Type: application/json\""
