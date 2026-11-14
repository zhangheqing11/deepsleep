// 后端扩展，非契约。只读接口规格 v1；状态结构对照 engine/evolve/status.py。
import type { Evolution, Metrics, RunReport } from './contractTypes';
import type { ExecutionMode } from './draftTypes';

export interface HealthResponse {
  status: string;
  data_source: 'files' | 'mock';
  execution_mode: ExecutionMode;
  contracts_version?: string;
}
export interface RunListItem {
  run_id: string;
  label: string | null;
  role: RunReport['role'] | null;
  playbook_version: string | null;
  split: string | null;
  n_visitors: number | null;
  created_at: string;
  duration_s: number | null;
  execution_mode: ExecutionMode;
  status: 'completed' | 'running';
  metrics: Metrics | null;
}
export type StepState = 'pending' | 'running' | 'done' | 'failed';
export interface ExperimentRun {
  run_id: string | null;
  playbook_version: string | null;
  split: string | null;
  state: StepState;
}
export interface Experiment {
  experiment_id: string;
  updated_at: string;
  stage: 'run1' | 'learning' | 'run2' | 'control' | 'done' | 'failed';
  run1: ExperimentRun | null;
  evolution: { evolution_id: string | null; state: StepState } | null;
  run2: ExperimentRun | null;
  control: ExperimentRun | null;
  error: string | null;
}
export type ExperimentResponse = Experiment | { available: false };
export type EvolutionPhase = 'reflecting' | 'validating' | 'committing' | 'done' | 'failed';
export interface EvolutionListItem {
  evolution_id: string;
  created_at: string;
  from_version: string;
  to_version: string | null;
  outcome: Evolution['outcome'] | null;
  source_run_id: string | null;
  chosen: string | null;
  phase: EvolutionPhase | null;
}
export type ValidationState = 'pending' | 'running' | 'done' | 'error' | 'skipped' | 'blocked' | 'empty';
export interface EvolutionStatus {
  schema: string;
  evolution_id: string;
  updated_at: string | null;
  from_version: string;
  phase: EvolutionPhase;
  reflector: { state: 'running' | 'done'; model: string | null; fell_back: boolean | null };
  validation: { baseline: ValidationState; candidates: Partial<Record<'c1' | 'c2' | 'c3', ValidationState>> };
  review: { state: 'not_needed' | 'waiting' | 'done'; deadline: string | null; pending_changes: number };
  outcome: Evolution['outcome'] | null;
  to_version: string | null;
  chosen: string | null;
  error: string | null;
}
// 规格要求原样返回，未冻结内部字段；保留 JSON，不冒充正式契约。
export type EvolutionInsights = Record<string, unknown>;
export type RunEvidence = { available: false } | { contract: false; summary: Record<string, unknown>; visitors: unknown[] };
export interface PlaybookVersion {
  version: string;
  /** 模拟数据源（API_DATA_SOURCE=mock）里的初始版本没有提交，为 null */
  sha: string | null;
  author: string;
  message: string;
  committed_at: string;
  is_head: boolean;
}
export interface Playbook { version: string; text: string }
export interface PlaybookDiff { from: string; to: string; diff: string }

// ---------- 全链路演示（api/PIPELINE_API.md，非契约） ----------

export type PipelineState = 'running' | 'done' | 'failed';
export type PipelineStepState = 'pending' | 'running' | 'done' | 'failed' | 'skipped';
export type PipelineStepKind = 'run' | 'generation' | 'practice' | 'final';
export type PipelineBatchRole = 'run1' | 'validation' | 'practice' | 'run2' | 'control';

export interface PipelineBatch {
  run_id: string;
  role: PipelineBatchRole;
  /** 运行 1、基线 · 第 n 次、候选 k · 第 n 次、练习（vN）、运行 2、对照 */
  label: string;
  version: string;
  split: string;
  total: number;
  completed: number;
  failed: number;
  state: 'running' | 'done' | 'failed';
  started_at: string | null;
  finished_at: string | null;
  duration_s: number | null;
  isi_response_rate: number | null;
}

export interface PipelineCandidate {
  id: string;
  state: 'pending' | 'running' | 'done';
  isi: number | null;
  /** 该代结束后取自 evolution.json，之前为 null */
  passed: boolean | null;
}

export interface PipelineGeneration {
  index: number;
  evolution_id: string;
  from_version: string;
  /** 原样取自 var/evolve/<id>/status.json */
  phase: EvolutionPhase | null;
  reflector: EvolutionStatus['reflector'] | null;
  baseline_isi: number | null;
  candidates: PipelineCandidate[];
  outcome: Evolution['outcome'] | null;
  to_version: string | null;
  chosen: string | null;
}

export interface PipelineStep {
  key: string;
  kind: PipelineStepKind;
  label: string;
  detail: string;
  state: PipelineStepState;
  started_at: string | null;
  finished_at: string | null;
  elapsed_s: number | null;
  expected_s: number | null;
  /** 非 running 时为 null */
  eta_s: number | null;
  batches: PipelineBatch[];
  /** 仅 kind=generation；尚未开始时为 null */
  generation?: PipelineGeneration | null;
}

export interface PipelineRunResult {
  isi_response_rate: number | null;
  referral_recall: number | null;
  referral_precision: number | null;
  n: number;
  playbook_version: string;
}

export interface PipelineResult {
  run1: PipelineRunResult | null;
  control: PipelineRunResult | null;
  run2: PipelineRunResult | null;
  /** (运行 2 − 对照) 的 ISI 有效率百分点差；任一缺失为 null */
  delta_pp: number | null;
}

export interface PipelinePreset {
  key: string;
  label: string;
  generations: number;
  description: string;
  expected_s: number;
  /** 11/15 增补：true = 先把 playbook 重置为 v1（开始一条新的进化链）；false = 从当前版本继续（`next`）。旧后端不发，按 true 处理 */
  reset?: boolean;
}

export interface PipelineLauncher {
  /** 服务端设置了 API_DEMO_LAUNCH=1 才为 true */
  enabled: boolean;
  state: 'idle' | 'running' | 'exited';
  pid: number | null;
  preset: string | null;
  started_at: string | null;
  exit_code: number | null;
  presets: PipelinePreset[];
  /** 子进程输出的最后 20 行 */
  log_tail: string[];
  /** 附加：上次启动是否 mock、是否经 POST /demo/stop 停止 */
  mock?: boolean;
  stopped?: boolean;
  /** 11/15 增补：版本库当前版本；版本库不存在为 null。旧后端不发 */
  current_version?: string | null;
  /** 11/15 增补：当前进化链里实验的模式；没有链为 null。旧后端不发 */
  lineage_mode?: 'real' | 'mock' | null;
}

// ---------- 逐代曲线（api/PIPELINE_API.md「续跑一代与逐代曲线」，11/15 增补） ----------

export interface PipelineCurveRun {
  run_id: string;
  /** control = 实验开始时的版本；run2 = 学习后的版本 */
  role: string;
  experiment_id: string;
  isi_response_rate: number | null;
  n: number;
}

export interface PipelineCurvePoint {
  version: string;
  /** 该版本在 B 组各次运行的 ISI 有效率算术平均 */
  mean: number | null;
  n_runs: number;
  /** 与上一个点的 mean 之差（百分点）；第一个点为 null */
  delta_pp: number | null;
  referral_recall?: number | null;
  referral_precision?: number | null;
  /** 产生该版本的那一代被采纳候选的摘要；起点版本为 null */
  learned?: string | null;
  evolution_id?: string | null;
  runs?: PipelineCurveRun[];
}

export interface PipelineCurveRejected {
  experiment_id: string;
  evolution_id: string;
  from_version: string;
  finished_at?: string | null;
}

export interface PipelineCurve {
  lineage_id: string | null;
  mode: 'real' | 'mock' | null;
  cohort: string;
  experiments: number;
  /** 按版本号升序；当前实验不属于任何链时为空数组 */
  points: PipelineCurvePoint[];
  rejected?: PipelineCurveRejected[];
}

export interface PipelineSnapshot {
  available: true;
  experiment_id: string;
  mode: 'real' | 'mock';
  state: PipelineState;
  error: string | null;
  started_at: string | null;
  updated_at: string | null;
  finished_at: string | null;
  elapsed_s: number | null;
  eta_s: number | null;
  generations_planned: number;
  playbook: { from_version: string; current_version: string };
  steps: PipelineStep[];
  result: PipelineResult;
  launcher: PipelineLauncher;
  /** 11/15 增补：当前进化链在留出集 B 上的逐代成绩。旧后端不发 */
  curve?: PipelineCurve | null;
}

export type PipelineResponse = PipelineSnapshot | { available: false; launcher: PipelineLauncher };

export interface PipelineLaunchRequest { preset: string; mock: boolean }
export interface PipelineLaunchResponse { pid: number; preset: string; mock: boolean }
export interface PipelineStopResponse { stopped: boolean }
