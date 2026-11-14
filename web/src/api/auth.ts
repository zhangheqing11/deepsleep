// 登录状态：对接后端的本地演示账号（POST /auth/login、/auth/register、/auth/logout，GET /auth/me）。
// - 后端没有开启登录（API_AUTH_MODE=none，默认）时 /auth/me 返回 authenticated:false，前端不出现登录页。
// - 令牌只放在 sessionStorage：关掉标签页即失效；后端重启后令牌也会失效，此时任何接口返回 401 都会回到登录页。
// - 这里的请求不经过 requestLog：账号和密码不进入调试页的请求记录。
import { useSyncExternalStore } from 'react';
import { API_ADAPTER, API_BASE_URL } from '../config';
import { ApiError } from './errors';

export interface AuthUser {
  id: string;
  display_name: string;
  role: string;
}

export type AuthState =
  | { state: 'checking' }
  /** 后端未启用登录，或使用前端本地模拟：所有页面直接可用 */
  | { state: 'open' }
  | { state: 'signed-out'; reason: 'required' | 'expired' | 'left' }
  /** fresh：这次是刚注册进来的，用户视角据此显示一次欢迎说明 */
  | { state: 'signed-in'; user: AuthUser; fresh?: boolean };

const TOKEN_KEY = 'deepsleep.auth.token.v1';
/** 这些 401 表示“需要重新登录”；账号密码错误（INVALID_CREDENTIALS）不在其中 */
const SESSION_CODES = new Set(['AUTH_REQUIRED', 'INVALID_TOKEN', 'TOKEN_EXPIRED']);

function storage(): Storage | null {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null;
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  try {
    return storage()?.getItem(TOKEN_KEY) ?? null;
  } catch {
    return null;
  }
}

function setToken(token: string | null): void {
  try {
    if (token === null) storage()?.removeItem(TOKEN_KEY);
    else storage()?.setItem(TOKEN_KEY, token);
  } catch {
    // 存不进去（隐私模式等）：本次页面内仍然可用，刷新后需要重新登录
  }
  memoryToken = token;
}

let memoryToken: string | null = null;
export function authHeader(): Record<string, string> {
  const token = memoryToken ?? getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

let current: AuthState = API_ADAPTER === 'http' ? { state: 'checking' } : { state: 'open' };
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

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...authHeader() },
      body: body !== undefined ? JSON.stringify(body) : undefined,
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
 * 后端连不上时不拦页面（各页有自己的“后端不可用”提示）；等它恢复后若返回 401，会由 noteUnauthorized 带回登录页。
 */
export async function refreshAuth(): Promise<void> {
  if (API_ADAPTER !== 'http') return set({ state: 'open' });
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

/** 账号 3–32 位字母、数字或 _ . -；密码至少 6 位。与后端的校验一致，先在本机拦一遍。 */
export function registrationProblem(username: string, password: string): string | null {
  if (!/^[A-Za-z0-9_.-]{3,32}$/.test(username)) return '账号用 3–32 位字母、数字或 _ . -。';
  if (password.length < 6) return '密码至少 6 位。';
  return null;
}

/** 注册一个演示账号并直接登录。重名时抛出 ApiError（code=USERNAME_TAKEN）。 */
export async function signUp(username: string, password: string, displayName: string): Promise<void> {
  const name = displayName.trim();
  const res = await call<{ access_token: string; user: AuthUser }>('POST', '/auth/register', {
    username,
    password,
    ...(name ? { display_name: name } : {}),
  });
  if (typeof res.access_token !== 'string' || !res.user) {
    throw new ApiError({ kind: 'invalid_response', message: '注册响应缺少令牌' });
  }
  setToken(res.access_token);
  set({ state: 'signed-in', user: res.user, fresh: true });
}

/** 欢迎说明看过之后调用，之后不再显示 */
export function dismissWelcome(): void {
  if (current.state === 'signed-in' && current.fresh) set({ state: 'signed-in', user: current.user });
}

export async function signOut(): Promise<void> {
  try {
    await call('POST', '/auth/logout');
  } catch {
    // 后端已经不认这个令牌也没关系：本机照样清掉
  }
  setToken(null);
  set({ state: 'signed-out', reason: 'left' });
}

/** 任何业务请求收到“需要登录”的 401 时调用：清掉令牌并回到登录页。 */
export function noteUnauthorized(code: string | undefined): void {
  if (!code || !SESSION_CODES.has(code)) return;
  const hadToken = authHeader().Authorization !== undefined;
  setToken(null);
  if (current.state !== 'signed-out') set({ state: 'signed-out', reason: hadToken ? 'expired' : 'required' });
}
