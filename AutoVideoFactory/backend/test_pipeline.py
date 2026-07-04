import asyncio, sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ["AVF_ENVIRONMENT"] = "development"

from app.services.pipeline_orchestrator import ContentPipeline

async def main():
    pipe = ContentPipeline()
    pid = await pipe.run_full_pipeline({
        "topic": "5 AI tools for productivity in 2026",
        "niche": "artificial intelligence",
        "duration": 30,
        "style": "fast-paced",
    })
    result = pipe.get_pipeline(pid)
    print(f"Pipeline: {pid}")
    print(f"Status: {result.get('status')}")
    if result.get("error"):
        print(f"Error: {result['error']}")
    print(f"Results: {list(result.get('results', {}).keys())}")
    video = result.get("results", {}).get("video", {})
    if video:
        print(f"Video: {video.get('video_path')}")

asyncio.run(main())
