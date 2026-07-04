import asyncio, os
os.environ.setdefault("AVF_LLM_PROVIDER", "openai")
os.environ.setdefault("AVF_OPENAI_DEFAULT_MODEL", "llama-3.3-70b-versatile")
from app.services.pipeline_orchestrator import ContentPipeline

async def t():
    p = ContentPipeline()
    pid = await p.run_full_pipeline({"topic":"AI productivity tools 2026","niche":"AI","duration":15})
    result = p.get_pipeline(pid)
    assets = result.get("results", {}).get("assets", {})
    print("Status:", result.get("status"))
    if result.get("error"):
        print("Error:", result["error"])
    print("Result keys:", list(result.get("results", {}).keys()))
    for a in assets.get("assets", []):
        print(f"  Scene {a['scene']}: url={a.get('file_path','')[:100]}")
    voice = result.get("results", {}).get("voice", {})
    vp = voice.get("file_path", "")
    print(f"Voice: {vp} exists={os.path.exists(vp)}")
    video = result.get("results", {}).get("video", {})
    print(f"Video: {video.get('video_path','')}")
    import subprocess, json
    subprocess.run([
        "C:\\Users\\ADMIN\\AppData\\Roaming\\Python\\Python314\\site-packages\\imageio_ffmpeg\\binaries\\ffmpeg-win-x86_64-v7.1.exe",
        "-i", video.get("video_path","")
    ], capture_output=True, text=True)

asyncio.run(t())
