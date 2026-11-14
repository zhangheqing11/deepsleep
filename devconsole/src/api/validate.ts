// 把接口返回（或 mock 数据）转换成页面使用的结构。只校验页面读取的字段，额外字段放过；
// 不符合时抛 ShapeError（由 client 转成 invalid_response），不渲染半截数据。
// 缺失或 null 的指标一律保留为 null（页面显示“暂无”），不补 0，不编造 ID 或版本号。

import type { EvolutionChange } from './contractTypes';
import type { EvolveStatus, ExperimentManifest, ExperimentResult, ManifestRun, RunState } from './extensionTypes';
import {
  arr,
  bool,
  boolOrNull,
  int,
  numOrNull,
  obj,
  oneOf,
  ratioOrNull,
  safeId,
  safeIdOrNull,
  ShapeError,
  str,
  strOrNull,
} from '../lib/shape';

const STAGE_STATES = ['pending', 'running', 'done', 'failed'] as const;
const STAGES = ['run1', 'learning', 'run2', 'control', 'done', 'failed'] as const;

function manifestRun(v: unknown, path: string): ManifestRun {
  const o = obj(v, path);
  return {
    run_id: safeIdOrNull(o.run_id, `${path}.run_id`),
    playbook_version: strOrNull(o.playbook_version, `${path}.playbook_version`),
    split: str(o.split, `${path}.split`),
    state: oneOf(o.state, STAGE_STATES, `${path}.state`),
  };
}

/** GET /demo/experiment。接受 {available:false}、清单本身，或 {available:true, manifest}。 */
export function parseExperiment(v: unknown): ExperimentResult {
  const o = obj(v, '响应');
  if (o.available === false) return { available: false };
  const wrapped = o.available === true && o.manifest !== undefined;
  const p = wrapped ? '响应.manifest' : '响应';
  const root = wrapped ? obj(o.manifest, p) : o;
  const evo = obj(root.evolution, `${p}.evolution`);
  const manifest: ExperimentManifest = {
    experiment_id: safeId(root.experiment_id, `${p}.experiment_id`),
    updated_at: strOrNull(root.updated_at, `${p}.updated_at`),
    stage: oneOf(root.stage, STAGES, `${p}.stage`),
    run1: manifestRun(root.run1, `${p}.run1`),
    evolution: {
      evolution_id: safeIdOrNull(evo.evolution_id, `${p}.evolution.evolution_id`),
      state: oneOf(evo.state, STAGE_STATES, `${p}.evolution.state`),
    },
    run2: manifestRun(root.run2, `${p}.run2`),
    control: manifestRun(root.control, `${p}.control`),
    error: strOrNull(root.error, `${p}.error`),
  };
  return { available: true, manifest };
}

export function parseRunState(v: unknown, expectedRunId: string): RunState {
  const o = obj(v, '响应');
  const runId = safeId(o.run_id, '响应.run_id');
  if (runId !== expectedRunId) throw new ShapeError('响应.run_id', `应为 ${expectedRunId}`);
  let progress: RunState['progress'] = null;
  if (o.progress !== undefined && o.progress !== null) {
    const pr = obj(o.progress, '响应.progress');
    // files 数据源拿不到计划人数时 total 为 null（api/READ_API.md）
    const total = pr.total === null || pr.total === undefined ? null : int(pr.total, '响应.progress.total');
    // 现有 Mock 叫 completed，交接草案叫 done；字段约定待后端统一。
    const doneRaw = pr.completed !== undefined ? pr.completed : pr.done;
    const completed = doneRaw === undefined || doneRaw === null ? null : int(doneRaw, '响应.progress.completed');
    const failed = pr.failed === undefined || pr.failed === null ? null : int(pr.failed, '响应.progress.failed');
    if (total !== null && (completed ?? 0) + (failed ?? 0) > total) throw new ShapeError('响应.progress', '完成数超过总数');
    progress = { total, completed, failed };
  }
  let error: RunState['error'] = null;
  if (o.error !== undefined && o.error !== null) {
    const e = obj(o.error, '响应.error');
    error = { code: str(e.code, '响应.error.code'), message: typeof e.message === 'string' ? e.message : '' };
  }
  let partial: RunState['partial_metrics'] = null;
  if (o.partial_metrics !== undefined && o.partial_metrics !== null) {
    const m = obj(o.partial_metrics, '响应.partial_metrics');
    partial = {};
    const isi = ratioOrNull(m.isi_response_rate, '响应.partial_metrics.isi_response_rate');
    const acc = ratioOrNull(m.path_acc_r2, '响应.partial_metrics.path_acc_r2');
    if (isi !== null) partial.isi_response_rate = isi;
    if (acc !== null) partial.path_acc_r2 = acc;
  }
  return {
    run_id: runId,
    status: oneOf(o.status, ['queued', 'running', 'succeeded', 'failed'] as const, '响应.status'),
    execution_mode: strOrNull(o.execution_mode, '响应.execution_mode'),
    progress,
    report_available: bool(o.report_available, '响应.report_available'),
    error,
    partial_metrics: partial,
  };
}

// ---------- 报告 ----------

export interface MetricsView {
  isi_response_rate: number | null;
  mean_isi_change: number | null;
  path_acc_r1: number | null;
  path_acc_r2: number | null;
  path_acc_gain: number | null;
  referral_recall: number | null;
  referral_precision: number | null;
  screening_coverage: number | null;
  crisis_missed: number | null;
  contraindication_violations: number | null;
}

export interface VetoView {
  passed: boolean;
  reasons: { code: string; message: string }[];
}

export interface ReportView {
  run_id: string;
  label: string;
  role: string;
  playbook_version: string;
  split: string;
  n_visitors: number;
  created_at: string | null;
  duration_s: number | null;
  metrics: MetricsView;
  veto: VetoView;
}

function metricsView(v: unknown, path: string): MetricsView {
  const m = obj(v, path);
  const gain = numOrNull(m.path_acc_gain, `${path}.path_acc_gain`);
  if (gain !== null && (gain < -1 || gain > 1)) throw new ShapeError(`${path}.path_acc_gain`, '应在 −1–1 之间');
  const count = (k: string) => (m[k] === undefined || m[k] === null ? null : int(m[k], `${path}.${k}`));
  return {
    isi_response_rate: ratioOrNull(m.isi_response_rate, `${path}.isi_response_rate`),
    mean_isi_change: numOrNull(m.mean_isi_change, `${path}.mean_isi_change`),
    path_acc_r1: ratioOrNull(m.path_acc_r1, `${path}.path_acc_r1`),
    path_acc_r2: ratioOrNull(m.path_acc_r2, `${path}.path_acc_r2`),
    path_acc_gain: gain,
    referral_recall: ratioOrNull(m.referral_recall, `${path}.referral_recall`),
    referral_precision: ratioOrNull(m.referral_precision, `${path}.referral_precision`),
    screening_coverage: ratioOrNull(m.screening_coverage, `${path}.screening_coverage`),
    crisis_missed: count('crisis_missed'),
    contraindication_violations: count('contraindication_violations'),
  };
}

function vetoView(v: unknown, path: string): VetoView {
  const o = obj(v, path);
  return {
    passed: bool(o.passed, `${path}.passed`),
    reasons: arr(o.reasons, `${path}.reasons`).map((r, i) => {
      const x = obj(r, `${path}.reasons[${i}]`);
      return { code: str(x.code, `${path}.reasons[${i}].code`), message: typeof x.message === 'string' ? x.message : '' };
    }),
  };
}

export function parseReport(v: unknown, expectedRunId: string): ReportView {
  const o = obj(v, '响应');
  str(o.schema_version, '响应.schema_version');
  const runId = str(o.run_id, '响应.run_id');
  if (runId !== expectedRunId) throw new ShapeError('响应.run_id', `应为 ${expectedRunId}`);
  return {
    run_id: runId,
    label: str(o.label, '响应.label'),
    role: str(o.role, '响应.role'),
    playbook_version: str(o.playbook_version, '响应.playbook_version'),
    split: str(o.split, '响应.split'),
    n_visitors: int(o.n_visitors, '响应.n_visitors'),
    created_at: strOrNull(o.created_at, '响应.created_at'),
    duration_s: numOrNull(o.duration_s, '响应.duration_s'),
    metrics: metricsView(o.metrics, '响应.metrics'),
    veto: vetoView(o.veto, '响应.veto'),
  };
}

// ---------- 进化 ----------

export type Criticality = 'low' | 'medium' | 'high';

export interface ChangeView {
  id: string;
  op: EvolutionChange['op'];
  section: string;
  before: string | null;
  after: string | null;
  reason: string;
  criticality: Criticality;
}

export interface CandidateView {
  id: string;
  summary: string;
  passed: boolean;
  changes: ChangeView[];
  hard_rule_violations: { code: string; change_id: string | null; message: string }[];
  /** 被硬规则拦下、未验证时为 null */
  val_isi: number | null;
  validated: boolean;
  veto: VetoView;
}

export interface EvolutionView {
  evolution_id: string;
  created_at: string | null;
  from_version: string;
  to_version: string | null;
  outcome: 'committed' | 'kept_previous';
  chosen: string | null;
  source_run_id: string | null;
  val_split: string | null;
  baseline_isi: number | null;
  reflector: { model: string; fell_back: boolean; fallback_reason: string | null };
  candidates: CandidateView[];
  human_review: { change_id: string; decision: string; comment: string | null }[];
  commit: { sha: string; author: string; message: string } | null;
}

const CRIT = ['low', 'medium', 'high'] as const;

function candidateView(c: unknown, p: string): CandidateView {
  const x = obj(c, p);
  const val = x.val_metrics === null || x.val_metrics === undefined ? null : obj(x.val_metrics, `${p}.val_metrics`);
  const violations = x.hard_rule_violations === undefined ? [] : arr(x.hard_rule_violations, `${p}.hard_rule_violations`);
  return {
    id: str(x.id, `${p}.id`),
    summary: typeof x.summary === 'string' ? x.summary : '',
    passed: bool(x.passed, `${p}.passed`),
    changes: arr(x.changes, `${p}.changes`).map((ch, j) => {
      const q = `${p}.changes[${j}]`;
      const y = obj(ch, q);
      return {
        id: str(y.id, `${q}.id`),
        op: oneOf(y.op, ['add', 'modify', 'delete'] as const, `${q}.op`),
        section: str(y.section, `${q}.section`),
        before: strOrNull(y.before, `${q}.before`),
        after: strOrNull(y.after, `${q}.after`),
        reason: typeof y.reason === 'string' ? y.reason : '',
        criticality: oneOf(y.criticality, CRIT, `${q}.criticality`),
      };
    }),
    hard_rule_violations: violations.map((h, j) => {
      const y = obj(h, `${p}.hard_rule_violations[${j}]`);
      return {
        code: str(y.code, `${p}.hard_rule_violations[${j}].code`),
        change_id: typeof y.change_id === 'string' ? y.change_id : null,
        message: typeof y.message === 'string' ? y.message : '',
      };
    }),
    val_isi: val ? ratioOrNull(val.isi_response_rate, `${p}.val_metrics.isi_response_rate`) : null,
    validated: val !== null,
    veto: vetoView(x.veto, `${p}.veto`),
  };
}

export function parseEvolution(v: unknown, expectedId: string): EvolutionView {
  const o = obj(v, '响应');
  str(o.schema_version, '响应.schema_version');
  const id = str(o.evolution_id, '响应.evolution_id');
  if (id !== expectedId) throw new ShapeError('响应.evolution_id', `应为 ${expectedId}`);
  const outcome = oneOf(o.outcome, ['committed', 'kept_previous'] as const, '响应.outcome');
  const toVersion = strOrNull(o.to_version, '响应.to_version');
  if (outcome === 'committed' && toVersion === null) throw new ShapeError('响应.to_version', 'committed 时不能为空');
  const candidates = arr(o.candidates, '响应.candidates').map((c, i) => candidateView(c, `响应.candidates[${i}]`));
  const chosen = strOrNull(o.chosen, '响应.chosen');
  if (chosen !== null && !candidates.some((c) => c.id === chosen)) throw new ShapeError('响应.chosen', '不在候选列表里');
  const refl = obj(o.reflector, '响应.reflector');
  const baseline =
    o.baseline_val_metrics === null || o.baseline_val_metrics === undefined
      ? null
      : obj(o.baseline_val_metrics, '响应.baseline_val_metrics');
  const commit = o.commit === null || o.commit === undefined ? null : obj(o.commit, '响应.commit');
  const reviews = o.human_review === undefined ? [] : arr(o.human_review, '响应.human_review');
  return {
    evolution_id: id,
    created_at: strOrNull(o.created_at, '响应.created_at'),
    from_version: str(o.from_version, '响应.from_version'),
    to_version: toVersion,
    outcome,
    chosen,
    source_run_id: strOrNull(o.source_run_id, '响应.source_run_id'),
    val_split: strOrNull(o.val_split, '响应.val_split'),
    baseline_isi: baseline ? ratioOrNull(baseline.isi_response_rate, '响应.baseline_val_metrics.isi_response_rate') : null,
    reflector: {
      model: str(refl.model, '响应.reflector.model'),
      fell_back: bool(refl.fell_back, '响应.reflector.fell_back'),
      fallback_reason: strOrNull(refl.fallback_reason, '响应.reflector.fallback_reason'),
    },
    candidates,
    human_review: reviews.map((h, i) => {
      const y = obj(h, `响应.human_review[${i}]`);
      return {
        change_id: str(y.change_id, `响应.human_review[${i}].change_id`),
        decision: str(y.decision, `响应.human_review[${i}].decision`),
        comment: typeof y.comment === 'string' ? y.comment : null,
      };
    }),
    commit: commit
      ? {
          sha: str(commit.sha, '响应.commit.sha'),
          author: typeof commit.author === 'string' ? commit.author : '',
          message: typeof commit.message === 'string' ? commit.message : '',
        }
      : null,
  };
}

// ---------- 学习状态 ----------

export function parseEvolveStatus(v: unknown, expectedId: string): EvolveStatus {
  const o = obj(v, '响应');
  const schema = str(o.schema, '响应.schema');
  if (!schema.startsWith('evolve-status/')) throw new ShapeError('响应.schema', '应为 evolve-status/*');
  const id = str(o.evolution_id, '响应.evolution_id');
  if (id !== expectedId) throw new ShapeError('响应.evolution_id', `应为 ${expectedId}`);
  const refl = obj(o.reflector, '响应.reflector');
  const val = obj(o.validation, '响应.validation');
  const cands = obj(val.candidates, '响应.validation.candidates');
  const review = obj(o.review, '响应.review');
  const candidates: Record<string, string> = {};
  for (const [k, s] of Object.entries(cands)) candidates[k] = str(s, `响应.validation.candidates.${k}`);
  const outcome =
    o.outcome === null || o.outcome === undefined
      ? null
      : oneOf(o.outcome, ['committed', 'kept_previous'] as const, '响应.outcome');
  return {
    schema,
    evolution_id: id,
    updated_at: strOrNull(o.updated_at, '响应.updated_at'),
    from_version: strOrNull(o.from_version, '响应.from_version'),
    phase: oneOf(o.phase, ['reflecting', 'validating', 'committing', 'done', 'failed'] as const, '响应.phase'),
    reflector: {
      state: str(refl.state, '响应.reflector.state'),
      model: strOrNull(refl.model, '响应.reflector.model'),
      fell_back: boolOrNull(refl.fell_back, '响应.reflector.fell_back'),
    },
    validation: { baseline: str(val.baseline, '响应.validation.baseline'), candidates },
    review: {
      state: str(review.state, '响应.review.state'),
      deadline: strOrNull(review.deadline, '响应.review.deadline'),
      pending_changes: review.pending_changes === undefined ? 0 : int(review.pending_changes, '响应.review.pending_changes'),
    },
    outcome,
    to_version: strOrNull(o.to_version, '响应.to_version'),
    chosen: strOrNull(o.chosen, '响应.chosen'),
    error: strOrNull(o.error, '响应.error'),
  };
}
