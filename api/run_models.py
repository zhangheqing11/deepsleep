"""联调任务元数据；业务报告和会谈直接使用 contracts/ 的 JSON。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

RunStatus = Literal["queued", "running", "succeeded", "failed"]
MockScenario = Literal["normal", "fail", "report_delay"]


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    split: Literal["A", "B"]
    playbook_version: Annotated[str, Field(min_length=1, max_length=64)] | None = None


class RunAccepted(BaseModel):
    run_id: str
    status: Literal["queued"] = "queued"
    execution_mode: Literal["mock"] = "mock"


class Progress(BaseModel):
    total: int
    completed: int
    failed: int


class RunError(BaseModel):
    code: str
    message: str


class RunState(BaseModel):
    run_id: str
    status: RunStatus
    execution_mode: Literal["mock"] = "mock"
    split: Literal["A", "B"]
    playbook_version: str
    progress: Progress
    elapsed_ms: int
    report_available: bool
    error: RunError | None


class SessionItem(BaseModel):
    visitor_id: str
    status: RunStatus
    session_available: bool
    session_status: Literal["completed", "crisis_exit", "error"] | None


class SessionList(BaseModel):
    items: list[SessionItem]


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
