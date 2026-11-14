// mock 适配器：报告与进化记录读 contracts/examples 的正式示例；实验清单、运行进度、学习状态读手写开发样例
// （src/fixtures/devSamples.ts）。所有数据都是静态的：不用定时器推进进度，也不制造“实时增长”。
// 数据同样经过 validate.ts，和 http 模式走同一套校验。

import run1Example from '../../../contracts/examples/run_report.run1.json';
import run2Example from '../../../contracts/examples/run_report.run2.json';
import controlExample from '../../../contracts/examples/run_report.control.json';
import evolutionExample from '../../../contracts/examples/evolution.v1-v2.json';
import type { DataClient } from './client';
import { ApiError } from './errors';
import { parseEvolution, parseEvolveStatus, parseExperiment, parseReport, parseRunState } from './validate';
import { fixtureData, type FixtureName } from '../fixtures/devSamples';
import { ShapeError } from '../lib/shape';

const REPORTS: Record<string, { n_visitors: number }> = {
  [run1Example.run_id]: run1Example,
  [run2Example.run_id]: run2Example,
  [controlExample.run_id]: controlExample,
};

function notFound(code: string, message: string): ApiError {
  return new ApiError({ kind: 'http', status: 404, code, message });
}

function parsed<T>(fn: () => T): T {
  try {
    return fn();
  } catch (e) {
    if (e instanceof ShapeError) throw new ApiError({ kind: 'invalid_response', status: 200, message: e.message });
    throw e;
  }
}

function checkAbort(signal: AbortSignal) {
  if (signal.aborted) throw new ApiError({ kind: 'aborted', message: '请求已取消' });
}

export function createMockClient(fixture: FixtureName): DataClient {
  const data = fixtureData(fixture, (id) => REPORTS[id]?.n_visitors ?? 0);

  return {
    mode: 'mock',
    async getExperiment(signal) {
      checkAbort(signal);
      return parsed(() => parseExperiment(data.experiment));
    },
    async getRunState(runId, signal) {
      checkAbort(signal);
      const s = data.runStates[runId];
      if (!s) throw notFound('RUN_NOT_FOUND', '未找到该运行');
      return parsed(() => parseRunState(s, runId));
    },
    async getReport(runId, signal) {
      checkAbort(signal);
      if (!data.reports.includes(runId) || !REPORTS[runId]) {
        if (data.runStates[runId]) throw new ApiError({ kind: 'http', status: 409, code: 'REPORT_NOT_READY', message: '报告尚未生成' });
        throw notFound('RUN_NOT_FOUND', '未找到该运行');
      }
      return parsed(() => parseReport(REPORTS[runId], runId));
    },
    async getEvolveStatus(id, signal) {
      checkAbort(signal);
      const s = data.statuses[id];
      if (!s) throw notFound('EVOLUTION_NOT_FOUND', '未找到该学习记录');
      return parsed(() => parseEvolveStatus(s, id));
    },
    async getEvolution(id, signal) {
      checkAbort(signal);
      if (data.evolution === null) {
        if (data.statuses[id]) throw new ApiError({ kind: 'http', status: 404, code: 'NOT_READY', message: '学习尚未完成' });
        throw notFound('EVOLUTION_NOT_FOUND', '未找到该学习记录');
      }
      const raw = data.evolution === 'example' ? evolutionExample : data.evolution;
      return parsed(() => parseEvolution(raw, id));
    },
  };
}
