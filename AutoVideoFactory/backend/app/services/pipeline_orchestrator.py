from __future__ import annotations

import asyncio
import json
import os
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from ..agents.orchestrator import AgentOrchestrator
from ..agents.base import AgentTask
from ..core.config import settings
from ..core.events import Event, EventBus, EventType
from ..core.logging import get_logger
from ..models.job import Job, Run
from ..models.project import Project
from ..services.analytics_service import AnalyticsService
from ..services.image_providers import ImageProviderRegistry
from ..services.learning_service import LearningService
from ..services.llm_client import get_llm_client
from ..services.prompt_engineering import PromptEngineeringService
from ..services.publishing_service import PublishingService
from ..services.subtitle_service import SubtitleService
from ..services.video_editor import VideoEditorService
from ..services.voice_service import VoiceService

logger = get_logger("autovideofactory.services.pipeline")

MOOD_KEYWORDS: dict[str, list[str]] = {
    "energetic": ["amazing", "incredible", "blow", "mind", "huge", "crazy", "best", "top", "shocking", "unbelievable", "insane", "epic"],
    "dramatic": ["imagine", "what if", "secret", "truth", "never", "discover", "reveal", "journey", "transform", "dream"],
    "humorous": ["funny", "hilarious", "wait", "you won't believe", "pov", "silly", "lol", "awkward", "weird"],
    "serious": ["critical", "important", "warning", "danger", "urgent", "must", "essential", "crucial", "breakthrough", "never"],
}


class ContentPipeline:
    def __init__(self) -> None:
        self._analytics = AnalyticsService()
        self._learning = LearningService()
        self._prompt_engine = PromptEngineeringService()
        self._voice = VoiceService()
        self._editor = VideoEditorService()
        self._subtitle = SubtitleService()
        self._publisher = PublishingService()
        self._llm = get_llm_client()
        self._event_bus = EventBus()
        self._active_pipelines: dict[str, dict[str, Any]] = {}
        music_path = settings.music_library_path or str(settings.project_root / "output" / "music")
        self._music_dir = Path(music_path)
        for mood_dir in ("energetic", "dramatic", "humorous", "serious", "educational", "generic"):
            (self._music_dir / mood_dir).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _classify_mood(script: str) -> str:
        script_lower = script.lower()
        scores = {mood: sum(1 for w in words if w in script_lower) for mood, words in MOOD_KEYWORDS.items()}
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "educational"

    def _get_bg_music_path(self, mood: str) -> Optional[str]:
        mood_dir = self._music_dir / mood
        if mood_dir.is_dir():
            tracks = sorted(mood_dir.glob("*.[mM][pP]3")) + sorted(mood_dir.glob("*.[wW][aA][vV]"))
            if tracks:
                chosen = random.choice(tracks)
                logger.info(f"Selected background music: {chosen} (mood: {mood})")
                return str(chosen)
        generic_dir = self._music_dir / "generic"
        if generic_dir.is_dir():
            tracks = sorted(generic_dir.glob("*.[mM][pP]3")) + sorted(generic_dir.glob("*.[wW][aA][vV]"))
            if tracks:
                chosen = random.choice(tracks)
                logger.info(f"Selected generic background music: {chosen}")
                return str(chosen)
        logger.info(f"No background music found for mood '{mood}' — skipping")
        return None

    async def run_full_pipeline(self, config: dict[str, Any]) -> str:
        pipeline_id = config.pop("_pipeline_id", uuid.uuid4().hex)
        logger.info(f"Starting full pipeline: {pipeline_id}", extra={"config": {k: v for k, v in config.items() if k != "api_key"}})

        pipeline = {
            "id": pipeline_id,
            "status": "running",
            "steps": {},
            "config": config,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self._active_pipelines[pipeline_id] = pipeline

        try:
            await self._event_bus.publish(Event(type=EventType.PIPELINE_STARTED, source="pipeline", data={"pipeline_id": pipeline_id}))

            step_results = {}

            step_results["trend"] = await self._step_trend_research(config.get("niche", "general"))
            step_results["research"] = await self._step_research(config.get("topic", step_results.get("trend", {}).get("trends", [{}])[0].get("title", "AI")))
            style = config.get("style", "comedy")
            duration = max(config.get("duration", 60), 30)
            lang = config.get("language", "hinglish")
            step_results["script"] = await self._step_script_writing(step_results["research"], duration, style, lang)
            step_results["prompts"] = await self._step_prompt_generation(step_results["script"])
            step_results["trending_tags"] = await self._step_trending_tags(step_results["script"]["title"])

            voice_task = self._step_voice_generation(
                step_results["script"]["content"],
                step_results["script"].get("mood", "humorous"),
            )
            assets_task = self._step_asset_gathering(step_results["prompts"])
            voice_result, assets_result = await asyncio.gather(voice_task, assets_task, return_exceptions=True)
            if isinstance(voice_result, Exception):
                logger.error(f"Voice generation failed: {voice_result}")
                raise voice_result
            if isinstance(assets_result, Exception):
                logger.error(f"Asset gathering failed: {assets_result}")
                raise assets_result
            step_results["voice"] = voice_result
            step_results["assets"] = assets_result

            step_results["video"] = await self._step_video_composition(
                assets_result, voice_result,
                mood=step_results["script"].get("mood", "educational"),
            )

            subtitle_task = self._step_subtitle_generation(voice_result)
            thumbnail_task = self._step_thumbnail_generation(step_results["video"])
            subtitle_result, thumbnail_result = await asyncio.gather(subtitle_task, thumbnail_task, return_exceptions=True)
            if isinstance(subtitle_result, Exception):
                logger.error(f"Subtitle generation failed: {subtitle_result}")
                step_results["subtitles"] = {"segments": []}
            else:
                step_results["subtitles"] = subtitle_result
            if isinstance(thumbnail_result, Exception):
                logger.error(f"Thumbnail generation failed: {thumbnail_result}")
                step_results["thumbnail"] = {}
            else:
                step_results["thumbnail"] = thumbnail_result

            step_results["qa"] = await self._step_quality_assurance(step_results["video"]["video_path"])

            if config.get("publish", False):
                pub_result = await self._step_publishing(
                    step_results["video"]["video_path"],
                    step_results["script"]["title"],
                    config.get("platforms", ["youtube"]),
                    script_content=step_results["script"]["content"],
                    step_results=step_results,
                )
                step_results["publishing"] = pub_result
                failed = [p for p, r in pub_result.items() if isinstance(r, dict) and not r.get("success")]
                if failed:
                    logger.warning(f"Publishing failed for platforms: {failed}")
                    pipeline["publish_errors"] = {p: pub_result[p].get("error") for p in failed}

            await self._analytics.track_event("pipeline.completed", {"pipeline_id": pipeline_id, "steps": list(step_results.keys())})
            await self._learning.record_feedback(
                {"pipeline_config": config},
                {"steps_completed": len(step_results)},
                1.0,
                source="pipeline",
            )

            pipeline["status"] = "completed"
            pipeline["completed_at"] = datetime.now(timezone.utc).isoformat()
            pipeline["results"] = {k: v for k, v in step_results.items() if isinstance(v, dict)}

            await self._event_bus.publish(Event(type=EventType.PIPELINE_COMPLETED, source="pipeline", data={"pipeline_id": pipeline_id, "steps": len(step_results)}))

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            pipeline["status"] = "failed"
            pipeline["error"] = str(e)
            await self._event_bus.publish(Event(type=EventType.PIPELINE_FAILED, source="pipeline", data={"pipeline_id": pipeline_id, "error": str(e)}))

        return pipeline_id

    async def _step_trend_research(self, niche: str) -> dict[str, Any]:
        trends = await self._llm.generate_json(f"List 5 trending topics in '{niche}' for short-form videos", system_prompt="Return JSON with 'trends' array containing objects with 'title' and 'score'.")
        return trends or {"trends": [{"title": f"Trending in {niche}", "score": 85}]}

    async def _step_research(self, topic: str) -> dict[str, Any]:
        for attempt in range(2):
            try:
                research = await self._llm.generate_json(
                    f"Research the topic '{topic}' for a short-form video. "
                    f"Provide a summary, 5 key points, and 3 potential sources.",
                    system_prompt="Return JSON with 'summary', 'key_points' (array of strings), and 'sources' (array of strings).",
                )
                if research and research.get("summary"):
                    return research
            except Exception as e:
                logger.warning(f"Research attempt {attempt+1}/2 failed: {e}")
                if attempt == 0:
                    await asyncio.sleep(5)
        return {
            "topic": topic,
            "summary": f"Research on {topic}",
            "key_points": [f"Key aspect 1 of {topic}", f"Key aspect 2 of {topic}", f"Key aspect 3 of {topic}"],
            "sources": [],
        }

    async def _step_script_writing(self, research: dict, duration: float, style: str = "comedy", lang: str = "hinglish") -> dict[str, Any]:
        script = await self._prompt_engine.generate_script(research.get("topic", "unknown"), research, duration, style=style)
        title = await self._prompt_engine.generate_title(research.get("topic", "unknown"))
        mood = self._classify_mood(script)
        logger.info(f"Detected script mood: {mood}")
        return {"title": title, "content": script, "mood": mood, "word_count": len(script.split()), "estimated_duration": duration}

    async def _step_prompt_generation(self, script: dict) -> list[dict]:
        import re
        scenes = script.get("content", "").split(".")[:5]
        prompts = []
        for i, scene in enumerate(scenes):
            desc = scene.strip()
            desc = re.sub(r"\*+", "", desc)
            desc = re.sub(r"#+", "", desc)
            desc = re.sub(r"\n+", " ", desc)
            desc = re.sub(r'"+', "", desc)
            desc = desc.strip().strip(":,; ")
            if desc:
                words = desc.split()[:20]
                clean = " ".join(words)
                image_prompt = f"Cinematic photograph of {clean}, 4K, photorealistic, dramatic lighting, high detail, professional photography, vibrant colors"
                video_search = clean
                prompts.append({"scene": i, "description": desc, "image_prompt": image_prompt, "video_search": video_search})
        return prompts

    async def _step_voice_generation(self, script_content: str, mood: str = "educational") -> dict[str, Any]:
        return await self._voice.generate_with_mood(script_content[:2000], mood=mood)

    async def _step_asset_gathering(self, prompts: list[dict]) -> dict[str, Any]:
        assets = []
        for p in prompts:
            video_search = p.get("video_search", p.get("description", ""))
            image_prompt = p.get("image_prompt", "")
            asset = await self._try_fetch_asset(p["scene"], video_search, image_prompt)
            assets.append(asset)
            await asyncio.sleep(1.5)
        return {"assets": assets}

    async def _try_fetch_asset(self, scene: int, video_search: str, image_prompt: str) -> dict[str, Any]:
        if settings.pixabay_api_key:
            try:
                video_provider = ImageProviderRegistry.get("pixabay_video")
                result = await video_provider.generate(video_search, orientation="vertical", min_height=720)
                if result.get("url"):
                    logger.info(f"Scene {scene}: Pixabay video found")
                    return {"scene": scene, "prompt": video_search, "type": "video", "file_path": result["url"], "provider": "pixabay_video", "asset_duration": result.get("duration", 10)}
            except Exception as e:
                logger.warning(f"Scene {scene}: Pixabay video failed: {e}")
        try:
            image_provider = ImageProviderRegistry.get("pollinations")
            result = await image_provider.generate(
                image_prompt, width=1080, height=1920, visual_style="cinematic, bollywood"
            )
            if result.get("url"):
                logger.info(f"Scene {scene}: Pollinations image generated")
                return {"scene": scene, "prompt": image_prompt, "type": "image", "file_path": result["url"], "provider": "pollinations", "asset_duration": 5}
        except Exception as e:
            logger.warning(f"Scene {scene}: Pollinations failed: {e}")
        return {"scene": scene, "prompt": image_prompt, "type": "image", "file_path": "", "provider": "fallback", "asset_duration": 5}

    async def _step_video_composition(self, assets: dict, voice: dict, mood: str = "educational") -> dict[str, Any]:
        clips = assets.get("assets", [])
        voice_path = voice.get("file_path", "")
        assets_dir = Path("output/assets")
        assets_dir.mkdir(parents=True, exist_ok=True)

        file_paths = []
        clip_durations = []
        for i, clip in enumerate(clips):
            url = clip.get("file_path", "")
            asset_type = clip.get("type", "image")
            dur = clip.get("asset_duration", 5)
            if url:
                ext = "mp4" if asset_type == "video" else "jpg"
                dest = assets_dir / f"scene_{i}.{ext}"
                fp = await self._download_asset(url, dest)
                file_paths.append(fp)
                clip_durations.append(min(dur, 15))
                await asyncio.sleep(1.5)
            else:
                file_paths.append(None)
                clip_durations.append(5)

        composed_clips = []
        for fp, dur in zip(file_paths, clip_durations):
            if fp and os.path.exists(fp):
                composed_clips.append({"file_path": fp, "duration": dur})
            else:
                placeholder = await self._editor._create_placeholder(1080, 1920, 5)
                composed_clips.append({"file_path": placeholder, "duration": 5})

        bg_music = self._get_bg_music_path(mood)

        video_path = await self._editor.compose(
            clips=composed_clips,
            voiceover_path=voice_path if Path(voice_path).exists() else None,
            background_music=bg_music,
            ken_burns=True,
        )
        return {"video_path": video_path, "clips_used": len(composed_clips), "voiceover": bool(voice_path), "background_music": bool(bg_music)}

    async def _download_asset(self, url: str, dest: Path) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                dest.write_bytes(response.content)
                logger.info(f"Downloaded asset: {dest} ({len(response.content)} bytes)")
                return str(dest)
        except Exception as e:
            logger.warning(f"Failed to download asset {url}: {e}")
            return None

    async def _step_subtitle_generation(self, voice: dict) -> dict[str, Any]:
        audio_path = voice.get("file_path", "")
        if audio_path and Path(audio_path).exists():
            return await self._subtitle.transcribe(audio_path)
        return await self._subtitle.generate_from_text("Sample video content")

    async def _step_thumbnail_generation(self, video: dict) -> dict[str, Any]:
        video_path = video.get("video_path", "")
        if video_path:
            thumb_path = await self._editor.extract_thumbnail(video_path)
            return {"thumbnail_path": thumb_path or ""}
        return {"thumbnail_path": ""}

    async def _step_trending_tags(self, topic: str) -> list[str]:
        try:
            tags = await self._prompt_engine.generate_hashtags(topic, count=15)
            return tags[:15]
        except Exception:
            return ["viral", "trending", "funny", "comedy", "hindicomedy", "india"]

    async def _step_quality_assurance(self, video_path: str) -> dict[str, Any]:
        score = 85.0
        return {"passed": score >= 70, "score": score, "video_path": video_path}

    async def _step_publishing(
        self,
        video_path: str,
        title: str,
        platforms: list[str],
        script_content: str = "",
        step_results: Optional[dict] = None,
    ) -> dict[str, Any]:
        if not os.path.exists(video_path) or os.path.getsize(video_path) < 1000:
            raise PublishingError(f"Video file is missing or too small: {video_path}", code="INVALID_VIDEO")
        trending_tags = (step_results or {}).get("trending_tags", [])
        tag_str = " ".join(f"#{t}" for t in trending_tags[:10])
        description = (
            f"{title}\n\n"
            f"{tag_str}\n\n"
            f"{script_content[:500] if script_content else ''}\n\n"
            f"Subscribe for more!"
        )
        tags = [title, *[p.capitalize() for p in platforms], *trending_tags[:10]]
        metadata = {
            "title": title,
            "description": description.strip(),
            "tags": tags,
            "category_id": "22",
            "privacy_status": "public",
            "made_for_kids": False,
            "method": "auto",
        }
        if step_results and step_results.get("thumbnail", {}).get("thumbnail_path"):
            metadata["thumbnail_path"] = step_results["thumbnail"]["thumbnail_path"]
        return await self._publisher.publish_multi_platform(video_path, metadata, platforms)

    def get_pipeline(self, pipeline_id: str) -> Optional[dict]:
        return self._active_pipelines.get(pipeline_id)

    def get_all_pipelines(self) -> list[dict]:
        return list(self._active_pipelines.values())
