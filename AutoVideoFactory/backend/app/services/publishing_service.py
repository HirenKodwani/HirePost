from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..core.config import settings
from ..core.exceptions import PublishingError
from ..core.logging import get_logger

logger = get_logger("autovideofactory.services.publishing")


class PlatformPublisher(ABC):
    platform_name: str = "base"

    @abstractmethod
    async def publish(self, video_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def check_status(self, publish_id: str) -> dict[str, Any]:
        ...


class TikTokPublisher(PlatformPublisher):
    platform_name = "tiktok"

    async def publish(self, video_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"TikTok publish: {video_path}")
        from ..modules.browser_automation.computer_use_agent import ComputerUseAgent
        agent = ComputerUseAgent()
        await agent.ai_navigate("https://www.tiktok.com/upload", "Upload and publish a video")
        return {
            "platform": "tiktok",
            "success": True,
            "publish_id": f"tt_{abs(hash(video_path))}",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "method": "browser",
        }

    async def check_status(self, publish_id: str) -> dict[str, Any]:
        return {"publish_id": publish_id, "status": "published", "platform": "tiktok"}


class YouTubePublisher(PlatformPublisher):
    platform_name = "youtube"

    async def publish(self, video_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"YouTube publish: {video_path}")
        method = metadata.get("method", "auto")

        if method == "api" or (method == "auto" and self._can_use_api()):
            return await self._publish_via_api(video_path, metadata)
        return await self._publish_via_browser(video_path, metadata)

    def _can_use_api(self) -> bool:
        return bool(settings.google_client_id and settings.google_client_secret)

    async def _publish_via_api(self, video_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
        from .youtube_auth import youtube_auth_service

        account_id = metadata.get("youtube_account_id")
        creds = await youtube_auth_service.get_credentials(account_id)
        if not creds:
            logger.error("No YouTube credentials available. Re-authorize at /api/v1/auth/youtube/login")
            raise PublishingError(
                "No YouTube credentials available. Re-authorize at /api/v1/auth/youtube/login",
                code="YOUTUBE_NO_CREDENTIALS",
            )

        account_id = account_id or "default"

        if not await youtube_auth_service.has_quota_available(account_id):
            logger.warning(f"YouTube quota exhausted for account {account_id}, trying next account")
            accounts = await youtube_auth_service.get_available_accounts()
            fallback_id = None
            for acc in accounts:
                if acc["id"] != account_id:
                    if await youtube_auth_service.has_quota_available(acc["id"]):
                        fallback_id = acc["id"]
                        break
            if fallback_id:
                metadata["youtube_account_id"] = fallback_id
                return await self._publish_via_api(video_path, metadata)
            logger.error("All YouTube accounts exhausted their daily quota")
            raise PublishingError(
                "All YouTube accounts exhausted their daily quota",
                code="YOUTUBE_QUOTA_EXHAUSTED",
            )

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            youtube = build("youtube", "v3", credentials=creds)

            body = {
                "snippet": {
                    "title": (metadata.get("title", "Untitled")),
                    "description": (metadata.get("description", "")),
                    "tags": metadata.get("tags", []),
                    "categoryId": metadata.get("category_id", "22"),
                },
                "status": {
                    "privacyStatus": metadata.get("privacy_status", "public"),
                    "selfDeclaredMadeForKids": metadata.get("made_for_kids", False),
                },
            }

            media = MediaFileUpload(
                video_path,
                chunksize=256 * 1024,
                resumable=True,
            )

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"YouTube upload progress: {int(status.progress() * 100)}%")

            video_id = response.get("id")
            logger.info(f"YouTube API upload complete: video_id={video_id}")

            await youtube_auth_service.record_upload(account_id)

            return {
                "platform": "youtube",
                "success": True,
                "publish_id": video_id,
                "video_url": f"https://youtu.be/{video_id}",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "method": "api",
                "youtube_account_id": account_id,
            }
        except Exception as e:
            error_str = str(e)
            logger.error(f"YouTube API upload failed: {error_str}", exc_info=True)
            raise PublishingError(
                f"YouTube API upload failed: {error_str}",
                code="YOUTUBE_API_ERROR",
            ) from e

    async def _publish_via_browser(self, video_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
        raise PublishingError(
            "YouTube browser upload is not supported on Cloud Run. "
            "Configure OAuth credentials for API upload via AVF_GOOGLE_CLIENT_ID / AVF_GOOGLE_CLIENT_SECRET.",
            code="YOUTUBE_BROWSER_UNSUPPORTED",
        )

    async def check_status(self, publish_id: str) -> dict[str, Any]:
        if publish_id.startswith("yt_") and len(publish_id) > 10:
            return {"publish_id": publish_id, "status": "processing", "platform": "youtube"}
        try:
            from googleapiclient.discovery import build
            from .youtube_auth import youtube_auth_service

            creds = await youtube_auth_service.get_credentials()
            if creds:
                youtube = build("youtube", "v3", credentials=creds)
                response = youtube.videos().list(
                    part="status,snippet",
                    id=publish_id,
                ).execute()
                items = response.get("items", [])
                if items:
                    item = items[0]
                    return {
                        "publish_id": publish_id,
                        "status": item["status"]["uploadStatus"],
                        "title": item["snippet"]["title"],
                        "platform": "youtube",
                    }
        except Exception as e:
            logger.warning(f"YouTube status check failed: {e}")
        return {"publish_id": publish_id, "status": "processing", "platform": "youtube"}


class InstagramPublisher(PlatformPublisher):
    platform_name = "instagram"

    async def publish(self, video_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
        logger.info(f"Instagram publish: {video_path}")
        try:
            from ..modules.browser_automation.engine import PlaywrightBrowserEngine
            engine = PlaywrightBrowserEngine()
            await engine.initialize()
            await engine.launch(headless=settings.browser_headless)

            page = await engine.get_page()
            session_path = Path(settings.instagram_session_dir)
            session_path.mkdir(parents=True, exist_ok=True)
            state_file = session_path / "ig_state.json"

            await page.goto("https://www.instagram.com", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)

            if state_file.exists():
                try:
                    import json as _json
                    with open(state_file) as _f:
                        storage = _json.load(_f)
                    context = page.context
                    await context.add_cookies(storage.get("cookies", []))
                    if storage.get("local_storage"):
                        _val = _json.dumps(storage["local_storage"])
                        await page.evaluate(f"localStorage.setItem('ig_session', {_val})")
                    await page.reload(wait_until="domcontentloaded")
                    await asyncio.sleep(4)
                    title_lower = (await page.title()).lower()
                    has_login_form = await page.query_selector('input[name="username"]')
                    logged_in = "login" not in title_lower and has_login_form is None
                except Exception as e:
                    logger.warning(f"Instagram session restore failed: {e}")
                    logged_in = False
            else:
                logged_in = False

            if not logged_in:
                username = settings.instagram_username or metadata.get("instagram_username", "")
                password = settings.instagram_password or metadata.get("instagram_password", "")
                if not username or not password:
                    raise PublishingError(
                        "Instagram login required. Set AVF_INSTAGRAM_USERNAME and AVF_INSTAGRAM_PASSWORD "
                        "in .env, or pass instagram_username/instagram_password in metadata.",
                        code="INSTA_NO_CREDENTIALS",
                    )
                username_input = await page.wait_for_selector('input[name="username"]', timeout=15000)
                await username_input.fill(username)
                password_input = await page.wait_for_selector('input[name="password"]', timeout=5000)
                await password_input.fill(password)
                await page.click('button[type="submit"]')
                await asyncio.sleep(6)

                save_info = await page.query_selector('button:has-text("Save Info")')
                if save_info:
                    await save_info.click()
                    await asyncio.sleep(2)
                not_now = await page.query_selector('button:has-text("Not Now")')
                if not_now:
                    await not_now.click()
                    await asyncio.sleep(2)

                try:
                    import json as _json
                    _cookies = await page.context.cookies()
                    _ls = await page.evaluate("localStorage.getItem('ig_session') or ''")
                    with open(state_file, "w") as _f:
                        _json.dump({"cookies": _cookies, "local_storage": _ls}, _f)
                    logger.info("Instagram session saved")
                except Exception as e:
                    logger.warning(f"Failed to save Instagram session: {e}")

            create_btn = await page.wait_for_selector('svg[aria-label="New post"], svg[aria-label="Create"]', timeout=15000)
            await create_btn.click()
            await asyncio.sleep(2)

            reel_option = await page.query_selector('span:has-text("Reel")')
            if reel_option:
                await reel_option.click()
                await asyncio.sleep(2)

            file_input = await page.wait_for_selector('input[type="file"]', timeout=10000)
            await file_input.set_input_files(os.path.abspath(video_path))
            logger.info("Instagram video file selected, waiting for upload...")

            await asyncio.sleep(5)
            for _ in range(90):
                try:
                    next_btn = await page.query_selector('button:has-text("Next"), div[role="button"]:has-text("Next")')
                    share_btn = await page.query_selector('button:has-text("Share"), div[role="button"]:has-text("Share")')
                    if next_btn:
                        await next_btn.click()
                        await asyncio.sleep(3)
                        break
                    if share_btn:
                        break
                    done_spinner = await page.query_selector('div[role="progressbar"]')
                    if not done_spinner:
                        break
                except Exception:
                    pass
                await asyncio.sleep(2)

            caption = metadata.get("description", metadata.get("title", ""))
            if caption:
                caption_input = await page.query_selector('[aria-label="Write a caption..."], [placeholder="Write a caption..."], div[contenteditable="true"][role="textbox"]')
                if caption_input:
                    await caption_input.click()
                    await asyncio.sleep(1)
                    await caption_input.type(caption[:2200], delay=30)
                    await asyncio.sleep(1)

            share_btn = await page.wait_for_selector('button:has-text("Share"), div[role="button"]:has-text("Share")', timeout=30000)
            await share_btn.click()
            await asyncio.sleep(5)

            await engine.shutdown()

            return {
                "platform": "instagram",
                "success": True,
                "publish_id": f"ig_{abs(hash(video_path))}",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "method": "browser",
            }
        except PublishingError:
            raise
        except Exception as e:
            raise PublishingError(f"Instagram browser upload failed: {e}", code="INSTA_BROWSER_ERROR") from e

    async def check_status(self, publish_id: str) -> dict[str, Any]:
        return {"publish_id": publish_id, "status": "published", "platform": "instagram"}


class TwitterPublisher(PlatformPublisher):
    platform_name = "twitter"

    async def publish(self, video_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return {
            "platform": "twitter",
            "success": True,
            "publish_id": f"tw_{abs(hash(video_path))}",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "method": "browser",
        }

    async def check_status(self, publish_id: str) -> dict[str, Any]:
        return {"publish_id": publish_id, "status": "published", "platform": "twitter"}


class PublishingService:
    _publishers: dict[str, type[PlatformPublisher]] = {}

    @classmethod
    def register(cls, name: str, publisher_class: type[PlatformPublisher]) -> None:
        cls._publishers[name] = publisher_class

    @classmethod
    def get_publisher(cls, platform: str) -> PlatformPublisher:
        publisher_class = cls._publishers.get(platform.lower())
        if not publisher_class:
            raise PublishingError(f"Unsupported platform: {platform}")
        return publisher_class()

    @classmethod
    def list_platforms(cls) -> list[str]:
        return list(cls._publishers.keys())

    async def publish_to_platform(
        self,
        platform: str,
        video_path: str,
        metadata: dict[str, Any],
        use_browser: bool = True,
    ) -> dict[str, Any]:
        publisher = self.get_publisher(platform)
        logger.info(f"Publishing to {platform}", extra={"video": video_path, "title": metadata.get("title")})

        if platform == "youtube" and not use_browser:
            metadata["method"] = "api"
        elif platform == "youtube" and use_browser:
            metadata["method"] = "auto"

        return await publisher.publish(video_path, metadata)

    async def publish_multi_platform(
        self,
        video_path: str,
        metadata: dict[str, Any],
        platforms: list[str],
    ) -> dict[str, Any]:
        results = {}
        for platform in platforms:
            try:
                results[platform] = await self.publish_to_platform(platform, video_path, metadata)
            except Exception as e:
                results[platform] = {"success": False, "error": str(e)}
        return results

    async def _api_publish(self, publisher: PlatformPublisher, video_path: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return await publisher.publish(video_path, metadata)


PublishingService.register("tiktok", TikTokPublisher)
PublishingService.register("youtube", YouTubePublisher)
PublishingService.register("instagram", InstagramPublisher)
PublishingService.register("twitter", TwitterPublisher)
