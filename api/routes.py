"""第一轮 Mock 联调接口。"""

from typing import Annotated

from fastapi import APIRouter, Header, Request

from api.run_models import ErrorResponse, MockScenario, RunAccepted, RunRequest, RunState, SessionList
from api.read_routes import RunID, VisitorID


def run_source(request: Request, run_id: str):
    store = request.app.state.read_store
    return store if run_id in store.run_ids else request.app.state.runs

router = APIRouter(
    prefix="/api/v1/runs", tags=["Mock 运行"],
    responses={status: {"model": ErrorResponse} for status in (404, 409, 422)},
)


@router.post("", status_code=202)
async def create_run(
    body: RunRequest, request: Request,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")],
    x_mock_scenario: Annotated[MockScenario, Header()] = "normal",
) -> RunAccepted:
    return await request.app.state.runs.create(body, idempotency_key, x_mock_scenario)


@router.get("/{run_id}")
async def get_run(run_id: RunID, request: Request) -> RunState:
    return run_source(request, run_id).state(run_id)


@router.get("/{run_id}/report")
async def get_report(run_id: RunID, request: Request) -> dict:
    return run_source(request, run_id).report(run_id)


@router.get("/{run_id}/sessions")
async def get_sessions(run_id: RunID, request: Request) -> SessionList:
    return run_source(request, run_id).sessions(run_id)


@router.get("/{run_id}/sessions/{visitor_id}")
async def get_session(run_id: RunID, visitor_id: VisitorID, request: Request) -> dict:
    return run_source(request, run_id).session(run_id, visitor_id)
