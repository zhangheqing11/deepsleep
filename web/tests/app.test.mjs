// 用户端回归：会谈配对、逐步回放、两场对比和自评的展示。
// 使用已安装的 Vite SSR 加载前端 TS；不安装包，不连接真实后端或模型。
import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { mkdtemp, rm, readFile, readdir } from 'node:fs/promises';
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

test('用户端：配对、回放、对比与自评', async (t) => {
  const temp = await mkdtemp(join(tmpdir(), 'deepsleep-app-'));
  const server = await createServer({ root, configFile: false, cacheDir: temp, server: { middlewareMode: true },
    esbuild: { jsx: 'automatic' }, define: { 'import.meta.env.VITE_API_ADAPTER': '"http"' } });
  const oldWindow = globalThis.window;
  globalThis.window = { setTimeout, clearTimeout, setInterval, clearInterval, localStorage: memoryStorage(), sessionStorage: memoryStorage() };
  try {
    const replay = await server.ssrLoadModule('/src/lib/replay.ts');
    const view = await server.ssrLoadModule('/src/components/app/Replay.tsx');
    const { parseRoute, visitorHref } = await server.ssrLoadModule('/src/hooks/useHashRoute.ts');
    const { SCALE_INFO } = await server.ssrLoadModule('/src/lib/scales.ts');
    const { readCatalog, createCatalogCache, pairVisitors, tally, buildSteps, advance, initialShown, pendingLine, openingLine,
      digest, onlyIn, scaleResults, headline, sideName } = replay;
    const html = (el) => renderToStaticMarkup(el);
    const signal = new AbortController().signal;

    const controlReport = await example('run_report.control.json');
    const run2Report = await example('run_report.run2.json');
    const run1Report = await example('run_report.run1.json');
    const evolution = await example('evolution.v1-v2.json');
    const s1 = await example('session.A-001.json');
    const s2 = await example('session.A-002.json');
    const s3 = await example('session.A-003.json');

    // 让两份报告里的来访与三场示例会谈对上号
    const ids = ['A-001', 'A-002', 'A-003'];
    const withRows = (report, changes) => {
      const r = clone(report);
      r.per_visitor = ids.map((id, i) => {
        const row = clone(report.per_visitor[i]);
        const end = row.isi_week[0] + changes[i];
        return { ...row, visitor_id: id, crisis_pred: 'none', isi_week: [row.isi_week[0], row.isi_week[0], end, end, end], isi_change: changes[i], responder: changes[i] < -7 };
      });
      return r;
    };
    const control = withRows(controlReport, [-3, -9, -4]);
    const run2 = withRows(run2Report, [-9, -9, -2]);
    const node = (report, state = 'done') => ({ run_id: report.run_id, playbook_version: report.playbook_version, split: report.split, state });
    const experiment = (extra = {}) => ({
      experiment_id: 'exp-1', updated_at: '2026-11-15T09:05:00+08:00', stage: 'done', error: null,
      run1: node(run1Report), control: node(control), run2: node(run2),
      evolution: { evolution_id: evolution.evolution_id, state: 'done' }, ...extra,
    });
    const fakeApi = (exp, overrides = {}) => {
      const calls = {};
      const reports = { [run1Report.run_id]: run1Report, [control.run_id]: control, [run2.run_id]: run2 };
      const base = {
        adapter: 'http',
        getExperiment: async () => exp,
        getReport: async (id) => clone(reports[id]),
        listSessions: async () => ({ items: ids.map((id) => ({
          visitor_id: id, status: 'succeeded', session_available: true, session_status: id === 'A-003' ? 'crisis_exit' : 'completed' })) }),
        getEvolution: async () => clone(evolution),
        ...overrides,
      };
      const api = {};
      for (const [k, v] of Object.entries(base)) {
        api[k] = typeof v === 'function' ? (...args) => { calls[k] = (calls[k] ?? 0) + 1; return v(...args); } : v;
      }
      return { api, calls };
    };

    await t.test('配对：学习前取对照，学习后取运行 2；读过的报告不再重读', async () => {
      const { api, calls } = fakeApi(experiment());
      const cache = createCatalogCache();
      const cat = await readCatalog(api, cache, signal);
      await readCatalog(api, cache, signal);
      assert.equal(cat.before.role, 'control');
      assert.equal(cat.after.role, 'run2');
      assert.equal(cat.sameVersion, false);
      assert.equal(calls.getReport, 2);
      assert.equal(calls.listSessions, 2);
      assert.equal(calls.getEvolution, 1);
      // 学到的规则来自被选中的那份候选
      const chosen = evolution.candidates.find((c) => c.id === evolution.chosen);
      assert.deepEqual(cat.learned.map((c) => c.id), chosen.changes.map((c) => c.id));
      // 按学习后多降的分数排序：A-001 多降 6 分，A-002 一样，A-003 少降 2 分
      assert.deepEqual(cat.visitors.map((v) => [v.id, v.gain]), [['A-001', 6], ['A-002', 0], ['A-003', -2]]);
      assert.equal(cat.visitors.find((v) => v.id === 'A-003').safety, true);
      assert.deepEqual(tally(cat.visitors), { paired: 3, better: 1, same: 1, worse: 1 });
      assert.match(headline(cat), /从 v1 改写成了 v2/);
      assert.equal(sideName(cat, 'before'), '学习前');
      assert.equal(sideName(cat, 'after'), '学习后');
    });

    await t.test('各阶段如实降级：没有实验、只有运行 1、保留上一代', async () => {
      assert.equal(await readCatalog(fakeApi({ available: false }).api, createCatalogCache(), signal), null);
      assert.match(headline(null), /还没有跑出会谈/);

      const early = experiment({ stage: 'learning', control: null, run2: null, evolution: { evolution_id: null, state: 'running' } });
      const cat1 = await readCatalog(fakeApi(early).api, createCatalogCache(), signal);
      assert.equal(cat1.before.role, 'run1');
      assert.equal(cat1.after, null);
      assert.equal(cat1.outcome, null);
      assert.equal(sideName(cat1, 'before'), '运行 1');
      assert.match(headline(cat1), /学习后的版本还没有跑/);
      assert.equal(cat1.visitors.every((v) => v.gain === null && v.hasBefore && !v.hasAfter), true);

      const kept = clone(evolution);
      Object.assign(kept, { outcome: 'kept_previous', to_version: null, chosen: null, commit: null });
      const sameRun2 = { ...node(run2), playbook_version: 'v1' };
      const { api } = fakeApi(experiment({ run2: sameRun2 }), {
        getEvolution: async () => kept,
        getReport: async (id) => (id === run2.run_id ? { ...clone(run2), playbook_version: 'v1' } : clone(control)),
      });
      const cat2 = await readCatalog(api, createCatalogCache(), signal);
      assert.equal(cat2.sameVersion, true);
      assert.equal(cat2.outcome, 'kept_previous');
      assert.deepEqual(cat2.learned, []);
      assert.equal(sideName(cat2, 'before'), '对照');
      assert.equal(sideName(cat2, 'after'), '运行 2');
      assert.match(headline(cat2), /保留了上一代手册/);

      // 报告读不到时仍然能列出来访，只是没有分数
      const { api: noReport } = fakeApi(experiment(), { getReport: async () => { throw new Error('boom'); } });
      const cat3 = await readCatalog(noReport, createCatalogCache(), signal);
      assert.equal(cat3.visitors.length, 3);
      assert.equal(cat3.visitors.every((v) => v.gain === null), true);
    });

    await t.test('回放：替来访说一句，教练的回应连同筛查一起出现', () => {
      const steps = buildSteps(s2);
      assert.equal(steps[0].kind, 'round');
      assert.equal(steps.at(-1).kind, 'end');
      // 工具调用按序号插进对话里
      const tool = steps.findIndex((s) => s.kind === 'tool');
      assert.ok(tool > 0);
      const call = s2.tool_calls[0];
      const before = steps.slice(0, tool).filter((s) => s.kind === 'turn' && s.round === call.round);
      assert.equal(before.every((s) => s.turn.turn < call.turn), true);

      let at = initialShown(steps);
      assert.equal(pendingLine(steps, at), openingLine(s2));
      let guard = 0;
      while (at < steps.length && guard++ < 50) {
        const next = advance(steps, at);
        assert.ok(next > at);
        // 每次推进后要么停在下一句来访发言前，要么放完
        assert.equal(next === steps.length || pendingLine(steps, next) !== null, true);
        at = next;
      }
      assert.equal(at, steps.length);

      // 第 2 轮由教练先开口时，不会卡住
      const agentFirst = clone(s2);
      agentFirst.rounds[0].transcript = agentFirst.rounds[0].transcript.filter((x) => x.speaker !== 'visitor').slice(0, 1);
      const st = buildSteps(agentFirst);
      assert.ok(advance(st, initialShown(st)) > initialShown(st));
    });

    await t.test('会谈展示：安全层的话原样显示并标明不随进化改变', () => {
      const steps = buildSteps(s3);
      const page = html(React.createElement(view.Transcript, { steps, shown: steps.length, typing: false }));
      const safety = s3.rounds.flatMap((r) => r.transcript).find((x) => x.speaker === 'safety');
      assert.ok(safety);
      assert.match(page, /安全层 · 固定话术，不随进化改变/);
      assert.ok(page.includes(safety.text.split('\n')[0]));
      assert.match(page, /教练补做了一次情绪筛查/);
      assert.equal((page.match(/class="ua-msg visitor"/g) ?? []).length, s3.rounds.flatMap((r) => r.transcript).filter((x) => x.speaker === 'visitor').length);
      // 只显示已经放到的部分
      const partial = html(React.createElement(view.Transcript, { steps, shown: 2, typing: true }));
      assert.equal((partial.match(/class="ua-msg/g) ?? []).length, 2);
      assert.match(partial, /教练正在回应/);
    });

    await t.test('收尾：计划与四周结果；出错和安全流程如实说明', () => {
      const d = digest(s1, control.per_visitor[0]);
      const done = html(React.createElement(view.Ending, { session: s1, digest: d }));
      assert.match(done, /教练给出的计划/);
      assert.ok(done.includes(s1.plan.bedtime) && done.includes(s1.plan.risetime));
      assert.match(done, /未达到有效线/);
      assert.match(done, /不是真人的结果/);

      const broken = { ...clone(s1), status: 'error', error: '模型超时', plan: null };
      const err = html(React.createElement(view.Ending, { session: broken, digest: digest(broken, null) }));
      assert.match(err, /中途出错，没有走完：模型超时/);
      assert.doesNotMatch(err, /教练给出的计划/);

      const crisis = { ...clone(s1), status: 'crisis_exit', plan: null };
      const out = html(React.createElement(view.Ending, { session: crisis, digest: digest(crisis, null) }));
      assert.match(out, /安全层接管后，这场会谈到此结束/);
      assert.doesNotMatch(out, /四周/);
    });

    await t.test('对比：只在一侧出现的话题带标记；同一版手册时不把差别算在学习头上', () => {
      const a = clone(s1);
      a.playbook_version = 'v2';
      a.rounds[0].asked_topics = [...new Set([...a.rounds[0].asked_topics, 'weekend_catchup'])];
      const b = clone(s1);
      b.rounds.forEach((r) => { r.asked_topics = r.asked_topics.filter((x) => x !== 'weekend_catchup'); });
      const dB = digest(b, control.per_visitor[0]);
      const dA = digest(a, run2.per_visitor[0]);
      assert.deepEqual([...onlyIn(dA.topics, dB.topics)], ['weekend_catchup']);
      assert.equal(onlyIn(dA.topics, null).size, 0);

      const chosen = evolution.candidates.find((c) => c.id === evolution.chosen);
      const props = { before: dB, after: dA, beforeName: '学习前', afterName: '学习后', sameVersion: false,
        learned: chosen.changes, learnedSummary: chosen.summary, outcome: 'committed' };
      const page = html(React.createElement(view.Compare, props));
      assert.match(page, /<li class="fresh">周末补觉<\/li>/);
      assert.match(page, /教练写进新手册的规则/);
      assert.ok(page.includes(chosen.changes[0].after));
      assert.match(page, /不做逐句对应/);
      assert.match(page, /四周 ISI，学习前 \d+ 到 \d+，学习后 \d+ 到 \d+/);
      assert.match(page, /−9 分，有效/);
      assert.doesNotMatch(page, /同一版手册/);

      const same = html(React.createElement(view.Compare, { ...props, beforeName: '对照', afterName: '运行 2', sameVersion: true,
        learned: [], learnedSummary: null, outcome: 'kept_previous' }));
      assert.match(same, /两场会谈用的是同一版手册。下面的差别来自对话本身，不是学习的结果。/);
      assert.match(same, /教练这次没有改手册/);

      // 只有一场时另一列如实留空；还没有进化结果时不提规则
      const single = html(React.createElement(view.Compare, { ...props, after: null, learned: [], outcome: null }));
      assert.match(single, /这一场还没有/);
      assert.doesNotMatch(single, /手册的规则|没有改手册/);
    });

    await t.test('自评：只展示模拟来访的作答；第 9 题大于 0 标出并说明交给安全层', () => {
      const s = clone(s1);
      s.context_scales = [
        { scale: 'isi', reported_score: 19, items: null },
        { scale: 'phq9', reported_score: 5, items: [1, 1, 1, 0, 0, 0, 0, 0, 2] },
      ];
      s.tool_calls = [{ round: 1, turn: 4, tool: 'screen_osa', result: { stop_bang: 4 } }];
      const results = scaleResults(s);
      assert.deepEqual(results.map((r) => [r.scale, r.score, r.source]), [['isi', 19, 'prefilled'], ['phq9', 5, 'prefilled'], ['stop_bang', 4, 'screened']]);
      const page = html(React.createElement(view.Scales, { session: s }));
      assert.match(page, /class="flagged"/);
      assert.equal((page.match(/class="flagged"/g) ?? []).length, 1);
      assert.match(page, /第 9 题大于 0 时不由教练处理，直接交给固定的安全层/);
      assert.match(page, /一半以上的天数/);
      assert.match(page, /这次只记录了总分，没有逐题作答/);
      assert.match(page, /不是量表原文/);
      assert.match(page, /页面上没有让真人填写的入口/);
      assert.doesNotMatch(page, /<input|<select|<textarea|<form/);
      assert.equal(SCALE_INFO.phq9.items.length, 9);
      assert.equal(SCALE_INFO.gad7.items.length, 7);
      assert.equal(SCALE_INFO.isi.items.length, 7);
      assert.equal(SCALE_INFO.stop_bang.items.length, 8);

      const none = html(React.createElement(view.Scales, { session: { ...clone(s2), context_scales: [], tool_calls: [] } }));
      assert.match(none, /没有填自评表/);
    });

    await t.test('路由：旧的用户端地址回到首页；来访页带标签', () => {
      for (const h of ['#/app', '#/app/chat', '#/app/settings']) assert.deepEqual(parseRoute(h), { name: 'app-home' });
      assert.deepEqual(parseRoute('#/app/v/B-012'), { name: 'app-visitor', visitorId: 'B-012', tab: 'talk' });
      assert.deepEqual(parseRoute(visitorHref('sample-002', 'compare')), { name: 'app-visitor', visitorId: 'sample-002', tab: 'compare' });
      assert.deepEqual(parseRoute('#/app/v/x/other'), { name: 'board' });
    });

    await t.test('措辞边界：用户端源码里不出现禁用字样，也没有自由输入', async () => {
      const files = ['src/lib/replay.ts', 'src/lib/scales.ts', 'src/hooks/useReplay.ts', 'src/app.css',
        ...(await readdir(join(root, 'src/pages/app'))).map((f) => `src/pages/app/${f}`),
        ...(await readdir(join(root, 'src/components/app'))).map((f) => `src/components/app/${f}`)];
      for (const f of files) {
        const text = await readFile(join(root, f), 'utf8');
        assert.doesNotMatch(text, /诊断|治疗|患者|病人|治愈|根治|痊愈|处方|开药|褪黑素/, f);
        assert.doesNotMatch(text, /24 ?小时|免费拨打/, f);
        assert.doesNotMatch(text, /<input|<textarea|contentEditable/, f);
      }
    });
  } finally {
    globalThis.window = oldWindow;
    await server.close();
    await rm(temp, { recursive: true, force: true });
  }
});
