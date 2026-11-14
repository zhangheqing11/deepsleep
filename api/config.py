"""启动时读取配置；当前阶段仅支持 mock 模式。"""

import os
import math
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    execution_mode: Literal["mock"] = "mock"
    cors_origins: tuple[str, ...] = ()
    mock_step_delay_s: float = 0.5
    mock_report_delay_s: float = 3.0

    def __post_init__(self) -> None:
        if self.execution_mode != "mock":
            raise ValueError("当前服务骨架仅支持 mock 模式，真实引擎尚未接入。")
        for name, value, maximum in (
            ("mock_step_delay_s", self.mock_step_delay_s, 5),
            ("mock_report_delay_s", self.mock_report_delay_s, 10),
        ):
            if not math.isfinite(value) or not 0.01 <= value <= maximum:
                raise ValueError(f"{name} 必须在 0.01 到 {maximum} 秒之间。")
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or "*" in parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or any(char.isspace() for char in origin)
            ):
                raise ValueError("API_CORS_ORIGINS 只能包含 HTTP(S) 来源地址，不含路径或通配符。")
            # 访问 port 会校验端口格式和范围。
            parsed.port

    @classmethod
    def from_env(cls) -> "Settings":
        mode = os.getenv("API_EXECUTION_MODE", "mock").strip()
        if mode != "mock":
            raise ValueError("API_EXECUTION_MODE 当前只能设为 mock，真实引擎尚未接入。")
        origins = tuple(
            dict.fromkeys(
                item.strip().rstrip("/")
                for item in os.getenv("API_CORS_ORIGINS", "").split(",")
                if item.strip()
            )
        )
        return cls(
            execution_mode=mode, cors_origins=origins,
            mock_step_delay_s=float(os.getenv("API_MOCK_STEP_DELAY_S", "0.5")),
            mock_report_delay_s=float(os.getenv("API_MOCK_REPORT_DELAY_S", "3")),
        )
