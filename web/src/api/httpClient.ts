import { API_BASE_URL } from '../config';
import type { ApiClient } from './client';
import type { RunReport, Session } from './contractTypes';
import type {
  CreateRunResponse,
  ErrorEnvelope,
  HealthResponse,
  ListResponse,
  RunStatusResponse,
  SessionListItem,
} from './draftTypes';
import { ApiError } from './errors';

interface RequestOptions {
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

function isErrorEnvelope(v: unknown): v is ErrorEnvelope {
  if (typeof v !== 'object' || v === null) return false;
  const err = (v as { error?: unknown }).error;
  return typeof err === 'object' && err !== null && typeof (err as { code?: unknown }).code === 'string';
}

async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const { body, headers, signal } = opts;
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      signal,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    if (signal?.aborted) throw new ApiError({ kind: 'aborted', message: '请求已取消' });
    throw new ApiError({ kind: 'network', message: e instanceof Error ? e.message : '网络错误' });
  }

  const headerRequestId = res.headers.get('X-Request-ID') ?? undefined;
  let text: string;
  try {
    text = await res.text();
  } catch (e) {
    if (signal?.aborted) throw new ApiError({ kind: 'aborted', message: '请求已取消' });
    throw new ApiError({ kind: 'network', message: '读取响应失败', status: res.status, requestId: headerRequestId });
  }

  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = undefined;
    }
  }

  if (!res.ok) {
    if (isErrorEnvelope(data)) {
      throw new ApiError({
        kind: 'http',
        status: res.status,
        code: data.error.code,
        message: data.error.message,
        requestId: data.error.request_id ?? headerRequestId,
        details: data.error.details,
      });
    }
    // 没有统一错误结构的 5xx（例如开发代理连不上后端时的空 500、网关 502 的 HTML）：
    // 不是后端业务返回的错误，按“连不上后端”处理
    throw new ApiError({
      kind: res.status >= 500 ? 'network' : 'http',
      status: res.status,
      message: `服务返回 HTTP ${res.status}`,
      requestId: headerRequestId,
    });
  }

  if (data === undefined) {
    throw new ApiError({
      kind: 'invalid_response',
      status: res.status,
      message: '响应不是 JSON',
      requestId: headerRequestId,
    });
  }
  return data as T;
}

const enc = encodeURIComponent;

export const httpClient: ApiClient = {
  adapter: 'http',
  health: (signal) => request<HealthResponse>('GET', '/health', { signal }),
  createRun: (body, idempotencyKey, signal) =>
    request<CreateRunResponse>('POST', '/runs', {
      body,
      headers: { 'Idempotency-Key': idempotencyKey },
      signal,
    }),
  getRun: (runId, signal) => request<RunStatusResponse>('GET', `/runs/${enc(runId)}`, { signal }),
  getReport: (runId, signal) => request<RunReport>('GET', `/runs/${enc(runId)}/report`, { signal }),
  listSessions: (runId, signal) =>
    request<ListResponse<SessionListItem>>('GET', `/runs/${enc(runId)}/sessions`, { signal }),
  getSession: (runId, visitorId, signal) =>
    request<Session>('GET', `/runs/${enc(runId)}/sessions/${enc(visitorId)}`, { signal }),
};
