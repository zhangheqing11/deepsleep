"""第一轮 Mock 联调接口。"""

from typing import Annotated

from fastapi import APIRouter, Header, Request

from api.run_models import ErrorResponse, MockScenario, RunAccepted, RunRequest, RunState, SessionList

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
async def get_run(run_id: str, request: Request) -> RunState:
    return request.app.state.runs.state(run_id)


@router.get("/{run_id}/report")
async def get_report(run_id: str, request: Request) -> dict:
    return request.app.state.runs.report(run_id)


@router.get("/{run_id}/sessions")
async def get_sessions(run_id: str, request: Request) -> SessionList:
    return request.app.state.runs.sessions(run_id)


@router.get("/{run_id}/sessions/{visitor_id}")
async def get_session(run_id: str, visitor_id: str, request: Request) -> dict:
    return request.app.state.runs.session(run_id, visitor_id)
