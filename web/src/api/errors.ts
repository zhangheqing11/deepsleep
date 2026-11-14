// 统一的前端错误类型。区分四类：
// network          请求没到达后端或没收到响应（断网、后端未启动、代理 502 无 JSON）
// http             后端返回了非 2xx（带错误码时是业务可识别的错误）
// invalid_response 2xx 但响应体不是预期的 JSON
// aborted          组件卸载或切换任务时主动取消，不应显示给用户

export type ApiErrorKind = 'network' | 'http' | 'invalid_response' | 'aborted';

export interface ApiErrorInit {
  kind: ApiErrorKind;
  message: string;
  status?: number;
  code?: string;
  requestId?: string;
  details?: { field?: string; message: string }[];
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly code?: string;
  readonly requestId?: string;
  readonly details?: { field?: string; message: string }[];

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = 'ApiError';
    this.kind = init.kind;
    this.status = init.status;
    this.code = init.code;
    this.requestId = init.requestId;
    this.details = init.details;
  }

  /** 5xx 或网络问题：值得退避重试 */
  get isTransient(): boolean {
    return this.code !== 'RUNS_VIA_CLI' && (this.kind === 'network' || (this.kind === 'http' && (this.status ?? 0) >= 500));
  }
}

export function isAbortError(e: unknown): boolean {
  if (e instanceof ApiError) return e.kind === 'aborted';
  return e instanceof DOMException && e.name === 'AbortError';
}

export function toApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  if (isAbortError(e)) return new ApiError({ kind: 'aborted', message: '请求已取消' });
  return new ApiError({ kind: 'invalid_response', message: e instanceof Error ? e.message : String(e) });
}

/** 已知错误码的前端中文文案；未知错误码使用后端 message */
const CODE_MESSAGES: Record<string, string> = {
  RUN_NOT_FOUND: '未找到该运行记录',
  SESSION_NOT_FOUND: '未找到该会谈记录',
  REPORT_NOT_READY: '报告尚未生成',
  RUN_CONFLICT: '当前操作与运行状态冲突',
  IDEMPOTENCY_KEY_REUSED: '同一提交标识对应了不同的请求内容，已拒绝重复创建',
  VALIDATION_ERROR: '请求参数不合法',
  SERVICE_UNAVAILABLE: '依赖服务暂不可用，请稍后重试',
};

export function describeError(e: ApiError): string {
  switch (e.kind) {
    case 'network':
      return '无法连接后端服务，请检查服务是否启动或网络是否正常';
    case 'invalid_response':
      return '后端返回的数据格式不符合预期';
    case 'aborted':
      return '请求已取消';
    case 'http':
      if (e.code && CODE_MESSAGES[e.code]) return CODE_MESSAGES[e.code];
      return e.message || `服务返回错误（HTTP ${e.status ?? '未知'}）`;
  }
}
