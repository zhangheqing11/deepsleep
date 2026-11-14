"""Bounded, persisted offline jobs around the upstream engine and scoring."""

import asyncio
from copy import deepcopy
import json
import logging
from time import time
from uuid import uuid4

from api.errors import APIError
from api.integration_models import IntegrationAccepted, IntegrationRequest, IntegrationState
from api.integration_models import IntegrationSessionItem, IntegrationSessionList
from api.integration_store import IntegrationStore, IdempotencyConflict, CapacityExceeded

logger = logging.getLogger(__name__)


class IntegrationService:
    def __init__(self, backend, store: IntegrationStore, *, concurrency: int = 2, timeout_s: float = 30):
        if type(concurrency) is not int or not 1 <= concurrency <= 10:
            raise ValueError("offline concurrency must be 1..10")
        if not 0 < timeout_s <= 300:
            raise ValueError("offline timeout must be positive and at most 300 seconds")
        self.backend, self.store = backend, store
        self.timeout_s = timeout_s
        self._slots = asyncio.Semaphore(concurrency)
        self._tasks: set[asyncio.Task] = set()
        self._closed = False
        self.recovered = self.store.recover_interrupted()

    async def create(self, body: IntegrationRequest, key: str) -> IntegrationAccepted:
        if self._closed:
            raise APIError(503, "SERVICE_STOPPING", "服务正在关闭。")
        visitors = self.backend.visitors(body.limit)
        fingerprint = json.dumps(body.model_dump(), sort_keys=True, separators=(",", ":"))
        state = {
            "run_id": f"integration_{uuid4().hex}", "status": "queued",
            "execution_mode": "mock", "execution_source": "engine_offline",
            "split": "sample", "playbook_version": self.backend.version,
            "created_at": time(), "finished_at": None, "elapsed_ms": 0,
            "progress": {"total": len(visitors), "completed": 0, "failed": 0},
            "report_available": False, "error": None,
            "visitor_status": {v["id"]: "queued" for v in visitors},
            "sources": deepcopy(self.backend.sources),
        }
        try:
            state, created = self.store.create(key, fingerprint, state, visitors)
        except IdempotencyConflict:
            raise APIError(409, "IDEMPOTENCY_KEY_REUSED", "此幂等键已用于不同的请求。") from None
        except CapacityExceeded:
            raise APIError(429, "RUN_CAPACITY_EXCEEDED", "离线集成记录已达上限，请保留结果后使用新的数据库。") from None
        if created:
            task = asyncio.create_task(self._execute(state, visitors), name=state["run_id"])
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return IntegrationAccepted(run_id=state["run_id"], status=state["status"])

    def _refresh(self, state: dict) -> None:
        statuses = list(state["visitor_status"].values())
        state["progress"] = {"total": len(statuses), "completed": statuses.count("succeeded"),
                             "failed": statuses.count("failed")}
        end = state["finished_at"] or time()
        state["elapsed_ms"] = max(0, int((end - state["created_at"]) * 1000))

    def _persist(self, state: dict) -> None:
        self._refresh(state)
        self.store.update(state)

    def _fail(self, state: dict, code: str, message: str) -> None:
        for visitor_id, status in state["visitor_status"].items():
            if status not in ("succeeded", "failed"):
                state["visitor_status"][visitor_id] = "failed"
        state.update(status="failed", finished_at=time(), report_available=False,
                     error={"code": code, "message": message})
        self._persist(state)

    async def _one(self, state: dict, visitor: dict) -> None:
        visitor_id = visitor["id"]
        async with self._slots:
            state["visitor_status"][visitor_id] = "running"
            self._persist(state)
            session, trace = None, None
            try:
                session, trace = await asyncio.wait_for(
                    self.backend.run_session(visitor, state["run_id"]), self.timeout_s)
                if session.get("run_id") != state["run_id"]:
                    raise ValueError("Engine session belongs to a different run.")
                self.backend.validate_session(session, visitor)
                state["visitor_status"][visitor_id] = (
                    "succeeded" if session["status"] in ("completed", "crisis_exit") else "failed")
                if session["status"] not in ("completed", "crisis_exit"):
                    trace = {"integration_error": "SESSION_ERROR", "raw_session": session, "trace": trace}
                    session = None
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                state["visitor_status"][visitor_id] = "failed"
                session, trace = None, {"integration_error": "SESSION_TIMEOUT"}
            except Exception as exc:
                logger.warning("Offline session failed: %s; run_id=%s; visitor_id=%s",
                               type(exc).__name__, state["run_id"], visitor_id)
                state["visitor_status"][visitor_id] = "failed"
                # Invalid contract data is retained for local diagnosis, never served as a valid session.
                trace = {"integration_error": type(exc).__name__, "raw_session": session,
                         "contract_errors": getattr(exc, "errors", None), "trace": trace}
                session = None
            self._refresh(state)
            try:
                self.store.save_session(state["run_id"], visitor_id, session, trace, state=state)
            except Exception:
                # A rolled-back transaction must not leave successful progress in memory.
                state["visitor_status"][visitor_id] = "failed"
                self._refresh(state)
                raise

    async def _execute(self, state: dict, visitors: list[dict]) -> None:
        children = []
        try:
            state["status"] = "running"
            self._persist(state)
            children = [asyncio.create_task(self._one(state, visitor)) for visitor in visitors]
            await asyncio.gather(*children)
            if state["progress"]["failed"]:
                self._fail(state, "RUN_INCOMPLETE",
                           "部分会谈失败或不符合契约；已保留记录，未生成可能失真的汇总分数。")
                return
            sessions = self.store.sessions(state["run_id"])
            report = self.backend.make_report(visitors, [sessions[v["id"]] for v in visitors],
                                              state["run_id"], max(0, time() - state["created_at"]))
            state.update(status="succeeded", finished_at=time(), report_available=True)
            self._refresh(state)
            self.store.save_report(state["run_id"], report, state=state)
        except asyncio.CancelledError:
            for task in children:
                task.cancel()
            await asyncio.gather(*children, return_exceptions=True)
            self._fail(state, "RUN_INTERRUPTED", "服务关闭，未完成任务已终止；不会自动重跑。")
            raise
        except Exception as exc:
            for task in children:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*children, return_exceptions=True)
            logger.warning("Offline run failed: %s; run_id=%s", type(exc).__name__, state["run_id"])
            self._fail(state, "INTEGRATION_ERROR", "离线模块集成或报告校验失败，请凭运行编号检查本地记录。")

    def _get(self, run_id: str) -> dict:
        try:
            return self.store.state(run_id)
        except KeyError:
            raise APIError(404, "RUN_NOT_FOUND", "未找到该离线集成运行。") from None

    def state(self, run_id: str) -> IntegrationState:
        state = self._get(run_id)
        if state["status"] in ("queued", "running"):
            state["elapsed_ms"] = max(0, int((time() - state["created_at"]) * 1000))
        return IntegrationState.model_validate(state)

    def report(self, run_id: str) -> dict:
        state = self._get(run_id)
        report = self.store.report(run_id)
        if not state["report_available"] or report is None:
            raise APIError(409, "REPORT_NOT_READY", "该运行暂无可用报告，请先查看运行状态。")
        return report

    def sessions(self, run_id: str) -> IntegrationSessionList:
        state = self._get(run_id)
        sessions = self.store.sessions(run_id)
        return IntegrationSessionList(items=[IntegrationSessionItem(
            visitor_id=visitor_id, status=status, session_available=visitor_id in sessions,
            session_status=sessions[visitor_id]["status"] if visitor_id in sessions else None,
        ) for visitor_id, status in state["visitor_status"].items()])

    def session(self, run_id: str, visitor_id: str) -> dict:
        self._get(run_id)
        try:
            return self.store.session(run_id, visitor_id)
        except KeyError:
            raise APIError(404, "SESSION_NOT_FOUND", "暂无此来访的有效会谈记录。") from None

    async def close(self) -> None:
        self._closed = True
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self.store.close()
