// 逐代曲线回归：纯逻辑（纵轴、增量格式、单点与空态、离线复测那句话）、两张图的静态渲染、
// 全链路演示页的“再进化一代”预设（顺序、默认、确认文案、演练与真实冲突）、旧后端缺字段时的容错，以及看板上的面板。
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
const text = (html) => html.replace(/<!-- -->/g, '').replace(/<[^>]+>/g, '');
const memoryStorage = () => {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: (key) => data.delete(key) };
};
/** SVG 里某一类文字，按出现顺序 */
const svgTexts = (html, cls) => [...html.matchAll(new RegExp(`<text class="${cls}[^"]*"[^>]*>([^<]*)</text>`, 'g'))].map((m) => m[1]);

test('逐代曲线', async (t) => {
  const temp = await mkdtemp(join(tmpdir(), 'deepsleep-curve-'));
  const server = await createServer({ root, configFile: false, cacheDir: temp, server: { middlewareMode: true },
    esbuild: { jsx: 'automatic' }, define: { 'import.meta.env.VITE_API_ADAPTER': '"http"' } });
  const oldWindow = globalThis.window;
  globalThis.window = { setTimeout, clearTimeout, setInterval, clearInterval, localStorage: memoryStorage(), sessionStorage: memoryStorage() };
  try {
    const gc = await server.ssrLoadModule('/src/lib/generationCurve.ts');
    const pl = await server.ssrLoadModule('/src/lib/pipeline.ts');
    const { LiveGenerationCurve, OfflineGenerationCurve, OFFLINE_MODEL } = await server.ssrLoadModule('/src/components/GenerationCurve.tsx');
    const { MOCK_PIPELINE } = await server.ssrLoadModule('/src/api/mockPipeline.ts');
    const { PipelineView } = await server.ssrLoadModule('/src/pages/console/PipelinePage.tsx');
    const { EvolutionBoard } = await server.ssrLoadModule('/src/components/board/Board.tsx');
    const board = await server.ssrLoadModule('/src/lib/board.ts');
    const { ApiError } = await server.ssrLoadModule('/src/api/errors.ts');
    const offline = JSON.parse(await readFile(join(root, 'src/data/offlineGenerationCurve.json'), 'utf8'));

    const live = (curve, props = {}) => renderToStaticMarkup(React.createElement(LiveGenerationCurve, { curve, ...props }));
    const point = (version, mean, delta_pp, extra = {}) => ({ version, mean, n_runs: 1, delta_pp, runs: [{ run_id: `r-${version}`, role: 'control', experiment_id: 'e', isi_response_rate: mean, n: 45 }], ...extra });
    const curveOf = (points, extra = {}) => ({ lineage_id: 'lin-x', mode: 'real', cohort: 'B', experiments: points.length, points, rejected: [], ...extra });

    // ---------- 纯逻辑 ----------

    await t.test('纵轴：两侧留白、对齐到整步长、刻度不超过 5 段、夹在 0–100', () => {
      assert.deepEqual(gc.axisRange([]), { min: 40, max: 80, ticks: [40, 50, 60, 70, 80] });
      // 单个值：上下各留 3 个百分点
      assert.deepEqual(gc.axisRange([57]), { min: 54, max: 60, ticks: [54, 56, 58, 60] });
      // mock 曲线的点与单次运行
      assert.deepEqual(gc.axisRange([55.6, 65.6, 68.9, 66.7, 64.4, 71.1]), { min: 50, max: 75, ticks: [50, 55, 60, 65, 70, 75] });
      // 离线文件：包括结构性上限
      const off = gc.axisRange([53.33, 82.2]);
      assert.equal(off.min, 40);
      assert.equal(off.max, 90);
      assert.ok(off.ticks.length - 1 <= 5);
      // 贴着边界也不越界
      const top = gc.axisRange([99, 100]);
      assert.ok(top.min >= 0 && top.max === 100);
      assert.equal(gc.axisRange([0]).min, 0);
      for (const r of [gc.axisRange([12, 13]), gc.axisRange([20, 90]), gc.axisRange([50.4, 50.6])]) {
        assert.ok(r.ticks.length >= 2 && r.ticks.length <= 6, JSON.stringify(r));
        assert.equal(r.ticks[0], r.min);
        assert.equal(r.ticks[r.ticks.length - 1], r.max);
      }
    });

    await t.test('增量：带符号、一位小数；持平与下降照实写', () => {
      assert.equal(gc.formatIncrement(10), '+10.0');
      assert.equal(gc.formatIncrement(6.66), '+6.7');
      assert.equal(gc.formatIncrement(-0.7), '−0.7');
      assert.equal(gc.formatIncrement(0), '±0.0');
      assert.equal(gc.formatIncrement(0.04), '±0.0');
      assert.equal(gc.formatIncrement(null), '');
      assert.equal(gc.incrementTone(2.2), 'up');
      assert.equal(gc.incrementTone(-0.7), 'down');
      assert.equal(gc.incrementTone(0), 'flat');
      assert.equal(gc.pctText(0.5704), '57.0%');
      assert.equal(gc.pctText(null), '—');
    });

    await t.test('现场曲线：空、缺字段、单点', () => {
      for (const c of [null, undefined, curveOf([]), { lineage_id: null }]) {
        const m = gc.liveCurveModel(c);
        assert.equal(m.empty, true);
        assert.deepEqual(m.rows, []);
      }
      const one = gc.liveCurveModel(curveOf([point('v1', 0.567, null)]));
      assert.equal(one.empty, false);
      assert.equal(one.points.length, 1);
      assert.equal(one.rows[0].learned, '团队手写的初始版本');
      assert.equal(one.rows[0].runsText, '1 次运行');
      assert.equal(one.rows[0].referralText, null);
      // 后端没给 delta_pp 时由相邻 mean 相减；乱序的点按版本号排
      const m = gc.liveCurveModel(curveOf([point('v10', 0.6, null), point('v2', 0.6, null), point('v1', 0.5, null)]));
      assert.deepEqual(m.versions, ['v1', 'v2', 'v10']);
      assert.deepEqual(m.points.map((p) => p.deltaPp), [null, 10, 0]);
      assert.deepEqual(m.rows.map((r) => r.deltaText), ['', '+10.0', '±0.0']);
    });

    await t.test('mock 曲线：三个版本、各次运行、未采纳的一代平铺直叙', () => {
      const m = gc.liveCurveModel(MOCK_PIPELINE.curve);
      assert.deepEqual(m.versions, ['v1', 'v2', 'v3']);
      assert.deepEqual(m.rows.map((r) => [r.version, r.meanText, r.deltaText, r.runsText]), [
        ['v1', '55.6%', '', '1 次运行'],
        ['v2', '65.6%', '+10.0', '2 次运行'],
        ['v3', '68.9%', '+3.3', '3 次运行'],
      ]);
      assert.equal(m.dots.length, 6);
      assert.equal(m.rows[1].referralText, '转介召回 78.0% / 精确率 82.0%');
      assert.deepEqual(m.rejected, ['从 v3 出发的一代：三份候选均未通过门禁，保留 v3']);
    });

    await t.test('离线复测：平均线、增量和那句话都来自文件', () => {
      assert.equal(gc.offlineSentence(offline),
        '两条链 v1 → v4 累计 +11.1［+2.2, +21.5］与 +10.4［+3.0, +19.3］个百分点（95% 区间）；单步变化大多在区间内无法与 0 区分；增量先陡后缓，没有加速。');
      // 数据不支持时不写后两句
      const steep = clone(offline);
      steep.average[3].delta_pp = 9;
      steep.chains.forEach((c) => c.points.forEach((p) => { if (p.delta_ci) p.delta_ci = [1, 5]; }));
      assert.equal(gc.offlineSentence(steep), '两条链 v1 → v4 累计 +11.1［+2.2, +21.5］与 +10.4［+3.0, +19.3］个百分点（95% 区间）。');
      const m = OFFLINE_MODEL;
      assert.deepEqual(m.versions, ['v1', 'v2', 'v3', 'v4']);
      assert.deepEqual(m.points.map((p) => (p.mean * 100).toFixed(1)), ['57.0', '63.7', '65.6', '67.8']);
      assert.deepEqual(m.points.map((p) => gc.formatIncrement(p.deltaPp)), ['', '+6.7', '+1.9', '+2.2']);
      assert.deepEqual(m.thin.map((l) => l.key), ['E11', 'E12']);
      // 两条链共用同一组 v1 测量，只画一次：3 + 3×3×2
      assert.equal(m.dots.length, 3 + 3 * 3 * 2);
      assert.equal(m.ceiling.label, '结构性上限 82.2%（其余来访在任何手册下都无法有效）');
      assert.equal(m.subline, '2026-11-15 实测 · 留出集 B 组 45 位来访 · 每个版本 3 次 · 反思器 gpt-6-astra (high)');
    });

    // ---------- 渲染 ----------

    await t.test('离线图：画出来的数与 JSON 一致', () => {
      const html = renderToStaticMarkup(React.createElement(OfflineGenerationCurve));
      const plain = text(html);
      assert.match(plain, /离线复测：两条独立进化链在留出集上的逐代成绩/);
      assert.match(plain, /2026-11-15 实测 · 留出集 B 组 45 位来访 · 每个版本 3 次 · 反思器 gpt-6-astra \(high\)/);
      const expectedValues = offline.average.map((p) => `${(p.mean * 100).toFixed(1)}%`);
      assert.deepEqual(expectedValues, ['57.0%', '63.7%', '65.6%', '67.8%']);
      assert.deepEqual(svgTexts(html, 'gc-value'), expectedValues);
      const expectedDeltas = offline.average.slice(1).map((p) => gc.formatIncrement(p.delta_pp));
      assert.deepEqual(expectedDeltas, ['+6.7', '+1.9', '+2.2']);
      assert.deepEqual(svgTexts(html, 'gc-delta'), expectedDeltas);
      assert.deepEqual(svgTexts(html, 'gc-tick gc-xtick'), ['v1', 'v2', 'v3', 'v4']);
      assert.equal((html.match(/class="gc-line"/g) ?? []).length, 1);
      assert.equal((html.match(/<g class="gc-thin"><path/g) ?? []).length, 2);
      assert.equal((html.match(/class="gc-run"/g) ?? []).length, 21);
      assert.equal((html.match(/class="gc-ceiling"/g) ?? []).length, 1);
      assert.match(plain, /结构性上限 82\.2%（其余来访在任何手册下都无法有效）/);
      assert.match(plain, /累计 \+11\.1［\+2\.2, \+21\.5］与 \+10\.4［\+3\.0, \+19\.3］个百分点/);
      assert.match(plain, /单步变化大多在区间内无法与 0 区分；增量先陡后缓，没有加速。/);
    });

    await t.test('现场图：空态、单点不画线、持平与下降照实画、十个版本仍可读', () => {
      const empty = text(live(null));
      assert.match(empty, /这条进化链还没有在 B 组上的成绩；跑完一轮后这里会出现第一个点。/);
      assert.match(empty, /留出集 B 组从不参与学习和门禁/);

      const single = live(curveOf([point('v1', 0.567, null)]));
      assert.doesNotMatch(single, /class="gc-line"/);
      assert.equal((single.match(/class="gc-mean"/g) ?? []).length, 1);
      assert.deepEqual(svgTexts(single, 'gc-value'), ['56.7%']);
      assert.match(text(single), /v156\.7%1 次运行团队手写的初始版本/);

      const mixed = live(curveOf([point('v1', 0.6, null), point('v2', 0.6, 0, { learned: '甲' }), point('v3', 0.578, -2.2, { learned: '乙' })]));
      assert.deepEqual(svgTexts(mixed, 'gc-delta'), ['±0.0', '−2.2']);
      assert.match(mixed, /class="gc-delta flat"/);
      assert.match(mixed, /class="gc-delta down"/);
      assert.match(mixed, /class="gc-delta-text down">−2\.2</);

      const ten = Array.from({ length: 10 }, (_, i) => point(`v${i + 1}`, 0.5 + i * 0.02, i === 0 ? null : 2, { learned: `第 ${i + 1} 版学到的一句话`.repeat(4) }));
      const many = live(curveOf(ten));
      assert.equal(svgTexts(many, 'gc-tick gc-xtick').length, 10);
      assert.match(many, /class="gc-value dense"/);
      // 学到了什么：一行截断，全文放在 title 里
      assert.match(many, /<span class="gc-learned" title="(第 10 版学到的一句话){4}">/);
    });

    await t.test('现场图：mock 曲线、演练标注、未采纳的一代中性呈现', () => {
      const html = live(MOCK_PIPELINE.curve, { title: '现场' });
      const plain = text(html);
      assert.match(plain, /4 次实验/);
      assert.deepEqual(svgTexts(html, 'gc-value'), ['55.6%', '65.6%', '68.9%']);
      assert.deepEqual(svgTexts(html, 'gc-delta'), ['+10.0', '+3.3']);
      assert.match(plain, /v265\.6%\+10\.02 次运行转介召回 78\.0% \/ 精确率 82\.0%优先修复 8 名转介漏判者/);
      assert.match(html, /<ul class="gc-rejected"[^>]*><li>从 v3 出发的一代：三份候选均未通过门禁，保留 v3<\/li><\/ul>/);
      const mock = text(live({ ...clone(MOCK_PIPELINE.curve), mode: 'mock' }));
      assert.match(mock, /演练数据 · 未调用模型/);
    });

    // ---------- 全链路演示页 ----------

    const actions = { busy: null, error: null, launch: () => {}, stop: () => {}, dismiss: () => {} };
    const NOW = 1_700_000_000_000;
    const view = (data, extra = {}) => renderToStaticMarkup(React.createElement(PipelineView, {
      poll: { data, error: null, receivedAt: NOW }, now: NOW, actions: { ...actions, ...extra.actions },
    }));
    /** 进程已退出、可以再次启动的快照 */
    const idle = (mutate = () => {}) => {
      const s = clone(MOCK_PIPELINE);
      s.state = 'done'; s.eta_s = null; s.launcher.state = 'exited';
      mutate(s);
      return s;
    };

    await t.test('预设：再进化一代排第一并默认选中；重置类预设标明从 v1 重新开始', () => {
      assert.deepEqual(pl.orderPresets(MOCK_PIPELINE.launcher.presets).map((p) => p.key), ['next', 'live', 'full']);
      assert.equal(pl.defaultPreset(MOCK_PIPELINE.launcher.presets).key, 'next');
      // 旧后端：没有 reset 字段，全部当作重置，顺序不变
      const old = MOCK_PIPELINE.launcher.presets.filter((p) => p.key !== 'next').map(({ reset, ...p }) => p);
      assert.deepEqual(pl.orderPresets(old).map((p) => p.key), ['live', 'full']);
      assert.equal(pl.defaultPreset(old).key, 'live');
      assert.equal(pl.defaultPreset([]), null);

      const html = view(idle());
      const order = ['再进化一代', '现场模式', '完整模式'].map((l) => html.indexOf(`<strong>${l}</strong>`));
      assert.ok(order.every((i) => i > 0) && order[0] < order[1] && order[1] < order[2], `${order}`);
      assert.match(html, /checked="" value="next"/);
      assert.match(html, /<span class="pl-preset-from">从 v3 继续<\/span>/);
      assert.equal((html.match(/<span class="pl-preset-from is-reset">从 v1 重新开始<\/span>/g) ?? []).length, 2);
      assert.match(html, /<button type="button" class="btn btn-primary pl-start">再进化一代<\/button>/);
    });

    await t.test('从哪里继续：当前版本为空或是 v1 时写“从 v1 开始”', () => {
      assert.equal(pl.continueFromText({ current_version: 'v2' }), '从 v2 继续');
      assert.equal(pl.continueFromText({ current_version: 'v1' }), '从 v1 开始');
      assert.equal(pl.continueFromText({ current_version: null }), '从 v1 开始');
      assert.equal(pl.continueFromText({}), '从 v1 开始');
      assert.match(view(idle((s) => { s.launcher.current_version = null; })), /<span class="pl-preset-from">从 v1 开始<\/span>/);
    });

    await t.test('确认文案：续跑说明不重置；重置类预设保留警告并说明曲线从头开始', () => {
      const [live_, full, next] = MOCK_PIPELINE.launcher.presets;
      const a = pl.launchConfirmText(next, { current_version: 'v3' });
      assert.match(a, /从当前版本 v3 继续/);
      assert.match(a, /不重置 playbook/);
      assert.doesNotMatch(a, /重置为 v1/);
      assert.match(a, /再进化一代（从当前版本继续：.*，约 8 分钟）/);
      assert.match(pl.launchConfirmText(next, { current_version: null }), /从当前版本 v1 继续/);
      for (const p of [live_, full]) {
        const b = pl.launchConfirmText(p, { current_version: 'v3' });
        assert.match(b, /将把 playbook 重置为 v1，并开始一次新的实验/);
        assert.match(b, /开始一条新的进化链，逐代曲线从头开始/);
        assert.doesNotMatch(b, /不重置/);
      }
      // 旧后端的预设没有 reset：按重置处理
      const { reset, ...oldLive } = live_;
      assert.match(pl.launchConfirmText(oldLive, null), /重置为 v1/);
    });

    await t.test('演练与真实不能接在同一条链上：续跑按钮禁用并提示；服务端 409 也在原地显示', () => {
      const next = MOCK_PIPELINE.launcher.presets[2];
      const live_ = MOCK_PIPELINE.launcher.presets[0];
      assert.equal(pl.lineageConflict({ lineage_mode: 'real' }, next, false), null);
      assert.equal(pl.lineageConflict({ lineage_mode: 'mock' }, next, true), null);
      assert.equal(pl.lineageConflict({ lineage_mode: null }, next, true), null);
      assert.equal(pl.lineageConflict({}, next, true), null);
      assert.equal(pl.lineageConflict({ lineage_mode: 'mock' }, live_, false), null);
      assert.equal(pl.lineageConflict({ lineage_mode: 'real' }, next, true), '当前进化链是真实数据，演练与真实不能接在同一条链上；请先从 v1 重新开始');
      assert.equal(pl.lineageConflict({ lineage_mode: 'mock' }, next, false), '当前进化链是演练数据，演练与真实不能接在同一条链上；请先从 v1 重新开始');

      // 链是演练的，复选框默认不勾（真实）：续跑按钮禁用
      const html = view(idle((s) => { s.launcher.lineage_mode = 'mock'; }));
      assert.match(html, /<button type="button" class="btn btn-primary pl-start" disabled="">再进化一代<\/button>/);
      assert.match(text(html), /当前进化链是演练数据，演练与真实不能接在同一条链上；请先从 v1 重新开始/);

      const conflict = new ApiError({ kind: 'http', status: 409, code: 'LINEAGE_MODE_MISMATCH', message: '演练数据和真实数据不能接在同一条链上，请先从 v1 重新开始' });
      const failed = text(view(idle(), { actions: { error: { op: 'launch', error: conflict } } }));
      assert.match(failed, /没能启动：演练与真实不能接在同一条链上，请先从 v1 重新开始/);
      assert.match(failed, /演练数据和真实数据不能接在同一条链上/);
    });

    await t.test('旧后端：没有 curve / reset / current_version / lineage_mode 也照常显示', () => {
      const s = idle((x) => {
        delete x.curve;
        delete x.launcher.current_version;
        delete x.launcher.lineage_mode;
        x.launcher.presets = x.launcher.presets.filter((p) => p.key !== 'next').map(({ reset, ...p }) => p);
      });
      const html = view(s);
      const plain = text(html);
      assert.match(html, /checked="" value="live"/);
      assert.match(html, /<button type="button" class="btn btn-primary pl-start">开始全链路<\/button>/);
      assert.equal((html.match(/从 v1 重新开始/g) ?? []).length, 2);
      assert.match(plain, /逐代曲线这条进化链还没有在 B 组上的成绩/);
      // 还没有实验（available=false）时也一样
      const none = text(view({ available: false, launcher: { ...clone(s.launcher), state: 'idle', pid: null, preset: null, log_tail: [] } }));
      assert.match(none, /这条进化链还没有在 B 组上的成绩/);
    });

    await t.test('全链路页：曲线卡片在左栏步骤下面，随快照更新；结果卡片用后端给的版本', () => {
      const html = view(MOCK_PIPELINE);
      const main = html.slice(html.indexOf('<section class="pl-main"'), html.indexOf('<section class="pl-card pl-launch"'));
      assert.ok(main.indexOf('class="pl-steps"') < main.indexOf('id="pl-curve-title"'), '曲线在步骤之后、仍在左栏');
      assert.deepEqual(svgTexts(main, 'gc-value'), ['55.6%', '65.6%', '68.9%']);
      // 下一次轮询多了一个点
      const next = clone(MOCK_PIPELINE);
      next.curve.points.push({ version: 'v4', mean: 0.711, n_runs: 1, delta_pp: 2.2, referral_recall: null, referral_precision: null, learned: '新学到的', evolution_id: 'g', runs: [{ run_id: 'x-run2', role: 'run2', experiment_id: 'x', isi_response_rate: 0.711, n: 45 }] });
      assert.deepEqual(svgTexts(view(next), 'gc-value'), ['55.6%', '65.6%', '68.9%', '71.1%']);
      const plain = text(html);
      assert.match(plain, /运行 1（v3 · A 组）/);
      assert.match(plain, /对照（v3 · B 组）/);
      assert.match(plain, /用当前 playbook（v3）跑 A 组来访/);
      assert.doesNotMatch(plain, /初版手册|用 v1 谈/);
    });

    // ---------- 看板 ----------

    const boardHtml = (extra) => renderToStaticMarkup(React.createElement(EvolutionBoard, { data: { ...board.EMPTY_BOARD, ...extra } }));

    await t.test('看板：逐代曲线面板在主栅格之后、证据之前；没有 curve 显示空态，离线图照常', () => {
      const html = boardHtml({});
      const plain = text(html);
      const grid = html.indexOf('class="bd-grid"');
      const curve = html.indexOf('bd-panel bd-curve');
      const proof = html.indexOf('class="bd-proof"');
      assert.ok(grid > 0 && grid < curve && curve < proof, `${grid} ${curve} ${proof}`);
      assert.match(plain, /逐代曲线/);
      assert.match(plain, /这条进化链还没有在 B 组上的成绩/);
      assert.match(plain, /离线复测：两条独立进化链在留出集上的逐代成绩/);
      assert.deepEqual(svgTexts(html, 'gc-value'), ['57.0%', '63.7%', '65.6%', '67.8%']);
      // 看板原有图表的类名不被占用
      assert.doesNotMatch(html, /class="ch"/);
      const withCurve = boardHtml({ curve: MOCK_PIPELINE.curve });
      assert.deepEqual(svgTexts(withCurve, 'gc-value'), ['55.6%', '65.6%', '68.9%', '57.0%', '63.7%', '65.6%', '67.8%']);
      assert.match(text(withCurve), /现场：这条进化链在留出集 B 组的逐代成绩/);
    });

    await t.test('看板读取：curve 来自 GET /demo/pipeline；失败沿用上一份，缺字段为空', async () => {
      let respond = async () => clone(MOCK_PIPELINE);
      const api = {
        adapter: 'http',
        getExperiment: async () => ({ available: false }),
        listPlaybookVersions: async () => ({ items: [] }),
        getPipeline: async () => respond(),
      };
      const signal = new AbortController().signal;
      const cache = board.createBoardCache();
      const a = await board.readBoard(api, cache, signal);
      assert.deepEqual(a.curve.points.map((p) => p.version), ['v1', 'v2', 'v3']);
      respond = async () => { throw new ApiError({ kind: 'network', message: 'down' }); };
      const b = await board.readBoard(api, cache, signal);
      assert.equal(b.curve.points.length, 3);
      respond = async () => { const s = clone(MOCK_PIPELINE); delete s.curve; return s; };
      assert.equal((await board.readBoard(api, cache, signal)).curve, null);
      respond = async () => ({ available: false, launcher: clone(MOCK_PIPELINE.launcher) });
      assert.equal((await board.readBoard(api, board.createBoardCache(), signal)).curve, null);
      respond = async () => ({ ...clone(MOCK_PIPELINE), curve: { points: 'oops' } });
      assert.equal((await board.readBoard(api, board.createBoardCache(), signal)).curve, null);
      // 接口不存在（例如更旧的客户端）也不打断整页
      const { getPipeline, ...noPipeline } = api;
      assert.equal((await board.readBoard(noPipeline, board.createBoardCache(), signal)).curve, null);
    });

    await t.test('措辞边界：新文件不出现禁用字样', async () => {
      for (const f of ['src/components/GenerationCurve.tsx', 'src/lib/generationCurve.ts', 'src/generationCurve.css', 'src/api/mockPipeline.ts', 'src/lib/pipeline.ts']) {
        assert.doesNotMatch(await readFile(join(root, f), 'utf8'), /诊断|治疗失眠症/, f);
      }
      assert.doesNotMatch(text(boardHtml({ curve: MOCK_PIPELINE.curve })), /诊断|治疗失眠症/);
    });
  } finally {
    globalThis.window = oldWindow;
    await server.close();
    await rm(temp, { recursive: true, force: true });
  }
});
