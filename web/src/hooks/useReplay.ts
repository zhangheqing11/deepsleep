import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import type { Session } from '../api/contractTypes';
import { isAbortError, toApiError, type ApiError } from '../api/errors';
import { POLL_BACKOFF_MS } from '../config';
import { createCatalogCache, readCatalog, type Catalog } from '../lib/replay';
import { useResource, type ResourceState } from './useResource';

const ACTIVE_MS = 2000;
const IDLE_MS = 6000;

export interface CatalogState {
  /** undefined = 还没读到；null = 后端没有实验 */
  catalog: Catalog | null | undefined;
  error: ApiError | null;
  reload: () => void;
}

/**
 * 用户端的读取循环：实验在跑的时候跟着刷新，跑完后放慢；失败时保留上一份并自己重试。
 * 明早现场跑完两次运行后，页面不用刷新就能换成当场的会谈。
 */
export function useCatalog(): CatalogState {
  const [state, setState] = useState<Omit<CatalogState, 'reload'>>({ catalog: undefined, error: null });
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    const cache = createCatalogCache();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    let signature = '';

    async function tick() {
      try {
        const catalog = await readCatalog(api, cache, controller.signal);
        if (controller.signal.aborted) return;
        failures = 0;
        // 内容没变就不换对象，免得正在看的会谈被无谓地重渲染
        const next = catalog
          ? [catalog.experimentId, catalog.stage, catalog.before?.runId, catalog.after?.runId, catalog.visitors.length,
            catalog.before?.report ? 1 : 0, catalog.after?.report ? 1 : 0, catalog.learned.length, catalog.outcome].join('|')
          : 'none';
        if (next !== signature) {
          signature = next;
          setState({ catalog, error: null });
        } else {
          setState((prev) => (prev.error ? { ...prev, error: null } : prev));
        }
        const settled = catalog !== null && (catalog.stage === 'done' || catalog.stage === 'failed');
        timer = setTimeout(tick, settled ? IDLE_MS : ACTIVE_MS);
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

// 已完成运行的会谈不会再变：整个页面共用一份缓存，首页读过开场白的会谈点进去不用再等。
const sessions = new Map<string, Promise<Session>>();

function loadSession(runId: string, visitorId: string): Promise<Session> {
  const key = `${runId}/${visitorId}`;
  let p = sessions.get(key);
  if (!p) {
    p = api.getSession(runId, visitorId);
    sessions.set(key, p);
    p.catch(() => sessions.delete(key));
  }
  return p;
}

export function useSession(runId: string | null, visitorId: string | null): ResourceState<Session> & { reload: () => void } {
  const key = runId && visitorId ? `${runId}/${visitorId}` : null;
  return useResource<Session>(key, () => loadSession(runId as string, visitorId as string));
}
