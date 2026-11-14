// ⚠ 用户端交互演示的本机存储：偏好与“我记住的事”。
// 只保存在这台设备的浏览器里，不同步到任何账号；后端偏好 / 记忆接口确定后替换为真实接口。

import { useSyncExternalStore } from 'react';
import { readJson, writeJson } from './storage';

// ---------- 偏好 ----------

export type ThemeChoice = 'system' | 'light' | 'dark';

export interface Preferences {
  schedule: {
    /** "HH:MM" 或空字符串（未设置） */
    wake_target: string;
    shift_work: boolean;
    habits: string[];
  };
  communication: {
    style: 'listen_first' | 'brief_advice';
    length: 'short' | 'medium';
    reminders: boolean;
  };
  memory: {
    enabled: boolean;
    paused: boolean;
  };
  privacy: {
    retention: 'session' | 'days_7' | 'days_30';
  };
  appearance: {
    theme: ThemeChoice;
    font: 'standard' | 'large';
  };
}

export const DEFAULT_PREFERENCES: Preferences = {
  schedule: { wake_target: '', shift_work: false, habits: [] },
  communication: { style: 'listen_first', length: 'short', reminders: false },
  memory: { enabled: true, paused: false },
  privacy: { retention: 'session' },
  appearance: { theme: 'system', font: 'standard' },
};

export const HABIT_OPTIONS = ['睡前刷手机', '周末补觉', '晚上喝咖啡或茶', '躺在床上想事情', '作息不固定'];

const PREFS_KEY = 'deepsleep.demo.prefs.v1';
const MEMORIES_KEY = 'deepsleep.demo.memories.v1';

function mergeDefaults(p: Partial<Preferences> | null): Preferences {
  const d = DEFAULT_PREFERENCES;
  return {
    schedule: { ...d.schedule, ...p?.schedule },
    communication: { ...d.communication, ...p?.communication },
    memory: { ...d.memory, ...p?.memory },
    privacy: { ...d.privacy, ...p?.privacy },
    appearance: { ...d.appearance, ...p?.appearance },
  };
}

function createStore<T>(read: () => T) {
  let snapshot = read();
  const listeners = new Set<() => void>();
  return {
    get: () => snapshot,
    subscribe(l: () => void) {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    refresh() {
      snapshot = read();
      listeners.forEach((l) => l());
    },
  };
}

const prefsStore = createStore(() => mergeDefaults(readJson<Partial<Preferences>>('local', PREFS_KEY)));

export function useSavedPreferences(): Preferences {
  return useSyncExternalStore(prefsStore.subscribe, prefsStore.get, prefsStore.get);
}

export function getSavedPreferences(): Preferences {
  return prefsStore.get();
}

/** 演示用的“保存”：模拟一次网络往返，可选模拟失败 */
export async function savePreferencesDemo(p: Preferences, opts: { fail?: boolean } = {}): Promise<void> {
  await new Promise((r) => window.setTimeout(r, 500));
  if (opts.fail) throw new Error('模拟：保存失败');
  writeJson('local', PREFS_KEY, p);
  prefsStore.refresh();
}

/** 外观是本机即时设置，不走“保存”演示：立刻写入并生效。 */
export function setThemeChoice(theme: ThemeChoice): void {
  const p = prefsStore.get();
  writeJson('local', PREFS_KEY, { ...p, appearance: { ...p.appearance, theme } });
  prefsStore.refresh();
}

// ---------- 我记住的事 ----------

export interface MemoryItem {
  id: string;
  text: string;
  source: string;
  created_at: string;
  /** ISO 时间或 null（不过期） */
  valid_until: string | null;
}

const memoryStore = createStore(() => readJson<MemoryItem[]>('local', MEMORIES_KEY) ?? []);

export function useMemories(): MemoryItem[] {
  return useSyncExternalStore(memoryStore.subscribe, memoryStore.get, memoryStore.get);
}

function writeMemories(items: MemoryItem[]) {
  writeJson('local', MEMORIES_KEY, items);
  memoryStore.refresh();
}

export const memories = {
  add(item: Omit<MemoryItem, 'id' | 'created_at'>): MemoryItem {
    const m: MemoryItem = {
      ...item,
      id: `mem_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
      created_at: new Date().toISOString(),
    };
    writeMemories([m, ...memoryStore.get()]);
    return m;
  },
  update(id: string, text: string) {
    writeMemories(memoryStore.get().map((m) => (m.id === id ? { ...m, text } : m)));
  },
  remove(id: string) {
    writeMemories(memoryStore.get().filter((m) => m.id !== id));
  },
};

export function isExpired(m: MemoryItem, now = Date.now()): boolean {
  return m.valid_until !== null && new Date(m.valid_until).getTime() < now;
}

// ---------- 外观 ----------

export function applyAppearance(a: Preferences['appearance']): void {
  const el = document.documentElement;
  if (a.theme === 'system') delete el.dataset.theme;
  else el.dataset.theme = a.theme;
  if (a.font === 'large') el.dataset.font = 'large';
  else delete el.dataset.font;
}

// ---------- 演示调试开关（只在内存里，刷新即恢复） ----------

export interface DemoFlags {
  /** 下一条聊天消息模拟发送失败 */
  chatFailNext: boolean;
  /** 下一次保存偏好模拟失败 */
  saveFailNext: boolean;
}

let flags: DemoFlags = { chatFailNext: false, saveFailNext: false };
const flagListeners = new Set<() => void>();

export const demoFlags = {
  get: () => flags,
  set(patch: Partial<DemoFlags>) {
    flags = { ...flags, ...patch };
    flagListeners.forEach((l) => l());
  },
  subscribe(l: () => void) {
    flagListeners.add(l);
    return () => flagListeners.delete(l);
  },
  /** 读取并清除一次性开关 */
  take(key: keyof DemoFlags): boolean {
    const v = flags[key];
    if (v) demoFlags.set({ [key]: false });
    return v;
  },
};

export function useDemoFlags(): DemoFlags {
  return useSyncExternalStore(demoFlags.subscribe, demoFlags.get, demoFlags.get);
}
