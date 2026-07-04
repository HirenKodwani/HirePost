from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body

from ...agents.orchestrator import AgentOrchestrator
from ...services.pipeline_orchestrator import ContentPipeline

router = APIRouter()
orchestrator = AgentOrchestrator()


@router.get("/")
async def list_agents():
    return {"agents": orchestrator.get_all_agent_statuses()}


@router.get("/{agent_name}")
async def get_agent(agent_name: str):
    agent = orchestrator.get_agent(agent_name)
    if not agent:
        return {"error": f"Agent '{agent_name}' not found"}, 404
    return {"agent": agent.get_status_info()}


@router.post("/pipeline")
async def run_pipeline(data: dict = Body(...)):
    name = data.get("name", "default")
    steps = data.get("steps", [])
    pipeline_id = await orchestrator.run_pipeline(name=name, steps=steps)
    return {"pipeline_id": pipeline_id, "status": "started"}


_content_pipeline: ContentPipeline = None

def _get_pipeline():
    global _content_pipeline
    if _content_pipeline is None:
        _content_pipeline = ContentPipeline()
    return _content_pipeline

import uuid
from datetime import datetime, timezone

@router.post("/run-full-pipeline")
async def run_full_pipeline(data: dict = Body(...)):
    pipe = _get_pipeline()
    pipeline_id = uuid.uuid4().hex
    pipe._active_pipelines[pipeline_id] = {
        "id": pipeline_id, "status": "starting", "steps": {},
        "config": data, "started_at": datetime.now(timezone.utc).isoformat(),
    }
    data["_pipeline_id"] = pipeline_id
    asyncio.create_task(pipe.run_full_pipeline(data))
    return {"pipeline_id": pipeline_id, "status": "started"}

@router.get("/pipeline-status/{pipeline_id}")
async def get_pipeline_status(pipeline_id: str):
    pipe = _get_pipeline()
    result = pipe.get_pipeline(pipeline_id)
    if not result:
        return {"error": "Pipeline not found"}, 404
    return result

@router.post("/pipeline/{pipeline_id}/cancel")
async def cancel_pipeline(pipeline_id: str):
    success = await orchestrator.cancel_pipeline(pipeline_id)
    return {"cancelled": success}


@router.get("/pipeline/{pipeline_id}")
async def get_pipeline(pipeline_id: str):
    pipeline = orchestrator.get_pipeline(pipeline_id)
    if not pipeline:
        return {"error": "Pipeline not found"}, 404
    return {
        "pipeline": {
            "id": pipeline.id,
            "name": pipeline.name,
            "status": pipeline.status.value,
            "current_step": pipeline.current_step,
            "steps": pipeline.steps,
            "errors": pipeline.errors,
            "started_at": str(pipeline.started_at) if pipeline.started_at else None,
            "completed_at": str(pipeline.completed_at) if pipeline.completed_at else None,
        }
    }
