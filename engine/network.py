"""Bounded transport-only retry policy; never record provider bodies or keys."""
import asyncio

import httpx

# Recent OpenAI SDK builds use httpx2; older builds use httpx. These
# packages expose distinct exception classes even though names match.
CONNECTION_ERRORS = (httpx.ConnectError, httpx.ReadTimeout)
HTTP_ERRORS = (httpx.HTTPStatusError,)
try:
    import httpx2
except ImportError:
    pass
else:
    CONNECTION_ERRORS += (httpx2.ConnectError, httpx2.ReadTimeout)
    HTTP_ERRORS += (httpx2.HTTPStatusError,)

from .telemetry import CURRENT_CALL


def is_connection_error(exc):
    """OpenAI wraps httpx exceptions; inspect explicit causes, not message text."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, CONNECTION_ERRORS):
            return True
        exc = exc.__cause__
    return False


def is_http_error(exc):
    return isinstance(exc, HTTP_ERRORS) or getattr(exc, "status_code", None) is not None


async def retry_connection(request, settings, *, stats=None):
    retries = settings.get("max_retries", 2)
    delay = settings.get("backoff_s", 0.5)
    cap = settings.get("max_backoff_s", 2.0)
    row = CURRENT_CALL.get()
    for attempt in range(retries + 1):
        if stats is not None:
            stats["attempts"] = stats.get("attempts", 0) + 1
        if row is not None:
            row["network_attempts"] = row.get("network_attempts", 0) + 1
        try:
            return await request()
        except Exception as exc:
            if not is_connection_error(exc) or attempt == retries:
                raise
            if stats is not None:
                stats["retries"] = stats.get("retries", 0) + 1
            if row is not None:
                row["network_retries"] = row.get("network_retries", 0) + 1
            await asyncio.sleep(min(delay * 2 ** attempt, cap))
