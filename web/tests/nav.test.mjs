// 顶栏界面切换回归：四个去处与顺序只在这里断言一次；四套界面都渲染同一个切换，顶栏里没有其他跨界面链接。
// 使用已安装的 Vite SSR 加载前端 TS；不连接后端。
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
const memoryStorage = () => {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: (key) => data.delete(key) };
};

/** 唯一一处写明四个去处与顺序 */
const EXPECTED = [
  ['进化看板', '#/'],
  ['来访视角', '#/app'],
  ['用户视角', '#/me'],
  ['控制台', '#/console'],
];
const CROSS = new Set(EXPECTED.map(([, href]) => href));

const between = (html, open, close) => {
  const start = html.indexOf(open);
  assert.ok(start >= 0, `找不到 ${open}`);
  const end = html.indexOf(close, start);
  return html.slice(start, end + close.length);
};
const links = (html) => [...html.matchAll(/<a\b[^>]*href="([^"]*)"[^>]*>(.*?)<\/a>/g)].map((m) => ({ href: m[1], text: m[2].replace(/<[^>]+>/g, ''), tag: m[0] }));

test('界面切换', async (t) => {
  const temp = await mkdtemp(join(tmpdir(), 'deepsleep-nav-'));
  const server = await createServer({ root, configFile: false, cacheDir: temp, server: { middlewareMode: true },
    esbuild: { jsx: 'automatic' }, define: { 'import.meta.env.VITE_API_ADAPTER': '"http"' } });
  const oldWindow = globalThis.window;
  globalThis.window = { setTimeout, clearTimeout, setInterval, clearInterval, localStorage: memoryStorage(), sessionStorage: memoryStorage() };
  try {
    const nav = await server.ssrLoadModule('/src/components/SurfaceNav.tsx');
    const { parseRoute } = await server.ssrLoadModule('/src/hooks/useHashRoute.ts');
    const { ConsoleLayout, CONSOLE_NAV } = await server.ssrLoadModule('/src/layouts/ConsoleLayout.tsx');
    const { BoardPage } = await server.ssrLoadModule('/src/pages/board/BoardPage.tsx');
    const { UserApp } = await server.ssrLoadModule('/src/pages/app/UserApp.tsx');
    const { MeApp } = await server.ssrLoadModule('/src/pages/me/MeApp.tsx');
    const render = (c, props) => renderToStaticMarkup(React.createElement(c, props));

    await t.test('四个去处、顺序与文字固定；每个去处都回到对应界面', () => {
      assert.deepEqual(nav.SURFACES.map((s) => [s.label, s.href]), EXPECTED);
      for (const s of nav.SURFACES) assert.equal(nav.surfaceOf(parseRoute(s.href)), s.key, s.href);
      assert.equal(nav.surfaceOf(parseRoute('#/console/pipeline')), 'console');
      assert.equal(nav.surfaceOf(parseRoute('#/runs/r1/sessions/A-001')), 'console');
      assert.equal(nav.surfaceOf(parseRoute('#/app/v/B-012/compare')), 'app');
      assert.equal(nav.surfaceOf(parseRoute('#/me/v/B-012/chat')), 'me');
    });

    await t.test('当前界面标 aria-current，其余是普通链接，没有箭头和“返回”', () => {
      for (const s of nav.SURFACES) {
        const html = render(nav.SurfaceNav, { current: s.key });
        assert.match(html, /^<nav class="sf-nav" aria-label="界面切换">/);
        const items = links(html);
        assert.deepEqual(items.map((l) => [l.text, l.href]), EXPECTED);
        const current = items.filter((l) => l.tag.includes('aria-current="page"'));
        assert.equal(current.length, 1);
        assert.equal(current[0].href, s.href);
        assert.doesNotMatch(html, /[←→↗]|返回/);
      }
    });

    // 四套界面的顶栏：品牌指向看板、显示界面名称、只有一个界面切换、顶栏里没有别的跨界面链接
    const health = { status: 'ok', data: { status: 'ok', data_source: 'files', execution_mode: 'real' } };
    const pages = {
      board: render(BoardPage, {}),
      app: render(UserApp, { route: { name: 'app-home' } }),
      'app-visitor': render(UserApp, { route: { name: 'app-visitor', visitorId: 'B-012', tab: 'talk' } }),
      me: render(MeApp, { route: { name: 'me', visitorId: null, tab: 'tonight' } }),
      console: render(ConsoleLayout, { route: { name: 'console-runs' }, adapter: 'http', health, onRetryHealth: () => {}, children: React.createElement('p', null, '内容') }),
    };
    const NAME = { board: '进化看板', app: '来访视角', 'app-visitor': '来访视角', me: '用户视角', console: '开发者控制台' };

    await t.test('四套界面都渲染同一个切换，品牌一律回到看板', () => {
      for (const [key, html] of Object.entries(pages)) {
        const surface = key === 'app-visitor' ? 'app' : key;
        assert.equal(html.split('aria-label="界面切换"').length - 1, 1, `${key} 应只有一个界面切换`);
        const switcher = between(html, '<nav class="sf-nav"', '</nav>');
        assert.equal(switcher, render(nav.SurfaceNav, { current: surface }), key);
        assert.match(html, new RegExp(`<span class="sf-name">${NAME[key]}</span>`), key);
        const brand = links(html).find((l) => l.text.includes('deepsleep'));
        assert.equal(brand?.href, '#/', `${key} 的品牌应指向看板`);
      }
    });

    await t.test('顶栏里除了品牌和切换，没有其他跨界面链接', () => {
      for (const [key, html] of Object.entries(pages)) {
        const header = between(html, '<header', '</header>');
        const switcher = between(header, '<nav class="sf-nav"', '</nav>');
        const rest = links(header.replace(switcher, '')).filter((l) => !l.text.includes('deepsleep'));
        assert.deepEqual(rest.filter((l) => CROSS.has(l.href) || l.href.startsWith('#/')), [], key);
      }
    });

    await t.test('控制台侧栏只有控制台自己的页面，全链路演示排第一，进化后台标明新标签页', async () => {
      assert.deepEqual(CONSOLE_NAV.map((n) => n.label), ['全链路演示', '运行与报告', '模拟来访', '进化记录', '调试与日志']);
      assert.equal(CONSOLE_NAV[0].href, '#/console/pipeline');
      assert.ok(CONSOLE_NAV.every((n) => n.href.startsWith('#/console')));
      const side = between(pages.console, '<nav class="console-nav"', '</nav>');
      assert.ok(links(side).every((l) => l.href.startsWith('#/console') || l.tag.includes('target="_blank"')));
      const source = await readFile(join(root, 'src/components/console/DevconsoleNavLink.tsx'), 'utf8');
      assert.match(source, /↗/);
      assert.match(source, /新标签页/);
      assert.match(source, /target="_blank" rel="noopener noreferrer"/);
    });

    await t.test('旧的各自为政的跳转链接已删除', async () => {
      for (const f of ['src/layouts/ConsoleLayout.tsx', 'src/pages/board/BoardPage.tsx', 'src/pages/app/UserApp.tsx', 'src/pages/me/MeApp.tsx']) {
        const text = await readFile(join(root, f), 'utf8');
        assert.doesNotMatch(text, /← 进化看板|来访视角 →|评委怎么看这位来访|所有来访与两次回应/, f);
        assert.doesNotMatch(text, /href=\{HREF\.(board|me|runs|console)\}/, f);
        assert.match(text, /<SurfaceNav current=/, f);
      }
    });
  } finally {
    globalThis.window = oldWindow;
    await server.close();
    await rm(temp, { recursive: true, force: true });
  }
});
