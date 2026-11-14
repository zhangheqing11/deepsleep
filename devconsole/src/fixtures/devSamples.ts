// ⚠ 开发样例（手写占位），只在 mock 模式使用，页面会标“开发样例”。不是任何一次运行的结果。
//
// 指标、报告、进化记录一律直接用 contracts/examples 的正式示例（由 mockClient 读取），这里不写任何指标数字。
// 本文件只补正式示例里没有的东西：实验清单（engine/demo.py 格式）、运行进度（api 运行状态格式）、
// 学习状态（engine/evolve/status.py 格式），以及 kept_previous 的进化记录（BACKLOG G4：正式示例缺）。
// 运行 ID / 进化 ID 沿用正式示例里的 ID，不另造。等正式示例补齐后替换。

import evolutionExample from '../../../contracts/examples/evolution.v1-v2.json';

export const RUN1 = 'run-20261115-01';
export const RUN2 = 'run-20261115-02';
export const CONTROL = 'run-20261115-control';
export const EVOLUTION = 'evolution-20261115-01';

export type FixtureName = 'complete' | 'running' | 'learning' | 'kept_previous' | 'failed' | 'none';

export const FIXTURES: Record<FixtureName, string> = {
  complete: '实验已完成（正式示例数据）',
  running: '运行 2 与对照进行中',
  learning: '学习中：候选验证 + 审核窗口',
  kept_previous: '学习结果：保留上一代',
  failed: '学习失败',
  none: '没有实验',
};

type Stage = 'pending' | 'running' | 'done' | 'failed';

function manifest(
  stage: string,
  states: { run1: Stage; evolution: Stage; run2: Stage; control: Stage },
  run2Version: string | null,
  error: string | null = null,
) {
  return {
    _dev_sample: true,
    experiment_id: 'exp-dev-sample',
    updated_at: '2026-11-15T09:08:30+08:00',
    stage,
    run1: { run_id: RUN1, playbook_version: 'v1', split: 'A', state: states.run1 },
    evolution: { evolution_id: EVOLUTION, state: states.evolution },
    run2: { run_id: RUN2, playbook_version: run2Version, split: 'B', state: states.run2 },
    control: { run_id: CONTROL, playbook_version: 'v1', split: 'B', state: states.control },
    error,
  };
}

/** 运行状态：已完成的运行进度由正式示例报告的 n_visitors 得出；运行中的进度是手写样例。 */
export function runState(runId: string, status: 'running' | 'succeeded' | 'failed', total: number, completed: number) {
  return {
    _dev_sample: true,
    run_id: runId,
    status,
    execution_mode: 'mock',
    split: runId === RUN1 ? 'A' : 'B',
    progress: { total, completed, failed: 0 },
    report_available: status === 'succeeded',
    error: null,
  };
}

function status(
  phase: string,
  fields: Partial<{
    reflector: object;
    validation: object;
    review: object;
    outcome: string | null;
    to_version: string | null;
    chosen: string | null;
    error: string | null;
  }>,
) {
  return {
    _dev_sample: true,
    schema: 'evolve-status/1',
    evolution_id: EVOLUTION,
    updated_at: '2026-11-15T09:02:10+08:00',
    from_version: 'v1',
    phase,
    reflector: { state: 'done', model: 'claude-opus-5-5', fell_back: false },
    validation: { baseline: 'done', candidates: { c1: 'blocked', c2: 'done', c3: 'done' } },
    review: { state: 'done', deadline: '2026-11-15T09:02:30+08:00', pending_changes: 0 },
    outcome: null,
    to_version: null,
    chosen: null,
    error: null,
    ...fields,
  };
}

/** kept_previous：从正式示例改出，所有候选都没通过。c2 的拦截原因是手写样例。 */
function keptPrevious() {
  const e = JSON.parse(JSON.stringify(evolutionExample)) as Record<string, unknown> & {
    candidates: Record<string, unknown>[];
  };
  for (const c of e.candidates) {
    if (c.id === 'c2') {
      c.passed = false;
      c.veto = {
        passed: false,
        reasons: [{ code: 'referral_recall_regressed', message: '开发样例：假设该候选在 C 组上转介召回退步' }],
      };
    }
  }
  return {
    ...e,
    _dev_sample: true,
    outcome: 'kept_previous',
    to_version: null,
    chosen: null,
    commit: null,
    diff: null,
  };
}

export interface FixtureData {
  experiment: unknown;
  runStates: Record<string, unknown>;
  statuses: Record<string, unknown>;
  /** 有值时替代正式示例的进化记录；null = 没有 evolution.json（进行中或失败） */
  evolution: 'example' | unknown | null;
  /** 哪些运行的报告可读（读正式示例） */
  reports: string[];
}

export function fixtureData(name: FixtureName, nVisitors: (runId: string) => number): FixtureData {
  const done = (id: string) => runState(id, 'succeeded', nVisitors(id), nVisitors(id));
  switch (name) {
    case 'none':
      return { experiment: { available: false }, runStates: {}, statuses: {}, evolution: null, reports: [] };
    case 'complete':
      return {
        experiment: manifest('done', { run1: 'done', evolution: 'done', run2: 'done', control: 'done' }, 'v2'),
        runStates: { [RUN1]: done(RUN1), [RUN2]: done(RUN2), [CONTROL]: done(CONTROL) },
        statuses: { [EVOLUTION]: status('done', { outcome: 'committed', to_version: 'v2', chosen: 'c2' }) },
        evolution: 'example',
        reports: [RUN1, RUN2, CONTROL],
      };
    case 'running':
      return {
        experiment: manifest('run2', { run1: 'done', evolution: 'done', run2: 'running', control: 'running' }, 'v2'),
        runStates: {
          [RUN1]: done(RUN1),
          [RUN2]: runState(RUN2, 'running', nVisitors(RUN2), 5),
          [CONTROL]: runState(CONTROL, 'running', nVisitors(CONTROL), 6),
        },
        statuses: { [EVOLUTION]: status('done', { outcome: 'committed', to_version: 'v2', chosen: 'c2' }) },
        evolution: 'example',
        reports: [RUN1],
      };
    case 'learning':
      return {
        experiment: manifest('learning', { run1: 'done', evolution: 'running', run2: 'pending', control: 'pending' }, null),
        runStates: { [RUN1]: done(RUN1) },
        statuses: {
          [EVOLUTION]: status('validating', {
            validation: { baseline: 'done', candidates: { c1: 'blocked', c2: 'running', c3: 'done' } },
            review: { state: 'waiting', deadline: '2026-11-15T09:02:30+08:00', pending_changes: 1 },
          }),
        },
        evolution: null,
        reports: [RUN1],
      };
    case 'kept_previous':
      return {
        experiment: manifest('run2', { run1: 'done', evolution: 'done', run2: 'pending', control: 'pending' }, 'v1'),
        runStates: { [RUN1]: done(RUN1) },
        statuses: { [EVOLUTION]: status('done', { outcome: 'kept_previous', to_version: null, chosen: null }) },
        evolution: keptPrevious(),
        reports: [RUN1],
      };
    case 'failed':
      return {
        experiment: manifest(
          'failed',
          { run1: 'done', evolution: 'failed', run2: 'pending', control: 'pending' },
          null,
          '开发样例：RuntimeError: 反思器与降级模型都不可用',
        ),
        runStates: { [RUN1]: done(RUN1) },
        statuses: {
          [EVOLUTION]: status('failed', {
            reflector: { state: 'running', model: null, fell_back: true },
            validation: { baseline: 'done', candidates: {} },
            review: { state: 'not_needed', deadline: null, pending_changes: 0 },
            error: '开发样例：RuntimeError: 反思器与降级模型都不可用',
          }),
        },
        evolution: null,
        reports: [RUN1],
      };
  }
}

export function parseFixtureName(search: string): { name: FixtureName; unknown: string | null } {
  const raw = new URLSearchParams(search).get('fixture');
  if (raw === null || raw === '') return { name: 'complete', unknown: null };
  if (raw in FIXTURES) return { name: raw as FixtureName, unknown: null };
  return { name: 'complete', unknown: raw };
}
