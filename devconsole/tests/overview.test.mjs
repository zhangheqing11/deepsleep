// 进化总览推导：缺失或未完成指标不画成 0；kept_previous 是正常结果；版本号只从数据读；红线如实标出。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { example, loadModules } from './support/load.mjs';

const m = await loadModules();
const report = (f) => {
  const r = example(f);
  return m.parseReport(r, r.run_id);
};
const evolution = (patch = {}) => {
  const e = { ...example('evolution.v1-v2.json'), ...patch };
  return m.parseEvolution(e, e.evolution_id);
};
const manifest = (patch = {}) =>
  m.parseExperiment({
    experiment_id: 'exp-1',
    updated_at: null,
    stage: 'run1',
    run1: { run_id: 'exp-1-run1', playbook_version: 'v1', split: 'A', state: 'running' },
    run2: { run_id: 'exp-1-run2', playbook_version: null, split: 'B', state: 'pending' },
    control: { run_id: 'exp-1-control', playbook_version: 'v1', split: 'B', state: 'pending' },
    evolution: { evolution_id: 'exp-1-learn', state: 'pending' },
    error: null,
    ...patch,
  }).manifest;

test('百分点差：只做相减保留一位；任一缺失为 null', () => {
  assert.equal(m.pointDiff(0.5, 0.875), 37.5);
  assert.equal(m.pointDiff(0.625, 0.5), -12.5);
  assert.equal(m.pointDiff(null, 0.8), null);
  assert.equal(m.pointDiff(0.5, undefined), null);
  assert.equal(m.pointDiff(0, 0), 0);
});

test('正式示例：对照 → 运行 2 的主指标差', () => {
  const c = report('run_report.control.json');
  const r2 = report('run_report.run2.json');
  assert.equal(m.pointDiff(c.metrics.isi_response_rate, r2.metrics.isi_response_rate), 37.5);
});

test('红线：通过、未通过、缺失三种状态', () => {
  const ok = report('run_report.run2.json');
  assert.ok(m.redLines(ok).every((l) => l.ok === true));
  assert.equal(m.redLineFailed(ok), false);

  const raw = example('run_report.run2.json');
  raw.metrics.crisis_missed = 1;
  raw.veto = { passed: false, reasons: [{ code: 'crisis_missed', message: '漏报 1 例' }] };
  const bad = m.parseReport(raw, raw.run_id);
  assert.equal(m.redLineFailed(bad), true);
  assert.equal(m.redLines(bad).find((l) => l.key === 'crisis_missed').value, '1');

  const missing = example('run_report.run2.json');
  delete missing.metrics.contraindication_violations;
  const line = m.redLines(m.parseReport(missing, missing.run_id)).find((l) => l.key === 'contraindication_violations');
  assert.equal(line.ok, null, '缺失不当成通过，也不当成 0');
  assert.equal(line.value, '暂无');
});

test('选中改动：按关键度排序，最多 3 条，其余计数', () => {
  const e = evolution();
  const { shown, hidden } = m.chosenChanges(e);
  assert.deepEqual(
    shown.map((c) => c.id),
    ['c2-path-1', 'c2-question-1', 'c2-question-2'],
  );
  assert.equal(hidden, 0);
  const two = m.chosenChanges(e, 2);
  assert.equal(two.shown.length, 2);
  assert.equal(two.hidden, 1);
  assert.equal(two.shown.at(-1).criticality, 'medium', '低关键度的排在后面被折叠');
});

test('kept_previous：没有选中改动，每个候选都有来自数据的拦截原因', () => {
  const raw = example('evolution.v1-v2.json');
  const c2 = raw.candidates.find((c) => c.id === 'c2');
  c2.passed = false;
  c2.veto = { passed: false, reasons: [{ code: 'referral_recall_regressed', message: 'R3 退步' }] };
  const e = m.parseEvolution({ ...raw, outcome: 'kept_previous', to_version: null, chosen: null, commit: null }, raw.evolution_id);
  assert.deepEqual(m.chosenChanges(e), { shown: [], hidden: 0 });
  const reasons = Object.fromEntries(e.candidates.map((c) => [c.id, m.blockReasons(c, e)]));
  assert.ok(reasons.c1.some((r) => r.startsWith('硬规则拦下')), 'c1 被硬规则拦下');
  assert.ok(reasons.c1.some((r) => r.startsWith('人工审核')), 'c1 的高关键度改动被人工否决');
  assert.ok(reasons.c2.some((r) => r.includes('转介召回退步')));
  assert.ok(reasons.c3.some((r) => r.includes('没有高于上一代')), 'c3 验证集 0.375 ≤ 上一代 0.5');
  const v = m.versionInfo(manifest({ stage: 'run2' }), null, e);
  assert.deepEqual([v.current, v.previous], ['v1', null], '保留上一代：当前仍是起点版本，没有可回退的上一代');
});

test('版本号只从数据读：学习前取清单，提交后取进化记录，都没有时为 null', () => {
  assert.equal(m.versionInfo(manifest(), null, null).current, 'v1');
  const committed = m.versionInfo(manifest(), null, evolution());
  assert.deepEqual([committed.current, committed.previous], ['v2', 'v1']);
  const noVersion = manifest({ run1: { run_id: 'exp-1-run1', playbook_version: null, split: 'A', state: 'running' } });
  assert.equal(m.versionInfo(noVersion, null, null).current, null);
  const status = {
    schema: 'evolve-status/1',
    evolution_id: 'exp-1-learn',
    updated_at: null,
    from_version: 'v3',
    phase: 'done',
    reflector: { state: 'done', model: 'x', fell_back: false },
    validation: { baseline: 'done', candidates: {} },
    review: { state: 'done', deadline: null, pending_changes: 0 },
    outcome: 'committed',
    to_version: 'v4',
    chosen: 'c1',
    error: null,
  };
  const fromStatus = m.versionInfo(noVersion, m.parseEvolveStatus(status, 'exp-1-learn'), null);
  assert.deepEqual([fromStatus.current, fromStatus.previous], ['v4', 'v3'], '不写死 v1 / v2');
});

test('时间线：版本未知显示“版本待定”，进度来自运行状态，没有就是 null', () => {
  const nodes = m.timeline(manifest(), {}, null);
  assert.deepEqual(
    nodes.map((n) => n.key),
    ['run1', 'evolution', 'run2', 'control'],
  );
  assert.equal(nodes[2].sub, 'B 组 · 版本待定');
  assert.equal(nodes[0].progress, null);
  const rs = m.parseRunState({ run_id: 'exp-1-run1', status: 'running', report_available: false, progress: { total: 40, completed: 12, failed: 0 } }, 'exp-1-run1');
  assert.equal(m.timeline(manifest(), { run1: rs }, null)[0].progress.completed, 12);
});

test('审核倒计时：按后端截止时间（带时区）计算，无法解析为 null', () => {
  const now = Date.parse('2026-11-15T01:02:00Z');
  assert.equal(m.secondsLeft('2026-11-15T09:02:30+08:00', now), 30);
  assert.equal(m.secondsLeft('2026-11-15T09:01:30+08:00', now), -30);
  assert.equal(m.secondsLeft(null, now), null);
  assert.equal(m.secondsLeft('明天', now), null);
});
