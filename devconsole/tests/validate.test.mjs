// 结构校验：正式示例全部通过；缺失指标保留为 null（显示“暂无”），不补 0；坏结构给出字段路径。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { example, loadModules } from './support/load.mjs';

const m = await loadModules();
const clone = (x) => JSON.parse(JSON.stringify(x));

// engine/demo.py create_manifest() 写出的格式：运行开始前 playbook_version 为 null
const demoManifest = () => ({
  experiment_id: 'exp-20261115-090000-abcd1234',
  updated_at: '2026-11-15T09:00:00+08:00',
  stage: 'run1',
  run1: { run_id: 'exp-20261115-090000-abcd1234-run1', playbook_version: 'v1', split: 'A', state: 'running' },
  run2: { run_id: 'exp-20261115-090000-abcd1234-run2', playbook_version: null, split: 'B', state: 'pending' },
  control: { run_id: 'exp-20261115-090000-abcd1234-control', playbook_version: 'v1', split: 'B', state: 'pending' },
  evolution: { evolution_id: 'exp-20261115-090000-abcd1234-learn', state: 'pending' },
  error: null,
});

// engine/evolve/status.py StatusTracker 的初始状态
const engineStatus = () => ({
  schema: 'evolve-status/1',
  evolution_id: 'exp-1-learn',
  updated_at: '2026-11-15T09:01:00+08:00',
  from_version: 'v1',
  phase: 'reflecting',
  reflector: { state: 'running', model: null, fell_back: null },
  validation: { baseline: 'pending', candidates: {} },
  review: { state: 'not_needed', deadline: null, pending_changes: 0 },
  outcome: null,
  to_version: null,
  chosen: null,
  error: null,
});

test('正式示例（三份报告 + 进化记录）全部通过，额外字段放过', () => {
  for (const f of ['run_report.run1.json', 'run_report.run2.json', 'run_report.control.json']) {
    const r = example(f);
    r.extra_field = { anything: 1 };
    const v = m.parseReport(r, r.run_id);
    assert.equal(v.n_visitors, r.n_visitors);
    assert.equal(v.metrics.isi_response_rate, r.metrics.isi_response_rate);
  }
  const e = example('evolution.v1-v2.json');
  const v = m.parseEvolution(e, e.evolution_id);
  assert.equal(v.chosen, 'c2');
  assert.equal(v.to_version, 'v2');
  assert.equal(v.candidates.find((c) => c.id === 'c1').validated, false, '硬规则拦下的候选 val_metrics=null → 未验证');
});

test('缺失或 null 的指标保留为 null，不补成 0', () => {
  const r = example('run_report.run1.json');
  r.metrics.isi_response_rate = null;
  delete r.metrics.referral_precision;
  delete r.metrics.crisis_missed;
  const v = m.parseReport(r, r.run_id);
  assert.equal(v.metrics.isi_response_rate, null);
  assert.equal(v.metrics.referral_precision, null);
  assert.equal(v.metrics.crisis_missed, null);
});

test('报告结构不符：给出字段路径', () => {
  const cases = [
    [(r) => delete r.metrics, /响应\.metrics/],
    [(r) => (r.metrics.isi_response_rate = 1.5), /isi_response_rate.*0–1/],
    [(r) => (r.n_visitors = -1), /n_visitors/],
    [(r) => (r.veto.passed = 'yes'), /veto\.passed/],
    [(r) => (r.run_id = 'other'), /run_id/],
  ];
  for (const [mutate, re] of cases) {
    const r = example('run_report.run1.json');
    const id = r.run_id;
    mutate(r);
    assert.throws(() => m.parseReport(r, id), (e) => e instanceof m.ShapeError && re.test(e.message));
  }
});

test('实验清单：engine/demo.py 格式、{available:false}、包装格式', () => {
  const r = m.parseExperiment(demoManifest());
  assert.equal(r.available, true);
  assert.equal(r.manifest.run2.playbook_version, null, '版本未知时保持 null，不补造');
  assert.deepEqual(m.parseExperiment({ available: false }), { available: false });
  assert.equal(m.parseExperiment({ available: true, manifest: demoManifest() }).manifest.stage, 'run1');
});

test('实验清单：坏结构与危险 ID 被拒', () => {
  const bad = [
    (x) => (x.stage = 'learn'),
    (x) => (x.run1.state = 'ok'),
    (x) => (x.run1.run_id = '../etc'),
    (x) => (x.run1.run_id = 'a/b'),
    (x) => delete x.evolution,
  ];
  for (const mutate of bad) {
    const x = demoManifest();
    mutate(x);
    assert.throws(() => m.parseExperiment(x), m.ShapeError);
  }
});

test('运行状态：Mock 的 completed 与草案的 done 都能读；缺进度为 null', () => {
  const base = { run_id: 'r1', status: 'running', report_available: false, error: null };
  assert.deepEqual(m.parseRunState({ ...base, progress: { total: 8, completed: 3, failed: 1 } }, 'r1').progress, {
    total: 8,
    completed: 3,
    failed: 1,
  });
  assert.equal(m.parseRunState({ ...base, progress: { total: 8, done: 5 } }, 'r1').progress.completed, 5);
  const noProg = m.parseRunState(base, 'r1');
  assert.equal(noProg.progress, null);
  assert.equal(noProg.execution_mode, null, '后端没给执行模式就是 null');
  assert.equal(noProg.partial_metrics, null, '后端没给阶段统计就不显示');
  assert.throws(() => m.parseRunState({ ...base, progress: { total: 2, completed: 3 } }, 'r1'), /超过总数/);
  assert.throws(() => m.parseRunState({ ...base, run_id: 'r2' }, 'r1'), /run_id/);
});

test('学习状态：engine/evolve/status.py 的初始与审核中格式', () => {
  const s = m.parseEvolveStatus(engineStatus(), 'exp-1-learn');
  assert.equal(s.phase, 'reflecting');
  assert.equal(s.reflector.fell_back, null);
  const w = engineStatus();
  Object.assign(w, {
    phase: 'validating',
    validation: { baseline: 'done', candidates: { c1: 'blocked', c2: 'running' } },
    review: { state: 'waiting', deadline: '2026-11-15T09:02:30+08:00', pending_changes: 2 },
  });
  assert.equal(m.parseEvolveStatus(w, 'exp-1-learn').review.deadline, '2026-11-15T09:02:30+08:00');
  assert.throws(() => m.parseEvolveStatus({ ...engineStatus(), schema: 'x' }, 'exp-1-learn'), /schema/);
  assert.throws(() => m.parseEvolveStatus({ ...engineStatus(), phase: 'learning' }, 'exp-1-learn'), /phase/);
});

test('进化记录：kept_previous 正常；committed 缺 to_version 或 chosen 不在候选里被拒', () => {
  const e = example('evolution.v1-v2.json');
  const kept = { ...clone(e), outcome: 'kept_previous', to_version: null, chosen: null, commit: null };
  const v = m.parseEvolution(kept, e.evolution_id);
  assert.equal(v.outcome, 'kept_previous');
  assert.equal(v.commit, null);
  assert.throws(() => m.parseEvolution({ ...clone(e), to_version: null }, e.evolution_id), /to_version/);
  assert.throws(() => m.parseEvolution({ ...clone(e), chosen: 'c9' }, e.evolution_id), /chosen/);
});
