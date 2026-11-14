// 进化看板回归：数据聚合、结论推导和各阶段的展示。
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
const example = async (name) => JSON.parse(await readFile(new URL(`../../contracts/examples/${name}`, import.meta.url), 'utf8'));
const clone = (v) => JSON.parse(JSON.stringify(v));
const memoryStorage = () => {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: (key) => data.delete(key) };
};

test('进化看板：聚合、结论与各阶段展示', async (t) => {
  const temp = await mkdtemp(join(tmpdir(), 'deepsleep-board-'));
  const server = await createServer({ root, configFile: false, cacheDir: temp, server: { middlewareMode: true },
    esbuild: { jsx: 'automatic' }, define: { 'import.meta.env.VITE_API_ADAPTER': '"http"' } });
  const oldWindow = globalThis.window;
  globalThis.window = { setTimeout, clearTimeout, setInterval, clearInterval, localStorage: memoryStorage(), sessionStorage: memoryStorage() };
  try {
    const board = await server.ssrLoadModule('/src/lib/board.ts');
    const { EvolutionBoard } = await server.ssrLoadModule('/src/components/board/Board.tsx');
    const { ApiError } = await server.ssrLoadModule('/src/api/errors.ts');
    const { parseRoute } = await server.ssrLoadModule('/src/hooks/useHashRoute.ts');
    const { readBoard, createBoardCache, finding, pairVisitors, alertSlots, parseEvidence, isiTrajectories, EMPTY_BOARD } = board;

    const run1 = await example('run_report.run1.json');
    const control = await example('run_report.control.json');
    const run2 = await example('run_report.run2.json');
    const evolution = await example('evolution.v1-v2.json');
    const versions = [
      { version: 'v2', sha: 'c2a4e6b8d0f1', author: 'deepsleep-agent', message: '第二代', committed_at: '2026-11-15T09:03:00+08:00', is_head: true },
      { version: 'v1', sha: 'a1b2c3d4e5f6', author: 'deepsleep-team', message: '初始版本', committed_at: '2026-11-15T09:00:00+08:00', is_head: false },
    ];
    const node = (report, state = 'done') => ({ run_id: report.run_id, playbook_version: report.playbook_version, split: report.split, state });
    const doneExperiment = () => ({
      experiment_id: 'exp-1', updated_at: '2026-11-15T09:05:00+08:00', stage: 'done', error: null,
      run1: node(run1), control: node(control), run2: node(run2),
      evolution: { evolution_id: evolution.evolution_id, state: 'done' },
    });
    const status = (report, extra = {}) => ({
      run_id: report.run_id, status: 'succeeded', execution_mode: 'real', split: report.split,
      playbook_version: report.playbook_version, progress: { total: report.n_visitors, completed: report.n_visitors, failed: 0 },
      elapsed_ms: 1000, report_available: true, error: null, ...extra,
    });
    /** 记录调用次数的假接口；overrides 覆盖单个方法 */
    const fakeApi = (experiment, overrides = {}) => {
      const calls = {};
      const reports = { [run1.run_id]: run1, [control.run_id]: control, [run2.run_id]: run2 };
      const base = {
        adapter: 'http',
        getExperiment: async () => (typeof experiment === 'function' ? experiment() : experiment),
        getReport: async (id) => clone(reports[id]),
        getRun: async (id) => status(reports[id]),
        getEvolution: async () => clone(evolution),
        getEvolutionStatus: async () => { throw new Error('不应读取进度'); },
        getEvidence: async () => ({ available: false }),
        listPlaybookVersions: async () => ({ items: clone(versions) }),
      };
      const api = {};
      for (const key of Object.keys(base)) {
        if (key === 'adapter') { api.adapter = overrides.adapter ?? base.adapter; continue; }
        api[key] = async (...args) => { calls[key] = (calls[key] ?? 0) + 1; return (overrides[key] ?? base[key])(...args); };
      }
      return { api, calls };
    };
    const signal = new AbortController().signal;
    const html = (data, props = {}) => renderToStaticMarkup(React.createElement(EvolutionBoard, { data, ...props }));
    const slot = (role, report, extra = {}) => ({ role, node: report ? node(report) : null, report, status: null, error: null, evidence: null, ...extra });
    const full = (extra = {}) => ({
      experiment: doneExperiment(), run1: slot('run1', run1), control: slot('control', control), run2: slot('run2', run2),
      evolution, evolutionStatus: null, versions: [...versions].reverse(), mock: false, ...extra,
    });

    await t.test('首页是看板，控制台与旧会谈链接保持可用', () => {
      assert.equal(parseRoute('').name, 'board');
      assert.equal(parseRoute('#/').name, 'board');
      assert.equal(parseRoute('#/unknown').name, 'board');
      assert.equal(parseRoute('#/console').name, 'console-runs');
      assert.equal(parseRoute('#/console/evolution').name, 'console-evolution');
      assert.deepEqual(parseRoute('#/runs/r1/sessions/A-001'), { name: 'console-session', runId: 'r1', visitorId: 'A-001' });
      assert.equal(parseRoute('#/app/chat').name, 'app-chat');
    });

    await t.test('完成的报告和进化记录只读一次，版本按序排列', async () => {
      const { api, calls } = fakeApi(doneExperiment());
      const cache = createBoardCache();
      const first = await readBoard(api, cache, signal);
      const second = await readBoard(api, cache, signal);
      assert.equal(calls.getExperiment, 2);
      assert.equal(calls.getReport, 3);
      assert.equal(calls.getEvolution, 1);
      assert.equal(calls.listPlaybookVersions, 1);
      // 证据只读对照与运行 2，各一次；后端说没有也不再重复请求
      assert.equal(calls.getEvidence, 2);
      assert.equal(second.run2.evidence, null);
      assert.equal(second.run2.report.run_id, run2.run_id);
      assert.deepEqual(first.versions.map((v) => v.version), ['v1', 'v2']);
      assert.equal(first.mock, false);
    });

    await t.test('实验换了一场就丢弃旧缓存', async () => {
      let id = 'exp-1';
      const { api, calls } = fakeApi(() => ({ ...doneExperiment(), experiment_id: id }));
      const cache = createBoardCache();
      await readBoard(api, cache, signal);
      id = 'exp-2';
      await readBoard(api, cache, signal);
      assert.equal(calls.getReport, 6);
      assert.equal(calls.getEvolution, 2);
    });

    await t.test('学习未开始不请求进化记录；进行中读进度', async () => {
      const pending = { ...doneExperiment(), stage: 'run1', run1: node(run1, 'running'), control: node(control, 'pending'),
        run2: node(run2, 'pending'), evolution: { evolution_id: evolution.evolution_id, state: 'pending' } };
      const a = fakeApi(pending, { getRun: async () => status(run1, { status: 'running', progress: { total: null, completed: 3, failed: 0 }, report_available: false }) });
      const data = await readBoard(a.api, createBoardCache(), signal);
      assert.equal(a.calls.getEvolution, undefined);
      assert.equal(a.calls.getReport, undefined);
      assert.equal(data.run1.status.progress.completed, 3);
      assert.equal(data.evolution, null);

      const learning = { ...pending, stage: 'learning', run1: node(run1), evolution: { evolution_id: evolution.evolution_id, state: 'running' } };
      const progress = { schema: 'evolve-status/1', evolution_id: evolution.evolution_id, updated_at: null, from_version: 'v1', phase: 'validating',
        reflector: { state: 'done', model: 'fallback-model', fell_back: true },
        validation: { baseline: 'done', candidates: { c1: 'blocked', c2: 'running' } },
        review: { state: 'waiting', deadline: '2000-01-01T00:00:00Z', pending_changes: 2 }, outcome: null, to_version: null, chosen: null, error: null };
      const b = fakeApi(learning, {
        getEvolution: async () => { throw new ApiError({ kind: 'http', status: 404, code: 'NOT_READY', message: 'not ready' }); },
        getEvolutionStatus: async () => progress,
      });
      const during = await readBoard(b.api, createBoardCache(), signal);
      assert.equal(during.evolution, null);
      assert.equal(during.evolutionStatus.phase, 'validating');
      const page = html(during);
      assert.match(page, /学习进行中/);
      assert.match(page, /反思器自动降级/);
      assert.match(page, /c1 硬规则拦下/);
      assert.match(page, /审核窗口已到期，等待后端确认/);
      assert.match(page, /待审 2 条/);
    });

    await t.test('子资源失败不打断整页，实验清单失败才抛出', async () => {
      const { api } = fakeApi(doneExperiment(), {
        getReport: async (id) => { if (id === run2.run_id) throw new ApiError({ kind: 'http', status: 409, code: 'REPORT_NOT_READY', message: 'x' }); return clone(control); },
        listPlaybookVersions: async () => { throw new ApiError({ kind: 'network', message: 'down' }); },
      });
      const data = await readBoard(api, createBoardCache(), signal);
      assert.equal(data.run2.report, null);
      assert.equal(data.run2.error.code, 'REPORT_NOT_READY');
      assert.equal(data.versions, null);
      assert.match(html(data), /报告读取失败，正在重试/);
      const broken = fakeApi(doneExperiment(), { getExperiment: async () => { throw new ApiError({ kind: 'network', message: 'down' }); } });
      await assert.rejects(readBoard(broken.api, createBoardCache(), signal), (e) => e.kind === 'network');
    });

    await t.test('模拟来源始终被标出', async () => {
      const perRun = fakeApi(doneExperiment(), { getRun: async (id) => status(run1, { run_id: id, execution_mode: 'mock' }) });
      assert.equal((await readBoard(perRun.api, createBoardCache(), signal)).mock, true);
      const local = fakeApi(doneExperiment(), { adapter: 'mock' });
      assert.equal((await readBoard(local.api, createBoardCache(), signal)).mock, true);
    });

    await t.test('暂无实验：框架保留，指标写“尚未生成”，不画成 0', async () => {
      const { api } = fakeApi({ available: false });
      const data = await readBoard(api, createBoardCache(), signal);
      assert.equal(data.experiment, null);
      const page = html(data);
      assert.match(page, /暂无实验，等待操作员发起。/);
      assert.match(page, /尚未生成/);
      assert.doesNotMatch(page, />0<span class="bd-unit">%/);
      assert.doesNotMatch(page, /0 例危机漏报/);
      assert.match(html(EMPTY_BOARD, { loading: true }), /正在读取实验…/);
    });

    await t.test('完成且生成新版本：结论、配对点阵与改动', () => {
      const data = full();
      assert.deepEqual(finding(data), { tone: 'positive', text: '同一批 8 位 B 组来访，v2 的有效率比 v1 高 37.5 个百分点。' });
      const pairing = pairVisitors(control, run2);
      assert.deepEqual(pairing.counts, { gained: 3, both: 4, lost: 0, neither: 1 });
      assert.equal(pairing.counts.both + pairing.counts.gained, run2.per_visitor.filter((v) => v.responder).length);
      const page = html(data);
      assert.match(page, /87\.5<span class="bd-unit">%/);
      assert.match(page, /\+37\.5 个百分点/);
      assert.match(page, /新版新增有效 <b>3<\/b> 位/);
      assert.match(page, /系统自己给 playbook 写了 3 条改动/);
      assert.match(page, /先问是否在沙发上反而能睡着/);
      assert.match(page, /硬规则拦下/);
      assert.match(page, /python -m engine\.evolve rollback v1/);
      assert.match(page, /全部守住/);
      assert.doesNotMatch(page, /诊断|治疗失眠/);
    });

    await t.test('来访不是同一批时不硬凑配对', () => {
      const other = clone(run2);
      other.per_visitor[0].visitor_id = 'X-999';
      assert.equal(pairVisitors(control, other), null);
      assert.match(html(full({ run2: slot('run2', other) })), /不是同一批，不能逐个配对/);
    });

    await t.test('保留上一代按正常结果呈现，没有回退命令可给时说明原因', () => {
      const kept = { ...clone(evolution), outcome: 'kept_previous', to_version: null, chosen: null, commit: null, diff: null,
        reflector: { model: 'backup-model', fell_back: true, fallback_reason: '主模型超时' } };
      const sameVersion = { ...clone(run2), playbook_version: 'v1', metrics: clone(control.metrics), per_visitor: clone(control.per_visitor) };
      const data = full({ evolution: kept, run2: slot('run2', sameVersion), versions: [versions[1]].map((v) => ({ ...v, is_head: true })) });
      assert.equal(finding(data).tone, 'neutral');
      const page = html(data);
      assert.match(page, /本次学习保留上一代 playbook/);
      assert.match(page, /这是门禁在正常工作，不是系统故障/);
      assert.match(page, /反思器自动降级/);
      assert.match(page, /主模型超时/);
      assert.match(page, /±0 个百分点/);
      assert.match(page, /没有更早的版本可退/);
      assert.doesNotMatch(page, /engine.evolve rollback/);
      assert.doesNotMatch(page, /role="alert"/);
    });

    await t.test('总人数未知时只报已处理数，不画比例条', () => {
      const running = slot('run2', null, { node: node(run2, 'running'),
        status: status(run2, { status: 'running', progress: { total: null, completed: 3, failed: 0 }, report_available: false }) });
      const exp = { ...doneExperiment(), stage: 'run2', run2: node(run2, 'running'), control: node(control, 'pending') };
      const page = html(full({ experiment: exp, run2: running, control: slot('control', null, { node: node(control, 'pending') }) }));
      assert.match(page, /已处理 3 位来访 · 总人数未知/);
      assert.doesNotMatch(page, /bd-progress/);
      assert.match(page, /运行 2 与对照进行中/);
      const known = { ...running, status: status(run2, { status: 'running', progress: { total: 8, completed: 2, failed: 0 }, report_available: false }) };
      const withTotal = html(full({ experiment: exp, run2: known, control: slot('control', null) }));
      assert.match(withTotal, /已处理 2 \/ 8 位来访/);
      assert.match(withTotal, /width:25%/);
    });

    await t.test('空值显示为“—”，不显示为 0', () => {
      const partial = clone(run2);
      partial.metrics.referral_precision = null;
      const page = html(full({ run2: slot('run2', partial) }));
      const row = page.slice(page.indexOf('转介精确率'), page.indexOf('平均 ISI 变化'));
      assert.match(row, /class="num none">—</);
      assert.match(row, /class="num bd-diff flat">—</);
      // 缺失的值不画点：这一行只剩对照的点和运行 1 的短线
      assert.doesNotMatch(row, /dot lead/);
      assert.match(row, /dot base/);
    });

    await t.test('证据接口字段未冻结：结构不对就当作没有', async () => {
      const raw = { contract: false, visitors: [], summary: { by_step: [
        { round: 2, step: 1, n: 6, mean_p_true: 0.4 }, { round: 1, step: 2, n: 6, mean_p_true: 0.3 }, { round: 1, step: 1, n: 6, mean_p_true: 0.2 }] } };
      assert.deepEqual(parseEvidence(raw), [{ round: 1, step: 1, pTrue: 0.2 }, { round: 1, step: 2, pTrue: 0.3 }, { round: 2, step: 1, pTrue: 0.4 }]);
      assert.equal(parseEvidence({ available: false }), null);
      assert.equal(parseEvidence({ summary: { by_step: [{ round: 1, step: 1, mean_p_true: 'x' }] } }), null);
      assert.equal(parseEvidence({ summary: { by_step: [] } }), null);
      assert.equal(parseEvidence(null), null);
      const { api, calls } = fakeApi(doneExperiment(), { getEvidence: async () => raw });
      const cache = createBoardCache();
      const data = await readBoard(api, cache, signal);
      await readBoard(api, cache, signal);
      assert.equal(calls.getEvidence, 2);
      assert.equal(data.control.evidence.length, 3);
      assert.equal(data.run1.evidence, null);
      const page = html(data);
      assert.match(page, /逐步判断把握：对照 40%，运行 2 40%/);
      assert.match(page, /第 2 轮/);
      assert.match(page, /五选一的起点/);
    });

    await t.test('图表从数据画出：轨迹、对比条与门禁条', () => {
      const t2 = isiTrajectories(run2);
      assert.equal(t2.visitors.length, run2.per_visitor.length);
      assert.equal(t2.mean[0], 0);
      const expected = run2.per_visitor.reduce((sum, v) => sum + (v.isi_week[4] - v.isi_week[0]), 0) / run2.per_visitor.length;
      assert.ok(Math.abs(t2.mean[4] - expected) < 1e-9);
      const broken = clone(run2);
      broken.per_visitor.forEach((v) => { v.isi_week = v.isi_week.slice(0, 3); });
      assert.equal(isiTrajectories(broken), null);

      const page = html(full());
      // 轨迹：对照与运行 2 各一条均值线，每位来访一条细线，有效线画出
      assert.equal((page.match(/class="ch-line /g) ?? []).length, 2);
      assert.equal((page.match(/class="ch-faint /g) ?? []).length, control.per_visitor.length + run2.per_visitor.length);
      assert.match(page, /有效线 −7 分/);
      // 对比条：路径准确率第 2 轮 62.5% → 100%
      assert.match(page, /路径准确率 · 第 2 轮：对照 62\.5%，运行 2 100%，运行 1 62\.5%/);
      assert.match(page, /class="dot lead" style="left:100%"/);
      assert.match(page, /class="dot base" style="left:62\.5%"/);
      // 门禁条：基线 50%，选中的候选 75%，被硬规则拦下的不画长度
      assert.match(page, /--baseline:50%/);
      assert.match(page, /class="bar lead" style="width:75%"/);
      assert.match(page, /class="bar none"/);
      assert.match(page, /竖线是上一代 v1 的 <b>50%<\/b>/);
      // 没有证据时说明原因，不画假曲线
      assert.match(page, /这份证据尚未生成/);
      // 只有一次运行完成时，轨迹只画那一条
      const partial = html(full({ run2: slot('run2', null) }));
      assert.equal((partial.match(/class="ch-line /g) ?? []).length, 1);
      const none = html(full({ run2: slot('run2', null), control: slot('control', null) }));
      assert.doesNotMatch(none, /class="ch"/);
    });

    await t.test('安全线失守或实验失败时整页告警', () => {
      const bad = clone(run2);
      bad.metrics.crisis_missed = 1;
      bad.veto = { passed: false, reasons: [{ code: 'crisis_missed', message: '漏掉 1 例危机来访。' }] };
      const data = full({ run2: slot('run2', bad) });
      assert.equal(alertSlots(data).length, 1);
      assert.equal(finding(data).tone, 'negative');
      const page = html(data);
      assert.match(page, /bd-alert/);
      assert.match(page, /未守住/);
      assert.match(page, /运行 2：危机漏报。漏掉 1 例危机来访。/);
      assert.match(page, /role="alert"/);
      const failed = full({ experiment: { ...doneExperiment(), stage: 'failed', error: 'TimeoutError' }, run2: slot('run2', null), control: slot('control', null) });
      assert.deepEqual(finding(failed), { tone: 'negative', text: '实验执行失败：TimeoutError' });
      assert.match(html(failed), /bd-alert/);
    });
  } finally {
    globalThis.window = oldWindow;
    await server.close();
    await rm(temp, { recursive: true, force: true });
  }
});
