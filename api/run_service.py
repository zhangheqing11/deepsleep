"""单进程、内存中的 Mock 任务；服务重启后任务和幂等记录清空。"""

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
import logging
from time import monotonic
from uuid import uuid4

from api.config import Settings
from api.errors import APIError
from api.run_models import (
    MockScenario, Progress, RunAccepted, RunError, RunRequest, RunState,
    RunStatus, SessionItem, SessionList,
)
from mocks.fixtures import FixtureCatalog

logger = logging.getLogger(__name__)


@dataclass
class _Run:
    run_id: str
    template: dict
    sessions: dict[str, dict]
    scenario: MockScenario
    created: float = field(default_factory=monotonic)
    finished: float | None = None
    status: RunStatus = "queued"
    visitor_status: dict[str, RunStatus] = field(default_factory=dict)
    report: dict | None = None
    error: RunError | None = None


class MockRunService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.catalog = FixtureCatalog()
        self._runs: dict[str, _Run] = {}
        self._keys: dict[str, tuple[tuple, str]] = {}
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    async def create(self, body: RunRequest, key: str, scenario: MockScenario) -> RunAccepted:
        # 比较已校验的字段值，与 JSON 字段顺序无关；省略和 null 均表示当前版本。
        fingerprint = (body.split, body.playbook_version, scenario)
        async with self._lock:
            existing = self._keys.get(key)
            if existing:
                previous, run_id = existing
                if fingerprint != previous:
                    raise APIError(409, "IDEMPOTENCY_KEY_REUSED", "此幂等键已用于不同的请求，请为新操作使用新键。")
                return RunAccepted(run_id=run_id)
            version = body.playbook_version or self.catalog.current_version
            try:
                report, sessions = self.catalog.snapshot(body.split, version)
            except KeyError:
                raise APIError(422, "VALIDATION_ERROR", "当前 Mock 支持 A/v1、B/v1、B/v2，省略版本时使用 v1。") from None
            run_id = f"run_{uuid4().hex}"
            report["run_id"] = run_id
            for visitor_id, session in sessions.items():
                session["run_id"] = run_id
                session["session_id"] = f"{run_id}/{visitor_id}"
            record = _Run(run_id, report, sessions, scenario)
            record.visitor_status = {row["visitor_id"]: "queued" for row in report["per_visitor"]}
            self._runs[run_id] = record
            self._keys[key] = (fingerprint, run_id)
            task = asyncio.create_task(self._execute(record), name=f"mock:{run_id}")
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return RunAccepted(run_id=run_id)

    async def _execute(self, record: _Run) -> None:
        try:
            # 先让 202 响应完成；进度由任务推进，不依赖浏览器轮询次数。
            await asyncio.sleep(self.settings.mock_step_delay_s)
            record.status = "running"
            for visitor_id in record.visitor_status:
                record.visitor_status[visitor_id] = "running"
                await asyncio.sleep(self.settings.mock_step_delay_s)
                if record.scenario == "fail":
                    self._fail(record, "MOCK_RUN_FAILED", "这是联调指定的模拟失败，本次不生成报告。")
                    return
                record.visitor_status[visitor_id] = "succeeded"
            record.finished = monotonic()
            if record.scenario != "report_delay":
                record.report = deepcopy(record.template)
            record.status = "succeeded"
            if record.scenario == "report_delay":
                await asyncio.sleep(self.settings.mock_report_delay_s)
                record.report = deepcopy(record.template)
        except asyncio.CancelledError:
            self._fail(record, "RUN_INTERRUPTED", "服务正在关闭，模拟任务已终止。")
            raise
        except Exception as exc:
            logger.error("Mock run failed: %s; run_id=%s", type(exc).__name__, record.run_id)
            self._fail(record, "MOCK_EXECUTION_ERROR", "模拟任务执行异常，请凭运行编号排查。")

    @staticmethod
    def _fail(record: _Run, code: str, message: str) -> None:
        for visitor_id, status in record.visitor_status.items():
            if status != "succeeded":
                record.visitor_status[visitor_id] = "failed"
        record.error = RunError(code=code, message=message)
        record.report = None
        record.finished = monotonic()
        record.status = "failed"

    def _get(self, run_id: str) -> _Run:
        try:
            return self._runs[run_id]
        except KeyError:
            raise APIError(404, "RUN_NOT_FOUND", "未找到该运行记录，服务重启后请创建新运行。") from None

    def state(self, run_id: str) -> RunState:
        record = self._get(run_id)
        statuses = list(record.visitor_status.values())
        end = record.finished if record.finished is not None else monotonic()
        return RunState(
            run_id=run_id, status=record.status, split=record.template["split"],
            playbook_version=record.template["playbook_version"],
            progress=Progress(total=len(statuses), completed=statuses.count("succeeded"), failed=statuses.count("failed")),
            elapsed_ms=max(0, int((end - record.created) * 1000)),
            report_available=record.report is not None, error=record.error,
        )

    def report(self, run_id: str) -> dict:
        record = self._get(run_id)
        if record.report is None:
            raise APIError(409, "REPORT_NOT_READY", "该运行尚无可用报告，请查询运行状态。")
        return deepcopy(record.report)

    def sessions(self, run_id: str) -> SessionList:
        record = self._get(run_id)
        items = []
        for visitor_id, status in record.visitor_status.items():
            session = record.sessions.get(visitor_id) if status == "succeeded" else None
            items.append(SessionItem(
                visitor_id=visitor_id, status=status, session_available=session is not None,
                session_status=session["status"] if session is not None else None,
            ))
        return SessionList(items=items)

    def session(self, run_id: str, visitor_id: str) -> dict:
        record = self._get(run_id)
        if record.visitor_status.get(visitor_id) != "succeeded" or visitor_id not in record.sessions:
            raise APIError(404, "SESSION_NOT_FOUND", "该运行暂无此来访的可用会谈记录。")
        return deepcopy(record.sessions[visitor_id])

    async def close(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
