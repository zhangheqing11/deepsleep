"""Per-attempt metadata, isolated across concurrent sessions and speculative tasks."""
from contextlib import contextmanager
from contextvars import ContextVar
import time

CURRENT_CALL = ContextVar('engine_call', default=None)
CALL_SCOPE = ContextVar('engine_call_scope', default=None)


@contextmanager
def record_call(log, agent, task, **fields):
    row = dict(agent=agent, task=task, ok=False, status='running', finish_reason=None,
               truncated=None, request_started=False, ms=0, scope=CALL_SCOPE.get(), discarded=False, **fields)
    log.append(row)  # Before awaiting: failed/cancelled/speculative attempts must survive.
    token = CURRENT_CALL.set(row)
    started = time.perf_counter()
    try:
        yield row
        row['ok'], row['status'] = True, 'ok'
    except BaseException as exc:
        row['status'] = ('cancelled' if type(exc).__name__ == 'CancelledError' else
                         'timeout' if isinstance(exc, TimeoutError) else 'error')
        row['error_type'] = type(exc).__name__  # No provider bodies, headers or secrets.
        raise
    finally:
        row['ms'] = round((time.perf_counter() - started) * 1000, 1)
        CURRENT_CALL.reset(token)


def annotate_response(response):
    row = CURRENT_CALL.get()
    if row is None:
        return
    choice = response.choices[0]
    reason = getattr(choice, 'finish_reason', None)
    row.update(finish_reason=reason, truncated=reason == 'length' if reason else None,
               content_chars=len(choice.message.content or ''),
               reasoning_chars=len(getattr(choice.message, 'reasoning_content', '') or ''))
    usage = getattr(response, 'usage', None)
    if usage is not None:
        row['usage'] = {k: getattr(usage, k, None) for k in
                        ('prompt_tokens', 'completion_tokens', 'total_tokens')}
