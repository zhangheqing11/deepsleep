import { useCallback, useEffect, useState } from 'react';
import { isAbortError, toApiError, type ApiError } from '../api/errors';
import { POLL_BACKOFF_MS, POLL_INTERVAL_MS } from '../config';

interface Snapshot<T> { key: string | null; data: T | null; error: ApiError | null; polling: boolean }
/** 串行读取循环：返回清理函数；React 卸载和测试使用同一取消路径。 */
export function startReadPolling<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  terminal: (data: T) => boolean,
  onData: (data: T, polling: boolean) => void,
  onError: (error: ApiError, polling: boolean) => void,
): () => void {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let failures = 0;
  async function tick() {
    try {
      const data = await fetcher(controller.signal);
      if (controller.signal.aborted) return;
      failures = 0;
      const done = terminal(data);
      onData(data, !done);
      if (!done) timer = setTimeout(tick, POLL_INTERVAL_MS);
    } catch (e) {
      if (controller.signal.aborted || isAbortError(e)) return;
      const error = toApiError(e);
      onError(error, error.isTransient);
      if (error.isTransient) timer = setTimeout(tick, POLL_BACKOFF_MS[Math.min(failures++, POLL_BACKOFF_MS.length - 1)]);
    }
  }
  void tick();
  return () => { controller.abort(); clearTimeout(timer); };
}

/** 与 useRunPoller 相同的串行、终态停止、卸载取消和网络失败退避规则。 */
export function useReadPoller<T>(
  key: string | null,
  fetcher: (signal: AbortSignal) => Promise<T>,
  terminal: (data: T) => boolean,
) {
  const [snapshot, setSnapshot] = useState<Snapshot<T>>({ key: null, data: null, error: null, polling: false });
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  useEffect(() => {
    setSnapshot({ key, data: null, error: null, polling: key !== null });
    if (key === null) return;
    return startReadPolling(fetcher, terminal,
      (data, polling) => setSnapshot({ key, data, error: null, polling }),
      (error, polling) => setSnapshot((prev) => ({ ...prev, error, polling })));
    // fetcher 和 terminal 由 key 唯一确定；刷新显式使用 reload。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce]);
  return { ...(snapshot.key === key ? snapshot : { data: null, error: null, polling: key !== null }), reload };
}
