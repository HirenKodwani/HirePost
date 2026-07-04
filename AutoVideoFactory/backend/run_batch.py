import asyncio, sys, os
sys.path.insert(0, ".")
from app.services.pipeline_orchestrator import ContentPipeline

TOPICS = [
    {"topic": "Why your phone is secretly spying on you", "niche": "tech comedy", "style": "comedy", "duration": 60},
    {"topic": "Everything wrong with Indian traffic", "niche": "comedy commentary", "style": "commentary", "duration": 60},
    {"topic": "why do guys think they can fix everything", "niche": "relationship comedy", "style": "comedy", "duration": 60},
    {"topic": "why parents think video games are the devil", "niche": "comedy", "style": "comedy", "duration": 60},
    {"topic": "things girls do that guys will never understand", "niche": "comedy", "style": "comedy", "duration": 60},
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
            r = pipe.get_pipeline(pid)
            pub = r.get("results",{}).get("publishing",{})
            yt = pub.get("youtube",{})
            vid_url = yt.get("video_url", "")
            print(f"  Status: {r['status']}")
            print(f"  YouTube: {vid_url}")
            results.append({"topic": cfg["topic"], "status": r["status"], "url": vid_url})
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({"topic": cfg["topic"], "status": "failed", "error": str(e)})

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        print(f"  {r['topic']}: {r['status']} - {r.get('url', 'N/A')}")

asyncio.run(main())
