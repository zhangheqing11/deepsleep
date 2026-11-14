import { useEffect, useRef, useState } from 'react';
import { SerialPoller, type PollerOptions, type PollSnapshot } from '../lib/poller';

const IDLE: PollSnapshot<never> = {
  data: null,
  error: null,
  failures: 0,
  lastSuccessAt: null,
  stale: false,
  done: false,
  inFlight: false,
};

export type PollHandle<T> = PollSnapshot<T> & { retryNow: () => void; enabled: boolean };

/**
 * key 变化（或 enabled 变化）时停止旧轮询、清空数据、开始新的；卸载时取消在途请求。
 * key 为 null 表示不轮询（例如运行还没开始）。
 */
export function usePoller<T>(key: string | null, opts: Omit<PollerOptions<T>, 'onUpdate'>): PollHandle<T> {
  const [snap, setSnap] = useState<PollSnapshot<T>>(IDLE);
  const pollerRef = useRef<SerialPoller<T> | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    setSnap(IDLE);
    if (key === null) return;
    const o = optsRef.current;
    const poller = new SerialPoller<T>({ ...o, fetch: (s) => optsRef.current.fetch(s), onUpdate: setSnap });
    pollerRef.current = poller;
    poller.start();
    return () => {
      poller.stop();
      if (pollerRef.current === poller) pollerRef.current = null;
    };
  }, [key]);

  return { ...snap, enabled: key !== null, retryNow: () => pollerRef.current?.retryNow() };
}
