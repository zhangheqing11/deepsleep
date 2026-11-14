// HTTP 适配器：只发 GET；错误信封、无信封 5xx、非 JSON、结构不符都有明确错误类型；不回退到 mock。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { example, loadModules } from './support/load.mjs';

const { createHttpClient } = await loadModules();
const signal = new AbortController().signal;

function fakeFetch(handler) {
  const calls = [];
  const impl = async (url, init) => {
    calls.push({ url, init });
    return handler(url, init);
  };
  return { calls, impl };
}
const json = (status, body, headers = {}) =>
  new Response(body === undefined ? '' : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });

test('只发 GET，路径按草案拼接', async () => {
  const report = example('run_report.run1.json');
  const f = fakeFetch((url) => (url.endsWith('/report') ? json(200, report) : json(200, { available: false })));
  const c = createHttpClient('http://h:8000/api/v1', f.impl);
  await c.getExperiment(signal);
  await c.getReport(report.run_id, signal);
  assert.deepEqual(
    f.calls.map((x) => [x.init.method, x.url]),
    [
      ['GET', 'http://h:8000/api/v1/demo/experiment'],
      ['GET', `http://h:8000/api/v1/runs/${report.run_id}/report`],
    ],
  );
});

test('错误信封：保留错误码与 request_id', async () => {
  const f = fakeFetch(() => json(409, { error: { code: 'REPORT_NOT_READY', message: 'x', request_id: 'req-1' } }));
  await assert.rejects(
    createHttpClient('', f.impl).getReport('r1', signal),
    (e) => e.kind === 'http' && e.status === 409 && e.code === 'REPORT_NOT_READY' && e.requestId === 'req-1',
  );
});

test('接口不存在（404 无信封）：http 错误，不当成“没有实验”', async () => {
  const f = fakeFetch(() => new Response('Not Found', { status: 404 }));
  await assert.rejects(createHttpClient('', f.impl).getExperiment(signal), (e) => e.kind === 'http' && e.status === 404 && !e.code);
});

test('现有后端对未实现接口返回 404 NOT_FOUND：显示“接口可能尚未部署”', async () => {
  const { describeError } = await loadModules();
  const f = fakeFetch(() => json(404, { error: { code: 'NOT_FOUND', message: '接口或资源不存在。', request_id: 'req_x' } }));
  await assert.rejects(createHttpClient('', f.impl).getExperiment(signal), (e) => {
    assert.equal(e.code, 'NOT_FOUND');
    assert.match(describeError(e), /尚未部署/);
    return true;
  });
});

test('无信封的 5xx（代理连不上后端）按网络问题处理', async () => {
  const f = fakeFetch(() => new Response('', { status: 502 }));
  await assert.rejects(createHttpClient('', f.impl).getExperiment(signal), (e) => e.kind === 'network');
});

test('fetch 抛错 → network；signal 已取消 → aborted', async () => {
  const f = fakeFetch(() => {
    throw new TypeError('Failed to fetch');
  });
  await assert.rejects(createHttpClient('', f.impl).getExperiment(signal), (e) => e.kind === 'network');
  const ac = new AbortController();
  ac.abort();
  await assert.rejects(createHttpClient('', f.impl).getExperiment(ac.signal), (e) => e.kind === 'aborted');
});

test('200 但不是 JSON（例如 SPA 回退页），或结构不符 → invalid_response', async () => {
  const html = fakeFetch(
    () => new Response('<!doctype html><title>deepsleep</title>', { status: 200, headers: { 'X-Request-ID': 'req-h' } }),
  );
  await assert.rejects(
    createHttpClient('', html.impl).getExperiment(signal),
    (e) => e.kind === 'invalid_response' && e.requestId === 'req-h',
  );
  const bad = fakeFetch(() => json(200, { experiment_id: 'x', stage: 'run1' }));
  await assert.rejects(
    createHttpClient('', bad.impl).getExperiment(signal),
    (e) => e.kind === 'invalid_response' && /evolution/.test(e.message),
  );
});
