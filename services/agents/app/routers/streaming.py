from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent_harness.graph import AgentGraph
from app.agent_harness.runtime import AgentRuntime
from app.agent_harness.schemas import AgentState

router = APIRouter(prefix="/api/v1/agents", tags=["Agent Streaming"])
_graphs: dict[str, tuple[AgentGraph, AgentRuntime]] = {}


class StreamRunRequest(BaseModel):
    graph: str = "default"
    run_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    resume_run_id: str | None = None


def register_streaming_graph(name: str, graph: AgentGraph, runtime: AgentRuntime) -> None:
    _graphs[name] = (graph, runtime)


async def stream_graph(
    graph: AgentGraph,
    runtime: AgentRuntime,
    state: AgentState,
    *,
    resume_run_id: str | None = None,
) -> AsyncIterator[str]:
    events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def sink(event: dict[str, Any]) -> None:
        await events.put(event)

    async def run_graph() -> None:
        try:
            await graph.run(runtime, state=state, resume_run_id=resume_run_id, event_sink=sink)
        except Exception as exc:  # noqa: BLE001
            await events.put({"type": "run_error", "error": str(exc)})
        finally:
            await events.put(None)

    task = asyncio.create_task(run_graph())
    try:
        while True:
            event = await events.get()
            if event is None:
                break
            yield f"event: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"
        await task
    finally:
        if not task.done():
            task.cancel()


@router.post("/stream")
async def stream_agent_run(request: StreamRunRequest) -> StreamingResponse:
    configured = _graphs.get(request.graph)
    if configured is None:
        raise HTTPException(status_code=404, detail=f"streaming graph not found: {request.graph}")
    graph, runtime = configured
    state = AgentState(run_id=request.run_id, data=request.data) if request.run_id else AgentState(data=request.data)
    return StreamingResponse(
        stream_graph(graph, runtime, state, resume_run_id=request.resume_run_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )