from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from .core.config import settings
from .core.database import DatabaseEngine
from .core.events import Event, EventBus, EventType
from .core.exceptions import AutoVideoFactoryError
from .core.logging import get_logger
from .api.router import api_router
from .agents.analytics_agent import AnalyticsAgent
from .agents.browser_agent import BrowserAgent
from .agents.editing_agent import EditingAgent
from .agents.learning_agent import LearningAgent
from .agents.orchestrator import AgentOrchestrator
from .agents.planner_agent import PlannerAgent
from .agents.prompt_agent import PromptAgent
from .agents.publishing_agent import PublishingAgent
from .agents.qa_agent import QAAgent
from .agents.recovery_agent import RecoveryAgent
from .agents.research_agent import ResearchAgent
from .agents.script_agent import ScriptAgent
from .agents.subtitle_agent import SubtitleAgent
from .agents.supervisor_agent import SupervisorAgent
from .agents.trend_agent import TrendAgent
from .agents.video_agent import VideoAgent
from .agents.visual_agent import VisualAgent
from .agents.voice_agent import VoiceAgent

logger = get_logger("autovideofactory")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "Starting AutoVideoFactory",
        extra={
            "version": settings.app_version,
            "environment": settings.environment.value,
        },
    )
    await DatabaseEngine.create_all()
    orchestrator = AgentOrchestrator()
    orchestrator.register_agent(PlannerAgent())
    orchestrator.register_agent(TrendAgent())
    orchestrator.register_agent(ResearchAgent())
    orchestrator.register_agent(ScriptAgent())
    orchestrator.register_agent(PromptAgent())
    orchestrator.register_agent(VoiceAgent())
    orchestrator.register_agent(VisualAgent())
    orchestrator.register_agent(VideoAgent())
    orchestrator.register_agent(EditingAgent())
    orchestrator.register_agent(SubtitleAgent())
    orchestrator.register_agent(PublishingAgent())
    orchestrator.register_agent(AnalyticsAgent())
    orchestrator.register_agent(LearningAgent())
    orchestrator.register_agent(QAAgent())
    orchestrator.register_agent(RecoveryAgent())
    orchestrator.register_agent(BrowserAgent())
    orchestrator.register_agent(SupervisorAgent())
    logger.info("All 17 agents registered")
    event_bus = EventBus()
    await event_bus.publish(
        Event(
            type=EventType.SYSTEM_STARTUP,
            source="system",
            data={"version": settings.app_version},
        )
    )
    yield
    logger.info("Shutting down AutoVideoFactory")
    await event_bus.publish(
        Event(
            type=EventType.SYSTEM_SHUTDOWN,
            source="system",
            data={},
        )
    )
    await DatabaseEngine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AutoVideoFactoryError)
async def avf_exception_handler(
    request: Request, exc: AutoVideoFactoryError
) -> JSONResponse:
    logger.error(
        "Request error",
        extra={
            "path": request.url.path,
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version, "environment": settings.environment.value}


@app.get("/")
async def root_handler():
    return HTMLResponse("<h2>AutoVideoFactory Backend</h2><p>Server is running.</p>")
