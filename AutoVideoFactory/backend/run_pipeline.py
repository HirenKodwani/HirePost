import asyncio, sys, os
sys.path.insert(0, ".")
from app.services.pipeline_orchestrator import ContentPipeline

TOPICS = [
    {
        "topic": "Why your phone is secretly spying on you",
        "niche": "tech comedy",
        "style": "comedy",
        "duration": 60,
    },
    {
        "topic": "The real reason Bollywood movies are 3 hours long",
        "niche": "entertainment comedy",
        "style": "comedy",
        "duration": 60,
    },
    {
        "topic": "How I wasted 10 years of my life on social media",
        "niche": "story commentary",
        "style": "story",
        "duration": 90,
    },
    {
        "topic": "Everything wrong with Indian traffic",
        "niche": "comedy commentary",
        "style": "commentary",
        "duration": 60,
    },
    {
        "topic": "Why parents think video games are the devil",
        "niche": "comedy",
        "style": "comedy",
        "duration": 60,
    },
]

async def main():
    pipe = ContentPipeline()
    results = []
    for i, cfg in enumerate(TOPICS):
        print(f"\n{'='*60}")
        print(f"Pipeline {i+1}/{len(TOPICS)}: {cfg['topic']}")
        print(f"{'='*60}")
        try:
            pid = await pipe.run_full_pipeline({
                "topic": cfg["topic"],
                "niche": cfg["niche"],
                "duration": cfg["duration"],
                "style": cfg["style"],
                "publish": True,
                "platforms": ["youtube"],
            })
            result = pipe.get_pipeline(pid)
            status = result.get("status", "unknown")
            video = result.get("results",{}).get("video",{}).get("video_path","")
            pub = result.get("results",{}).get("publishing",{})
            yt_result = pub.get("youtube", {}) if isinstance(pub, dict) else {}
            vid_url = yt_result.get("video_url", "")
            print(f"  Status: {status}")
            print(f"  Video: {video}")
            print(f"  YouTube: {vid_url}")
            results.append({"topic": cfg["topic"], "status": status, "url": vid_url})
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({"topic": cfg["topic"], "status": "failed", "error": str(e)})

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        print(f"  {r['topic']}: {r['status']} - {r.get('url', 'N/A')}")

asyncio.run(main())
