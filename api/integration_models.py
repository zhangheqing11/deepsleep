"""Internal offline integration API; the A/B Mock contract stays unchanged."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from api.run_models import Progress, RunError, RunStatus


class IntegrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    split: Literal["sample"] = "sample"
    limit: Annotated[int, Field(ge=1, le=18)] = 1
    playbook_version: Literal["v0"] = "v0"


class IntegrationAccepted(BaseModel):
    run_id: str
    status: RunStatus
    execution_mode: Literal["mock"] = "mock"
    execution_source: Literal["engine_offline"] = "engine_offline"


class IntegrationState(IntegrationAccepted):
    split: Literal["sample"] = "sample"
    playbook_version: str
    progress: Progress
    elapsed_ms: int
    report_available: bool
    error: RunError | None


class IntegrationSessionItem(BaseModel):
    visitor_id: str
    status: RunStatus
    session_available: bool
    session_status: Literal["completed", "crisis_exit", "error"] | None


class IntegrationSessionList(BaseModel):
    items: list[IntegrationSessionItem]
