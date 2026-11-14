// HTTP 适配器：只发 GET。失败一律抛 ApiError，不回退到 mock。
// 单次超时、取消、退避由 lib/poller.ts 负责；这里只做请求、错误信封解析和结构校验。
// 读接口由后端 api/read_routes.py 提供（#38，规格见 api/READ_API.md）。

import type { DataClient } from './client';
import { ApiError } from './errors';
import { parseEvolution, parseEvolveStatus, parseExperiment, parseReport, parseRunState } from './validate';
import { ShapeError } from '../lib/shape';

export type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

function readEnvelope(body: unknown): { code?: string; message?: string; request_id?: string } {
  if (typeof body !== 'object' || body === null) return {};
  const err = (body as { error?: unknown }).error;
  if (typeof err !== 'object' || err === null) return {};
  const e = err as Record<string, unknown>;
  return {
    code: typeof e.code === 'string' ? e.code : undefined,
    message: typeof e.message === 'string' ? e.message : undefined,
    request_id: typeof e.request_id === 'string' ? e.request_id : undefined,
  };
}

export function createHttpClient(baseUrl: string, fetchImpl: FetchLike = (i, init) => fetch(i, init)): DataClient {
  async function getJson<T>(path: string, signal: AbortSignal, parse: (body: unknown) => T): Promise<T> {
    let res: Response;
    try {
      res = await fetchImpl(`${baseUrl}${path}`, {
        method: 'GET',
        headers: { Accept: 'application/json' },
        signal,
        cache: 'no-store',
      });
    } catch (e) {
      if (signal.aborted) throw new ApiError({ kind: 'aborted', message: '请求已取消' });
      throw new ApiError({ kind: 'network', message: e instanceof Error ? e.message : String(e) });
    }
    const headerRequestId = res.headers.get('X-Request-ID') ?? undefined;
    let body: unknown = undefined;
    const text = await res.text().catch(() => '');
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = undefined;
      }
    }
    if (!res.ok) {
      const env = readEnvelope(body);
      // 没有统一错误结构的 5xx（例如开发代理连不上后端）按网络问题处理。
      if (res.status >= 500 && !env.code) {
        throw new ApiError({ kind: 'network', status: res.status, message: `HTTP ${res.status}`, requestId: headerRequestId });
      }
      throw new ApiError({
        kind: 'http',
        status: res.status,
        code: env.code,
        message: env.message ?? `HTTP ${res.status}`,
        requestId: env.request_id ?? headerRequestId,
      });
    }
    if (body === undefined) {
      throw new ApiError({ kind: 'invalid_response', status: res.status, message: '响应不是 JSON', requestId: headerRequestId });
    }
    try {
      return parse(body);
    } catch (e) {
      const msg = e instanceof ShapeError ? e.message : e instanceof Error ? e.message : String(e);
      throw new ApiError({ kind: 'invalid_response', status: res.status, message: msg, requestId: headerRequestId });
    }
  }

  const seg = encodeURIComponent;
  return {
    mode: 'http',
    getExperiment: (signal) => getJson('/demo/experiment', signal, parseExperiment),
    getRunState: (id, signal) => getJson(`/runs/${seg(id)}`, signal, (b) => parseRunState(b, id)),
    getReport: (id, signal) => getJson(`/runs/${seg(id)}/report`, signal, (b) => parseReport(b, id)),
    getEvolveStatus: (id, signal) => getJson(`/evolutions/${seg(id)}/status`, signal, (b) => parseEvolveStatus(b, id)),
    getEvolution: (id, signal) => getJson(`/evolutions/${seg(id)}`, signal, (b) => parseEvolution(b, id)),
  };
}
