"""Bounded transport-only retry policy; never record provider bodies or keys."""
import asyncio
import random

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


def is_rate_limited(exc):
    """HTTP 429 from the provider (the SDK's RateLimitError carries status_code=429)."""
    return getattr(exc, "status_code", None) == 429


async def retry_connection(request, settings, *, stats=None):
    """Bounded retries for transport failures and, separately, for provider rate limiting (429).

    Other HTTP status errors are never retried. Rate-limit waits are longer and jittered so that
    concurrent sessions do not retry in lockstep; both budgets are frozen in engine/config.yaml.
    """
    retries = settings.get("max_retries", 2)
    delay = settings.get("backoff_s", 0.5)
    cap = settings.get("max_backoff_s", 2.0)
    rl_retries = settings.get("rate_limit_retries", 0)
    rl_delay = settings.get("rate_limit_backoff_s", 1.0)
    rl_cap = settings.get("rate_limit_max_backoff_s", 8.0)
    row = CURRENT_CALL.get()
    attempt = rl_attempt = 0
    while True:
        if stats is not None:
            stats["attempts"] = stats.get("attempts", 0) + 1
        if row is not None:
            row["network_attempts"] = row.get("network_attempts", 0) + 1
        try:
            return await request()
        except Exception as exc:
            if is_rate_limited(exc) and rl_attempt < rl_retries:
                wait = min(rl_delay * 2 ** rl_attempt, rl_cap) * (0.5 + random.random())
                rl_attempt += 1
                if stats is not None:
                    stats["rate_limit_retries"] = stats.get("rate_limit_retries", 0) + 1
                if row is not None:
                    row["rate_limit_retries"] = row.get("rate_limit_retries", 0) + 1
                await asyncio.sleep(wait)
                continue
            if not is_connection_error(exc) or attempt == retries:
                raise
            if stats is not None:
                stats["retries"] = stats.get("retries", 0) + 1
            if row is not None:
                row["network_retries"] = row.get("network_retries", 0) + 1
            await asyncio.sleep(min(delay * 2 ** attempt, cap))
            attempt += 1
