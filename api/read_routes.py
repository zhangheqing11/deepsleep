"""Read APIs shared by the dashboard and developer console."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from api.errors import APIError
from api.file_store import ID_PATTERN, VISITOR_PATTERN, VERSION_PATTERN
from api.run_models import ErrorResponse, RunState, SessionList

RunID = Annotated[str, Path(pattern=ID_PATTERN)]
VisitorID = Annotated[str, Path(pattern=VISITOR_PATTERN)]
Version = Annotated[str, Path(pattern=VERSION_PATTERN)]

router = APIRouter(prefix="/api/v1", tags=["只读产物"],
                   responses={s: {"model": ErrorResponse} for s in (404, 422)})
files_router = APIRouter(prefix="/api/v1/runs", tags=["文件运行"],
                         responses={s: {"model": ErrorResponse} for s in (404, 422, 501)})


@router.get("/demo/experiment")
def experiment(request: Request) -> dict:
    return request.app.state.read_store.experiment()


@router.get("/runs")
def runs(request: Request, limit: Annotated[int, Query(ge=1)] = 50) -> dict:
    return request.app.state.read_store.runs(limit)


@router.get("/runs/{run_id}/evidence")
def evidence(run_id: RunID, request: Request) -> dict:
    store = request.app.state.read_store
    if request.app.state.settings.data_source == "mock" and run_id not in store.run_ids:
        request.app.state.runs.state(run_id)
        return {"available": False}
    return store.evidence(run_id)


@router.get("/evolutions")
def evolutions(request: Request, limit: Annotated[int, Query(ge=1)] = 20) -> dict:
    return request.app.state.read_store.evolutions(limit)


@router.get("/evolutions/{evolution_id}")
def evolution(evolution_id: RunID, request: Request) -> dict:
    return request.app.state.read_store.evolution(evolution_id)


@router.get("/evolutions/{evolution_id}/status")
def evolution_status(evolution_id: RunID, request: Request) -> dict:
    return request.app.state.read_store.evolution_status(evolution_id)


@router.get("/evolutions/{evolution_id}/insights")
def insights(evolution_id: RunID, request: Request) -> dict:
    return request.app.state.read_store.insights(evolution_id)


# Static names must precede /{version}.
@router.get("/playbook/versions")
def versions(request: Request) -> dict:
    return request.app.state.read_store.versions()


@router.get("/playbook/diff")
def diff(request: Request,
         from_version: Annotated[str, Query(alias="from", pattern=VERSION_PATTERN)],
         to_version: Annotated[str, Query(alias="to", pattern=VERSION_PATTERN)]) -> dict:
    return request.app.state.read_store.diff(from_version, to_version)


@router.get("/playbook/{version}")
def playbook(version: Version, request: Request) -> dict:
    return request.app.state.read_store.playbook(version)


@files_router.post("", status_code=501)
def create_run() -> None:
    raise APIError(501, "RUNS_VIA_CLI", "真实运行请在操作员终端执行 make demo-run1 / make demo-run2")


@files_router.get("/{run_id}")
def run_state(run_id: RunID, request: Request) -> RunState:
    return RunState(**request.app.state.read_store.state(run_id))


@files_router.get("/{run_id}/report")
def report(run_id: RunID, request: Request) -> dict:
    return request.app.state.read_store.report(run_id)


@files_router.get("/{run_id}/sessions")
def sessions(run_id: RunID, request: Request) -> SessionList:
    return SessionList(**request.app.state.read_store.sessions(run_id))


@files_router.get("/{run_id}/sessions/{visitor_id}")
def session(run_id: RunID, visitor_id: VisitorID, request: Request) -> dict:
    return request.app.state.read_store.session(run_id, visitor_id)
