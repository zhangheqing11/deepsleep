// ⚠ 前端本地模拟适配器（模拟数据）。
// - 不访问后端；运行进度按时间推算，状态存 localStorage，所以刷新后能继续“查询”。
// - 报告和会谈内容直接取自 contracts/examples 的正式示例（只读），只改写 run_id / session_id。
// - 分组与版本的对应关系和后端 Mock 保持一致（崔秀净 11/14 说明）：
//     {split:A} → 运行 1（A/v1）；{split:B} → 对照（B/v1）；{split:B, playbook_version:v2} → 运行 2（B/v2）
//   不指定版本时固定 v1；其他组合返回 422（后端对此的行为待确认）。
// - 进度、错误结构等仍按接口草案模拟，不代表后端最终实现。
// - 页面必须标注“模拟数据”。真实后端失败时不得切换到这里。

import evolutionExample from '../../../contracts/examples/evolution.v1-v2.json';
import type { Experiment, PlaybookVersion } from './extensionTypes';
import run1Example from '../../../contracts/examples/run_report.run1.json';
import run2Example from '../../../contracts/examples/run_report.run2.json';
import controlExample from '../../../contracts/examples/run_report.control.json';
import sessionA001 from '../../../contracts/examples/session.A-001.json';
import sessionA002 from '../../../contracts/examples/session.A-002.json';
import sessionA003 from '../../../contracts/examples/session.A-003.json';
import { readJson, writeJson } from '../lib/storage';
import type { ApiClient } from './client';
import type { Evolution, RunReport, Session } from './contractTypes';
import type { CreateRunRequest, RunStatusResponse, SessionListItem } from './draftTypes';
import { ApiError } from './errors';
import { MOCK_PIPELINE } from './mockPipeline';

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

type ExampleKey = 'run1' | 'control' | 'run2';

interface MockRun {
  run_id: string;
  split: 'A' | 'B';
  playbook_version: string;
  /** 对应的契约示例报告；旧版本存的数据没有此字段，按分组和版本推断 */
  example?: ExampleKey;
  created_at_ms: number;
  scenario: MockScenario;
  total: number;
}

const sessionExamples: Record<string, Session> = {
  'A-001': sessionA001 as unknown as Session,
  'A-002': sessionA002 as unknown as Session,
  'A-003': sessionA003 as unknown as Session,
};

/** 与后端 Mock 一致：不指定版本时固定为 v1 */
const DEFAULT_VERSION = 'v1';

const REPORT_EXAMPLES: { key: ExampleKey; split: 'A' | 'B'; version: string; report: RunReport }[] = [
  { key: 'run1', split: 'A', version: 'v1', report: run1Example as unknown as RunReport },
  { key: 'control', split: 'B', version: 'v1', report: controlExample as unknown as RunReport },
  { key: 'run2', split: 'B', version: 'v2', report: run2Example as unknown as RunReport },
];

const AVAILABLE_COMBOS = REPORT_EXAMPLES.map((e) => `${e.split}/${e.version}`).join('、');

function findExample(split: string, version: string) {
  return REPORT_EXAMPLES.find((e) => e.split === split && e.version === version);
}

function reportFor(run: MockRun): RunReport {
  const entry =
    REPORT_EXAMPLES.find((e) => e.key === run.example) ??
    findExample(run.split, run.playbook_version) ??
    REPORT_EXAMPLES[0];
  return entry.report;
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
  const example = REPORT_EXAMPLES.find((e) => e.report.run_id === runId);
  const run = loadRuns()[runId] ?? (example ? {
    run_id: runId, split: example.split, playbook_version: example.version,
    example: example.key, created_at_ms: 0, scenario: 'normal' as const, total: example.report.n_visitors,
  } : undefined);
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

const evolution = evolutionExample as unknown as Evolution;
// 非契约占位：实验编排与版本元数据只用于本地预览，不表示实际执行。
const experiment: Experiment = {
  experiment_id: 'exp-mock-placeholder', updated_at: evolution.created_at, stage: 'done',
  run1: { run_id: run1Example.run_id, playbook_version: 'v1', split: 'A', state: 'done' },
  evolution: { evolution_id: evolution.evolution_id, state: 'done' },
  run2: { run_id: run2Example.run_id, playbook_version: 'v2', split: 'B', state: 'done' },
  control: { run_id: controlExample.run_id, playbook_version: 'v1', split: 'B', state: 'done' }, error: null,
};
const versions: PlaybookVersion[] = ['v1', 'v2'].map((version) => ({
  version, sha: version === 'v2' ? evolution.commit!.sha : 'mock-v1-placeholder',
  author: version === 'v2' ? evolution.commit!.author : 'mock',
  message: '模拟版本元数据（占位）', committed_at: evolution.created_at, is_head: version === 'v2',
}));
// 契约仅提供差异片段，因此本地版本正文也仅展示片段，不伪造完整 playbook。
function mockPlaybook(version: string): string {
  if (!versions.some((v) => v.version === version)) throw httpError(404, 'NOT_FOUND', '未找到该版本');
  return (evolution.diff ?? '').split('\n')
    .filter((line) => /^[ +\-]/.test(line) && !line.startsWith('---') && !line.startsWith('+++'))
    .filter((line) => version === 'v1' ? !line.startsWith('+') : !line.startsWith('-'))
    .map((line) => line.slice(1)).join('\n') + '\n';
}
function requireEvolution(id: string) {
  if (id !== evolution.evolution_id) throw httpError(404, 'NOT_FOUND', '未找到该进化记录');
}

export const mockClient: ApiClient = {
  adapter: 'mock',

  async health(signal) {
    await latency(signal);
    return { status: 'ok', data_source: 'mock', execution_mode: 'mock', contracts_version: '0.1.0' };
  },

  async listRuns(limit = 50, signal) {
    await latency(signal);
    const samples = REPORT_EXAMPLES.map(({ report }) => ({
      run_id: report.run_id, label: report.label, role: report.role, playbook_version: report.playbook_version,
      split: report.split, n_visitors: report.n_visitors, created_at: report.created_at,
      duration_s: report.duration_s, execution_mode: 'mock' as const, status: 'completed' as const, metrics: clone(report.metrics),
    }));
    const dynamic = Object.values(loadRuns()).map((run) => {
      const status = computeStatus(run);
      const report = reportFor(run);
      return { ...samples.find((r) => r.role === report.role)!, run_id: run.run_id,
        created_at: new Date(run.created_at_ms).toISOString(),
        status: status.report_available ? 'completed' as const : 'running' as const,
        metrics: status.report_available ? clone(report.metrics) : null };
    });
    return { items: [...dynamic, ...samples].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, limit) };
  },
  async getExperiment(signal) { await latency(signal); return clone(experiment); },
  async getEvidence(id, signal) { await latency(signal); findRun(id); return { available: false }; },
  async listEvolutions(limit = 20, signal) {
    await latency(signal);
    const { evolution_id, created_at, from_version, to_version, outcome, source_run_id, chosen } = evolution;
    return { items: [{ evolution_id, created_at, from_version, to_version, outcome, source_run_id, chosen, phase: 'done' as const }].slice(0, limit) };
  },
  async getEvolution(id, signal) { await latency(signal); requireEvolution(id); return clone(evolution); },
  async getEvolutionStatus(id, signal) {
    await latency(signal); requireEvolution(id);
    return { schema: 'evolve-status/1', evolution_id: id, updated_at: evolution.created_at,
      from_version: evolution.from_version, phase: 'done',
      reflector: { state: 'done', model: evolution.reflector.model, fell_back: evolution.reflector.fell_back },
      validation: { baseline: 'done', candidates: { c1: 'blocked', c2: 'done', c3: 'done' } },
      review: { state: 'done', deadline: null, pending_changes: 0 }, outcome: evolution.outcome,
      to_version: evolution.to_version, chosen: evolution.chosen, error: null };
  },
  async getEvolutionInsights(id, signal) { await latency(signal); requireEvolution(id); return { available: false }; },
  async listPlaybookVersions(signal) { await latency(signal); return { items: clone(versions) }; },
  async getPlaybook(version, signal) { await latency(signal); return { version, text: mockPlaybook(version) }; },
  async getPlaybookDiff(from, to, signal) {
    await latency(signal);
    const before = mockPlaybook(from).trimEnd().split('\n');
    const after = mockPlaybook(to).trimEnd().split('\n');
    const diff = from === to ? '' : from === 'v1' && to === 'v2' ? evolution.diff! :
      `--- a/playbook.md\n+++ b/playbook.md\n@@ -1,${before.length} +1,${after.length} @@\n${before.map((l) => '-' + l).join('\n')}\n${after.map((l) => '+' + l).join('\n')}\n`;
    return { from, to, diff };
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

    const version = body.playbook_version?.trim() || DEFAULT_VERSION;
    const example = findExample(body.split, version);
    if (!example) {
      throw httpError(
        422,
        'VALIDATION_ERROR',
        `模拟数据里没有 ${body.split} 组 ${version} 的示例报告（可用：${AVAILABLE_COMBOS}）`,
      );
    }
    const runs = loadRuns();
    const seq = Object.keys(runs).length + 1;
    const run: MockRun = {
      run_id: `run-mock-${String(seq).padStart(3, '0')}`,
      split: body.split,
      // 版本取示例报告里的实际值
      playbook_version: example.report.playbook_version,
      example: example.key,
      created_at_ms: Date.now(),
      scenario: getMockScenario(),
      total: example.report.n_visitors,
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
    // 只改写 run_id；label、role、版本等保持示例原值，与后端 Mock 一致
    const report = clone(reportFor(run));
    report.run_id = run.run_id;
    return report;
  },

  async listSessions(runId, signal) {
    await latency(signal);
    const run = findRun(runId);
    const status = computeStatus(run);
    const rows = reportFor(run).per_visitor;
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

  // 全链路演示：固定快照，不随时间推进；本地模拟没有后端，不能启动或停止。
  async getPipeline(signal) { await latency(signal); return clone(MOCK_PIPELINE); },
  async launchPipeline(_body, signal) {
    await latency(signal);
    throw httpError(501, 'RUNS_VIA_CLI', '模拟数据模式下不能启动或停止全链路：前端本地模拟没有连接后端。');
  },
  async stopPipeline(signal) {
    await latency(signal);
    throw httpError(501, 'RUNS_VIA_CLI', '模拟数据模式下不能启动或停止全链路：前端本地模拟没有连接后端。');
  },

  async getSession(runId, visitorId, signal) {
    await latency(signal);
    const run = findRun(runId);
    const example = sessionExamples[visitorId];
    const rowIndex = reportFor(run).per_visitor.findIndex((r) => r.visitor_id === visitorId);
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
