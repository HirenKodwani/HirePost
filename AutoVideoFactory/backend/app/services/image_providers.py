from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Any, Optional

import httpx
import urllib.parse

from ..core.config import settings
from ..core.exceptions import ProviderError
from ..core.logging import get_logger

logger = get_logger("autovideofactory.services.image_providers")


class ImageGenerationProvider(ABC):
    provider_name: str = "base"

    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        ...

    @abstractmethod
    async def generate_variation(self, image_path: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        ...


class PollinationsProvider(ImageGenerationProvider):
    provider_name = "pollinations"

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        try:
            width = kwargs.get("width", 1024)
            height = kwargs.get("height", 1024)
            visual_style = kwargs.get("visual_style", "cinematic")
            enhanced = f"{prompt}, {visual_style}, photorealistic, 4k, highly detailed, dramatic lighting, sharp focus"
            url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(enhanced[:400])}?width={width}&height={height}&nologo=true&enhance=true"
            return {"url": url, "provider": "pollinations", "prompt": prompt}
        except Exception as e:
            raise ProviderError(f"Pollinations failed: {e}") from e

    async def generate_variation(self, image_path: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return await self.generate(prompt, **kwargs)


class PixabayImageProvider(ImageGenerationProvider):
    provider_name = "pixabay_image"

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        api_key = settings.pixabay_api_key
        if not api_key:
            raise ProviderError("Pixabay API key not configured", provider_name="pixabay_image")
        query = urllib.parse.quote(prompt[:100])
        orientation = kwargs.get("orientation", "vertical")
        orient_param = "vertical" if orientation in ("portrait", "vertical") else "horizontal"
        url = f"https://pixabay.com/api/?key={api_key}&q={query}&orientation={orient_param}&per_page=20&safesearch=true"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            if resp.status_code == 400:
                logger.error(
                    "Pixabay API returned 400 Bad Request. "
                    "Your API key appears invalid or malformed. "
                    "Get a valid free key at: https://pixabay.com/api/docs/"
                )
                raise ProviderError(
                    "Pixabay API key invalid. Get a free key at https://pixabay.com/api/docs/",
                    provider_name="pixabay_image",
                )
            resp.raise_for_status()
            data = resp.json()
        hits = data.get("hits", [])
        if hits:
            chosen = random.choice(hits)
            img_url = chosen.get("largeImageURL", chosen.get("webformatURL", ""))
            logger.info(f"Pixabay image found: {img_url[:80]}...")
            return {"url": img_url, "provider": "pixabay_image", "prompt": prompt}
        logger.warning(f"Pixabay no images for: {prompt[:40]}")
        return {"url": "", "provider": "pixabay_image", "prompt": prompt}

    async def generate_variation(self, image_path: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return await self.generate(prompt, **kwargs)


class PixabayVideoProvider(ImageGenerationProvider):
    provider_name = "pixabay_video"

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        api_key = settings.pixabay_api_key
        if not api_key:
            raise ProviderError("Pixabay API key not configured", provider_name="pixabay_video")
        query = urllib.parse.quote(prompt[:100])
        orientation = kwargs.get("orientation", "vertical")
        orient_param = "vertical" if orientation in ("portrait", "vertical") else "horizontal"
        min_height = kwargs.get("min_height", 720)
        url = f"https://pixabay.com/api/videos/?key={api_key}&q={query}&orientation={orient_param}&min_height={min_height}&per_page=20&safesearch=true"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            if resp.status_code == 400:
                logger.error(
                    "Pixabay API returned 400 Bad Request. "
                    "Your API key appears invalid or malformed. "
                    "Get a valid free key at: https://pixabay.com/api/docs/"
                )
                raise ProviderError(
                    "Pixabay API key invalid. Get a free key at https://pixabay.com/api/docs/",
                    provider_name="pixabay_video",
                )
            resp.raise_for_status()
            data = resp.json()
        hits = data.get("hits", [])
        if hits:
            chosen = random.choice(hits)
            video_src = chosen.get("videos", {})
            for quality in ("large", "medium", "small"):
                rendition = video_src.get(quality)
                if rendition and rendition.get("url"):
                    vid_url = rendition["url"]
                    duration = chosen.get("duration", 10)
                    logger.info(f"Pixabay video found: {vid_url[:80]}... ({duration}s)")
                    return {
                        "url": vid_url,
                        "provider": "pixabay_video",
                        "prompt": prompt,
                        "duration": duration,
                        "width": rendition.get("width", 0),
                        "height": rendition.get("height", 0),
                    }
        logger.warning(f"Pixabay no videos for: {prompt[:40]}")
        return {"url": "", "provider": "pixabay_video", "prompt": prompt, "duration": 0}

    async def generate_variation(self, image_path: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return await self.generate(prompt, **kwargs)


class StableDiffusionProvider(ImageGenerationProvider):
    provider_name = "stability"

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        logger.info(f"SD generating: {prompt[:50]}...")
        return {"provider": "stability", "prompt": prompt, "status": "mock"}

    async def generate_variation(self, image_path: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return await self.generate(prompt, **kwargs)


class ImageProviderRegistry:
    _providers: dict[str, type[ImageGenerationProvider]] = {}

    @classmethod
    def register(cls, name: str, provider_class: type[ImageGenerationProvider]) -> None:
        cls._providers[name] = provider_class

    @classmethod
    def get(cls, name: str) -> ImageGenerationProvider:
        provider_class = cls._providers.get(name)
        if not provider_class:
            raise ProviderError(f"Unknown image provider: {name}", provider_name=name)
        return provider_class()

    @classmethod
    def list_providers(cls) -> list[dict[str, str]]:
        return [{"name": n, "class": p.__name__} for n, p in cls._providers.items()]


ImageProviderRegistry.register("pollinations", PollinationsProvider)
ImageProviderRegistry.register("pixabay_image", PixabayImageProvider)
ImageProviderRegistry.register("pixabay_video", PixabayVideoProvider)
ImageProviderRegistry.register("stability", StableDiffusionProvider)
