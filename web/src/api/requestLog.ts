// 调试用的请求记录（只在内存里，刷新即清空）。控制台“调试”页读取它。
// 只记录操作名、参数里的 ID、结果、耗时和 request_id，不记录请求体内容。

import { useSyncExternalStore } from 'react';
import type { ApiClient } from './client';
import { isAbortError, toApiError } from './errors';

export interface RequestLogEntry {
  seq: number;
  at: string;
  op: string;
  target: string;
  ok: boolean;
  aborted: boolean;
  duration_ms: number;
  status?: number;
  code?: string;
  kind?: string;
  message?: string;
  request_id?: string;
}

const MAX = 60;
let entries: RequestLogEntry[] = [];
let seq = 0;
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((l) => l());
}

export const requestLog = {
  subscribe(l: () => void) {
    listeners.add(l);
    return () => listeners.delete(l);
  },
  snapshot: () => entries,
  clear() {
    entries = [];
    emit();
  },
};

export function useRequestLog(): RequestLogEntry[] {
  return useSyncExternalStore(requestLog.subscribe, requestLog.snapshot, requestLog.snapshot);
}

async function track<T>(op: string, target: string, fn: () => Promise<T>): Promise<T> {
  const started = performance.now();
  const base = { seq: ++seq, at: new Date().toISOString(), op, target };
  const push = (e: RequestLogEntry) => {
    entries = [e, ...entries].slice(0, MAX);
    emit();
  };
  try {
    const result = await fn();
    push({ ...base, ok: true, aborted: false, duration_ms: performance.now() - started });
    return result;
  } catch (e) {
    const err = toApiError(e);
    push({
      ...base,
      ok: false,
      aborted: isAbortError(e),
      duration_ms: performance.now() - started,
      status: err.status,
      code: err.code,
      kind: err.kind,
      message: err.message,
      request_id: err.requestId,
    });
    throw e;
  }
}

export function withRequestLog(client: ApiClient): ApiClient {
  return {
    adapter: client.adapter,
    health: (signal) => track('GET /health', '', () => client.health(signal)),
    createRun: (body, key, signal) =>
      track('POST /runs', `${body.split}${body.playbook_version ? `/${body.playbook_version}` : ''}`, () =>
        client.createRun(body, key, signal),
      ),
    getRun: (runId, signal) => track('GET /runs/{id}', runId, () => client.getRun(runId, signal)),
    getReport: (runId, signal) => track('GET /runs/{id}/report', runId, () => client.getReport(runId, signal)),
    listSessions: (runId, signal) =>
      track('GET /runs/{id}/sessions', runId, () => client.listSessions(runId, signal)),
    getSession: (runId, visitorId, signal) =>
      track('GET /runs/{id}/sessions/{vid}', `${runId} · ${visitorId}`, () =>
        client.getSession(runId, visitorId, signal),
      ),
  };
}
