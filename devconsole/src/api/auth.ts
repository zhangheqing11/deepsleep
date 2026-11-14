// 登录状态：对接后端的本地演示账号（POST /auth/login、POST /auth/logout、GET /auth/me）。
// 与 web/src/api/auth.ts 同一套约定，但进化后台是独立应用，自己保存令牌：
// - 后端没开登录（API_AUTH_MODE=none，默认）时 /auth/me 返回 authenticated:false，不出现登录页。
// - 令牌只放在 sessionStorage（关掉标签页即失效），键名与 web 控制台不同；从控制台侧栏新标签页跳过来需要重新登录。
// - 后端重启后令牌失效：任何只读接口返回 401 都会清掉令牌，回到登录页。
// - 进化后台的数据请求仍然全是 GET；登录和退出是仅有的两个 POST，不碰任何运行或进化数据。
import { useSyncExternalStore } from 'react';
import { API_BASE_URL, MODE_SETTING } from '../config';
import { ApiError } from './errors';

export interface AuthUser {
  id: string;
  display_name: string;
  role: string;
}

export type SignedOutReason = 'required' | 'expired' | 'left';

export type AuthState =
  | { state: 'checking' }
  /** 后端没开登录，或使用模拟数据：页面直接可用 */
  | { state: 'open' }
  | { state: 'signed-out'; reason: SignedOutReason }
  | { state: 'signed-in'; user: AuthUser };

const TOKEN_KEY = 'deepsleep.devconsole.token.v1';
/** 这些 401 表示“需要重新登录”；账号密码错误（INVALID_CREDENTIALS）不在其中 */
const SESSION_CODES = new Set(['AUTH_REQUIRED', 'INVALID_TOKEN', 'TOKEN_EXPIRED']);

let memoryToken: string | null = null;

function storage(): Storage | null {
  try {
    return typeof window !== 'undefined' ? (window.sessionStorage ?? null) : null;
  } catch {
    return null;
  }
}

function readStoredToken(): string | null {
  try {
    return storage()?.getItem(TOKEN_KEY) ?? null;
  } catch {
    return null;
  }
}

function setToken(token: string | null): void {
  memoryToken = token;
  try {
    if (token === null) storage()?.removeItem(TOKEN_KEY);
    else storage()?.setItem(TOKEN_KEY, token);
  } catch {
    // 存不进去（隐私模式等）：本次页面内仍然可用，刷新后需要重新登录
  }
}

/** 每个请求带上的鉴权头；没有令牌时为空对象（后端没开登录时不需要）。 */
export function authHeader(): Record<string, string> {
  const token = memoryToken ?? readStoredToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

let current: AuthState = MODE_SETTING.ok && MODE_SETTING.mode === 'http' ? { state: 'checking' } : { state: 'open' };
const listeners = new Set<() => void>();

function set(next: AuthState): void {
  current = next;
  listeners.forEach((l) => l());
}
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};
const get = () => current;

export function useAuth(): AuthState {
  return useSyncExternalStore(subscribe, get, get);
}

export function getAuthState(): AuthState {
  return current;
}

async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...authHeader(),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: 'no-store',
    });
  } catch (e) {
    throw new ApiError({ kind: 'network', message: e instanceof Error ? e.message : '网络错误' });
  }
  let data: unknown;
  try {
    data = await res.json();
  } catch {
    data = undefined;
  }
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string } } | undefined)?.error;
    throw new ApiError({
      kind: err?.code || res.status < 500 ? 'http' : 'network',
      status: res.status,
      code: err?.code,
      message: err?.message ?? `服务返回 HTTP ${res.status}`,
    });
  }
  if (data === undefined) throw new ApiError({ kind: 'invalid_response', status: res.status, message: '响应不是 JSON' });
  return data as T;
}

/**
 * 进入页面时问一次后端：要不要登录、现在是谁。
 * 后端连不上时不拦页面（页面自己有“接口不可用”提示）；等它恢复后若返回 401，会由 noteUnauthorized 带回登录页。
 */
export async function refreshAuth(): Promise<void> {
  if (!(MODE_SETTING.ok && MODE_SETTING.mode === 'http')) return set({ state: 'open' });
  try {
    const me = await call<{ authenticated: boolean; user: AuthUser | null }>('GET', '/auth/me');
    if (me.authenticated && me.user) set({ state: 'signed-in', user: me.user });
    else {
      setToken(null);
      set({ state: 'open' });
    }
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      const hadToken = authHeader().Authorization !== undefined;
      setToken(null);
      set({ state: 'signed-out', reason: hadToken ? 'expired' : 'required' });
    } else {
      set({ state: 'open' });
    }
  }
}

/** 登录。账号或密码不对时抛出 ApiError（code=INVALID_CREDENTIALS），状态保持未登录。 */
export async function signIn(username: string, password: string): Promise<void> {
  const res = await call<{ access_token: string; user: AuthUser }>('POST', '/auth/login', { username, password });
  if (typeof res.access_token !== 'string' || !res.user) {
    throw new ApiError({ kind: 'invalid_response', message: '登录响应缺少令牌' });
  }
  setToken(res.access_token);
  set({ state: 'signed-in', user: res.user });
}

export async function signOut(): Promise<void> {
  try {
    await call('POST', '/auth/logout');
  } catch {
    // 后端不可达也要在本机退出
  }
  setToken(null);
  set({ state: 'signed-out', reason: 'left' });
}

/**
 * 数据请求收到 401 时由 httpClient 调用：令牌缺失、无效或过期都回到登录页。
 * 账号密码错误（INVALID_CREDENTIALS）只会出现在登录请求里，不会走到这里。
 */
export function noteUnauthorized(code: string | undefined): void {
  if (code !== undefined && !SESSION_CODES.has(code)) return;
  if (current.state === 'signed-out') return;
  const hadToken = authHeader().Authorization !== undefined;
  setToken(null);
  set({ state: 'signed-out', reason: hadToken ? 'expired' : 'required' });
}
