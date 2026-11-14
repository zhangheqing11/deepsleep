// 使用已安装的 Vite SSR 加载前端 TS；不安装包，不连接真实后端或模型。
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
const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };
const memoryStorage = () => {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: (key) => data.delete(key) };
};

test('只读 API、mock、轮询与控制台展示回归', async (t) => {
  const temp = await mkdtemp(join(tmpdir(), 'deepsleep-read-api-'));
  const server = await createServer({ root, configFile: false, cacheDir: temp, server: { middlewareMode: true },
    esbuild: { jsx: 'automatic' }, define: { 'import.meta.env.VITE_API_ADAPTER': '"http"' } });
  const oldFetch = globalThis.fetch, oldWindow = globalThis.window;
  globalThis.window = { setTimeout, clearTimeout, localStorage: memoryStorage(), sessionStorage: memoryStorage() };
  try {
    const { mockClient } = await server.ssrLoadModule('/src/api/mockClient.ts');
    const { httpClient } = await server.ssrLoadModule('/src/api/httpClient.ts');
    const { withRequestLog, requestLog } = await server.ssrLoadModule('/src/api/requestLog.ts');
    const { ApiError } = await server.ssrLoadModule('/src/api/errors.ts');
    const { startReadPolling } = await server.ssrLoadModule('/src/hooks/useReadPoller.ts');
    const { EvolutionDetail, EvolutionProgress, readEvolution } = await server.ssrLoadModule('/src/pages/console/EvolutionPage.tsx');
    const { ExperimentCard } = await server.ssrLoadModule('/src/components/console/ExperimentCard.tsx');
    const { runHistoryStore } = await server.ssrLoadModule('/src/lib/storage.ts');
    const { RunLauncher } = await server.ssrLoadModule('/src/components/RunLauncher.tsx');
    const { DataSourceBanner } = await server.ssrLoadModule('/src/components/DataSourceBanner.tsx');
    const { RunProgress } = await server.ssrLoadModule('/src/components/RunProgress.tsx');
    const { metricDifference } = await server.ssrLoadModule('/src/components/console/RunCompare.tsx');
    const fixture = JSON.parse(await readFile(new URL('../../contracts/examples/evolution.v1-v2.json', import.meta.url), 'utf8'));
    const html = (component, props) => renderToStaticMarkup(React.createElement(component, props));

    await t.test('mock 三份报告与实验、进化、版本一致；所有新增方法支持取消', async () => {
      const client = withRequestLog(mockClient);
      const health = await client.health(); assert.equal(health.data_source, 'mock');
      const experiment = await client.getExperiment(); assert.equal(experiment.stage, 'done');
      assert.match(experiment.experiment_id, /placeholder/);
      const runs = await client.listRuns(); assert.equal(runs.items.length, 3);
      for (const key of ['run1', 'control', 'run2']) {
        const report = await client.getReport(experiment[key].run_id);
        assert.equal(report.role, key); assert.equal(report.playbook_version, experiment[key].playbook_version);
        assert.equal((await client.getRun(report.run_id)).status, 'succeeded');
      }
      const list = await client.listEvolutions(); assert.equal(list.items[0].evolution_id, experiment.evolution.evolution_id);
      assert.deepEqual(await client.getEvolution(experiment.evolution.evolution_id), fixture);
      assert.equal((await client.getEvolutionStatus(fixture.evolution_id)).phase, 'done');
      assert.equal((await client.getEvolutionInsights(fixture.evolution_id)).available, false);
      assert.equal((await client.getEvidence(experiment.run1.run_id)).available, false);
      assert.deepEqual((await client.listPlaybookVersions()).items.map((v) => v.version), ['v1', 'v2']);
      assert.ok((await client.getPlaybook('v2')).text.includes('床外容易困'));
      assert.equal((await client.getPlaybookDiff('v1', 'v2')).diff, fixture.diff);
      assert.match((await client.getPlaybookDiff('v2', 'v1')).diff, /-先问是否/);
      assert.equal((await client.getPlaybookDiff('v2', 'v2')).diff, '');
      await assert.rejects(client.getEvolution('missing'), (e) => e.code === 'NOT_FOUND');
      const controller = new AbortController(); controller.abort(); const signal = controller.signal;
      for (const promise of [client.health(signal), client.listRuns(50, signal), client.getExperiment(signal), client.getEvidence('id', signal), client.listEvolutions(20, signal), client.getEvolution('id', signal), client.getEvolutionStatus('id', signal), client.getEvolutionInsights('id', signal), client.listPlaybookVersions(signal), client.getPlaybook('v1', signal), client.getPlaybookDiff('v1', 'v2', signal)]) {
        await assert.rejects(promise, (e) => e.kind === 'aborted');
      }
    });

    await t.test('HTTP 精确路由、query、AbortSignal 和每个新请求的 request_id 日志', async () => {
      requestLog.clear(); const seen = [];
      globalThis.fetch = async (url, options) => { seen.push({ url, options }); return new Response(JSON.stringify({ items: [] }), { headers: { 'X-Request-ID': 'req-read-api' } }); };
      const client = withRequestLog(httpClient); const signal = new AbortController().signal;
      await client.health(signal); await client.listRuns(7, signal); await client.getExperiment(signal); await client.getEvidence('run-1', signal);
      await client.listEvolutions(3, signal); await client.getEvolution('evo-1', signal); await client.getEvolutionStatus('evo-1', signal);
      await client.getEvolutionInsights('evo-1', signal); await client.listPlaybookVersions(signal); await client.getPlaybook('v2', signal); await client.getPlaybookDiff('v2', 'v1', signal);
      assert.deepEqual(seen.map((r) => r.url), ['/health', '/runs?limit=7', '/demo/experiment', '/runs/run-1/evidence', '/evolutions?limit=3', '/evolutions/evo-1', '/evolutions/evo-1/status', '/evolutions/evo-1/insights', '/playbook/versions', '/playbook/v2', '/playbook/diff?from=v2&to=v1'].map((path) => '/api/v1' + path));
      assert.ok(seen.every((r) => r.options.method === 'GET' && r.options.signal === signal));
      assert.equal(requestLog.snapshot().length, 11); assert.ok(requestLog.snapshot().every((e) => e.request_id === 'req-read-api' && e.status === 200));
      await client.getEvolution('a/b'); assert.ok(seen.at(-1).url.endsWith('a%2Fb'));
    });

    await t.test('HTTP 501 RUNS_VIA_CLI 为说明；真实网络故障仍保留重试', async () => {
      const message = '真实运行请在操作员终端执行 make demo-run1 / make demo-run2';
      globalThis.fetch = async () => new Response(JSON.stringify({ error: { code: 'RUNS_VIA_CLI', message } }), { status: 501 });
      let error; try { await httpClient.createRun({ split: 'A' }, 'key'); } catch (e) { error = e; }
      assert.equal(error.isTransient, false);
      const markup = html(RunLauncher, { adapter: 'http', healthMode: 'real', subtitle: '', busy: false, disabledReason: null, submitting: false, error, pending: null, onStart() {}, onRetry() {}, onDiscard() {} });
      assert.ok(markup.includes(message)); assert.ok(!markup.includes('未能创建运行')); assert.ok(!markup.includes('提交结果未确认'));
      assert.equal(new ApiError({ kind: 'network', message: 'offline' }).isTransient, true);
      assert.equal(new ApiError({ kind: 'http', status: 503, message: 'offline' }).isTransient, true);
      assert.ok(html(DataSourceBanner, { adapter: 'http', unavailable: true }).includes('后端不可用'));
    });

    await t.test('1 秒串行轮询、不重叠、done/failed 停止', async (t) => {
      t.mock.timers.enable({ apis: ['setTimeout'] });
      let calls = 0, resolve; const results = [];
      const stop = startReadPolling(() => { calls++; return new Promise((r) => { resolve = r; }); }, (data) => ['done', 'failed'].includes(data.stage), (data, polling) => results.push({ data, polling }), assert.fail);
      t.mock.timers.tick(10000); assert.equal(calls, 1);
      resolve({ stage: 'run1' }); await flush(); t.mock.timers.tick(999); assert.equal(calls, 1); t.mock.timers.tick(1); assert.equal(calls, 2);
      resolve({ stage: 'done' }); await flush(); t.mock.timers.tick(5000); assert.equal(calls, 2); assert.equal(results.at(-1).polling, false); stop();
      let failedCalls = 0; const stopFailed = startReadPolling(async () => { failedCalls++; return { stage: 'failed' }; }, (d) => d.stage === 'failed', () => {}, assert.fail);
      await flush(); t.mock.timers.tick(5000); assert.equal(failedCalls, 1); stopFailed();
    });

    await t.test('2/4/5 秒失败退避；成功后恢复 1 秒；4xx 停止', async (t) => {
      t.mock.timers.enable({ apis: ['setTimeout'] });
      let calls = 0; const errors = [];
      const stop = startReadPolling(async () => { calls++; if (calls < 4) throw new ApiError({ kind: 'http', status: 503, message: 'offline' }); return {}; }, () => false, () => {}, (e, retry) => errors.push(retry));
      await flush();
      for (const wait of [2000, 4000, 5000]) { const before = calls; t.mock.timers.tick(wait - 1); await flush(); assert.equal(calls, before); t.mock.timers.tick(1); await flush(); assert.equal(calls, before + 1); }
      t.mock.timers.tick(1000); await flush(); assert.equal(calls, 5); assert.deepEqual(errors, [true, true, true]); stop();
      let rejected = 0; const stopBad = startReadPolling(async () => { rejected++; throw new ApiError({ kind: 'http', status: 404, message: 'missing' }); }, () => false, assert.fail, (_, retry) => assert.equal(retry, false));
      await flush(); t.mock.timers.tick(20000); assert.equal(rejected, 1); stopBad();
    });

    await t.test('卸载 abort 正在进行的请求，不接收迟到数据，不遗留定时器', async (t) => {
      t.mock.timers.enable({ apis: ['setTimeout'] });
      let signal, resolve, calls = 0;
      const stop = startReadPolling((value) => { signal = value; calls++; return new Promise((r) => { resolve = r; }); }, () => false, assert.fail, assert.fail);
      stop(); assert.equal(signal.aborted, true); resolve({ stage: 'run1' }); await flush(); t.mock.timers.tick(10000); assert.equal(calls, 1);
    });

    await t.test('NOT_READY 读取 status；结果就绪不依赖 status；NOT_FOUND 不伪装进行中', async () => {
      const paths = [];
      globalThis.fetch = async (url) => { paths.push(url); return url.endsWith('/status') ? new Response(JSON.stringify({ phase: 'validating' })) : new Response(JSON.stringify({ error: { code: 'NOT_READY', message: 'pending' } }), { status: 404 }); };
      const result = await readEvolution('evo-1', new AbortController().signal); assert.equal(result.evolution, null); assert.equal(result.status.phase, 'validating'); assert.equal(paths.length, 2);
      globalThis.fetch = async () => new Response(JSON.stringify(fixture)); assert.deepEqual((await readEvolution('evo-1', new AbortController().signal)).evolution, fixture);
      globalThis.fetch = async () => new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'missing' } }), { status: 404 });
      await assert.rejects(readEvolution('missing', new AbortController().signal), (e) => e.code === 'NOT_FOUND');
    });

    await t.test('保留上一代、反思器降级、deadline 到期仍等待确认', async () => {
      const markup = html(EvolutionDetail, { evo: { ...fixture, outcome: 'kept_previous', to_version: null, chosen: null, commit: null, diff: null, reflector: { model: 'ds-flash', fell_back: true, fallback_reason: 'timeout' } } });
      assert.ok(markup.includes('本次学习保留上一代 playbook')); assert.ok(markup.includes('反思器自动降级')); assert.ok(markup.includes('timeout'));
      const progress = html(EvolutionProgress, { status: { phase: 'validating', reflector: { state: 'done', model: 'ds-flash', fell_back: true }, validation: { baseline: 'done', candidates: { c1: 'blocked', c2: 'running', c3: 'pending' } }, review: { state: 'waiting', deadline: '2020-01-01T00:00:00+08:00', pending_changes: 2 } } });
      assert.ok(progress.includes('审核窗口已到期，等待后端确认')); assert.ok(progress.includes('2020-01-01T00:00:00+08:00')); assert.ok(progress.includes('硬规则拦下')); assert.ok(progress.includes('c3'));
      const run = { run_id: 'run-unknown', status: 'running', execution_mode: 'real', split: 'A', playbook_version: 'v1', elapsed_ms: 1000, progress: { total: null, completed: 3, failed: 0 } };
      const runHtml = html(RunProgress, { adapter: 'http', runId: run.run_id, poller: { run, polling: true, transientError: null, stop: null, stopError: null, restart() {} }, onClear() {} });
      assert.ok(runHtml.includes('已处理 3 个来访 · 总人数未知')); assert.ok(!runHtml.includes('aria-valuenow'));
    });

    await t.test('实验 done 才显示对比入口；缺失节点和无实验有明确显示', () => {
      const render = (data) => html(ExperimentCard, { poller: { data, error: null, polling: false, reload() {} }, mock: true, onCompare() {} });
      assert.ok(render({ available: false }).includes('暂无实验，等待操作员发起。'));
      const experiment = { experiment_id: 'exp', updated_at: fixture.created_at, stage: 'done', run1: null, run2: null, control: null, evolution: null, error: null };
      assert.ok(render(experiment).includes('打开三方对比')); assert.ok(render(experiment).includes('暂无'));
      assert.ok(!render({ ...experiment, stage: 'failed', error: 'failed-test' }).includes('打开三方对比'));
      assert.ok(render({ ...experiment, stage: 'failed', error: 'failed-test' }).includes('实验执行失败'));
    });

    await t.test('超过缓存上限时保留最新 20 条；服务端空列表清除过期缓存', () => {
      const entries = Array.from({ length: 50 }, (_, i) => ({ run_id: `run-${i}`, adapter: 'http', created_at: new Date(1700000000000 + i * 1000).toISOString(), split: 'A', playbook_version: 'v1', status: 'succeeded' }));
      runHistoryStore.cache('http', entries);
      const cached = runHistoryStore.list('http'); assert.equal(cached.length, 20); assert.equal(cached[0].run_id, 'run-49'); assert.equal(cached.at(-1).run_id, 'run-30');
      runHistoryStore.cache('http', []); assert.deepEqual(runHistoryStore.list('http'), []);
    });

    await t.test('三方对比差值不把 null 当 0', () => {
      assert.equal(metricDifference(0.75, 0.5), 0.25); assert.equal(metricDifference(null, 0.5), null);
      assert.equal(metricDifference(0.5, null), null); assert.equal(metricDifference(undefined, 0.5), null);
      assert.equal(metricDifference(0, 0), 0); assert.equal(metricDifference(-8.5, -7), -1.5);
    });
  } finally {
    globalThis.fetch = oldFetch; globalThis.window = oldWindow;
    await server.close(); await rm(temp, { recursive: true, force: true });
  }
});
