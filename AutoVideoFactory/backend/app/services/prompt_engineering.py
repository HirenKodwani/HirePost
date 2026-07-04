from __future__ import annotations

import re
from typing import Any, Optional

from ..services.llm_client import get_llm_client
from ..core.logging import get_logger

logger = get_logger("autovideofactory.services.prompt")


class PromptEngineeringService:
    def __init__(self) -> None:
        self._llm = get_llm_client()

    async def generate_image_prompt(self, scene_description: str, style: Optional[str] = None) -> str:
        style_hint = f" in {style} style" if style else ""
        prompt = f"""Generate a detailed image generation prompt for this scene description:
'{scene_description}'
Create a prompt suitable for Stable Diffusion / Midjourney{style_hint}.
Focus on visual details, lighting, composition, and mood.
Keep it under 200 words."""
        return await self._llm.generate(prompt, system_prompt="You are an expert prompt engineer for AI image generation.")

    async def generate_video_prompt(self, scene_description: str, duration: float = 5.0) -> str:
        prompt = f"""Generate a video generation prompt for a {duration}-second clip:
Scene: {scene_description}
Include: motion description, camera movement, visual style, mood.
Suitable for text-to-video AI models."""
        return await self._llm.generate(prompt, system_prompt="You are an expert at creating video generation prompts.")

    async def generate_script(self, topic: str, research_data: dict[str, Any], duration_seconds: float = 60.0, style: str = "comedy") -> str:
        word_limit = int(duration_seconds * 2.5)
        style_guide = {
            "comedy": "Funny, witty, roast-style with punchlines and humorous analogies.",
            "story": "Storytelling format with narrative arc, characters, and a twist or moral at the end.",
            "commentary": "Opinionated hot take with strong point of view. Edgy, controversial, relatable.",
        }
        style_desc = style_guide.get(style, style_guide["comedy"])
        prompt = f"""Write a {style} voiceover script for a short video about: {topic}

Research context: {research_data.get('summary', '')}
Key points to cover: {', '.join(research_data.get('key_points', []))}

Style: {style_desc}

LANGUAGE RULES:
- Write in Hinglish: Hindi script (Devanagari) for Hindi words, English for English words
- Mix naturally like Indian youth speak: "Yaar, yeh AI tools actually bohot crazy hain"
- Use Hindi phrases: "bohot", "yaar", "dekho", "karo", "aisa", "waisa", "chalo", "accha"
- Keep sentences short and punchy for short-form video
- Every 8-10 seconds should have a new thought or punchline

STRUCTURE (exactly 4 parts):
1. HOOK (first 3 seconds): Funny/intriguing opening that grabs attention
2. BODY (middle 40 seconds): Main content with 2-3 points, each with a joke or observation
3. CLIMAX (10 seconds): Strongest punchline or reveal
4. CTA (last 5 seconds): "Agar acha laga to like karo aur subscribe karo!"

FORMAT: Return ONLY the spoken words. No labels, no stage directions, no explanations. Just pure narration text.
Target: exactly {word_limit} words for {duration_seconds}s duration."""
        return await self._llm.generate(prompt, system_prompt="You write viral Hinglish short-video scripts in Devanagari Hindi + English mix. Natural, funny, conversational. Return ONLY the spoken script.")

    async def optimize_prompt(self, prompt: str, target_provider: str) -> str:
        prompt_text = f"""Optimize this prompt for {target_provider}:
'{prompt}'
Make it more effective for {target_provider}'s AI model specifically.
Add relevant keywords, improve clarity, ensure best results."""
        return await self._llm.generate(prompt_text, system_prompt="You are an AI prompt optimization expert.")

    async def generate_hashtags(self, topic: str, count: int = 15) -> list[str]:
        prompt = f"""Generate {count} trending hashtags for a YouTube video about: {topic}
Mix of broad and niche hashtags. Include some Hindi/Indian audience hashtags.
Return as comma-separated list. Example: viral, trending, funny, comedy, hindivideo, india, tech"""
        result = await self._llm.generate(prompt, system_prompt="You are a social media hashtag strategist for Indian YouTube audience.")
        return [h.strip().lstrip("#") for h in result.replace("\n", ",").split(",") if h.strip()]

    async def generate_title(self, topic: str, platform: str = "youtube") -> str:
        prompt = f"""Generate an attention-grabbing title for a {platform} video about: {topic}
Make it curiosity-driven, under 100 characters, optimized for {platform} algorithm.
Use trending keywords and numbers. Make it clickbaity but honest.
Style: Funny/comedy/story commentary tone.
Return ONLY the title text. No quotes, no markdown, no explanation."""
        raw = await self._llm.generate(prompt, system_prompt="You are a viral content title expert for Indian YouTube audience. Return only the title text.")
        cleaned = raw.strip()
        cleaned = re.sub(r'^["\'`#*_]+', '', cleaned)
        cleaned = re.sub(r'["\'`#*_]+$', '', cleaned)
        cleaned = re.sub(r'^(Here\'s|Here is|Try:|Title:|Suggested title:)[:\s]*', '', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.split('\n')[0].strip()
        cleaned = re.sub(r'[^\x00-\x7F]+', '', cleaned)
        cleaned = cleaned.strip().strip('"').strip("'").strip()
        max_len = 95
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len].rsplit(' ', 1)[0] + '...'
        return cleaned or f"Top {topic} Tips"
