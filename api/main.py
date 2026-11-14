"""服务入口：从仓库根目录运行 python -m uvicorn api.main:app。"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from api.config import Settings
from api.auth import AuthService
from api.auth_routes import router as auth_router
from api.errors import APIError
from api.file_store import FileStore
from api.mock_read_store import MockReadStore
from api.read_routes import router as read_router, files_router
from api.routes import router
from api.run_service import MockRunService

logger = logging.getLogger(__name__)
WEB_DIST = Path(__file__).resolve().parents[1] / "web/dist"


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    data_source: Literal["files", "mock"]
    execution_mode: Literal["real", "mock"]


def error_response(request: Request, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request.state.request_id,
            }
        },
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_env()
    runs = MockRunService(settings) if settings.data_source == "mock" else None
    read_store = MockReadStore() if runs is not None else FileStore(settings.data_root)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            yield
        finally:
            if runs is not None:
                await runs.close()

    application = FastAPI(
        title="deepsleep 后端 API",
        description="只读引擎产物，或显式选择 Mock 联调；HTTP 服务不调用真实模型。",
        version="0.1.0",
        debug=False,
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.runs = runs
    application.state.read_store = read_store
    application.state.auth = AuthService(settings)
    application.include_router(read_router)
    application.include_router(router if runs is not None else files_router)
    application.include_router(auth_router)

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = f"req_{uuid4().hex}"
        try:
            response = await call_next(request)
        except Exception as exc:
            # 不记录请求正文或异常内容，仅保留类型与请求编号。
            logger.error(
                "Unhandled %s; request_id=%s",
                type(exc).__name__,
                request.state.request_id,
            )
            response = error_response(
                request, 500, "INTERNAL_ERROR", "服务内部错误，请凭请求编号排查。"
            )
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @application.exception_handler(APIError)
    async def api_error(request: Request, exc: APIError):
        return error_response(request, exc.status_code, exc.code, exc.message)

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code, message = {
            404: ("NOT_FOUND", "接口或资源不存在。"),
            405: ("METHOD_NOT_ALLOWED", "该接口不支持此请求方法。"),
        }.get(exc.status_code, ("HTTP_ERROR", "请求未能完成。"))
        response = error_response(request, exc.status_code, code, message)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(request, 422, "VALIDATION_ERROR", "请求参数不合法。")

    @application.get("/api/v1/health", tags=["服务状态"])
    async def health() -> HealthResponse:
        """仅表示 HTTP 服务可响应，不代表引擎、模型或评分已就绪。"""
        return HealthResponse(data_source=settings.data_source, execution_mode=settings.execution_mode)

    if settings.serve_web and WEB_DIST.is_dir():
        # Mount last so API/docs routes keep priority. Hash routes need no fallback.
        application.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")

    # CORS 在请求上下文外层，使应用错误响应同样带跨域头。
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key", "X-Mock-Scenario", "Authorization"],
        expose_headers=["X-Request-ID"],
    )
    return application


app = create_app()
