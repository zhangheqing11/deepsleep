import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { isAbortError, toApiError, type ApiError } from '../api/errors';
import { POLL_BACKOFF_MS, POLL_INTERVAL_MS } from '../config';
import { createBoardCache, readBoard, type BoardData } from '../lib/board';

/** 实验结束或尚未开始时放慢轮询；操作员重置并发起新实验后页面自己跟上。 */
const IDLE_INTERVAL_MS = 3000;

export interface BoardState {
  data: BoardData | null;
  /** 最近一次读取失败的原因；成功后清空。data 仍保留上一份。 */
  error: ApiError | null;
  /** 最近一次成功读取的时间 */
  updatedAt: number | null;
  reload: () => void;
}

/**
 * 看板的读取循环：串行、卸载时取消。
 * 与控制台的轮询不同，这里任何失败都不停止——展位上的页面要在后端恢复后自己接上，
 * 失败期间保留最后一份数据并交给页面标注时间。
 */
export function useBoard(): BoardState {
  const [state, setState] = useState<Omit<BoardState, 'reload'>>({ data: null, error: null, updatedAt: null });
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    const cache = createBoardCache();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;

    async function tick() {
      try {
        const data = await readBoard(api, cache, controller.signal);
        if (controller.signal.aborted) return;
        failures = 0;
        setState({ data, error: null, updatedAt: Date.now() });
        const stage = data.experiment?.stage;
        const active = stage !== undefined && stage !== 'done' && stage !== 'failed';
        const pendingReport = [data.run1, data.control, data.run2].some((s) => s.node?.state === 'done' && !s.report);
        timer = setTimeout(tick, active || pendingReport ? POLL_INTERVAL_MS : IDLE_INTERVAL_MS);
      } catch (e) {
        if (controller.signal.aborted || isAbortError(e)) return;
        setState((prev) => ({ ...prev, error: toApiError(e) }));
        timer = setTimeout(tick, POLL_BACKOFF_MS[Math.min(failures++, POLL_BACKOFF_MS.length - 1)]);
      }
    }
    void tick();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [nonce]);

  return { ...state, reload };
}
