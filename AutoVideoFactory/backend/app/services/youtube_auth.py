from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from ..core.config import settings
from ..core.database import DatabaseEngine
from ..core.exceptions import PublishingError
from ..core.logging import get_logger
from ..models.content import YouTubeAccount

logger = get_logger("autovideofactory.services.youtube_auth")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

SESSIONS_DIR = Path(settings.sessions_dir) / "youtube"


OAUTH_CLIENT_CONFIGS = {}

def _build_oauth_config(client_id: str, client_secret: str, redirect_uri: str) -> dict:
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

def _init_oauth_configs():
    if settings.google_client_id and settings.google_client_secret:
        OAUTH_CLIENT_CONFIGS["default"] = {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
        }
    if settings.google_client_id_2 and settings.google_client_secret_2:
        OAUTH_CLIENT_CONFIGS["secondary"] = {
            "client_id": settings.google_client_id_2,
            "client_secret": settings.google_client_secret_2,
        }

_init_oauth_configs()


class YouTubeAuthService:
    def __init__(self) -> None:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._flows: dict[str, InstalledAppFlow] = {}
        self._restore_scheduled = False

    async def _backup_tokens(self) -> None:
        try:
            from ..services.storage_service import storage
            import json, tempfile, os
            async with DatabaseEngine.get_session_factory()() as session:
                from sqlalchemy import select
                result = await session.execute(select(YouTubeAccount))
                accounts = result.scalars().all()
            if not accounts:
                return
            backup = [
                {
                    "email": a.email,
                    "channel_name": a.channel_name,
                    "refresh_token": a.refresh_token,
                    "token_expiry": a.token_expiry.isoformat() if a.token_expiry else None,
                    "oauth_config": a.oauth_config,
                    "is_active": a.is_active,
                    "upload_count": a.upload_count,
                }
                for a in accounts
            ]
            tmp = os.path.join(tempfile.gettempdir(), "avf_yt_tokens.json")
            with open(tmp, "w") as f:
                json.dump({"accounts": backup}, f)
            await storage.upload(tmp, "youtube_tokens/backup.json")
            os.unlink(tmp)
            logger.info(f"Backed up {len(backup)} YouTube token(s) to storage")
        except Exception as e:
            logger.error(f"Could not backup YouTube tokens: {e}", exc_info=True)

    async def _restore_tokens(self) -> int:
        try:
            from ..services.storage_service import storage
            import json, tempfile, os, datetime as dt
            exists = await storage.exists("youtube_tokens/backup.json")
            if not exists:
                return 0
            async with DatabaseEngine.get_session_factory()() as session:
                from sqlalchemy import select, func
                cnt = await session.execute(select(func.count()).select_from(YouTubeAccount))
                if cnt.scalar() > 0:
                    return 0
            tmp = os.path.join(tempfile.gettempdir(), "avf_yt_restore.json")
            await storage.download("youtube_tokens/backup.json", tmp)
            with open(tmp, "r") as f:
                data = json.load(f)
            os.unlink(tmp)
            restored = 0
            async with DatabaseEngine.get_session_factory()() as session:
                for entry in data.get("accounts", []):
                    try:
                        expiry = dt.datetime.fromisoformat(entry["token_expiry"]) if entry.get("token_expiry") else None
                        session.add(YouTubeAccount(
                            email=entry["email"],
                            channel_name=entry.get("channel_name", ""),
                            refresh_token=entry["refresh_token"],
                            token_expiry=expiry,
                            oauth_config=entry.get("oauth_config", "default"),
                            is_active=entry.get("is_active", True),
                            upload_count=entry.get("upload_count", 0),
                        ))
                        restored += 1
                    except Exception as e:
                        logger.warning(f"Failed to restore token for {entry.get('email')}: {e}")
                await session.commit()
            logger.info(f"Restored {restored} YouTube token(s) from storage backup")
            return restored
        except Exception as e:
            logger.error(f"Could not restore YouTube tokens: {e}", exc_info=True)
            return 0

    def get_oauth_configs(self) -> list[dict[str, str]]:
        return [
            {"id": k, "client_id": v["client_id"]}
            for k, v in OAUTH_CLIENT_CONFIGS.items()
        ]

    def _make_flow(self, redirect_uri: str, oauth_config_name: str = "default") -> InstalledAppFlow:
        config = OAUTH_CLIENT_CONFIGS.get(oauth_config_name)
        if not config:
            raise PublishingError(
                f"OAuth config '{oauth_config_name}' not found. "
                f"Available: {list(OAUTH_CLIENT_CONFIGS.keys())}",
                code="OAUTH_NOT_CONFIGURED",
            )
        flow = InstalledAppFlow.from_client_config(
            _build_oauth_config(config["client_id"], config["client_secret"], redirect_uri),
            SCOPES,
        )
        flow.redirect_uri = redirect_uri
        return flow

    def get_authorization_url(self, redirect_uri: str = "http://localhost:8080/auth/youtube/callback", oauth_config: str = "default") -> str:
        if not OAUTH_CLIENT_CONFIGS:
            raise PublishingError(
                "Google OAuth not configured. Set AVF_GOOGLE_CLIENT_ID and AVF_GOOGLE_CLIENT_SECRET",
                code="OAUTH_NOT_CONFIGURED",
            )
        flow = self._make_flow(redirect_uri, oauth_config)
        auth_url, state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
        )
        self._flows[state] = flow
        self._flows[f"{state}_config"] = oauth_config
        return auth_url

    async def exchange_code(self, code: str, state: str, redirect_uri: str = "http://localhost:8080/auth/youtube/callback") -> dict[str, Any]:
        flow = self._flows.pop(state, None)
        oauth_config = self._flows.pop(f"{state}_config", "default")
        if not flow:
            raise PublishingError("OAuth session expired. Please re-authorize.", code="OAUTH_SESSION_EXPIRED")

        import threading
        result_container = {}

        def _fetch_token():
            try:
                flow.fetch_token(code=code)
                result_container["tokens"] = flow.credentials
            except Exception as e:
                result_container["error"] = e

        thread = threading.Thread(target=_fetch_token, daemon=True)
        thread.start()
        thread.join(timeout=30)

        if "error" in result_container:
            raise PublishingError(f"Token exchange failed: {result_container['error']}", code="OAUTH_TOKEN_FAILED")

        creds = result_container["tokens"]
        refresh_token = creds.refresh_token
        if not refresh_token:
            raise PublishingError("No refresh_token returned.", code="OAUTH_NO_REFRESH_TOKEN")

        access_token = creds.token
        token_expiry = creds.expiry

        userinfo = await self._get_userinfo(access_token)
        email = userinfo.get("email", "unknown")
        channel_name = userinfo.get("name", "")

        async with DatabaseEngine.get_session_factory()() as session:
            from sqlalchemy import select
            result = await session.execute(select(YouTubeAccount).where(YouTubeAccount.email == email))
            existing = result.scalar_one_or_none()
            if existing:
                existing.refresh_token = refresh_token
                existing.token_expiry = token_expiry
                existing.oauth_config = oauth_config
            else:
                session.add(YouTubeAccount(
                    email=email, channel_name=channel_name,
                    refresh_token=refresh_token, token_expiry=token_expiry,
                    is_active=True, oauth_config=oauth_config))
            await session.commit()

        await self._backup_tokens()

        return {"success": True, "email": email, "channel_name": channel_name, "expires_at": token_expiry.isoformat()}

    async def _get_userinfo(self, access_token: str) -> dict[str, Any]:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code == 200:
                return resp.json()
        return {"email": "unknown", "name": "YouTube User"}

    async def get_credentials(
        self, account_id: Optional[str] = None
    ) -> Optional[Credentials]:
        async with DatabaseEngine.get_session_factory()() as session:
            from sqlalchemy import select, func
            cnt = await session.execute(select(func.count()).select_from(YouTubeAccount))
            if cnt.scalar() == 0:
                await self._restore_tokens()
        async with DatabaseEngine.get_session_factory()() as session:
            from sqlalchemy import select
            if account_id:
                result = await session.execute(
                    select(YouTubeAccount).where(
                        YouTubeAccount.id == account_id,
                        YouTubeAccount.is_active == True,
                    )
                )
            else:
                result = await session.execute(
                    select(YouTubeAccount).where(YouTubeAccount.is_active == True)
                    .order_by(YouTubeAccount.upload_count.asc())
                )
            account = result.scalar_one_or_none()
            if not account:
                return None

            oauth_cfg = OAUTH_CLIENT_CONFIGS.get(account.oauth_config, {})
            client_id = oauth_cfg.get("client_id", settings.google_client_id or "")
            client_secret = oauth_cfg.get("client_secret", settings.google_client_secret or "")

            creds = Credentials(
                token=None,
                refresh_token=account.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES,
            )

            if creds.expired or not creds.valid:
                try:
                    creds.refresh(Request())
                    if creds.refresh_token and creds.refresh_token != account.refresh_token:
                        account.refresh_token = creds.refresh_token
                        await session.commit()
                        await self._backup_tokens()
                except Exception as e:
                    logger.error(
                        f"Token refresh failed for {account.email} (config: {account.oauth_config}): {e}",
                        exc_info=True,
                    )
                    account.is_active = False
                    await session.commit()
                    return None

            return creds

    async def get_available_accounts(self) -> list[dict[str, Any]]:
        async with DatabaseEngine.get_session_factory()() as session:
            from sqlalchemy import select, func
            cnt = await session.execute(select(func.count()).select_from(YouTubeAccount))
            if cnt.scalar() == 0:
                await self._restore_tokens()
        async with DatabaseEngine.get_session_factory()() as session:
            result = await session.execute(
                select(YouTubeAccount).where(YouTubeAccount.is_active == True)
            )
            accounts = result.scalars().all()
            return [
                {
                    "id": acc.id,
                    "email": acc.email,
                    "channel_name": acc.channel_name,
                    "quota_used_today": acc.quota_used_today,
                    "upload_count": acc.upload_count,
                    "last_upload_at": (
                        acc.last_upload_at.isoformat()
                        if acc.last_upload_at
                        else None
                    ),
                }
                for acc in accounts
            ]

    async def has_quota_available(self, account_id: str) -> bool:
        async with DatabaseEngine.get_session_factory()() as session:
            account = await session.get(YouTubeAccount, account_id)
            if not account:
                return False

            import datetime as dt
            today = dt.date.today().isoformat()
            if account.quota_reset_date != today:
                account.quota_used_today = 0
                account.quota_reset_date = today
                await session.commit()
                return True

            cost_per_upload = settings.google_youtube_upload_cost
            return account.quota_used_today + cost_per_upload <= settings.google_youtube_quota_per_account

    async def record_upload(self, account_id: str) -> None:
        import datetime as dt
        async with DatabaseEngine.get_session_factory()() as session:
            account = await session.get(YouTubeAccount, account_id)
            if account:
                today = dt.date.today().isoformat()
                if account.quota_reset_date != today:
                    account.quota_used_today = 0
                    account.quota_reset_date = today
                account.quota_used_today += settings.google_youtube_upload_cost
                account.upload_count += 1
                account.last_upload_at = datetime.now(timezone.utc)
                await session.commit()


youtube_auth_service = YouTubeAuthService()
