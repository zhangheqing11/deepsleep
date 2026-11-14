import { useCallback, useEffect, useState } from 'react';
import { ApiError, isAbortError, toApiError } from '../api/errors';

export type ResourceState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ok'; data: T }
  | { status: 'error'; error: ApiError };

/**
 * 读取一次性资源（报告、会谈列表、单个会谈）。
 * key 为 null 时不请求；key 变化或卸载时取消旧请求，旧结果不会覆盖新状态。
 */
export function useResource<T>(
  key: string | null,
  fetcher: (signal: AbortSignal) => Promise<T>,
): ResourceState<T> & { reload: () => void } {
  const [state, setState] = useState<ResourceState<T>>({ status: 'idle' });
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (key === null) {
      setState({ status: 'idle' });
      return;
    }
    const controller = new AbortController();
    setState({ status: 'loading' });
    fetcher(controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ status: 'ok', data });
      },
      (e: unknown) => {
        if (controller.signal.aborted || isAbortError(e)) return;
        setState({ status: 'error', error: toApiError(e) });
      },
    );
    return () => controller.abort();
    // fetcher 由 key 唯一决定
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, nonce]);

  return { ...state, reload };
}

/** 可被 abort 打断的等待 */
export function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new ApiError({ kind: 'aborted', message: '请求已取消' }));
    const t = window.setTimeout(resolve, ms);
    signal.addEventListener(
      'abort',
      () => {
        window.clearTimeout(t);
        reject(new ApiError({ kind: 'aborted', message: '请求已取消' }));
      },
      { once: true },
    );
  });
}
