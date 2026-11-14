// “进化后台”入口的地址解析与部署探测。用 Vite 自带的 esbuild 打包真实源码，不新增依赖。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const out = await build({
  entryPoints: [join(here, '..', 'src', 'lib', 'devconsoleLink.ts')],
  bundle: true,
  format: 'esm',
  platform: 'neutral',
  write: false,
  logLevel: 'silent',
});
const { resolveDevconsoleLink, probeDevconsole } = await import(
  `data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString('base64')}`
);

const PAGE = 'http://10.0.0.5:8000/#/console';

test('不填：尚未配置（不给出会跳错的链接）', () => {
  assert.deepEqual(resolveDevconsoleLink(undefined, PAGE), { state: 'unconfigured' });
  assert.deepEqual(resolveDevconsoleLink('  ', PAGE), { state: 'unconfigured' });
});

test('同源路径：按当前页面解析，末尾补斜杠', () => {
  assert.deepEqual(resolveDevconsoleLink('/devconsole', PAGE), { state: 'configured', href: 'http://10.0.0.5:8000/devconsole/' });
  assert.deepEqual(resolveDevconsoleLink('/devconsole/', PAGE), { state: 'configured', href: 'http://10.0.0.5:8000/devconsole/' });
});

test('完整地址：保留，去掉 hash', () => {
  assert.equal(
    resolveDevconsoleLink('http://localhost:5174/devconsole/#/overview', PAGE).href,
    'http://localhost:5174/devconsole/',
  );
  assert.equal(resolveDevconsoleLink('https://demo.example/devconsole', PAGE).href, 'https://demo.example/devconsole/');
});

test('危险或含糊的配置被拒：javascript:、相对路径、协议相对、带账号密码', () => {
  for (const raw of ['javascript:alert(1)', 'data:text/html,x', 'devconsole/', '//evil.example/x', 'ftp://h/x', 'http://u:p@h/x']) {
    assert.equal(resolveDevconsoleLink(raw, PAGE).state, 'invalid', raw);
  }
});

const res = (status, body, type = 'application/json') =>
  new Response(typeof body === 'string' ? body : JSON.stringify(body), { status, headers: { 'Content-Type': type } });

test('探测：读目标下的标识文件，只有匹配才算已部署', async () => {
  const urls = [];
  const ok = await probeDevconsole('http://h/devconsole/', async (u) => {
    urls.push(u);
    return res(200, { app: 'deepsleep-devconsole' });
  });
  assert.equal(ok, 'ok');
  assert.deepEqual(urls, ['http://h/devconsole/devconsole-meta.json']);
});

test('探测：SPA 回退返回旧控制台首页（HTML 200）→ 待部署，不算成功', async () => {
  const r = await probeDevconsole('http://h/devconsole/', async () => res(200, '<!doctype html><title>deepsleep</title>', 'text/html'));
  assert.equal(r, 'not_deployed');
});

test('探测：404 或别的应用标识 → 待部署；网络失败 → 无法确认', async () => {
  assert.equal(await probeDevconsole('http://h/d/', async () => res(404, 'nope', 'text/plain')), 'not_deployed');
  assert.equal(await probeDevconsole('http://h/d/', async () => res(200, { app: 'other' })), 'not_deployed');
  assert.equal(
    await probeDevconsole('http://h/d/', async () => {
      throw new TypeError('Failed to fetch');
    }),
    'unreachable',
  );
});
