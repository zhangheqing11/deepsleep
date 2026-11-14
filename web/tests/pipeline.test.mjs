// 全链路演示回归：纯逻辑（时间、整体进度、会谈数、结论句）、串行轮询、接口适配器、mock 快照结构和页面静态渲染。
// 使用已安装的 Vite SSR 加载前端 TS；不连接真实后端，不调用模型。
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
const clone = (v) => JSON.parse(JSON.stringify(v));
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const memoryStorage = () => {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: (key) => data.delete(key) };
};

// ---------- api/PIPELINE_API.md 的结构，逐字段检查（与 extensionTypes.ts 的类型一一对应） ----------
const isStr = (v) => typeof v === 'string';
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const strOrNull = (v) => v === null || isStr(v);
const numOrNull = (v) => v === null || isNum(v);
const rateOrNull = (v) => v === null || (isNum(v) && v >= 0 && v <= 1);
const oneOf = (...xs) => (v) => xs.includes(v);
function check(ok, path, value) {
  assert.ok(ok, `${path} 不符合结构：${JSON.stringify(value)}`);
}
function checkLauncher(l, path = 'launcher') {
  check(typeof l.enabled === 'boolean', `${path}.enabled`, l.enabled);
  check(oneOf('idle', 'running', 'exited')(l.state), `${path}.state`, l.state);
  check(numOrNull(l.pid), `${path}.pid`, l.pid);
  check(strOrNull(l.preset), `${path}.preset`, l.preset);
  check(strOrNull(l.started_at), `${path}.started_at`, l.started_at);
  check(numOrNull(l.exit_code), `${path}.exit_code`, l.exit_code);
  check(Array.isArray(l.presets), `${path}.presets`, l.presets);
  for (const [i, p] of l.presets.entries()) {
    check(isStr(p.key) && isStr(p.label) && isStr(p.description), `${path}.presets[${i}]`, p);
    check(Number.isInteger(p.generations) && p.generations > 0 && isNum(p.expected_s), `${path}.presets[${i}]`, p);
  }
  check(Array.isArray(l.log_tail) && l.log_tail.every(isStr) && l.log_tail.length <= 20, `${path}.log_tail`, l.log_tail);
}
function checkRunResult(r, path) {
  if (r === null) return;
  check(rateOrNull(r.isi_response_rate) && rateOrNull(r.referral_recall) && rateOrNull(r.referral_precision), path, r);
  check(Number.isInteger(r.n) && isStr(r.playbook_version), path, r);
}
function checkSnapshot(s) {
  if (s.available === false) {
    assert.deepEqual(Object.keys(s).sort(), ['available', 'launcher']);
    return checkLauncher(s.launcher);
  }
  check(s.available === true && isStr(s.experiment_id), 'snapshot', s.experiment_id);
  check(oneOf('real', 'mock')(s.mode), 'mode', s.mode);
  check(oneOf('running', 'done', 'failed')(s.state), 'state', s.state);
  for (const k of ['error', 'started_at', 'updated_at', 'finished_at']) check(strOrNull(s[k]), k, s[k]);
  check(numOrNull(s.elapsed_s) && numOrNull(s.eta_s), 'elapsed_s/eta_s', [s.elapsed_s, s.eta_s]);
  check(Number.isInteger(s.generations_planned), 'generations_planned', s.generations_planned);
  check(isStr(s.playbook.from_version) && isStr(s.playbook.current_version), 'playbook', s.playbook);
  check(Array.isArray(s.steps), 'steps', s.steps);
  for (const [i, st] of s.steps.entries()) {
    const p = `steps[${i}]`;
    check(isStr(st.key) && isStr(st.label) && isStr(st.detail), p, st);
    check(oneOf('run', 'generation', 'practice', 'final')(st.kind), `${p}.kind`, st.kind);
    check(oneOf('pending', 'running', 'done', 'failed', 'skipped')(st.state), `${p}.state`, st.state);
    check(strOrNull(st.started_at) && strOrNull(st.finished_at), p, st);
    check(numOrNull(st.elapsed_s) && numOrNull(st.expected_s) && numOrNull(st.eta_s), p, st);
    if (st.state !== 'running') check(st.eta_s === null, `${p}.eta_s 只在进行中有值`, st.eta_s);
    check(Array.isArray(st.batches), `${p}.batches`, st.batches);
    for (const [j, b] of st.batches.entries()) {
      const q = `${p}.batches[${j}]`;
      check(isStr(b.run_id) && isStr(b.label) && isStr(b.version) && isStr(b.split), q, b);
      check(oneOf('run1', 'validation', 'practice', 'run2', 'control')(b.role), `${q}.role`, b.role);
      check(oneOf('running', 'done', 'failed')(b.state), `${q}.state`, b.state);
      check(Number.isInteger(b.total) && Number.isInteger(b.completed) && Number.isInteger(b.failed), q, b);
      check(b.completed + b.failed <= b.total, `${q} 会谈数不超过总数`, b);
      check(strOrNull(b.started_at) && strOrNull(b.finished_at) && numOrNull(b.duration_s) && rateOrNull(b.isi_response_rate), q, b);
    }
    if (st.kind === 'generation' && st.generation) {
      const g = st.generation;
      check(Number.isInteger(g.index) && isStr(g.evolution_id) && isStr(g.from_version), `${p}.generation`, g);
      check(g.phase === null || oneOf('reflecting', 'validating', 'committing', 'done', 'failed')(g.phase), `${p}.generation.phase`, g.phase);
      check(g.reflector === null || (oneOf('running', 'done')(g.reflector.state) && strOrNull(g.reflector.model)), `${p}.generation.reflector`, g.reflector);
      check(rateOrNull(g.baseline_isi), `${p}.generation.baseline_isi`, g.baseline_isi);
      for (const c of g.candidates) {
        check(isStr(c.id) && oneOf('pending', 'running', 'done')(c.state) && rateOrNull(c.isi), `${p}.candidate`, c);
        check(c.passed === null || typeof c.passed === 'boolean', `${p}.candidate.passed`, c);
      }
      check(g.outcome === null || oneOf('committed', 'kept_previous')(g.outcome), `${p}.generation.outcome`, g.outcome);
      check(strOrNull(g.to_version) && strOrNull(g.chosen), `${p}.generation`, g);
    } else {
      check(st.generation === undefined || st.generation === null, `${p}.generation 只属于 generation 步骤`, st.generation);
    }
  }
  for (const k of ['run1', 'control', 'run2']) checkRunResult(s.result[k], `result.${k}`);
  check(numOrNull(s.result.delta_pp), 'result.delta_pp', s.result.delta_pp);
  checkLauncher(s.launcher);
}

test('全链路演示', async (t) => {
  const temp = await mkdtemp(join(tmpdir(), 'deepsleep-pipeline-'));
  const server = await createServer({ root, configFile: false, cacheDir: temp, server: { middlewareMode: true },
    esbuild: { jsx: 'automatic' }, define: { 'import.meta.env.VITE_API_ADAPTER': '"http"' } });
  const oldWindow = globalThis.window;
  const oldFetch = globalThis.fetch;
  globalThis.window = { setTimeout, clearTimeout, setInterval, clearInterval, localStorage: memoryStorage(), sessionStorage: memoryStorage() };
  try {
    const lib = await server.ssrLoadModule('/src/lib/pipeline.ts');
    const { MOCK_PIPELINE } = await server.ssrLoadModule('/src/api/mockPipeline.ts');
    const { mockClient } = await server.ssrLoadModule('/src/api/mockClient.ts');
    const { httpClient } = await server.ssrLoadModule('/src/api/httpClient.ts');
    const { withRequestLog, requestLog } = await server.ssrLoadModule('/src/api/requestLog.ts');
    const { ApiError } = await server.ssrLoadModule('/src/api/errors.ts');
    const { startPipelinePolling, pipelineDelay } = await server.ssrLoadModule('/src/hooks/usePipeline.ts');
    const { parseRoute, HREF } = await server.ssrLoadModule('/src/hooks/useHashRoute.ts');
    const { PipelineView } = await server.ssrLoadModule('/src/pages/console/PipelinePage.tsx');

    await t.test('时间格式：mm:ss，一小时以上 h:mm:ss，缺失为“—”', () => {
      assert.equal(lib.clock(0), '00:00');
      assert.equal(lib.clock(59.9), '00:59');
      assert.equal(lib.clock(61), '01:01');
      assert.equal(lib.clock(605), '10:05');
      assert.equal(lib.clock(3725), '1:02:05');
      assert.equal(lib.clock(-3), '00:00');
      assert.equal(lib.clock(null), '—');
      assert.equal(lib.clock(undefined), '—');
      assert.equal(lib.aboutMinutes(400), '约 7 分钟');
      assert.equal(lib.aboutMinutes(1500), '约 25 分钟');
      assert.equal(lib.aboutMinutes(20), '约 1 分钟');
      assert.equal(lib.aboutMinutes(null), '—');
    });

    await t.test('本地走表只在进行中走，且从服务端的值起算', () => {
      assert.equal(lib.tick(100, 1000, 4000, true), 103);
      assert.equal(lib.tick(100, 1000, 4000, false), 100);
      assert.equal(lib.tick(10, 1000, 31000, true, -1), 0);
      assert.equal(lib.tick(10, 1000, 4000, true, -1), 7);
      assert.equal(lib.tick(null, 1000, 4000, true), null);
    });

    await t.test('整体进度：按预计时长估算，结束前最多 99%', () => {
      assert.equal(lib.overallProgress({ state: 'done', elapsed_s: 10, eta_s: null }), 1);
      assert.equal(lib.overallProgress({ state: 'running', elapsed_s: 100, eta_s: 100 }), 0.5);
      assert.equal(lib.overallProgress({ state: 'running', elapsed_s: 400, eta_s: 0 }), 0.99);
      assert.equal(lib.overallProgress({ state: 'running', elapsed_s: 100, eta_s: null, steps: [{ expected_s: 150 }, { expected_s: 250 }] }), 0.25);
      assert.equal(lib.overallProgress({ state: 'running', elapsed_s: 100, eta_s: null, steps: [] }), null);
      assert.equal(lib.overallProgress({ state: 'running', elapsed_s: null, eta_s: 50 }), null);
      assert.equal(lib.overallProgress({ state: 'failed', elapsed_s: 900, eta_s: null, steps: [{ expected_s: 400 }] }), 0.99);
      // 本地走表的值优先
      assert.equal(lib.overallProgress({ state: 'running', elapsed_s: 100, eta_s: 100 }, 150, 50), 0.75);
    });

    await t.test('每步会谈数把各批次加起来；没有批次时总数未知', () => {
      const b = (completed, failed, total) => ({ completed, failed, total });
      const t1 = lib.stepSessions({ batches: [b(30, 0, 45), b(7, 2, 45)] });
      assert.deepEqual(t1, { completed: 37, failed: 2, total: 90, ratio: 39 / 90 });
      assert.equal(lib.sessionsText(t1), '已完成 37 / 90 场会谈');
      const none = lib.stepSessions({ batches: [] });
      assert.equal(none.total, null);
      assert.equal(none.ratio, null);
      assert.equal(lib.sessionsText(none), '尚未开始会谈');
    });

    await t.test('结论句：采纳与保留上一代；未结束为 null', () => {
      const cands = [{ id: 'c1' }, { id: 'c2' }, { id: 'c3' }];
      assert.equal(lib.outcomeSentence({ outcome: 'committed', chosen: 'c1', to_version: 'v2', from_version: 'v1', candidates: cands }), '采纳候选 c1 → v2');
      assert.equal(lib.outcomeSentence({ outcome: 'kept_previous', chosen: null, to_version: null, from_version: 'v1', candidates: cands }), '三份候选均未通过，保留 v1');
      assert.equal(lib.outcomeSentence({ outcome: 'kept_previous', chosen: null, to_version: null, from_version: 'v2', candidates: cands.slice(0, 2) }), '两份候选均未通过，保留 v2');
      assert.equal(lib.outcomeSentence({ outcome: null, chosen: null, to_version: null, from_version: 'v1', candidates: cands }), null);
      assert.equal(lib.outcomeSentence(null), null);
    });

    await t.test('指标：缺失显示“—”，百分点差由两份结果直接算', () => {
      assert.equal(lib.rate(null), '—');
      assert.equal(lib.rate(0), '0.0%');
      assert.equal(lib.rate(0.5833), '58.3%');
      const r = (isi) => ({ isi_response_rate: isi, referral_recall: null, referral_precision: null, n: 45, playbook_version: 'v1' });
      assert.equal(lib.deltaPoints({ run1: null, control: r(0.511), run2: r(0.6), delta_pp: 8.9 }), 8.9);
      assert.equal(lib.deltaPoints({ run1: null, control: r(0.6), run2: null, delta_pp: null }), null);
      assert.equal(lib.signedPoints(8.9), '+8.9 个百分点');
      assert.equal(lib.signedPoints(-2), '−2.0 个百分点');
      assert.equal(lib.signedPoints(0), '±0.0 个百分点');
      assert.equal(lib.signedPoints(null), '—');
    });

    await t.test('折叠摘要与默认展开', () => {
      const [run1, gen1, final] = MOCK_PIPELINE.steps;
      assert.equal(lib.stepSummary(run1), '45 / 45 场会谈 · 运行 1 ISI 有效率 51.1% · 用时 01:58');
      assert.equal(lib.stepSummary(final), '等待中 · 预计约 1 分钟');
      assert.equal(lib.stepSummary({ ...final, kind: 'practice', state: 'skipped' }), '上一代没有采纳新版本，跳过练习');
      const kept = { ...clone(gen1), state: 'done', eta_s: null, generation: { ...clone(gen1.generation), outcome: 'kept_previous' } };
      assert.match(lib.stepSummary(kept), /^三份候选均未通过，保留 v1 · 72 \/ 90 场会谈 · 用时 01:35$/);
      assert.deepEqual(MOCK_PIPELINE.steps.map(lib.defaultOpen), [false, true, false]);
      assert.equal(lib.defaultOpen({ state: 'failed' }), true);
    });

    await t.test('轮询间隔：进行中 1 秒，其余 3 秒，失败按退避', () => {
      assert.equal(pipelineDelay(MOCK_PIPELINE, 0), 1000);
      assert.equal(pipelineDelay({ ...MOCK_PIPELINE, state: 'done' }, 0), 3000);
      assert.equal(pipelineDelay({ available: false, launcher: MOCK_PIPELINE.launcher }, 0), 3000);
      assert.equal(pipelineDelay(null, 0), 3000);
      assert.equal(pipelineDelay(MOCK_PIPELINE, 1), 2000);
      assert.equal(pipelineDelay(MOCK_PIPELINE, 9), 5000);
    });

    await t.test('串行轮询：不并发、失败后继续重试、poke 不并发、stop 取消', async () => {
      let active = 0, maxActive = 0, calls = 0;
      const seen = [];
      const errors = [];
      const fetcher = async (signal) => {
        calls += 1;
        active += 1; maxActive = Math.max(maxActive, active);
        await wait(5);
        active -= 1;
        if (signal.aborted) throw new ApiError({ kind: 'aborted', message: '请求已取消' });
        if (calls === 2 || calls === 3) throw new ApiError({ kind: 'http', status: 404, code: 'NOT_FOUND', message: 'x' });
        return calls;
      };
      const h = startPipelinePolling(fetcher, () => 1, (d) => seen.push(d), (e) => errors.push(e.code));
      await wait(15);
      h.poke(); h.poke(); // 正在请求时 poke：结束后再读一次，不并发
      await wait(80);
      h.stop();
      const after = calls;
      await wait(30);
      assert.equal(maxActive, 1);
      assert.deepEqual(errors, ['NOT_FOUND', 'NOT_FOUND']); // 4xx 也不停止
      assert.ok(seen.length >= 2 && seen[0] === 1 && seen[1] === 4, `seen=${seen}`);
      assert.equal(calls, after); // stop 之后不再请求
    });

    await t.test('路由与侧栏：#/console/pipeline 是全链路演示，#/console 仍是运行页', () => {
      assert.deepEqual(parseRoute('#/console/pipeline'), { name: 'console-pipeline' });
      assert.deepEqual(parseRoute(HREF.pipeline), { name: 'console-pipeline' });
      assert.deepEqual(parseRoute('#/console'), { name: 'console-runs' });
      assert.deepEqual(parseRoute('#/console/runs'), { name: 'console-runs' });
    });

    await t.test('mock 快照符合接口结构，且是一份进行中的静态快照', async () => {
      checkSnapshot(MOCK_PIPELINE);
      checkSnapshot({ available: false, launcher: { ...clone(MOCK_PIPELINE.launcher), enabled: false, state: 'idle', pid: null, preset: null, started_at: null, log_tail: [] } });
      assert.equal(MOCK_PIPELINE.state, 'running');
      assert.deepEqual(MOCK_PIPELINE.steps.map((s) => [s.key, s.state]), [['run1', 'done'], ['gen1', 'running'], ['final', 'pending']]);
      const gen = MOCK_PIPELINE.steps[1].generation;
      assert.equal(gen.phase, 'validating');
      assert.deepEqual(gen.candidates.map((c) => c.state), ['done', 'running', 'pending']);
      assert.equal(MOCK_PIPELINE.result.control, null);
      // 适配器返回副本，前后两次读到的都一样（没有计时器推进）
      const a = await mockClient.getPipeline();
      await wait(20);
      const b = await mockClient.getPipeline();
      assert.deepEqual(a, MOCK_PIPELINE);
      assert.deepEqual(b, a);
      a.steps.length = 0;
      assert.equal(MOCK_PIPELINE.steps.length, 3);
      await assert.rejects(mockClient.launchPipeline({ preset: 'live', mock: true }), (e) => e.status === 501 && /模拟数据模式下不能启动/.test(e.message));
      await assert.rejects(mockClient.stopPipeline(), (e) => e.status === 501 && /模拟数据模式下不能启动/.test(e.message));
      const controller = new AbortController(); controller.abort();
      await assert.rejects(mockClient.getPipeline(controller.signal), (e) => e.kind === 'aborted');
    });

    await t.test('HTTP：三个接口的方法、路径、请求体；错误沿用服务端 message', async () => {
      requestLog.clear();
      const seen = [];
      let respond = () => new Response(JSON.stringify(MOCK_PIPELINE), { headers: { 'X-Request-ID': 'req-pl' } });
      globalThis.fetch = async (url, options) => { seen.push({ url, method: options.method, body: options.body ?? null }); return respond(); };
      const client = withRequestLog(httpClient);
      const signal = new AbortController().signal;
      checkSnapshot(await client.getPipeline(signal));
      respond = () => new Response(JSON.stringify({ pid: 1, preset: 'full', mock: true }), { status: 202 });
      assert.deepEqual(await client.launchPipeline({ preset: 'full', mock: true }, signal), { pid: 1, preset: 'full', mock: true });
      respond = () => new Response(JSON.stringify({ stopped: true }));
      assert.deepEqual(await client.stopPipeline(signal), { stopped: true });
      assert.deepEqual(seen, [
        { url: '/api/v1/demo/pipeline', method: 'GET', body: null },
        { url: '/api/v1/demo/launch', method: 'POST', body: '{"preset":"full","mock":true}' },
        { url: '/api/v1/demo/stop', method: 'POST', body: null },
      ]);
      assert.deepEqual(requestLog.snapshot().map((e) => e.op), ['POST /demo/stop', 'POST /demo/launch', 'GET /demo/pipeline']);
      respond = () => new Response(JSON.stringify({ error: { code: 'ALREADY_RUNNING', message: '已有一场全链路在运行（pid 12345）' } }), { status: 409 });
      await assert.rejects(client.launchPipeline({ preset: 'live', mock: false }), (e) => e.status === 409 && e.code === 'ALREADY_RUNNING' && e.message === '已有一场全链路在运行（pid 12345）' && !e.isTransient);
      respond = () => new Response(JSON.stringify({ error: { code: 'LAUNCH_DISABLED', message: '未开启一键启动' } }), { status: 403 });
      await assert.rejects(client.stopPipeline(), (e) => e.status === 403 && e.code === 'LAUNCH_DISABLED');
    });

    // ---------- 页面静态渲染 ----------
    const actions = { busy: null, error: null, launch: () => {}, stop: () => {}, dismiss: () => {} };
    const NOW = 1_700_000_000_000;
    const view = (data, extra = {}) => renderToStaticMarkup(React.createElement(PipelineView, {
      poll: { data, error: null, receivedAt: NOW, ...extra.poll }, now: extra.now ?? NOW, actions: { ...actions, ...extra.actions },
    }));
    const text = (html) => html.replace(/<[^>]+>/g, '');

    await t.test('进行中：标题、状态、步骤按顺序全部列出，进行中的步骤展开', () => {
      const html = view(MOCK_PIPELINE);
      const plain = text(html);
      assert.match(plain, /全链路演示/);
      assert.match(html, /class="pl-pill pl-pill-running">进行中</);
      assert.match(plain, /已用时间03:33/);
      assert.match(plain, /预计剩余03:05/);
      const order = ['运行 1', '学习 · 第 1 代', '运行 2 与对照'].map((l) => html.indexOf(`<strong>${l}</strong>`));
      assert.ok(order.every((i) => i > 0) && order[0] < order[1] && order[1] < order[2], `${order}`);
      assert.match(html, /aria-expanded="true"[^>]*>.*学习 · 第 1 代/);
      assert.match(html, /aria-expanded="false"[^>]*>.*运行 1/);
      assert.match(plain, /已完成 72 \/ 90 场会谈/);
      assert.match(plain, /claude-opus-5-5/);
      assert.doesNotMatch(plain, /降级/);
      assert.match(plain, /上一代基线v1 · ISI 有效率 52\.2%/);
      assert.match(plain, /c1已验证58\.3%—/);
      assert.match(plain, /候选 2 · 第 1 次/);
      // 未开始的步骤不能展开，但在计划里
      assert.match(html, /<div class="pl-step-head"><span class="pl-step-title"><strong>运行 2 与对照<\/strong>/);
      // 进行中的子进程：启动控件换成停止
      assert.match(html, />停止<\/button>/);
      assert.doesNotMatch(plain, /开始全链路/);
    });

    await t.test('本地走表：两次轮询之间时间往前走，剩余时间往下减', () => {
      const plain = text(view(MOCK_PIPELINE, { now: NOW + 5000 }));
      assert.match(plain, /已用时间03:38/);
      assert.match(plain, /预计剩余03:00/);
    });

    await t.test('结果：没有的写“尚未生成”或“—”，不写成 0', () => {
      const plain = text(view(MOCK_PIPELINE));
      assert.match(plain, /运行 1（v1 · A 组）ISI 有效率51\.1%转介召回 80\.0% \/ 精确率 66\.7%/);
      assert.match(plain, /对照（v1 · B 组）ISI 有效率尚未生成/);
      assert.match(plain, /运行 2（新版本 · B 组）ISI 有效率尚未生成比对照 —/);
      assert.match(plain, /ISI 为规则状态模型的四周模拟值，所有来访均为模拟数据/);
      assert.match(plain, /运行日志/);
    });

    await t.test('完成：保留上一代按正常结果呈现，并给出进化记录与看板链接', () => {
      const done = clone(MOCK_PIPELINE);
      done.state = 'done'; done.eta_s = null; done.elapsed_s = 402;
      done.launcher.state = 'exited';
      const gen = done.steps[1];
      gen.state = 'done'; gen.eta_s = null;
      gen.generation = { ...gen.generation, phase: 'done', outcome: 'kept_previous', candidates: gen.generation.candidates.map((c) => ({ ...c, state: 'done', isi: 0.5, passed: false })) };
      done.steps[2] = { ...done.steps[2], state: 'done', elapsed_s: 80, batches: [] };
      const r = (isi, v) => ({ isi_response_rate: isi, referral_recall: 0.75, referral_precision: 0.6, n: 45, playbook_version: v });
      done.result = { run1: r(0.511, 'v1'), control: r(0.533, 'v1'), run2: r(0.533, 'v1'), delta_pp: 0 };
      const html = view(done, { /* 用户手动展开第 1 代需要交互；这里检查折叠摘要 */ });
      const plain = text(html);
      assert.match(html, /pl-pill-done">已完成</);
      assert.match(plain, /总用时06:42/);
      assert.match(plain, /三份候选均未通过，保留 v1/);
      assert.doesNotMatch(html, /pl-step is-failed|notice-danger/);
      assert.match(html, /href="#\/console\/evolution">查看进化记录</);
      assert.match(html, /href="#\/">回到进化看板</);
      assert.match(plain, /比对照 ±0\.0 个百分点/);
      // 进程已退出：重新出现启动控件
      assert.match(plain, /开始全链路/);
      assert.match(plain, /现场模式学习 1 代 · 约 7 分钟/);
      assert.match(plain, /完整模式学习 3 代 · 约 25 分钟/);
      assert.match(plain, /演练（不调用模型）/);
    });

    await t.test('展开后的保留上一代：中性样式，候选表写“未通过”', () => {
      const failedGen = clone(MOCK_PIPELINE);
      const gen = failedGen.steps[1];
      gen.state = 'failed'; gen.eta_s = null; // 失败的步骤默认展开，借此检查展开后的结论
      gen.generation = { ...gen.generation, outcome: 'kept_previous', candidates: gen.generation.candidates.map((c) => ({ ...c, state: 'done', isi: 0.5, passed: false })) };
      const html = view(failedGen);
      assert.match(html, /<p class="pl-outcome is-kept_previous">三份候选均未通过，保留 v1<\/p>/);
      assert.match(html, /<span class="pl-fail">未通过<\/span>/);
    });

    await t.test('反思器降级有可见标注', () => {
      const s = clone(MOCK_PIPELINE);
      s.steps[1].generation.reflector.fell_back = true;
      assert.match(text(view(s)), /已自动降级为备用模型/);
    });

    await t.test('后端没开一键启动：启动按钮禁用并提示终端命令，进度照常显示', () => {
      const s = clone(MOCK_PIPELINE);
      s.launcher = { ...s.launcher, enabled: false, state: 'idle', pid: null };
      const html = view(s);
      assert.match(text(html), /此后端未开启一键启动；请在终端执行 make demo-run1/);
      assert.match(html, /<button type="button" class="btn btn-primary pl-start" disabled="">开始全链路<\/button>/);
      assert.match(html, /<fieldset class="pl-presets" disabled="">/);
      assert.match(text(html), /已完成 72 \/ 90 场会谈/);
    });

    await t.test('还没有实验：尚未开始，结果全是“尚未生成”', () => {
      const html = view({ available: false, launcher: { ...clone(MOCK_PIPELINE.launcher), state: 'idle', pid: null, preset: null, log_tail: [] } });
      const plain = text(html);
      assert.match(html, /pl-pill-none">尚未开始</);
      assert.match(plain, /还没有全链路实验/);
      assert.equal(plain.match(/尚未生成/g).length, 3);
      assert.match(html, /<button type="button" class="btn btn-primary pl-start">开始全链路<\/button>/);
      assert.match(plain, /（暂无输出）/);
    });

    await t.test('连接中断：保留上一份数据并提示正在重试；启动失败用服务端的话', () => {
      const error = new ApiError({ kind: 'network', message: 'fetch failed' });
      const html = view(MOCK_PIPELINE, { poll: { error } });
      assert.match(text(html), /连接中断，正在重试/);
      assert.match(text(html), /学习 · 第 1 代/);
      const conflict = new ApiError({ kind: 'http', status: 409, code: 'ALREADY_RUNNING', message: '已有一场全链路在运行' });
      const failed = text(view(MOCK_PIPELINE, { actions: { error: { op: 'launch', error: conflict } } }));
      assert.match(failed, /没能启动/);
      assert.match(failed, /已有一场全链路在运行/);
      const first = text(view(null, { poll: { error } }));
      assert.match(first, /读不到全链路进度，正在重试/);
    });

    await t.test('失败：显示失败原因', () => {
      const s = clone(MOCK_PIPELINE);
      s.state = 'failed'; s.error = '已手动停止'; s.eta_s = null; s.launcher.state = 'exited';
      const html = view(s);
      assert.match(html, /pl-pill-failed">失败</);
      assert.match(text(html), /全链路没有走完已手动停止/);
    });

    await t.test('措辞边界：新页面与逻辑不出现禁用字样', async () => {
      for (const f of ['src/pages/console/PipelinePage.tsx', 'src/lib/pipeline.ts', 'src/api/mockPipeline.ts', 'src/components/SurfaceNav.tsx', 'src/pipeline.css']) {
        assert.doesNotMatch(await readFile(join(root, f), 'utf8'), /诊断|治疗失眠症/, f);
      }
    });
  } finally {
    globalThis.window = oldWindow;
    globalThis.fetch = oldFetch;
    await server.close();
    await rm(temp, { recursive: true, force: true });
  }
});
