import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { RunStatusResponse } from '../api/draftTypes';
import { ApiError, isAbortError, toApiError } from '../api/errors';
import { POLL_BACKOFF_MS, POLL_INTERVAL_MS, REPORT_WAIT_MAX_POLLS } from '../config';

export type PollStop =
  /** 正常结束：failed，或 succeeded 且报告可读 */
  | 'terminal'
  /** 404 RUN_NOT_FOUND */
  | 'not_found'
  /** 非临时性的 4xx，重试无意义 */
  | 'client_error'
  /** succeeded 后长时间 report_available 仍为 false */
  | 'report_wait_timeout';

export interface RunPollerState {
  run: RunStatusResponse | null;
  /** 正在轮询 */
  polling: boolean;
  /** 查询失败（网络或 5xx），会自动退避重试；与任务失败分开 */
  transientError: ApiError | null;
  stop: PollStop | null;
  stopError: ApiError | null;
  /** 停止后手动重新开始查询 */
  restart: () => void;
}

/**
 * 轮询运行状态。
 * - 用 setTimeout 串行：上一个请求结束才安排下一个，不会重叠。
 * - runId 变化或组件卸载时 abort 进行中的请求并清掉定时器。
 * - 网络失败与 5xx 不停止，按 POLL_BACKOFF_MS 退避。
 */
export function useRunPoller(runId: string | null, onNotFound?: () => void): RunPollerState {
  const [run, setRun] = useState<RunStatusResponse | null>(null);
  const [polling, setPolling] = useState(false);
  const [transientError, setTransientError] = useState<ApiError | null>(null);
  const [stop, setStop] = useState<PollStop | null>(null);
  const [stopError, setStopError] = useState<ApiError | null>(null);
  const [nonce, setNonce] = useState(0);

  const restart = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    setRun(null);
    setTransientError(null);
    setStop(null);
    setStopError(null);
    if (!runId) {
      setPolling(false);
      return;
    }

    const controller = new AbortController();
    let timer: number | undefined;
    let failures = 0;
    let waitingForReport = 0;
    let disposed = false;

    const schedule = (ms: number) => {
      if (!disposed) timer = window.setTimeout(tick, ms);
    };

    const finish = (reason: PollStop, err: ApiError | null = null) => {
      setStop(reason);
      setStopError(err);
      setPolling(false);
    };

    async function tick() {
      try {
        const status = await api.getRun(runId as string, controller.signal);
        if (disposed) return;
        failures = 0;
        setRun(status);
        setTransientError(null);

        if (status.status === 'failed') return finish('terminal');
        if (status.status === 'succeeded') {
          if (status.report_available) return finish('terminal');
          waitingForReport += 1;
          if (waitingForReport > REPORT_WAIT_MAX_POLLS) return finish('report_wait_timeout');
        }
        schedule(POLL_INTERVAL_MS);
      } catch (e) {
        if (disposed || isAbortError(e)) return;
        const err = toApiError(e);
        if (err.kind === 'http' && err.status === 404) {
          finish('not_found', err);
          onNotFound?.();
          return;
        }
        if (!err.isTransient) return finish('client_error', err);
        setTransientError(err);
        const wait = POLL_BACKOFF_MS[Math.min(failures, POLL_BACKOFF_MS.length - 1)];
        failures += 1;
        schedule(wait);
      }
    }

    setPolling(true);
    void tick();

    return () => {
      disposed = true;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
    // onNotFound 故意不放进依赖：它只在 404 时调用一次，不应重启轮询
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, nonce]);

  return { run, polling, transientError, stop, stopError, restart };
}
