param(
    [Parameter(Mandatory)]
    [string]$ProjectId,

    [Parameter(Mandatory)]
    [string]$Region = "us-central1",

    [Parameter(Mandatory)]
    [string]$CloudSqlConnection,

    [Parameter(Mandatory)]
    [string]$DbPassword,

    [Parameter(Mandatory)]
    [string]$GroqApiKey,

    [string]$GcsBucketName = "autovideofactory-$ProjectId",

    [string]$ServiceAccount = "",
    
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"

# Set project
gcloud config set project $ProjectId

# Enable required APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com sqladmin.googleapis.com storage.googleapis.com secretmanager.googleapis.com

# Create GCS bucket if needed
if (-not (gcloud storage buckets describe "gs://$GcsBucketName" 2>$null)) {
    gcloud storage buckets create "gs://$GcsBucketName" --location=$Region
}

# Store Groq API key in Secret Manager
gcloud secrets describe groq-api-key 2>$null
if ($LASTEXITCODE -ne 0) {
    echo $GroqApiKey | gcloud secrets create groq-api-key --data-file=-
}

# Build and push Docker image
if (-not $NoBuild) {
    $ImageName = "$Region-docker.pkg.dev/$ProjectId/cloud-run-source-deploy/autovideofactory:$(git rev-parse --short HEAD)"
    docker build -t $ImageName -f docker/Dockerfile.cloudrun .
    docker push $ImageName
}
else {
    $ImageName = "$Region-docker.pkg.dev/$ProjectId/cloud-run-source-deploy/autovideofactory:latest"
}

# Determine service account
if (-not $ServiceAccount) {
    $ServiceAccount = "$ProjectId-compute@developer.gserviceaccount.com"
}

# Deploy to Cloud Run
gcloud run deploy autovideofactory `
    --image=$ImageName `
    --region=$Region `
    --platform=managed `
    --allow-unauthenticated `
    --memory=4Gi `
    --cpu=2 `
    --timeout=600 `
    --set-env-vars="AVF_ENVIRONMENT=production,AVF_DEBUG=false,AVF_CONTAINER_MODE=true,AVF_LLM_PROVIDER=openai,AVF_OPENAI_BASE_URL=https://api.groq.com/openai/v1,AVF_OPENAI_DEFAULT_MODEL=llama-3.3-70b-versatile,AVF_LLM_TEMPERATURE=0.7,AVF_LLM_MAX_TOKENS=8192,AVF_STORAGE_PROVIDER=gcs,AVF_GCS_BUCKET_NAME=$GcsBucketName,AVF_DATABASE_URL=postgresql+asyncpg://autovideofactory:${DbPassword}@//cloudsql/${CloudSqlConnection}/autovideofactory" `
    --set-secrets="AVF_OPENAI_API_KEY=groq-api-key:latest" `
    --add-cloudsql-instances=$CloudSqlConnection `
    --service-account=$ServiceAccount `
    --update-env-vars="AVF_GOOGLE_REDIRECT_URI=https://autovideofactory-$(Get-Random -Maximum 999999)-$Region.a.run.app/api/v1/auth/youtube/callback"

Write-Output "`n=== Deployment URL ==="
$url = gcloud run services describe autovideofactory --region=$Region --format="value(status.url)" 2>$null
Write-Output "Service URL: $url"

Write-Output "`n=== Next Steps ==="
Write-Output "1. Add this callback URL to your Google Cloud Console OAuth credentials:"
Write-Output "   https://console.cloud.google.com/apis/credentials"
Write-Output "2. Visit $url/api/v1/auth/youtube/login for primary YouTube auth"
Write-Output "3. Visit $url/api/v1/auth/youtube/login?oauth_config=secondary for second channel"
Write-Output "4. Set AVF_PIXABAY_API_KEY via:"
Write-Output "   gcloud run services update autovideofactory --region=$Region --update-env-vars=AVF_PIXABAY_API_KEY=your_key"
