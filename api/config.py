"""启动时选择只读产物或内存 Mock，不加载 .env。"""

import os
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    data_source: Literal["files", "mock"] = "files"
    data_root: Path = Path(__file__).resolve().parents[1]
    serve_web: bool = False
    cors_origins: tuple[str, ...] = ()
    mock_step_delay_s: float = 0.5
    mock_report_delay_s: float = 3.0
    auth_mode: Literal["none", "demo"] = "none"
    auth_username: str = "demo"
    auth_password_sha256: str = ""
    auth_ttl_s: int = 28800
    # 控制台"一键全链路"：允许 HTTP 服务启动 python -m engine.demo 子进程（见 PIPELINE_API.md）。
    demo_launch: bool = False

    def __post_init__(self) -> None:
        if self.data_source not in {"files", "mock"}:
            raise ValueError("API_DATA_SOURCE 只能设为 files 或 mock。")
        if self.auth_mode not in ("none", "demo"):
            raise ValueError("API_AUTH_MODE 只能是 none 或 demo。")
        if not self.auth_username or len(self.auth_username) > 64:
            raise ValueError("API_AUTH_USERNAME 必须是 1 到 64 个字符。")
        if self.auth_mode == "demo" and (
            len(self.auth_password_sha256) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in self.auth_password_sha256)
        ):
            raise ValueError("启用 demo 登录时必须提供 64 位十六进制 API_AUTH_PASSWORD_SHA256。")
        if not 60 <= self.auth_ttl_s <= 7 * 24 * 60 * 60:
            raise ValueError("API_AUTH_TTL_S 必须在 60 秒到 7 天之间。")
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

    @property
    def execution_mode(self) -> Literal["real", "mock"]:
        return "real" if self.data_source == "files" else "mock"

    @classmethod
    def from_env(cls) -> "Settings":
        source = os.getenv("API_DATA_SOURCE", "files").strip()
        # 兼容旧配置，但不允许其与数据源矛盾。
        mode = os.getenv("API_EXECUTION_MODE")
        if mode is not None and mode != ("real" if source == "files" else "mock"):
            raise ValueError("API_EXECUTION_MODE 与 API_DATA_SOURCE 不一致。")
        origins = tuple(
            dict.fromkeys(
                item.strip().rstrip("/")
                for item in os.getenv("API_CORS_ORIGINS", "").split(",")
                if item.strip()
            )
        )
        return cls(
            data_source=source, cors_origins=origins,
            data_root=Path(os.getenv("API_DATA_ROOT", str(cls.data_root))),
            serve_web=os.getenv("API_SERVE_WEB", "0") == "1",
            mock_step_delay_s=float(os.getenv("API_MOCK_STEP_DELAY_S", "0.5")),
            mock_report_delay_s=float(os.getenv("API_MOCK_REPORT_DELAY_S", "3")),
            auth_mode=os.getenv("API_AUTH_MODE", "none").strip() or "none",
            auth_username=os.getenv("API_AUTH_USERNAME", "demo").strip() or "demo",
            auth_password_sha256=os.getenv("API_AUTH_PASSWORD_SHA256", "").strip(),
            auth_ttl_s=int(os.getenv("API_AUTH_TTL_S", "28800")),
            demo_launch=os.getenv("API_DEMO_LAUNCH", "0").strip() == "1",
        )
