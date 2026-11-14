"""Opt-in local development app. Start with the documented factory command."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Header, Request

from api.config import Settings
from api.main import create_app
from api.integration_models import (IntegrationRequest, IntegrationAccepted, IntegrationState,
                                    IntegrationSessionList)
from api.integration_service import IntegrationService
from api.integration_store import IntegrationStore
from api.run_models import ErrorResponse

ROOT = Path(__file__).resolve().parents[1]


def create_integration_app(*, backend=None, database_path: Path | None = None,
                           concurrency: int = 2, timeout_s: float = 30, max_runs: int = 100):
    if backend is None:
        from api.integration_backend import OfflineEngineBackend
        backend = OfflineEngineBackend(ROOT / "var/integration-deps")
    store = IntegrationStore(database_path or ROOT / "var/integration/runs.sqlite3", max_runs=max_runs)
    try:
        service = IntegrationService(backend, store, concurrency=concurrency, timeout_s=timeout_s)
    except Exception:
        store.close()
        raise
    app = create_app(Settings(data_source="mock"))
    app.title = "deepsleep 离线引擎集成（仅本地开发）"
    app.description = ("原 Mock 接口继续可用；integration 路由实际调用固定版本引擎与评分，"
                       "所有模型组件均为 Mock，数据为 sample，结果不作为正式评测证据。")
    app.state.integration = service
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application):
            try:
                yield
            finally:
                await service.close()

    app.router.lifespan_context = lifespan
    router = APIRouter(prefix="/api/v1/integration", tags=["离线模块集成"],
                       responses={s: {"model": ErrorResponse} for s in (404, 409, 422, 429, 503)})

    @router.get("/health")
    async def integration_health() -> dict:
        return {"status": "ok", "execution_mode": "mock",
                "execution_source": "engine_offline", "sources": backend.sources,
                "recovered_interrupted_runs": service.recovered,
                "limitations": ["sample data", "placeholder scoring parameters",
                                  "upstream safety review pending", "single process only"]}

    @router.post("/runs", status_code=202)
    async def create_run(body: IntegrationRequest, request: Request,
        idempotency_key: Annotated[str, Header(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")],
    ) -> IntegrationAccepted:
        return await request.app.state.integration.create(body, idempotency_key)

    @router.get("/runs/{run_id}")
    async def get_run(run_id: str) -> IntegrationState:
        return service.state(run_id)

    @router.get("/runs/{run_id}/report")
    async def get_report(run_id: str) -> dict:
        return service.report(run_id)

    @router.get("/runs/{run_id}/sessions")
    async def get_sessions(run_id: str) -> IntegrationSessionList:
        return service.sessions(run_id)

    @router.get("/runs/{run_id}/sessions/{visitor_id}")
    async def get_session(run_id: str, visitor_id: str) -> dict:
        return service.session(run_id, visitor_id)

    app.include_router(router)
    return app
