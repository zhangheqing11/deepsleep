// 进化看板的数据聚合与展示推导。
// 只读：把实验清单、三次运行、学习记录和 playbook 版本合成一份快照。
// 不计算任何指标；这里只做分组、差值和文案推导，数值全部来自后端。

import type { ApiClient } from '../api/client';
import type { Evolution, EvolutionCandidate, Metrics, PerVisitorRow, RunReport } from '../api/contractTypes';
import type { RunStatusResponse } from '../api/draftTypes';
import { isAbortError, toApiError, type ApiError } from '../api/errors';
import type { EvolutionStatus, Experiment, ExperimentRun, PipelineCurve, PlaybookVersion } from '../api/extensionTypes';
import { pct, pointDelta } from './format';

export type RunRole = 'run1' | 'control' | 'run2';

export interface RunSlot {
  role: RunRole;
  node: ExperimentRun | null;
  /** 运行完成后才有；未完成或读取失败时为 null */
  report: RunReport | null;
  /** 运行状态（进度、数据来源）；读不到时为 null */
  status: RunStatusResponse | null;
  /** 报告读取失败的原因；下一次轮询会重试 */
  error: ApiError | null;
  /** 问诊证据：会谈每一步里正确路径的平均权重；后端没有时为 null */
  evidence: EvidenceStep[] | null;
}

export interface EvidenceStep {
  round: number;
  step: number;
  /** 0–1 */
  pTrue: number;
}

export interface BoardData {
  /** null = 后端还没有实验 */
  experiment: Experiment | null;
  run1: RunSlot;
  control: RunSlot;
  run2: RunSlot;
  /** 学习完成后的进化记录 */
  evolution: Evolution | null;
  /** 学习进行中的进度 */
  evolutionStatus: EvolutionStatus | null;
  versions: PlaybookVersion[] | null;
  /** 任一运行为模拟执行，或前端使用本地模拟数据 */
  mock: boolean;
  /** 当前进化链在留出集 B 上的逐代成绩（GET /demo/pipeline 的 curve）；读不到或后端没有时为 null */
  curve?: PipelineCurve | null;
}

/** 跨轮询保留的只读缓存：完成的报告和进化记录不会再变。 */
export interface BoardCache {
  experimentId: string | null;
  reports: Map<string, RunReport>;
  finalStatus: Map<string, RunStatusResponse>;
  evolution: Evolution | null;
  versions: PlaybookVersion[] | null;
  versionsKey: string | null;
  /** 已读过的证据；null 表示后端明确没有，不再重复请求 */
  evidence: Map<string, EvidenceStep[] | null>;
  /** 最近一次读到的逐代曲线；读取失败时沿用（曲线属于进化链，不随实验换场清空） */
  curve: PipelineCurve | null;
}

export function createBoardCache(): BoardCache {
  return { experimentId: null, reports: new Map(), finalStatus: new Map(), evolution: null, versions: null, versionsKey: null, evidence: new Map(), curve: null };
}

const emptySlot = (role: RunRole): RunSlot => ({ role, node: null, report: null, status: null, error: null, evidence: null });

export const EMPTY_BOARD: BoardData = {
  experiment: null,
  run1: emptySlot('run1'),
  control: emptySlot('control'),
  run2: emptySlot('run2'),
  evolution: null,
  evolutionStatus: null,
  versions: null,
  mock: false,
  curve: null,
};

/** 子资源读取失败不打断整页：返回 null，由下一次轮询重试。取消请求照常抛出。 */
async function soft<T>(signal: AbortSignal, read: () => Promise<T>): Promise<{ data: T | null; error: ApiError | null }> {
  try {
    return { data: await read(), error: null };
  } catch (e) {
    if (signal.aborted || isAbortError(e)) throw e;
    return { data: null, error: toApiError(e) };
  }
}

async function readSlot(api: ApiClient, cache: BoardCache, role: RunRole, node: ExperimentRun | null, signal: AbortSignal): Promise<RunSlot> {
  if (!node || !node.run_id) return { ...emptySlot(role), node };
  const id = node.run_id;
  if (node.state === 'done') {
    let error: ApiError | null = null;
    if (!cache.reports.has(id)) {
      const r = await soft(signal, () => api.getReport(id, signal));
      if (r.data) cache.reports.set(id, r.data);
      error = r.error;
    }
    if (!cache.finalStatus.has(id)) {
      const s = await soft(signal, () => api.getRun(id, signal));
      if (s.data) cache.finalStatus.set(id, s.data);
    }
    // 证据只画对照与运行 2；读到一次（包括“没有”）就不再请求。
    if (role !== 'run1' && cache.reports.has(id) && !cache.evidence.has(id)) {
      const e = await soft(signal, () => api.getEvidence(id, signal));
      if (!e.error) cache.evidence.set(id, parseEvidence(e.data));
    }
    return { role, node, report: cache.reports.get(id) ?? null, status: cache.finalStatus.get(id) ?? null, error,
      evidence: cache.evidence.get(id) ?? null };
  }
  if (node.state === 'running') {
    const s = await soft(signal, () => api.getRun(id, signal));
    return { ...emptySlot(role), node, status: s.data };
  }
  return { ...emptySlot(role), node };
}

/** 读取一份完整快照。实验清单读取失败时抛出，由调用方保留上一份数据。 */
export async function readBoard(api: ApiClient, cache: BoardCache, signal: AbortSignal): Promise<BoardData> {
  const response = await api.getExperiment(signal);
  const experiment = 'experiment_id' in response ? response : null;
  const experimentId = experiment?.experiment_id ?? null;
  if (cache.experimentId !== experimentId) {
    Object.assign(cache, createBoardCache(), { experimentId, curve: cache.curve });
  }

  const [run1, control, run2] = await Promise.all([
    readSlot(api, cache, 'run1', experiment?.run1 ?? null, signal),
    readSlot(api, cache, 'control', experiment?.control ?? null, signal),
    readSlot(api, cache, 'run2', experiment?.run2 ?? null, signal),
  ]);

  let evolutionStatus: EvolutionStatus | null = null;
  const evolutionNode = experiment?.evolution ?? null;
  // 学习还没开始时记录不存在，不去请求。
  const evolutionId = evolutionNode && evolutionNode.state !== 'pending' ? evolutionNode.evolution_id : null;
  if (evolutionId && !cache.evolution) {
    const evo = await soft(signal, () => api.getEvolution(evolutionId, signal));
    if (evo.data) cache.evolution = evo.data;
    else evolutionStatus = (await soft(signal, () => api.getEvolutionStatus(evolutionId, signal))).data;
  }

  // 版本只在实验或学习结果变化时重读。
  const versionsKey = `${experimentId}:${cache.evolution?.outcome ?? evolutionStatus?.phase ?? ''}`;
  if (cache.versions === null || cache.versionsKey !== versionsKey) {
    const v = await soft(signal, () => api.listPlaybookVersions(signal));
    if (v.data) {
      cache.versions = [...v.data.items].sort((a, b) => versionNumber(a.version) - versionNumber(b.version));
      cache.versionsKey = versionsKey;
    }
  }

  // 逐代曲线：全链路接口的 curve（11/15 增补）。读取失败沿用上一份；后端没有这个字段（旧后端、available=false）时为 null。
  const pipeline = await soft(signal, () => api.getPipeline(signal));
  if (pipeline.data) cache.curve = readCurve(pipeline.data);

  const mock = api.adapter === 'mock' || [run1, control, run2].some((s) => s.status?.execution_mode === 'mock');
  return { experiment, run1, control, run2, evolution: cache.evolution, evolutionStatus, versions: cache.versions, mock, curve: cache.curve };
}

/** 只认结构对的 curve：必须有 points 数组；否则当作没有 */
export function readCurve(response: unknown): PipelineCurve | null {
  const r = response as { available?: unknown; curve?: unknown } | null;
  if (!r || r.available !== true) return null;
  const curve = r.curve as PipelineCurve | null | undefined;
  return curve && typeof curve === 'object' && Array.isArray(curve.points) ? curve : null;
}

/**
 * 证据接口不在契约里，字段未冻结：只取页面要画的三个数，结构不对就当作没有。
 */
export function parseEvidence(raw: unknown): EvidenceStep[] | null {
  const summary = (raw as { summary?: { by_step?: unknown } } | null)?.summary;
  if (!summary || !Array.isArray(summary.by_step)) return null;
  const steps: EvidenceStep[] = [];
  for (const item of summary.by_step as Record<string, unknown>[]) {
    const { round, step, mean_p_true: p } = item ?? {};
    if (typeof round !== 'number' || typeof step !== 'number' || typeof p !== 'number' || !Number.isFinite(p)) return null;
    steps.push({ round, step, pTrue: p });
  }
  steps.sort((a, b) => a.round - b.round || a.step - b.step);
  return steps.length > 0 ? steps : null;
}

function versionNumber(v: string): number {
  const n = Number(v.replace(/^v/, ''));
  return Number.isFinite(n) ? n : Number.MAX_SAFE_INTEGER;
}

// ---------- 展示推导 ----------

export function metricDifference(value: number | null | undefined, baseline: number | null | undefined): number | null {
  return value == null || baseline == null ? null : value - baseline;
}

/** 否决未通过或出现危机漏报的运行 */
export function alertSlots(data: BoardData): RunSlot[] {
  return [data.run1, data.control, data.run2].filter(
    (s) => s.report && (!s.report.veto.passed || s.report.metrics.crisis_missed > 0),
  );
}

export type FindingTone = 'neutral' | 'positive' | 'negative' | 'waiting';
export interface Finding { tone: FindingTone; text: string }

/** 标题下的一句话结论：当前阶段最需要被读到的事实。 */
export function finding(data: BoardData): Finding {
  const exp = data.experiment;
  if (!exp) return { tone: 'waiting', text: '暂无实验，等待操作员发起。' };
  if (exp.stage === 'failed') return { tone: 'negative', text: `实验执行失败：${exp.error ?? '后端没有给出原因'}` };

  const alerts = alertSlots(data);
  if (alerts.length > 0) {
    const names = alerts.map((s) => ROLE_LABEL[s.role]).join('、');
    return { tone: 'negative', text: `${names}没有守住安全线，本次结果不能作为进步的依据。` };
  }

  const c = data.control.report;
  const r = data.run2.report;
  if (c && r) {
    if (data.evolution?.outcome === 'kept_previous' || c.playbook_version === r.playbook_version) {
      return {
        tone: 'neutral',
        text: `本次学习保留上一代 playbook：没有候选通过门禁，运行 2 与对照都使用 ${r.playbook_version}。`,
      };
    }
    const d = r.metrics.isi_response_rate - c.metrics.isi_response_rate;
    const same = c.split === r.split && c.n_visitors === r.n_visitors;
    const scope = same ? `同一批 ${r.n_visitors} 位 ${r.split} 组来访` : `${r.split} 组来访`;
    if (d > 0) return { tone: 'positive', text: `${scope}，${r.playbook_version} 的有效率比 ${c.playbook_version} 高 ${pointDelta(d).slice(1)}。` };
    if (d < 0) return { tone: 'negative', text: `${scope}，${r.playbook_version} 的有效率比 ${c.playbook_version} 低 ${pointDelta(d).slice(1)}。` };
    return { tone: 'neutral', text: `${scope}，${r.playbook_version} 与 ${c.playbook_version} 的有效率相同（${pct(r.metrics.isi_response_rate)}）。` };
  }

  switch (exp.stage) {
    case 'run1':
      return { tone: 'waiting', text: `运行 1 进行中：${exp.run1?.playbook_version ?? '初始版本'} 正在与 ${exp.run1?.split ?? 'A'} 组来访会谈。` };
    case 'learning':
      return { tone: 'waiting', text: '学习进行中：系统读运行 1 的失败会谈，提出改动，并在验证集上过门禁。' };
    case 'run2':
    case 'control':
      return { tone: 'waiting', text: '运行 2 与对照进行中：新旧两版 playbook 在同一批新来访上各跑一遍。' };
    default:
      return { tone: 'waiting', text: '运行已结束，正在读取报告。' };
  }
}

export const ROLE_LABEL: Record<RunRole, string> = { run1: '运行 1', control: '对照', run2: '运行 2' };

export type UnitGroup = 'gained' | 'both' | 'lost' | 'neither';
export interface PairedUnit {
  visitor_id: string;
  control: PerVisitorRow;
  run2: PerVisitorRow;
  group: UnitGroup;
}
export interface Pairing {
  units: PairedUnit[];
  counts: Record<UnitGroup, number>;
}

const GROUP_ORDER: UnitGroup[] = ['both', 'gained', 'lost', 'neither'];

/**
 * 把对照与运行 2 按来访逐个配对。两份报告的来访不一致时返回 null，
 * 页面退回到各自计数，不硬凑配对。
 */
export function pairVisitors(control: RunReport | null, run2: RunReport | null): Pairing | null {
  if (!control || !run2 || control.per_visitor.length === 0) return null;
  if (control.per_visitor.length !== run2.per_visitor.length) return null;
  const byId = new Map(run2.per_visitor.map((v) => [v.visitor_id, v]));
  const units: PairedUnit[] = [];
  for (const c of control.per_visitor) {
    const r = byId.get(c.visitor_id);
    if (!r) return null;
    const group: UnitGroup = c.responder ? (r.responder ? 'both' : 'lost') : r.responder ? 'gained' : 'neither';
    units.push({ visitor_id: c.visitor_id, control: c, run2: r, group });
  }
  units.sort((a, b) => GROUP_ORDER.indexOf(a.group) - GROUP_ORDER.indexOf(b.group) || a.visitor_id.localeCompare(b.visitor_id));
  const counts: Record<UnitGroup, number> = { gained: 0, both: 0, lost: 0, neither: 0 };
  for (const u of units) counts[u.group] += 1;
  return { units, counts };
}

export function responders(report: RunReport): number {
  return report.per_visitor.filter((v) => v.responder).length;
}

export type CandidateVerdict = 'chosen' | 'hard_rule' | 'veto' | 'not_better' | 'passed_unchosen';

export function candidateVerdict(c: EvolutionCandidate, evo: Evolution): CandidateVerdict {
  if (c.id === evo.chosen) return 'chosen';
  if (c.hard_rule_violations.length > 0) return 'hard_rule';
  if (!c.veto.passed) return 'veto';
  if (!c.passed) return 'not_better';
  return 'passed_unchosen';
}

export const VERDICT_LABEL: Record<CandidateVerdict, string> = {
  chosen: '选中',
  hard_rule: '硬规则拦下',
  veto: '否决规则未过',
  not_better: '没有超过上一代',
  passed_unchosen: '通过，未选中',
};

export interface MetricRow {
  key: string;
  title: string;
  get: (m: Metrics) => number | null;
  kind: 'ratio' | 'points' | 'score';
  better: 'higher' | 'lower';
}

/** 副指标：主指标与危机漏报各有自己的位置，不在这张表里重复。 */
export const SECONDARY_METRICS: MetricRow[] = [
  { key: 'path_r1', title: '路径准确率 · 第 1 轮', get: (m) => m.path_acc_r1, kind: 'ratio', better: 'higher' },
  { key: 'path_r2', title: '路径准确率 · 第 2 轮', get: (m) => m.path_acc_r2, kind: 'ratio', better: 'higher' },
  { key: 'path_gain', title: '第 2 轮较第 1 轮', get: (m) => m.path_acc_gain, kind: 'points', better: 'higher' },
  { key: 'ref_recall', title: '转介召回率', get: (m) => m.referral_recall, kind: 'ratio', better: 'higher' },
  { key: 'ref_precision', title: '转介精确率', get: (m) => m.referral_precision, kind: 'ratio', better: 'higher' },
  { key: 'isi_change', title: '平均 ISI 变化', get: (m) => m.mean_isi_change, kind: 'score', better: 'lower' },
];

/** 每位来访相对第 0 周的 ISI 变化（第 0–4 周），以及各周的平均。周数不齐的来访不画。 */
export function isiTrajectories(report: RunReport): { visitors: { id: string; deltas: number[] }[]; mean: number[] } | null {
  const visitors = report.per_visitor
    .filter((v) => v.isi_week.length === 5 && v.isi_week.every((n) => Number.isFinite(n)))
    .map((v) => ({ id: v.visitor_id, deltas: v.isi_week.map((n) => n - v.isi_week[0]) }));
  if (visitors.length === 0) return null;
  const mean = [0, 1, 2, 3, 4].map((w) => visitors.reduce((sum, v) => sum + v.deltas[w], 0) / visitors.length);
  return { visitors, mean };
}
