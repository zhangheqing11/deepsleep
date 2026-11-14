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

// ---------- 最近运行：服务端列表的本机后备缓存 ----------

const RUN_HISTORY_KEY = 'deepsleep.runHistory.v1';
const RUN_HISTORY_MAX = 20;

export interface RunHistoryEntry {
  run_id: string;
  adapter: string;
  created_at: string;
  split: string;
  /** 请求时填的版本；拿到运行状态后改成后端返回的实际版本 */
  playbook_version: string | null;
  status: string | null;
}

export const runHistoryStore = {
  list(adapter: string): RunHistoryEntry[] {
    const all = readJson<RunHistoryEntry[]>('local', RUN_HISTORY_KEY) ?? [];
    return all.filter((e) => e.adapter === adapter);
  },
  cache(adapter: string, entries: RunHistoryEntry[]): void {
    const others = (readJson<RunHistoryEntry[]>('local', RUN_HISTORY_KEY) ?? []).filter((e) => e.adapter !== adapter);
    const recent = [...entries].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)).slice(0, RUN_HISTORY_MAX);
    writeJson('local', RUN_HISTORY_KEY, [...recent, ...others].slice(0, RUN_HISTORY_MAX));
  },
  upsert(entry: Pick<RunHistoryEntry, 'run_id' | 'adapter'> & Partial<RunHistoryEntry>): void {
    const all = readJson<RunHistoryEntry[]>('local', RUN_HISTORY_KEY) ?? [];
    const i = all.findIndex((e) => e.run_id === entry.run_id && e.adapter === entry.adapter);
    if (i >= 0) {
      all[i] = { ...all[i], ...entry };
    } else {
      all.unshift({
        created_at: new Date().toISOString(),
        split: '',
        playbook_version: null,
        status: null,
        ...entry,
      });
    }
    writeJson('local', RUN_HISTORY_KEY, all.slice(0, RUN_HISTORY_MAX));
  },
  remove(adapter: string, runId: string): void {
    const all = readJson<RunHistoryEntry[]>('local', RUN_HISTORY_KEY) ?? [];
    writeJson(
      'local',
      RUN_HISTORY_KEY,
      all.filter((e) => !(e.adapter === adapter && e.run_id === runId)),
    );
  },
};

// ---------- 未确认的创建请求：网络失败后重试复用同一个 Idempotency-Key ----------

const PENDING_CREATE_KEY = 'deepsleep.pendingCreate.v1';

export interface PendingCreate {
  idempotency_key: string;
  body: { split: 'A' | 'B'; playbook_version?: string };
  /** 后端 Mock 场景；重试必须沿用，否则后端按“同 key 不同请求”返回 409 */
  mock_scenario?: 'normal' | 'fail' | 'report_delay';
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
