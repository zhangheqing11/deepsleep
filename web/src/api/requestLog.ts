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

// 让 HTTP 适配器把成功响应的 X-Request-ID 和状态码交给当前这条记录。
// track 调用 fn() 时同步设置，httpClient 在发请求前（第一个 await 之前）同步领取，所以不会串到别的请求上。
export interface ResponseMeta {
  request_id?: string;
  status?: number;
}
let pendingMeta: ResponseMeta | null = null;

export function claimResponseMeta(): ResponseMeta | null {
  const m = pendingMeta;
  pendingMeta = null;
  return m;
}

async function track<T>(op: string, target: string, fn: () => Promise<T>): Promise<T> {
  const started = performance.now();
  const base = { seq: ++seq, at: new Date().toISOString(), op, target };
  const meta: ResponseMeta = {};
  const push = (e: RequestLogEntry) => {
    entries = [e, ...entries].slice(0, MAX);
    emit();
  };
  try {
    pendingMeta = meta;
    const promise = fn();
    pendingMeta = null;
    const result = await promise;
    push({
      ...base,
      ok: true,
      aborted: false,
      duration_ms: performance.now() - started,
      status: meta.status,
      request_id: meta.request_id,
    });
    return result;
  } catch (e) {
    pendingMeta = null;
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
    createRun: (body, key, signal, mockScenario) =>
      track(
        'POST /runs',
        `${body.split}${body.playbook_version ? `/${body.playbook_version}` : ''}${mockScenario ? ` · 场景 ${mockScenario}` : ''}`,
        () => client.createRun(body, key, signal, mockScenario),
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
