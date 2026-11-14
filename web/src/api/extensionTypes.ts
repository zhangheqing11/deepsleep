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
