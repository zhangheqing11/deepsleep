"""ds flash（OpenAI 兼容）客户端：只给模拟来访用来"把已定内容说成人话"。

- 配置从环境变量或仓库根 `.env` 读：DS_BASE_URL、DS_API_KEY、DS_MODEL（.env 不入库）。
- temperature 固定 0（锁定决定第 3 条）。
- 缺 key、未装 openai、超时或报错 → 返回 None，调用方自动降级为确定性 mock（事先写在代码里，
  不靠人现场操作）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMEOUT_S = 15.0


def load_dotenv(path: Path | None = None) -> None:
    """极简 .env 解析：KEY=VALUE，不覆盖已存在的环境变量。"""
    path = path or Path(os.getenv('DS_ENV_FILE', REPO_ROOT / '.env'))
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class DsConfig:
    base_url: str
    api_key: str
    model: str

    @classmethod
    def from_env(cls) -> 'DsConfig | None':
        load_dotenv()
        base_url = os.getenv('DS_BASE_URL', '').strip()
        api_key = os.getenv('DS_API_KEY', '').strip()
        model = os.getenv('DS_MODEL', '').strip()
        if not (base_url and api_key and model):
            return None
        return cls(base_url, api_key, model)


class DsClient:
    """异步聊天补全。complete() 失败时返回 None（并记下原因），从不抛异常。"""

    def __init__(self, config: DsConfig, timeout_s: float = DEFAULT_TIMEOUT_S):
        self.config = config
        self.timeout_s = timeout_s
        self.last_error: str | None = None
        self._client = None

    @property
    def model(self) -> str:
        return self.config.model

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI  # 延迟导入：mock 路径不需要 openai
            self._client = AsyncOpenAI(base_url=self.config.base_url, api_key=self.config.api_key,
                                       timeout=self.timeout_s, max_retries=1)
        return self._client

    async def complete(self, system: str, user: str, max_tokens: int = 300) -> str | None:
        try:
            response = await self._get_client().chat.completions.create(
                model=self.config.model,
                messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}],
                temperature=0,
                max_tokens=max_tokens,
            )
            text = (response.choices[0].message.content or '').strip()
            if not text:
                self.last_error = 'empty response'
                return None
            return text
        except Exception as exc:  # noqa: BLE001 — 任何失败都降级 mock
            self.last_error = f'{type(exc).__name__}: {exc}'[:200]
            return None


def client_from_env(force_mock: bool = False) -> DsClient | None:
    if force_mock:
        return None
    config = DsConfig.from_env()
    return DsClient(config) if config else None
