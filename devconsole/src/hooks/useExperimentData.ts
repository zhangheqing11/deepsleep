// 当前实验下的各项数据：运行进度、报告、学习状态、进化记录。
// 每项各自串行轮询；key 里带 run_id / evolution_id，实验切换时旧轮询自动停止并清空。
// - 运行状态：运行开始后轮询，到 succeeded / failed 停止；404 停止（运行不存在）。
// - 报告：清单标记该运行完成（或状态显示报告可读）后才读；409 REPORT_NOT_READY 稍后重试。
// - 学习状态：学习开始后轮询，到 done / failed 停止。
// - 进化记录：学习完成后读；404 NOT_READY 稍后重试。

import type { DataClient } from '../api/client';
import type { EvolveStatus, ExperimentManifest, RunState } from '../api/extensionTypes';
import type { ApiError } from '../api/errors';
import type { EvolutionView, ReportView } from '../api/validate';
import { BACKOFF_MS, REPORT_RETRY_MS, REQUEST_TIMEOUT_MS, RUN_POLL_MS, STALE_AFTER_FAILURES } from '../config';
import type { RunKey } from '../model/overview';
import { usePoller, type PollHandle } from './usePoller';

const base = { timeoutMs: REQUEST_TIMEOUT_MS, backoffMs: BACKOFF_MS, staleAfter: STALE_AFTER_FAILURES };

const notFoundStop = (e: ApiError) => e.kind === 'http' && e.status === 404 && e.code !== 'NOT_READY';
const notReadyRetry = (e: ApiError) => (e.code === 'REPORT_NOT_READY' || e.code === 'NOT_READY' ? REPORT_RETRY_MS : null);

export interface RunData {
  state: PollHandle<RunState>;
  report: PollHandle<ReportView>;
}

export interface ExperimentData {
  runs: Record<RunKey, RunData>;
  status: PollHandle<EvolveStatus>;
  evolution: PollHandle<EvolutionView>;
}

function useRun(client: DataClient, m: ExperimentManifest | null, key: RunKey): RunData {
  const item = m?.[key] ?? null;
  const runId = item?.run_id ?? null;
  const started = item !== null && item.state !== 'pending';
  const state = usePoller<RunState>(runId && started ? `${m!.experiment_id}:${runId}:state` : null, {
    ...base,
    fetch: (s) => client.getRunState(runId!, s),
    intervalMs: RUN_POLL_MS,
    isTerminal: (d) => d.status === 'succeeded' || d.status === 'failed',
    shouldStop: notFoundStop,
  });
  const reportReady = item?.state === 'done' || state.data?.report_available === true;
  const report = usePoller<ReportView>(runId && reportReady ? `${m!.experiment_id}:${runId}:report` : null, {
    ...base,
    fetch: (s) => client.getReport(runId!, s),
    intervalMs: RUN_POLL_MS,
    isTerminal: () => true,
    shouldStop: notFoundStop,
    retryDelay: notReadyRetry,
  });
  return { state, report };
}

export function useExperimentData(client: DataClient, m: ExperimentManifest | null): ExperimentData {
  const run1 = useRun(client, m, 'run1');
  const run2 = useRun(client, m, 'run2');
  const control = useRun(client, m, 'control');

  const evoId = m?.evolution.evolution_id ?? null;
  const evoStarted = m !== null && m.evolution.state !== 'pending';
  const status = usePoller<EvolveStatus>(evoId && evoStarted ? `${m!.experiment_id}:${evoId}:status` : null, {
    ...base,
    fetch: (s) => client.getEvolveStatus(evoId!, s),
    intervalMs: RUN_POLL_MS,
    isTerminal: (d) => d.phase === 'done' || d.phase === 'failed',
    shouldStop: notFoundStop,
  });
  const evoDone = m?.evolution.state === 'done' || status.data?.phase === 'done';
  const evolution = usePoller<EvolutionView>(evoId && evoDone ? `${m!.experiment_id}:${evoId}:evolution` : null, {
    ...base,
    fetch: (s) => client.getEvolution(evoId!, s),
    intervalMs: RUN_POLL_MS,
    isTerminal: () => true,
    shouldStop: notFoundStop,
    retryDelay: notReadyRetry,
  });

  return { runs: { run1, run2, control }, status, evolution };
}

/** 顶栏用：已知运行的执行模式（没有运行时为空数组，后端没给时为 null）。 */
export function executionModes(d: ExperimentData): (string | null)[] {
  return (['run1', 'run2', 'control'] as const)
    .map((k) => d.runs[k].state.data)
    .filter((s): s is RunState => s !== null)
    .map((s) => s.execution_mode);
}
