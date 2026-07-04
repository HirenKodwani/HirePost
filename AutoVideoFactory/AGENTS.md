# AutoVideoFactory — Agent Memory

## LLM Provider
- **Current**: Groq (`llama-3.3-70b-versatile`) via OpenAI-compatible API
- `.env` config: `AVF_LLM_PROVIDER=openai`, `AVF_OPENAI_BASE_URL=https://api.groq.com/openai/v1`
- API key: Stored in `.env` as `AVF_OPENAI_API_KEY`; for Cloud Run, stored in Secret Manager as `groq-api-key`
- Previously used: Ollama (`llama3.2:3b` local) — deprecated

## YouTube Channels
- **Primary**: OAuth client `default` (`129756332718-...`)
- **Secondary**: OAuth client `secondary` (`398847450753-...`)
- Auth routes: `/api/v1/auth/youtube/login` (primary), `/api/v1/auth/youtube/login?oauth_config=secondary`
- Both OAuth clients must have the redirect URI registered in Google Cloud Console

## Cloud Deployment
- **Target**: GCP Cloud Run (serverless containers)
- **Dockerfile**: `docker/Dockerfile.cloudrun` — optimized, no Playwright, healthcheck included
- **Build config**: `cloudbuild.yaml` — Cloud Build + Cloud Run deploy
- **Deploy scripts**: `scripts/deploy.ps1` (Windows), `scripts/deploy.sh` (Cloud Shell/Linux)
- **Database**: Cloud SQL PostgreSQL (asyncpg) — `AVF_DATABASE_URL=postgresql+asyncpg://...`
- **Storage**: GCS bucket — controlled by `AVF_STORAGE_PROVIDER=gcs`
- **CLI**: gcloud required for deployment. Run from Google Cloud Shell or local install

## Recent Improvements (Jul 2026)
- **LLM**: Migrated from Ollama (`llama3.2:3b`) → Groq (`llama-3.3-70b-versatile`). ~1.3s response time, 12k TPM rate limit
- **Bugfix**: `OpenAIClient.generate_json` now passes `response_format` to API (was silently dropped)
- **Voice**: Added `comedy`, `story`, `commentary`, `mystery` moods with tuned rate/pitch. Actual duration now measured via ffprobe
- **Pollinations**: Enhanced prompts with `cinematic, photorealistic` style suffixes, portrait res (1080x1920), `nologo=true`
- **Pixabay**: 400 Bad Request now gives a clear error with link to get a free API key
- **OAuth redirect**: Pulled from `settings.google_redirect_uri` (env `AVF_GOOGLE_REDIRECT_URI`), configurable per deployment
- **Cloud Run**: New `Dockerfile.cloudrun` with healthcheck, `asyncpg` for PostgreSQL, `google-cloud-storage` for GCS

## Known Issues
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
| `backend/.env` | Local config (secrets included for local dev) |
| `docker/Dockerfile.cloudrun` | Cloud Run optimized container |
| `scripts/deploy.ps1` | Windows deployment script |
| `scripts/deploy.sh` | Cloud Shell deployment script |
| `cloudbuild.yaml` | Cloud Build CI/CD config |
