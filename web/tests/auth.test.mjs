// 登录与用户视角回归：令牌只进 sessionStorage、401 回到登录页、后端没开登录时不拦页面。
// 使用已安装的 Vite SSR 加载前端 TS；fetch 是假的，不连接真实后端。
import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const root = fileURLToPath(new URL('../', import.meta.url));
const example = async (name) => JSON.parse(await readFile(new URL(`../../contracts/examples/${name}`, import.meta.url), 'utf8'));
const memoryStorage = () => {
  const data = new Map();
  return { data, getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, String(value)), removeItem: (key) => data.delete(key) };
};
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const failure = (status, code) => json(status, { error: { code, message: code } });

test('登录与用户视角', async (t) => {
  const temp = await mkdtemp(join(tmpdir(), 'deepsleep-auth-'));
  const server = await createServer({ root, configFile: false, cacheDir: temp, server: { middlewareMode: true },
    esbuild: { jsx: 'automatic' }, define: { 'import.meta.env.VITE_API_ADAPTER': '"http"' } });
  const oldWindow = globalThis.window;
  const oldFetch = globalThis.fetch;
  const session = memoryStorage();
  globalThis.window = { setTimeout, clearTimeout, setInterval, clearInterval, localStorage: memoryStorage(), sessionStorage: session };
  /** 记录每次请求；handler 决定响应 */
  let calls = [];
  let handler = () => json(200, {});
  globalThis.fetch = async (url, init = {}) => {
    const call = { url: String(url), method: init.method ?? 'GET', headers: init.headers ?? {}, body: init.body ?? null };
    calls.push(call);
    return handler(call);
  };
  const reset = (h) => { calls = []; handler = h; };
  const USER = { id: 'demo', display_name: '演示用户', role: 'operator' };

  try {
    const auth = await server.ssrLoadModule('/src/api/auth.ts');
    const { httpClient } = await server.ssrLoadModule('/src/api/httpClient.ts');
    const { LoginPage } = await server.ssrLoadModule('/src/pages/auth/LoginPage.tsx');
    const { parseRoute, meHref } = await server.ssrLoadModule('/src/hooks/useHashRoute.ts');
    const { defaultVisitor } = await server.ssrLoadModule('/src/pages/me/MeApp.tsx');
    const view = await server.ssrLoadModule('/src/components/app/Replay.tsx');
    const { buildSteps } = await server.ssrLoadModule('/src/lib/replay.ts');
    const TOKEN_KEY = 'deepsleep.auth.token.v1';

    await t.test('后端没开登录或连不上时不拦页面', async () => {
      assert.equal(auth.getAuthState().state, 'checking');
      reset(() => json(200, { authenticated: false, user: null }));
      await auth.refreshAuth();
      assert.equal(auth.getAuthState().state, 'open');
      assert.equal(calls[0].url, '/api/v1/auth/me');

      reset(() => { throw new TypeError('fetch failed'); });
      await auth.refreshAuth();
      assert.equal(auth.getAuthState().state, 'open');
    });

    await t.test('后端要求登录：没有令牌时进入登录页', async () => {
      reset(() => failure(401, 'AUTH_REQUIRED'));
      await auth.refreshAuth();
      assert.deepEqual(auth.getAuthState(), { state: 'signed-out', reason: 'required' });
    });

    await t.test('密码不对保持未登录；登录成功后令牌只进 sessionStorage', async () => {
      reset(() => failure(401, 'INVALID_CREDENTIALS'));
      await assert.rejects(auth.signIn('demo', 'nope'), (e) => e.code === 'INVALID_CREDENTIALS');
      assert.equal(auth.getAuthState().state, 'signed-out');
      assert.equal(session.getItem(TOKEN_KEY), null);

      reset(() => json(200, { access_token: 'tok-1', token_type: 'bearer', expires_in: 60, user: USER }));
      await auth.signIn('demo', 'right-password');
      assert.deepEqual(auth.getAuthState(), { state: 'signed-in', user: USER });
      assert.deepEqual(JSON.parse(calls[0].body), { username: 'demo', password: 'right-password' });
      assert.equal(calls[0].url, '/api/v1/auth/login');
      // 存下来的只有令牌，账号和密码不落盘
      assert.deepEqual([...session.data.entries()], [[TOKEN_KEY, 'tok-1']]);
      assert.equal(window.localStorage.getItem(TOKEN_KEY), null);
      assert.deepEqual(auth.authHeader(), { Authorization: 'Bearer tok-1' });
    });

    await t.test('业务请求带令牌；令牌失效的 401 清掉令牌并回到登录页', async () => {
      reset(() => json(200, { available: false }));
      await httpClient.getExperiment();
      assert.equal(calls[0].headers.Authorization, 'Bearer tok-1');

      // 与登录无关的 401/404 不影响登录状态
      reset(() => failure(404, 'RUN_NOT_FOUND'));
      await assert.rejects(httpClient.getRun('x'));
      assert.equal(auth.getAuthState().state, 'signed-in');

      reset(() => failure(401, 'TOKEN_EXPIRED'));
      await assert.rejects(httpClient.getExperiment(), (e) => e.status === 401 && e.code === 'TOKEN_EXPIRED');
      assert.deepEqual(auth.getAuthState(), { state: 'signed-out', reason: 'expired' });
      assert.equal(session.getItem(TOKEN_KEY), null);
      assert.deepEqual(auth.authHeader(), {});
    });

    await t.test('刷新页面后凭令牌恢复登录；退出登录通知后端并清掉令牌', async () => {
      session.setItem(TOKEN_KEY, 'tok-2');
      reset(() => json(200, { authenticated: true, user: USER }));
      await auth.refreshAuth();
      assert.equal(auth.getAuthState().state, 'signed-in');
      assert.equal(calls[0].headers.Authorization, 'Bearer tok-2');

      reset(() => json(200, { status: 'ok' }));
      await auth.signOut();
      assert.equal(calls[0].url, '/api/v1/auth/logout');
      assert.equal(calls[0].method, 'POST');
      assert.equal(calls[0].headers.Authorization, 'Bearer tok-2');
      assert.deepEqual(auth.getAuthState(), { state: 'signed-out', reason: 'left' });
      assert.equal(session.getItem(TOKEN_KEY), null);

      // 后端已经不认这个令牌时，本机照样退出
      session.setItem(TOKEN_KEY, 'tok-3');
      reset(() => failure(401, 'INVALID_TOKEN'));
      await auth.signOut();
      assert.equal(session.getItem(TOKEN_KEY), null);
    });

    await t.test('注册：本机先拦格式；成功后直接登录并标记为刚注册；重名保持未登录', async () => {
      assert.match(auth.registrationProblem('ab', 'pass-123'), /3–32 位/);
      assert.match(auth.registrationProblem('has space', 'pass-123'), /3–32 位/);
      assert.match(auth.registrationProblem('okname', '12345'), /至少 6 位/);
      assert.equal(auth.registrationProblem('ok_name-1.x', 'pass-123'), null);

      reset(() => failure(409, 'USERNAME_TAKEN'));
      await assert.rejects(auth.signUp('taken', 'pass-123', ''), (e) => e.code === 'USERNAME_TAKEN');
      assert.equal(auth.getAuthState().state, 'signed-out');
      assert.equal(session.getItem(TOKEN_KEY), null);

      const NEW = { id: 'xiaowang', display_name: '小王', role: 'user' };
      reset(() => json(201, { access_token: 'tok-new', token_type: 'bearer', expires_in: 60, user: NEW }));
      await auth.signUp('xiaowang', 'pass-123', ' 小王 ');
      assert.equal(calls[0].url, '/api/v1/auth/register');
      assert.deepEqual(JSON.parse(calls[0].body), { username: 'xiaowang', password: 'pass-123', display_name: '小王' });
      assert.deepEqual(auth.getAuthState(), { state: 'signed-in', user: NEW, fresh: true });
      assert.deepEqual([...session.data.entries()], [[TOKEN_KEY, 'tok-new']]);
      auth.dismissWelcome();
      assert.deepEqual(auth.getAuthState(), { state: 'signed-in', user: NEW });

      // 不填称呼时不发送这个字段
      reset(() => json(201, { access_token: 'tok-new2', token_type: 'bearer', expires_in: 60, user: { ...NEW, id: 'v2' } }));
      await auth.signUp('v2', 'pass-123', '   ');
      assert.deepEqual(JSON.parse(calls[0].body), { username: 'v2', password: 'pass-123' });
      reset(() => json(200, { status: 'ok' }));
      await auth.signOut();
    });

    await t.test('登录页：密码框不回显，可以切到注册，说明账号只是演示', () => {
      const page = renderToStaticMarkup(React.createElement(LoginPage, { reason: 'expired' }));
      assert.match(page, /type="password"/);
      assert.match(page, /autoComplete="current-password"|autocomplete="current-password"/);
      assert.match(page, /登录已失效，请重新登录。/);
      assert.match(page, /注册一个演示账号/);
      assert.match(page, /只保存在这个标签页里/);
      assert.match(page, /<button type="submit" class="lg-submit" disabled="">登录<\/button>/);
      assert.doesNotMatch(page, /忘记密码/);
      const reg = renderToStaticMarkup(React.createElement(LoginPage, { reason: 'expired', initialMode: 'register' }));
      assert.match(reg, /<h1>注册<\/h1>/);
      assert.match(reg, /autoComplete="new-password"|autocomplete="new-password"/);
      assert.match(reg, /后端一重启就清空/);
      assert.match(reg, /请不要用你在别处用的密码/);
      assert.match(reg, /不会收集你的睡眠或健康信息/);
      assert.doesNotMatch(reg, /登录已失效/);
      assert.doesNotMatch(renderToStaticMarkup(React.createElement(LoginPage, { reason: 'required' })), /lg-note/);
    });

    await t.test('顶栏的退出登录：只在已登录时出现', async () => {
      const { SignOutButton } = await server.ssrLoadModule('/src/components/SignOutButton.tsx');
      const render = () => renderToStaticMarkup(React.createElement(SignOutButton, { className: 'x-link' }));
      assert.equal(auth.getAuthState().state, 'signed-out');
      assert.equal(render(), '');
      reset(() => json(200, { authenticated: false, user: null }));
      await auth.refreshAuth();
      assert.equal(auth.getAuthState().state, 'open');
      assert.equal(render(), '');
      reset(() => json(200, { access_token: 'tok-bar', token_type: 'bearer', expires_in: 60, user: USER }));
      await auth.signIn('demo', 'right-password');
      assert.match(render(), /<button type="button" class="x-link">退出登录<span class="so-who">（演示用户）<\/span><\/button>/);
      // 三套界面的顶栏都接了这个按钮
      for (const f of ['src/pages/board/BoardPage.tsx', 'src/pages/app/UserApp.tsx', 'src/layouts/ConsoleLayout.tsx']) {
        assert.match(await readFile(join(root, f), 'utf8'), /<SignOutButton className=/, f);
      }
      reset(() => json(200, { status: 'ok' }));
      await auth.signOut();
    });

    await t.test('用户视角：路由、默认来访和第一人称的称呼', async () => {
      assert.deepEqual(parseRoute('#/me'), { name: 'me', visitorId: null, tab: 'tonight' });
      assert.deepEqual(parseRoute('#/me/chat'), { name: 'me', visitorId: null, tab: 'chat' });
      assert.deepEqual(parseRoute(meHref('B-012', 'profile')), { name: 'me', visitorId: 'B-012', tab: 'profile' });
      assert.equal(meHref(null), '#/me');
      assert.deepEqual(parseRoute('#/me/other'), { name: 'board' });

      const v = (id, extra = {}) => ({ id, before: null, after: null, hasBefore: true, hasAfter: true, safety: false, gain: null, ...extra });
      // 跳过触发安全线的来访和没有和最新一版教练谈过的来访
      assert.equal(defaultVisitor({ visitors: [v('a', { safety: true }), v('b', { hasAfter: false }), v('c')] }).id, 'c');
      assert.equal(defaultVisitor({ visitors: [v('a', { safety: true }), v('b', { hasAfter: false })] }).id, 'b');
      assert.equal(defaultVisitor({ visitors: [v('a', { safety: true })] }).id, 'a');
      assert.equal(defaultVisitor({ visitors: [] }), null);
      // 自己注册的账号固定分到一位合适的来访：同一个账号每次相同，不会分到安全线示例
      const many = { visitors: [v('s', { safety: true }), v('a'), v('b'), v('c'), v('d')] };
      const assigned = defaultVisitor(many, 'xiaowang').id;
      assert.equal(defaultVisitor(many, 'xiaowang').id, assigned);
      assert.notEqual(assigned, 's');
      assert.equal(new Set(['u1', 'u2', 'u3', 'u4', 'u5', 'u6', 'u7', 'u8'].map((u) => defaultVisitor(many, u).id)).size > 1, true);

      const s = await example('session.A-002.json');
      const steps = buildSteps(s);
      const mine = renderToStaticMarkup(React.createElement(view.Transcript, { steps, shown: steps.length, typing: false, names: { agent: '教练', visitor: '我' } }));
      assert.match(mine, /<span class="ua-who">我<\/span>/);
      assert.doesNotMatch(mine, /<span class="ua-who">来访<\/span>/);
      const theirs = renderToStaticMarkup(React.createElement(view.Transcript, { steps, shown: steps.length, typing: false }));
      assert.match(theirs, /<span class="ua-who">来访<\/span>/);
    });

    await t.test('措辞边界：登录页和用户视角的源码不出现禁用字样，用户视角没有输入框', async () => {
      for (const f of ['src/pages/me/MeApp.tsx', 'src/pages/auth/LoginPage.tsx', 'src/api/auth.ts', 'src/me.css', 'src/login.css']) {
        const text = await readFile(join(root, f), 'utf8');
        assert.doesNotMatch(text, /诊断|治疗|患者|病人|治愈|根治|痊愈|处方|开药|褪黑素/, f);
        assert.doesNotMatch(text, /24 ?小时|免费拨打/, f);
        if (f.includes('/me/')) assert.doesNotMatch(text, /<input|<textarea|contentEditable/, f);
      }
      // 密码不写进任何存储、日志或地址
      const source = await readFile(join(root, 'src/api/auth.ts'), 'utf8');
      assert.doesNotMatch(source, /console\.|localStorage/);
      assert.doesNotMatch(await readFile(join(root, 'src/pages/auth/LoginPage.tsx'), 'utf8'), /console\.|Storage/);
    });
  } finally {
    globalThis.window = oldWindow;
    globalThis.fetch = oldFetch;
    await server.close();
    await rm(temp, { recursive: true, force: true });
  }
});
