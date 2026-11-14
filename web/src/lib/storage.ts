// 浏览器存储的安全封装：隐私窗口、存储被禁用时读写都可能抛错，这里一律吞掉并回退。

type Area = 'local' | 'session';

function area(kind: Area): Storage | null {
  try {
    return kind === 'local' ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

export function readJson<T>(kind: Area, key: string): T | null {
  try {
    const raw = area(kind)?.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function writeJson(kind: Area, key: string, value: unknown): void {
  try {
    area(kind)?.setItem(key, JSON.stringify(value));
  } catch {
    /* 存储不可用时只影响刷新恢复，不影响当前页面 */
  }
}

export function removeKey(kind: Area, key: string): void {
  try {
    area(kind)?.removeItem(key);
  } catch {
    /* ignore */
  }
}

// ---------- 当前运行：刷新后据此继续查询 ----------

const CURRENT_RUN_KEY = 'deepsleep.currentRun.v1';

export interface SavedRun {
  run_id: string;
  adapter: string;
  saved_at: string;
}

export const currentRunStore = {
  get: (): SavedRun | null => readJson<SavedRun>('local', CURRENT_RUN_KEY),
  set: (run: SavedRun) => writeJson('local', CURRENT_RUN_KEY, run),
  clear: () => removeKey('local', CURRENT_RUN_KEY),
};

// ---------- 未确认的创建请求：网络失败后重试复用同一个 Idempotency-Key ----------

const PENDING_CREATE_KEY = 'deepsleep.pendingCreate.v1';

export interface PendingCreate {
  idempotency_key: string;
  body: { split: 'A' | 'B'; playbook_version?: string };
  adapter: string;
  first_attempt_at: string;
}

export const pendingCreateStore = {
  get: (): PendingCreate | null => readJson<PendingCreate>('session', PENDING_CREATE_KEY),
  set: (p: PendingCreate) => writeJson('session', PENDING_CREATE_KEY, p),
  clear: () => removeKey('session', PENDING_CREATE_KEY),
};

export function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // 非安全上下文（如手机通过局域网 http 访问）没有 randomUUID
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}
