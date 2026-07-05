import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings
from app.core.database import DatabaseEngine
from app.core.logging import get_logger
from app.services.pipeline_orchestrator import ContentPipeline
from app.services.youtube_auth import youtube_auth_service

logger = get_logger("autovideofactory.job")

async def main():
    style = os.environ.get("JOB_STYLE", "comedy")
    duration = int(os.environ.get("JOB_DURATION", "60"))
    language = os.environ.get("JOB_LANGUAGE", "hinglish")
    publish = os.environ.get("JOB_PUBLISH", "true").lower() == "true"
    platforms_raw = os.environ.get("JOB_PLATFORMS", "youtube")

    logger.info(f"Starting pipeline job", extra={
        "style": style, "duration": duration,
        "language": language, "publish": publish,
    })

    os.makedirs(settings.data_dir, exist_ok=True)
    await DatabaseEngine.create_all()
    restored = await youtube_auth_service._restore_tokens()
    logger.info(f"Restored {restored} YouTube token(s) from GCS backup")

    pipe = ContentPipeline()
    config = {
        "style": style,
        "duration": duration,
        "language": language,
        "publish": publish,
        "platforms": [p.strip() for p in platforms_raw.split(",")],
    }
    pipeline_id = await pipe.run_full_pipeline(config)
    result = pipe.get_pipeline(pipeline_id)
    status = result.get("status", "unknown")
    logger.info(f"Pipeline {pipeline_id} finished with status: {status}")
    if status == "failed":
        error = result.get("error", "Unknown error")
        logger.error(f"Pipeline failed: {error}")
        sys.exit(1)
    logger.info(f"Pipeline completed successfully")

if __name__ == "__main__":
    asyncio.run(main())
