// 登录接入：令牌只进 sessionStorage、数据请求带 Bearer、401 回到登录页、后端没开登录时不拦页面。
// fetch 与 sessionStorage 都是假的，不连接真实后端。每个用例重置令牌和状态。
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { loadModules } from './support/load.mjs';

const TOKEN_KEY = 'deepsleep.devconsole.token.v1';
const USER = { id: 'demo', display_name: '演示用户', role: 'operator' };
const signal = new AbortController().signal;

const store = new Map();
globalThis.sessionStorage = {
  getItem: (k) => store.get(k) ?? null,
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};

const json = (status, body) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const failure = (status, code) => json(status, { error: { code, message: code } });

let calls = [];
let handler = () => json(200, {});
const realFetch = globalThis.fetch;
globalThis.fetch = async (url, init = {}) => {
  const call = { url: String(url), method: init.method ?? 'GET', headers: init.headers ?? {}, body: init.body ?? null };
  calls.push(call);
  return handler(call);
};
process.on('exit', () => {
  globalThis.fetch = realFetch;
});

const m = await loadModules({ VITE_DATA_MODE: 'http' });
const { createHttpClient, authHeader, getAuthState, signIn, signOut, refreshAuth, noteUnauthorized } = m;

function reset(h = () => json(200, {})) {
  calls = [];
  handler = h;
}

beforeEach(async () => {
  store.clear();
  reset();
  // 回到“没令牌、后端没开登录”的起点：状态为 open
  reset(() => json(200, { authenticated: false, user: null }));
  await refreshAuth();
  store.clear();
  reset();
});

test('没登录时数据请求不带 Authorization', async () => {
  reset(() => json(200, { available: false }));
  await createHttpClient('/api/v1').getExperiment(signal);
  assert.equal(calls[0].headers.Authorization, undefined);
});

test('登录后令牌只放 sessionStorage，数据请求带 Bearer，且仍然只发 GET', async () => {
  reset((c) => (c.url.endsWith('/auth/login') ? json(200, { access_token: 'tok-1', user: USER }) : json(200, { available: false })));
  await signIn('demo', 'secret');
  assert.deepEqual(getAuthState(), { state: 'signed-in', user: USER });
  assert.equal(store.get(TOKEN_KEY), 'tok-1');
  assert.deepEqual(JSON.parse(calls[0].body), { username: 'demo', password: 'secret' });
  assert.equal(calls[0].headers.Authorization, undefined, '登录请求本身不带令牌');

  calls = [];
  const client = createHttpClient('/api/v1');
  await client.getExperiment(signal);
  assert.equal(calls[0].method, 'GET');
  assert.equal(calls[0].headers.Authorization, 'Bearer tok-1');
  assert.deepEqual(authHeader(), { Authorization: 'Bearer tok-1' });
  // 账号密码没有被存进任何存储
  assert.ok([...store.values()].every((v) => !v.includes('secret')));
});

test('账号或密码不对：抛 INVALID_CREDENTIALS，保持未登录，不存令牌', async () => {
  reset(() => failure(401, 'INVALID_CREDENTIALS'));
  await assert.rejects(signIn('demo', 'bad'), (e) => e.status === 401 && e.code === 'INVALID_CREDENTIALS');
  assert.notEqual(getAuthState().state, 'signed-in');
  assert.equal(store.get(TOKEN_KEY), undefined);
  noteUnauthorized('INVALID_CREDENTIALS'); // 不属于“会话失效”，不应改变状态
  assert.notEqual(getAuthState().reason, 'expired');
});

for (const code of ['AUTH_REQUIRED', 'INVALID_TOKEN', 'TOKEN_EXPIRED']) {
  test(`数据请求返回 401 ${code}：清令牌，回到登录页（已失效）`, async () => {
    reset((c) => (c.url.endsWith('/auth/login') ? json(200, { access_token: 'tok-2', user: USER }) : failure(401, code)));
    await signIn('demo', 'secret');
    await assert.rejects(createHttpClient('/api/v1').getExperiment(signal), (e) => e.kind === 'http' && e.status === 401 && e.code === code);
    assert.deepEqual(getAuthState(), { state: 'signed-out', reason: 'expired' });
    assert.equal(store.get(TOKEN_KEY), undefined);
    assert.deepEqual(authHeader(), {});
  });
}

test('从没登录就收到 401：回到登录页（需要登录）', async () => {
  reset(() => failure(401, 'AUTH_REQUIRED'));
  await assert.rejects(createHttpClient('/api/v1').getExperiment(signal));
  assert.deepEqual(getAuthState(), { state: 'signed-out', reason: 'required' });
});

test('refreshAuth：后端没开登录 → open；连不上 → open（不拦页面）', async () => {
  reset(() => json(200, { authenticated: false, user: null }));
  await refreshAuth();
  assert.deepEqual(getAuthState(), { state: 'open' });

  reset(() => {
    throw new TypeError('Failed to fetch');
  });
  await refreshAuth();
  assert.deepEqual(getAuthState(), { state: 'open' });
});

test('refreshAuth：令牌有效 → signed-in；令牌失效 → signed-out（已失效）并清令牌', async () => {
  store.set(TOKEN_KEY, 'tok-3');
  reset(() => json(200, { authenticated: true, user: USER }));
  await refreshAuth();
  assert.deepEqual(getAuthState(), { state: 'signed-in', user: USER });
  assert.equal(calls[0].headers.Authorization, 'Bearer tok-3');

  store.set(TOKEN_KEY, 'tok-3');
  reset(() => failure(401, 'INVALID_TOKEN'));
  await refreshAuth();
  assert.deepEqual(getAuthState(), { state: 'signed-out', reason: 'expired' });
  assert.equal(store.get(TOKEN_KEY), undefined);
});

test('退出：POST /auth/logout，清令牌；后端不可达也在本机退出', async () => {
  reset((c) => (c.url.endsWith('/auth/login') ? json(200, { access_token: 'tok-4', user: USER }) : json(200, { ok: true })));
  await signIn('demo', 'secret');
  calls = [];
  await signOut();
  assert.equal(calls[0].method, 'POST');
  assert.ok(calls[0].url.endsWith('/auth/logout'));
  assert.equal(calls[0].headers.Authorization, 'Bearer tok-4');
  assert.deepEqual(getAuthState(), { state: 'signed-out', reason: 'left' });
  assert.equal(store.get(TOKEN_KEY), undefined);

  reset((c) => (c.url.endsWith('/auth/login') ? json(200, { access_token: 'tok-5', user: USER }) : (() => { throw new TypeError('down'); })()));
  await signIn('demo', 'secret');
  await signOut();
  assert.deepEqual(getAuthState(), { state: 'signed-out', reason: 'left' });
  assert.equal(store.get(TOKEN_KEY), undefined);
});

test('模拟数据模式：不需要登录，状态直接 open', async () => {
  const mock = await loadModules({ VITE_DATA_MODE: 'mock' });
  assert.deepEqual(mock.getAuthState(), { state: 'open' });
  await mock.refreshAuth();
  assert.deepEqual(mock.getAuthState(), { state: 'open' });
});
