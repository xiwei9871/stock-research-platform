from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request


def install_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = (request.headers.get("x-request-id") or "").strip() or uuid4().hex
        agent_run_id = (request.headers.get("x-agent-run-id") or "").strip()
        request.state.request_id = request_id
        if agent_run_id:
            request.state.agent_run_id = agent_run_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        if agent_run_id:
            response.headers["X-Agent-Run-ID"] = agent_run_id
        return response
