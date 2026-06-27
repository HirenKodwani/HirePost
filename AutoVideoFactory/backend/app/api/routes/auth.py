from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from ...core.exceptions import PublishingError
from ...core.logging import get_logger
from ...services.youtube_auth import youtube_auth_service

logger = get_logger("autovideofactory.api.auth")

router = APIRouter()


REDIRECT_URI = "http://localhost:8080/api/v1/auth/youtube/callback"


@router.get("/youtube/login")
async def youtube_login():
    """Step 1: Get the Google OAuth URL to authorize YouTube upload access."""
    try:
        auth_url = youtube_auth_service.get_authorization_url(redirect_uri=REDIRECT_URI)
        return HTMLResponse(
            content=f"""
            <html><body style="font-family:sans-serif;padding:40px;text-align:center;">
            <h2>YouTube Authorization</h2>
            <p>Click the button below to authorize AutoVideoFactory to upload videos to your YouTube channel.</p>
            <br>
            <a href="{auth_url}" style="
                display:inline-block;padding:15px 30px;font-size:18px;
                background:#c00;color:white;text-decoration:none;border-radius:5px;
            ">Authorize YouTube</a>
            <p style="margin-top:30px;font-size:14px;color:#666;">
            After authorizing, you'll be redirected to localhost:8080 with a code.
            If you see an error page, copy the "code=" value from the URL bar
            and paste it here.</p>
            </body></html>
            """,
        )
    except PublishingError as e:
        return HTMLResponse(
            content=f"<h2>Error</h2><p>{e.message}</p>", status_code=500
        )


@router.get("/youtube/callback")
async def youtube_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
):
    """Step 2: Handle OAuth callback after user authorizes."""
    logger.info(f"OAuth callback received: code={'present' if code else 'missing'}, state={'present' if state else 'missing'}, error={error}")
    if error:
        return HTMLResponse(f"<h2>Authorization Failed</h2><p>Error: {error}</p>", status_code=400)
    if not code:
        return HTMLResponse("<h2>Missing code</h2>", status_code=400)

    try:
        result = await youtube_auth_service.exchange_code(code, state=state or "", redirect_uri=REDIRECT_URI)
        logger.info(f"YouTube authorized: {result['email']} ({result['channel_name']})")
        return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;padding:40px;text-align:center;">
        <h2>YouTube Account Authorized!</h2>
        <p>Email: {result['email']}</p>
        <p>Channel: {result['channel_name']}</p>
        <p>You can close this window.</p>
        </body></html>""")
    except PublishingError as e:
        return HTMLResponse(f"<h2>Authorization Failed</h2><p>{e.message}</p>", status_code=500)


@router.get("/youtube/accounts")
async def list_youtube_accounts():
    """List all authorized YouTube accounts."""
    accounts = await youtube_auth_service.get_available_accounts()
    return {"accounts": accounts, "count": len(accounts)}
