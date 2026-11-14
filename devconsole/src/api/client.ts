// 进化后台的数据接口：只有读取，没有任何写操作。
// mock 与 http 实现同一个接口；snapshot（回放包）尚未实现，见 src/api/index.ts。

import type { EvolveStatus, ExperimentResult, RunState } from './extensionTypes';
import type { EvolutionView, ReportView } from './validate';
import type { DataMode } from '../lib/settings';

export interface DataClient {
  readonly mode: DataMode;
  /** 当前实验清单（后端从 var/demo/experiment.json 读）；没有实验时 {available:false} */
  getExperiment(signal: AbortSignal): Promise<ExperimentResult>;
  getRunState(runId: string, signal: AbortSignal): Promise<RunState>;
  getReport(runId: string, signal: AbortSignal): Promise<ReportView>;
  getEvolveStatus(evolutionId: string, signal: AbortSignal): Promise<EvolveStatus>;
  getEvolution(evolutionId: string, signal: AbortSignal): Promise<EvolutionView>;
}
