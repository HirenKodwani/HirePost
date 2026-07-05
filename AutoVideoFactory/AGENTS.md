# AutoVideoFactory — Agent Memory

## LLM Provider
- **Current**: Groq (`llama-3.3-70b-versatile`) via OpenAI-compatible API
- `.env` config: `AVF_LLM_PROVIDER=openai`, `AVF_OPENAI_BASE_URL=https://api.groq.com/openai/v1`
- Primary key: Stored in `.env` as `AVF_OPENAI_API_KEY`; for Cloud Run, stored in Secret Manager as `groq-api-key`
- Backup key (for rotation): Stored as `AVF_OPENAI_API_KEY_BACKUP`; Cloud Run secret `groq-api-key-backup`
- **Key rotation**: `OpenAIClient` round-robins between keys on each `generate()` call; on 429, rotates with 2s delay — effective 24k TPM
- Throttle: 20s minimum between API calls
- Previously used: Ollama (`llama3.2:3b` local) — deprecated

## YouTube Channels
- **Primary**: OAuth client `default` (`129756332718-...`)
- **Secondary**: OAuth client `secondary` (`398847450753-...`)
- Auth routes: `/api/v1/auth/youtube/login` (primary), `/api/v1/auth/youtube/login?oauth_config=secondary`
- Both OAuth clients must have the redirect URI registered in Google Cloud Console

## Cloud Deployment (Free Tier — Jul 2026)
- **Target**: GCP Cloud Run (serverless containers), CPU throttled (no idle cost)
- **Dockerfile**: `docker/Dockerfile.cloudrun` — explicit Docker build via `gcloud builds submit`, avoids Buildpacks
- **Deploy script**: `scripts/deploy.sh` (Cloud Shell/Linux) — preferred for one-command deploy
- **Database**: SQLite via aiosqlite at `AVF_DATA_DIR=/tmp/data` — **no Cloud SQL** (saves ~$10/mo)
- **Storage**: GCS bucket — `AVF_STORAGE_PROVIDER=gcs`, `AVF_GCS_BUCKET_NAME=autovideofactory-{project}`
- **YouTube token persistence**: OAuth refresh tokens backed up to GCS (`youtube_tokens/backup.json`) and auto-restored on startup
- **Pipeline execution**: Cloud Run Jobs (not service background tasks) — CPU always-on, free tier covers 10,000 runs/month, ~300 daily runs
- **Schedule**: Cloud Scheduler triggers pipeline job daily at 06:00 UTC
- **Job script**: `scripts/deploy_job.sh` — sets up Cloud Run Job + Scheduler
- **Job entrypoint**: `backend/run_job.py` — reads config from `JOB_STYLE`, `JOB_DURATION`, `JOB_LANGUAGE`, `JOB_PUBLISH`, `JOB_PLATFORMS` env vars; restores YouTube tokens before running
- **CLI**: gcloud required. Run from Google Cloud Shell

## Recent Improvements (Jul 2026)
- **LLM**: Migrated from Ollama (`llama3.2:3b`) → Groq (`llama-3.3-70b-versatile`). ~1.3s response time, 12k TPM rate limit
- **Bugfix**: `OpenAIClient.generate_json` now passes `response_format` to API (was silently dropped)
- **Voice**: Added `comedy`, `story`, `commentary`, `mystery` moods with tuned rate/pitch. Actual duration now measured via ffprobe
- **Pollinations**: Enhanced prompts with `cinematic, photorealistic` style suffixes, portrait res (1080x1920), `nologo=true`
- **Pixabay**: 400 Bad Request now gives a clear error with link to get a free API key
- **OAuth redirect**: Pulled from `settings.google_redirect_uri` (env `AVF_GOOGLE_REDIRECT_URI`), configurable per deployment
- **Cloud Run**: New `Dockerfile.cloudrun` with healthcheck, `asyncpg` for PostgreSQL, `google-cloud-storage` for GCS

## Known Issues
- **Groq rate limits (12k TPM)**: Primary cause of pipeline failures. Mitigated by key rotation (2 keys × round-robin = 24k effective TPM) + 20s throttle + 15 retries. If both keys hit limit simultaneously, retry backoff kicks in (5-180s).
- **Pixabay**: Working with key `56515038-180ae2cbb9fdbd51f8ccb3806`. 500+ image and video results per query
- **Instagram publisher**: Browser automation works locally but won't run on Cloud Run (no GUI browser)
- **Ollama package uninstalled**: `ollama` pip package removed; project uses httpx directly

## Key Files
| File | Purpose |
|---|---|
| `backend/app/services/llm_client.py` | LLM abstraction (OpenAIClient, OllamaClient) |
| `backend/app/services/prompt_engineering.py` | Script, title, hashtag generation |
| `backend/app/services/pipeline_orchestrator.py` | Full pipeline orchestration |
| `backend/app/services/youtube_auth.py` | Multi-OAuth YouTube auth |
| `backend/app/services/storage_service.py` | Local/GCS storage abstraction |
| `backend/app/services/voice_service.py` | Edge-TTS voice generation (Hindi voices + moods) |
| `backend/app/services/image_providers.py` | Pollinations, Pixabay (image+video), Stable Diffusion |
| `backend/app/core/config.py` | All settings with env prefix `AVF_` |
| `backend/app/main.py` | FastAPI app with SQLite + GCS token restore on startup |
| `backend/.env` | Local config (secrets included for local dev) |
| `docker/Dockerfile.cloudrun` | Cloud Run optimized container |
| `scripts/deploy.sh` | Cloud Shell deployment script (free tier — SQLite, no Cloud SQL) |
| `cloudbuild.yaml` | Cloud Build CI/CD config (legacy, not used by deploy.sh) |
