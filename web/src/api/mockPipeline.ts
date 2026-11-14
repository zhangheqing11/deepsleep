// ⚠ 前端本地模拟：全链路演示的一份固定快照（api/PIPELINE_API.md 的结构，含 11/15 增补的 next 预设与 curve）。
// 静态数据，不随时间推进。情景：同一条进化链上的第 4 次实验，用“再进化一代”从 v3 出发——
// 运行 1（v3，A 组）已完成；这一代正在门禁验证（基线与候选 1 已完成，候选 2 进行中，候选 3 等待）；运行 2 与对照尚未开始。
// 链上此前三次实验：v1 → v2（采纳）、v2 → v3（采纳）、从 v3 出发的一代未采纳（保留 v3）。
// 只用于在没有后端时检查页面，不代表任何实际执行。
import type { PipelineCurve, PipelineSnapshot } from './extensionTypes';

const EXP = 'exp-20261115-103000-mock0004';
const LINEAGE = 'lin-20261115-093000-mock';
const E1 = 'exp-20261115-093000-mock0001';
const E2 = 'exp-20261115-095000-mock0002';
const E3 = 'exp-20261115-101000-mock0003';

/** B 组 45 位来访：比例都是 k/45 */
const MOCK_CURVE: PipelineCurve = {
  lineage_id: LINEAGE,
  mode: 'real',
  cohort: 'B',
  experiments: 4,
  points: [
    {
      version: 'v1', mean: 0.556, n_runs: 1, delta_pp: null,
      referral_recall: 0.47, referral_precision: 0.45,
      learned: null, evolution_id: null,
      runs: [{ run_id: `${E1}-control`, role: 'control', experiment_id: E1, isi_response_rate: 0.556, n: 45 }],
    },
    {
      version: 'v2', mean: 0.656, n_runs: 2, delta_pp: 10.0,
      referral_recall: 0.78, referral_precision: 0.82,
      learned: '优先修复 8 名转介漏判者：先问打鼾、夜间憋醒和白天犯困，再决定干预路径与是否建议就医',
      evolution_id: `${E1}-learn-g1`,
      runs: [
        { run_id: `${E1}-run2`, role: 'run2', experiment_id: E1, isi_response_rate: 0.667, n: 45 },
        { run_id: `${E2}-control`, role: 'control', experiment_id: E2, isi_response_rate: 0.644, n: 45 },
      ],
    },
    {
      version: 'v3', mean: 0.689, n_runs: 3, delta_pp: 3.3,
      referral_recall: 0.81, referral_precision: 0.8,
      learned: '第 1 轮先确认作息是否整体后移，第 2 轮再区分认知过度唤醒与床和清醒的条件联结',
      evolution_id: `${E2}-learn-g1`,
      runs: [
        { run_id: `${E2}-run2`, role: 'run2', experiment_id: E2, isi_response_rate: 0.689, n: 45 },
        { run_id: `${E3}-control`, role: 'control', experiment_id: E3, isi_response_rate: 0.711, n: 45 },
        { run_id: `${E3}-run2`, role: 'run2', experiment_id: E3, isi_response_rate: 0.667, n: 45 },
      ],
    },
  ],
  rejected: [
    { experiment_id: E3, evolution_id: `${E3}-learn-g1`, from_version: 'v3', finished_at: '2026-11-15T10:17:40+08:00' },
  ],
};

export const MOCK_PIPELINE: PipelineSnapshot = {
  available: true,
  experiment_id: EXP,
  mode: 'real',
  state: 'running',
  error: null,
  started_at: '2026-11-15T10:30:00+08:00',
  updated_at: '2026-11-15T10:33:33+08:00',
  finished_at: null,
  elapsed_s: 213.4,
  eta_s: 185,
  generations_planned: 1,
  playbook: { from_version: 'v3', current_version: 'v3' },
  steps: [
    {
      key: 'run1',
      kind: 'run',
      label: '运行 1',
      detail: '用当前 playbook（v3）跑 A 组来访',
      state: 'done',
      started_at: '2026-11-15T10:30:00+08:00',
      finished_at: '2026-11-15T10:31:58+08:00',
      elapsed_s: 118.2,
      expected_s: 120,
      eta_s: null,
      batches: [
        {
          run_id: `${EXP}-run1`, role: 'run1', label: '运行 1', version: 'v3', split: 'A',
          total: 45, completed: 45, failed: 0, state: 'done',
          started_at: '2026-11-15T10:30:00+08:00', finished_at: '2026-11-15T10:31:58+08:00',
          duration_s: 118.2, isi_response_rate: 0.511,
        },
      ],
      generation: null,
    },
    {
      key: 'gen1',
      kind: 'generation',
      label: '学习 · 第 1 代',
      detail: '反思运行结果，提出 3 份候选，在验证集 C 上过门禁',
      state: 'running',
      started_at: '2026-11-15T10:31:58+08:00',
      finished_at: null,
      elapsed_s: 95.2,
      expected_s: 200,
      eta_s: 105,
      batches: [
        {
          run_id: `${EXP}-learn-v3_base`, role: 'validation', label: '基线 · 第 1 次', version: 'v3', split: 'C',
          total: 30, completed: 30, failed: 0, state: 'done',
          started_at: '2026-11-15T10:32:38+08:00', finished_at: '2026-11-15T10:33:08+08:00',
          duration_s: 30.4, isi_response_rate: 0.522,
        },
        {
          run_id: `${EXP}-learn-v3_c1`, role: 'validation', label: '候选 1 · 第 1 次', version: 'v3+c1', split: 'C',
          total: 30, completed: 30, failed: 0, state: 'done',
          started_at: '2026-11-15T10:32:38+08:00', finished_at: '2026-11-15T10:33:12+08:00',
          duration_s: 33.9, isi_response_rate: 0.583,
        },
        {
          run_id: `${EXP}-learn-v3_c2`, role: 'validation', label: '候选 2 · 第 1 次', version: 'v3+c2', split: 'C',
          total: 30, completed: 12, failed: 0, state: 'running',
          started_at: '2026-11-15T10:33:12+08:00', finished_at: null,
          duration_s: null, isi_response_rate: null,
        },
      ],
      generation: {
        index: 1,
        evolution_id: `${EXP}-learn-g1`,
        from_version: 'v3',
        phase: 'validating',
        reflector: { state: 'done', model: 'claude-opus-5-5', fell_back: false },
        baseline_isi: 0.522,
        candidates: [
          { id: 'c1', state: 'done', isi: 0.583, passed: null },
          { id: 'c2', state: 'running', isi: null, passed: null },
          { id: 'c3', state: 'pending', isi: null, passed: null },
        ],
        outcome: null,
        to_version: null,
        chosen: null,
      },
    },
    {
      key: 'final',
      kind: 'final',
      label: '运行 2 与对照',
      detail: '学习后的版本与 v3 并行跑 B 组来访',
      state: 'pending',
      started_at: null,
      finished_at: null,
      elapsed_s: null,
      expected_s: 80,
      eta_s: null,
      batches: [],
      generation: null,
    },
  ],
  result: {
    run1: { isi_response_rate: 0.511, referral_recall: 0.8, referral_precision: 0.667, n: 45, playbook_version: 'v3' },
    control: null,
    run2: null,
    delta_pp: null,
  },
  launcher: {
    enabled: true,
    state: 'running',
    pid: 4242,
    preset: 'next',
    started_at: '2026-11-15T10:29:58+08:00',
    exit_code: null,
    presets: [
      { key: 'live', label: '现场模式', generations: 1, reset: true, description: '运行 1 → 学习 1 代 → 运行 2 与对照', expected_s: 400 },
      { key: 'full', label: '完整模式', generations: 3, reset: true, description: '运行 1 → 学习 3 代（含自我练习）→ 运行 2 与对照', expected_s: 1500 },
      { key: 'next', label: '再进化一代', generations: 1, reset: false, description: '从当前版本继续：运行（当前版本）→ 学习 1 代 → 新版本与当前版本在 B 组对比', expected_s: 480 },
    ],
    log_tail: [
      `experiment_id=${EXP}`,
      `[lineage] ${LINEAGE} · from_version=v3`,
      '[run1] split=A version=v3 visitors=45',
      '[run1] done 45/45 in 118.2s · isi_response_rate=0.511',
      '[learn g1] reflector=claude-opus-5-5 effort=high',
      '[learn g1] 3 candidates proposed',
      '[learn g1] baseline 30/30 · isi_response_rate=0.522',
      '[learn g1] c1 30/30 · isi_response_rate=0.583',
      '[learn g1] c2 12/30',
    ],
    mock: false,
    stopped: false,
    current_version: 'v3',
    lineage_mode: 'real',
  },
  curve: MOCK_CURVE,
};
