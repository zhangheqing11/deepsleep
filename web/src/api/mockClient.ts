// ⚠ 前端本地模拟适配器（模拟数据）。
// - 不访问后端；运行进度按时间推算，状态存 localStorage，所以刷新后能继续“查询”。
// - 报告和会谈内容直接取自 contracts/examples 的正式示例（只读），只改写 run_id / session_id。
// - 进度、错误结构等仍按接口草案模拟，不代表后端最终实现。
// - 页面必须标注“模拟数据”。真实后端失败时不得切换到这里。

import run1Example from '../../../contracts/examples/run_report.run1.json';
import run2Example from '../../../contracts/examples/run_report.run2.json';
import sessionA001 from '../../../contracts/examples/session.A-001.json';
import sessionA002 from '../../../contracts/examples/session.A-002.json';
import sessionA003 from '../../../contracts/examples/session.A-003.json';
import { readJson, writeJson } from '../lib/storage';
import type { ApiClient } from './client';
import type { RunReport, Session } from './contractTypes';
import type { CreateRunRequest, RunStatusResponse, SessionListItem } from './draftTypes';
import { ApiError } from './errors';

export type MockScenario = 'normal' | 'fail' | 'report_delay' | 'network_flaky';

export const MOCK_SCENARIOS: { value: MockScenario; label: string; hint: string }[] = [
  { value: 'normal', label: '正常完成', hint: '排队 1 秒后逐个完成来访，结束后可读取报告' },
  { value: 'fail', label: '任务失败', hint: '第 5 个来访出错，运行以 failed 结束，保留不完整报告' },
  {
    value: 'report_delay',
    label: '报告未准备好',
    hint: '运行成功，但报告接口在结束后 6 秒内返回 409 REPORT_NOT_READY；之后点“重新读取”',
  },
  {
    value: 'network_flaky',
    label: '网络不稳',
    hint: '创建请求的响应丢失一次（验证幂等重试）；运行中有 3 秒查询失败',
  },
];

const RUNS_KEY = 'deepsleep.mock.runs.v1';
const IDEM_KEY = 'deepsleep.mock.idempotency.v1';
const SCENARIO_KEY = 'deepsleep.mock.scenario.v1';
const LOST_RESPONSE_KEY = 'deepsleep.mock.lostResponse.v1';

const QUEUE_MS = 1000;
const PER_VISITOR_MS = 700;
// 大于前端 409 自动重试的总时长（3 × 1 秒），让“报告生成中”提示和手动重新读取能被看到
const REPORT_DELAY_MS = 6000;
const FAIL_AT_INDEX = 4; // 第 5 个来访

interface MockRun {
  run_id: string;
  split: 'A' | 'B';
  playbook_version: string;
  created_at_ms: number;
  scenario: MockScenario;
  total: number;
}

const sessionExamples: Record<string, Session> = {
  'A-001': sessionA001 as unknown as Session,
  'A-002': sessionA002 as unknown as Session,
  'A-003': sessionA003 as unknown as Session,
};

function reportExample(split: 'A' | 'B'): RunReport {
  return (split === 'A' ? run1Example : run2Example) as unknown as RunReport;
}

export function getMockScenario(): MockScenario {
  return readJson<MockScenario>('local', SCENARIO_KEY) ?? 'normal';
}

export function setMockScenario(s: MockScenario): void {
  writeJson('local', SCENARIO_KEY, s);
}

function loadRuns(): Record<string, MockRun> {
  return readJson<Record<string, MockRun>>('local', RUNS_KEY) ?? {};
}

function saveRuns(runs: Record<string, MockRun>): void {
  writeJson('local', RUNS_KEY, runs);
}

function requestId(): string {
  return `req_mock_${Math.random().toString(36).slice(2, 10)}`;
}

function httpError(status: number, code: string, message: string): ApiError {
  return new ApiError({ kind: 'http', status, code, message, requestId: requestId() });
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new ApiError({ kind: 'aborted', message: '请求已取消' }));
      return;
    }
    const t = window.setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        window.clearTimeout(t);
        reject(new ApiError({ kind: 'aborted', message: '请求已取消' }));
      },
      { once: true },
    );
  });
}

const latency = (signal?: AbortSignal) => delay(120 + Math.random() * 180, signal);

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

function findRun(runId: string): MockRun {
  const run = loadRuns()[runId];
  if (!run) throw httpError(404, 'RUN_NOT_FOUND', '未找到该运行记录');
  return run;
}

/** 按时间推算运行状态 */
function computeStatus(run: MockRun, now = Date.now()): RunStatusResponse {
  const elapsed = Math.max(0, now - run.created_at_ms);
  const base = {
    run_id: run.run_id,
    execution_mode: 'mock' as const,
    split: run.split,
    playbook_version: run.playbook_version,
    elapsed_ms: elapsed,
  };

  if (elapsed < QUEUE_MS) {
    return {
      ...base,
      status: 'queued',
      progress: { total: run.total, completed: 0, failed: 0 },
      report_available: false,
      error: null,
    };
  }

  const processed = Math.min(run.total, Math.floor((elapsed - QUEUE_MS) / PER_VISITOR_MS));

  if (run.scenario === 'fail' && processed > FAIL_AT_INDEX) {
    return {
      ...base,
      elapsed_ms: QUEUE_MS + (FAIL_AT_INDEX + 1) * PER_VISITOR_MS,
      status: 'failed',
      progress: { total: run.total, completed: FAIL_AT_INDEX, failed: 1 },
      report_available: true,
      error: { code: 'RUN_FAILED', message: '模拟场景：第 5 个来访执行出错，运行终止' },
    };
  }

  if (processed < run.total) {
    return {
      ...base,
      status: 'running',
      progress: { total: run.total, completed: processed, failed: 0 },
      report_available: false,
      error: null,
    };
  }

  return {
    ...base,
    elapsed_ms: QUEUE_MS + run.total * PER_VISITOR_MS,
    status: 'succeeded',
    progress: { total: run.total, completed: run.total, failed: 0 },
    report_available: true,
    error: null,
  };
}

function finishedAt(run: MockRun): number {
  return run.created_at_ms + QUEUE_MS + run.total * PER_VISITOR_MS;
}

export const mockClient: ApiClient = {
  adapter: 'mock',

  async health(signal) {
    await latency(signal);
    return { status: 'ok', execution_mode: 'mock', contracts_version: '0.1.0' };
  },

  async createRun(body: CreateRunRequest, idempotencyKey, signal) {
    await latency(signal);
    if (body.split !== 'A' && body.split !== 'B') {
      throw httpError(422, 'VALIDATION_ERROR', 'split 只能是 A 或 B');
    }
    const idem = readJson<Record<string, { run_id: string; body: string }>>('local', IDEM_KEY) ?? {};
    const bodyKey = JSON.stringify(body);
    const existing = idem[idempotencyKey];
    if (existing) {
      if (existing.body !== bodyKey) {
        throw httpError(409, 'IDEMPOTENCY_KEY_REUSED', '同一提交标识对应了不同的请求内容');
      }
      const run = findRun(existing.run_id);
      return { run_id: run.run_id, status: computeStatus(run).status, execution_mode: 'mock' };
    }

    const example = reportExample(body.split);
    const runs = loadRuns();
    const seq = Object.keys(runs).length + 1;
    const run: MockRun = {
      run_id: `run-mock-${String(seq).padStart(3, '0')}`,
      split: body.split,
      // 版本取示例报告里的实际值，不在前端写死
      playbook_version: body.playbook_version ?? example.playbook_version,
      created_at_ms: Date.now(),
      scenario: getMockScenario(),
      total: example.n_visitors,
    };
    runs[run.run_id] = run;
    saveRuns(runs);
    idem[idempotencyKey] = { run_id: run.run_id, body: bodyKey };
    writeJson('local', IDEM_KEY, idem);

    // 网络不稳场景：后端已创建任务，但第一次响应“丢失”
    if (run.scenario === 'network_flaky' && !readJson<boolean>('session', LOST_RESPONSE_KEY)) {
      writeJson('session', LOST_RESPONSE_KEY, true);
      throw new ApiError({ kind: 'network', message: '模拟：响应在网络中丢失' });
    }
    return { run_id: run.run_id, status: 'queued', execution_mode: 'mock' };
  },

  async getRun(runId, signal) {
    await latency(signal);
    const run = findRun(runId);
    if (run.scenario === 'network_flaky') {
      const elapsed = Date.now() - run.created_at_ms;
      if (elapsed > 2000 && elapsed < 5000) {
        throw new ApiError({ kind: 'network', message: '模拟：网络中断' });
      }
    }
    return computeStatus(run);
  },

  async getReport(runId, signal) {
    await latency(signal);
    const run = findRun(runId);
    const status = computeStatus(run);
    if (!status.report_available) {
      throw httpError(409, 'REPORT_NOT_READY', '报告尚未生成');
    }
    if (run.scenario === 'report_delay' && Date.now() < finishedAt(run) + REPORT_DELAY_MS) {
      throw httpError(409, 'REPORT_NOT_READY', '报告尚未生成');
    }
    const report = clone(reportExample(run.split));
    report.run_id = run.run_id;
    report.playbook_version = run.playbook_version;
    report.label = `模拟示例报告（${run.split} 组）`;
    return report;
  },

  async listSessions(runId, signal) {
    await latency(signal);
    const run = findRun(runId);
    const status = computeStatus(run);
    const rows = reportExample(run.split).per_visitor;
    const items: SessionListItem[] = rows.map((row, i) => {
      let taskStatus: SessionListItem['status'];
      if (status.status === 'failed') {
        taskStatus = i < FAIL_AT_INDEX ? 'succeeded' : i === FAIL_AT_INDEX ? 'failed' : 'queued';
      } else if (i < status.progress.completed) {
        taskStatus = 'succeeded';
      } else {
        taskStatus = status.status === 'queued' ? 'queued' : 'running';
      }
      const example = sessionExamples[row.visitor_id];
      const available = taskStatus === 'succeeded' && Boolean(example);
      return {
        visitor_id: row.visitor_id,
        status: taskStatus,
        session_available: available,
        session_status: available ? example.status : null,
      };
    });
    return { items };
  },

  async getSession(runId, visitorId, signal) {
    await latency(signal);
    const run = findRun(runId);
    const example = sessionExamples[visitorId];
    const rowIndex = reportExample(run.split).per_visitor.findIndex((r) => r.visitor_id === visitorId);
    if (!example || rowIndex < 0) {
      throw httpError(404, 'SESSION_NOT_FOUND', '未找到该会谈记录（契约示例里只有 A-001 至 A-003）');
    }
    const session = clone(example);
    session.run_id = run.run_id;
    session.session_id = `${run.run_id}/${visitorId}`;
    session.playbook_version = run.playbook_version;
    return session;
  },
};
