import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { isAbortError, toApiError, type ApiError } from '../api/errors';
import type { PipelineResponse } from '../api/extensionTypes';
import { POLL_BACKOFF_MS } from '../config';

/** 进行中每秒读一次；尚未开始、已结束或失败时每 3 秒读一次（终端里新启动的实验也能自己跟上） */
export const PIPELINE_RUNNING_MS = 1000;
export const PIPELINE_IDLE_MS = 3000;

/** 下一次读取前等多久：失败时按退避间隔，成功时看最近一份数据是否在进行中 */
export function pipelineDelay(last: PipelineResponse | null, failures: number): number {
  if (failures > 0) return POLL_BACKOFF_MS[Math.min(failures - 1, POLL_BACKOFF_MS.length - 1)];
  return last && last.available && last.state === 'running' ? PIPELINE_RUNNING_MS : PIPELINE_IDLE_MS;
}

export interface PollHandle {
  stop: () => void;
  /** 立即再读一次；正在读时，等这一次结束后马上再读（不会并发） */
  poke: () => void;
}

/**
 * 串行读取循环（与 useReadPoller 同一套写法）：下一次请求只在上一次结束后排期；
 * 任何失败都不停止，失败期间调用方保留最后一份数据。返回的 stop 用于卸载和测试。
 */
export function startPipelinePolling<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  delayFor: (last: T | null, failures: number) => number,
  onData: (data: T) => void,
  onError: (error: ApiError) => void,
): PollHandle {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let inFlight = false;
  let again = false;
  let stopped = false;
  let last: T | null = null;
  let failures = 0;

  async function tick(): Promise<void> {
    timer = undefined;
    if (stopped) return;
    inFlight = true;
    try {
      const data = await fetcher(controller.signal);
      if (stopped) return;
      last = data;
      failures = 0;
      onData(data);
    } catch (e) {
      if (stopped || isAbortError(e)) return;
      failures += 1;
      onError(toApiError(e));
    } finally {
      inFlight = false;
    }
    if (stopped) return;
    if (again) {
      again = false;
      timer = setTimeout(tick, 0);
      return;
    }
    timer = setTimeout(tick, delayFor(last, failures));
  }

  void tick();
  return {
    stop() {
      stopped = true;
      controller.abort();
      clearTimeout(timer);
    },
    poke() {
      if (stopped) return;
      if (inFlight) {
        again = true;
        return;
      }
      clearTimeout(timer);
      void tick();
    },
  };
}

export interface PipelinePoll {
  /** 最近一次成功读到的数据；读取失败时保留 */
  data: PipelineResponse | null;
  /** 最近一次读取失败的原因；成功后清空 */
  error: ApiError | null;
  /** 最近一次成功读取的本机时间（毫秒），用于两次轮询之间本地走表 */
  receivedAt: number | null;
  refresh: () => void;
}

export function usePipeline(): PipelinePoll {
  const [state, setState] = useState<Omit<PipelinePoll, 'refresh'>>({ data: null, error: null, receivedAt: null });
  const handle = useRef<PollHandle | null>(null);
  useEffect(() => {
    const h = startPipelinePolling(
      (signal) => api.getPipeline(signal),
      pipelineDelay,
      (data) => setState({ data, error: null, receivedAt: Date.now() }),
      (error) => setState((prev) => ({ ...prev, error })),
    );
    handle.current = h;
    return () => {
      h.stop();
      handle.current = null;
    };
  }, []);
  const refresh = useCallback(() => handle.current?.poke(), []);
  return { ...state, refresh };
}
