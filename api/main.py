"""服务入口：从仓库根目录运行 python -m uvicorn api.main:app。"""

import logging
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from api.config import Settings
from api.errors import APIError
from api.routes import router
from api.run_service import MockRunService

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    execution_mode: Literal["mock"] = "mock"


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
    runs = MockRunService(settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            yield
        finally:
            await runs.close()

    application = FastAPI(
        title="deepsleep 后端 API",
        description="Mock 联调：运行任务、进度、契约示例报告及已有会谈。不调用真实模型。",
        version="0.1.0",
        debug=False,
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.state.runs = runs
    application.include_router(router)

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
        return HealthResponse(execution_mode=settings.execution_mode)

    # CORS 在请求上下文外层，使应用错误响应同样带跨域头。
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Idempotency-Key", "X-Mock-Scenario"],
        expose_headers=["X-Request-ID"],
    )
    return application


app = create_app()
