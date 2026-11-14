// ⚠ 后端扩展，非契约。
// 来源：
//  - ExperimentManifest：engine/demo.py（main@0732150）写出的 var/demo/experiment.json；
//  - EvolveStatus：engine/evolve/status.py（schema "evolve-status/1"，main@cf570fb 起）；
//  - RunState：后端 Mock /runs/{id}（api/run_models.py）+ 交接文档提议的 progress.done / partial_metrics（未实现）。
// HTTP 读接口（/demo/experiment、/evolutions/{id}、/evolutions/{id}/status）尚未在 api/ 实现，字段以后端确认为准。
// 这里只写页面真正读取的字段；后端可以多给，前端不依赖。

import type { Metrics } from './contractTypes';

export type StageState = 'pending' | 'running' | 'done' | 'failed';
export type ExperimentStage = 'run1' | 'learning' | 'run2' | 'control' | 'done' | 'failed';

export interface ManifestRun {
  run_id: string | null;
  /** 运行开始前可能为 null（engine/demo.py 先写 null，学习后才知道 run2 的版本） */
  playbook_version: string | null;
  split: string;
  state: StageState;
}

export interface ExperimentManifest {
  experiment_id: string;
  updated_at: string | null;
  stage: ExperimentStage;
  run1: ManifestRun;
  evolution: { evolution_id: string | null; state: StageState };
  run2: ManifestRun;
  control: ManifestRun;
  error: string | null;
}

/** GET /demo/experiment：没有实验时 {available:false}。 */
export type ExperimentResult = { available: false } | { available: true; manifest: ExperimentManifest };

export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface RunState {
  run_id: string;
  status: RunStatus;
  /** mock | real；后端没给时为 null，页面显示“后端未提供” */
  execution_mode: string | null;
  progress: {
    total: number;
    /** 现有 Mock 叫 completed，交接草案叫 done；两者都没有时为 null */
    completed: number | null;
    failed: number | null;
  } | null;
  report_available: boolean;
  error: { code: string; message: string } | null;
  /** 只有后端真的提供时才有；页面标“阶段统计” */
  partial_metrics: Partial<Metrics> | null;
  /** 前端收到这份状态的时间（不是后端字段） */
  received_at?: number;
}

export type EvolvePhase = 'reflecting' | 'validating' | 'committing' | 'done' | 'failed';

export interface EvolveStatus {
  schema: string;
  evolution_id: string;
  updated_at: string | null;
  from_version: string | null;
  phase: EvolvePhase;
  reflector: { state: string; model: string | null; fell_back: boolean | null };
  validation: { baseline: string; candidates: Record<string, string> };
  review: { state: string; deadline: string | null; pending_changes: number };
  outcome: 'committed' | 'kept_previous' | null;
  to_version: string | null;
  chosen: string | null;
  error: string | null;
}
