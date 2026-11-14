// 逐代曲线的纯逻辑：纵轴范围、增量格式、现场曲线（GET /demo/pipeline 的 curve）与离线复测文件的整理。
// 只整理和格式化后端 / 测量文件给出的数，不计算任何新指标（单次运行的平均、差值、区间都来自数据本身）。
import type { PipelineCurve, PipelineCurvePoint, PipelineCurveRejected } from '../api/extensionTypes';

export const DASH = '—';

export const CURVE_CAPTION =
  '留出集 B 组从不参与学习和门禁；每个点是该版本在 B 组各次运行的平均，小圆点是单次运行。ISI 为规则状态模型的四周模拟值。';
export const CURVE_EMPTY = '这条进化链还没有在 B 组上的成绩；跑完一轮后这里会出现第一个点。';
export const INITIAL_LEARNED = '团队手写的初始版本';

const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

// ---------- 格式 ----------

/** 0–1 比例 → “63.7%”；缺失为“—” */
export function pctText(v: number | null | undefined, digits = 1): string {
  return finite(v) ? `${(v * 100).toFixed(digits)}%` : DASH;
}

/** 百分点增量 → “+10.0” / “−0.7” / “±0.0”（一位小数，正负照实写）；缺失为空串 */
export function formatIncrement(pp: number | null | undefined): string {
  if (!finite(pp)) return '';
  const r = Math.round(pp * 10) / 10;
  const sign = r > 0 ? '+' : r < 0 ? '−' : '±';
  return `${sign}${Math.abs(r).toFixed(1)}`;
}

export type IncrementTone = 'up' | 'down' | 'flat';
export function incrementTone(pp: number | null | undefined): IncrementTone {
  if (!finite(pp)) return 'flat';
  const r = Math.round(pp * 10) / 10;
  return r > 0 ? 'up' : r < 0 ? 'down' : 'flat';
}

export function versionNumber(v: string): number {
  const n = Number(String(v).replace(/^v/i, ''));
  return Number.isFinite(n) ? n : Number.MAX_SAFE_INTEGER;
}

// ---------- 纵轴 ----------

export interface AxisRange {
  /** 百分比（0–100） */
  min: number;
  max: number;
  ticks: number[];
}

const STEPS = [1, 2, 5, 10, 20, 25];

/**
 * 纵轴范围（单位：百分比 0–100）：在数据两侧各留出至少 3 个百分点（或跨度的 15%），
 * 取 1/2/5/10/20/25 中让刻度不超过 5 段的最小步长，对齐到步长并夹在 0–100 内。没有数据时给 40–80。
 */
export function axisRange(valuesPct: number[]): AxisRange {
  const vs = valuesPct.filter(finite);
  if (vs.length === 0) return { min: 40, max: 80, ticks: [40, 50, 60, 70, 80] };
  const lo0 = Math.min(...vs);
  const hi0 = Math.max(...vs);
  const pad = Math.max(3, (hi0 - lo0) * 0.15);
  const lo = lo0 - pad;
  const hi = hi0 + pad;
  const step = STEPS.find((s) => (hi - lo) / s <= 5) ?? 25;
  let min = Math.max(0, Math.floor(lo / step) * step);
  let max = Math.min(100, Math.ceil(hi / step) * step);
  if (max - min < step) {
    if (min === 0) max = step;
    else min = max - step;
  }
  const ticks: number[] = [];
  for (let t = min; t <= max + 1e-9; t += step) ticks.push(Math.round(t * 1000) / 1000);
  return { min, max, ticks };
}

// ---------- 图表的统一输入 ----------

export interface CurvePoint {
  version: string;
  /** 0–1；缺失为 null（不画点） */
  mean: number | null;
  /** 与上一个点之差（百分点）；第一个点为 null */
  deltaPp: number | null;
}

export interface RunDot {
  key: string;
  /** 第几个版本（横轴下标） */
  index: number;
  /** 0–1 */
  value: number;
}

export interface ThinLine {
  key: string;
  label: string;
  values: (number | null)[];
}

export interface ChartModel {
  versions: string[];
  points: CurvePoint[];
  dots: RunDot[];
  thin: ThinLine[];
  ceiling: { value: number; label: string } | null;
  axis: AxisRange;
}

function chartAxis(points: CurvePoint[], dots: RunDot[], thin: ThinLine[], ceiling: number | null): AxisRange {
  const all = [
    ...points.map((p) => p.mean),
    ...dots.map((d) => d.value),
    ...thin.flatMap((t) => t.values),
    ceiling,
  ].filter(finite);
  return axisRange(all.map((v) => v * 100));
}

// ---------- 现场：GET /demo/pipeline 的 curve ----------

export interface VersionRow {
  version: string;
  meanText: string;
  deltaText: string;
  deltaTone: IncrementTone;
  runsText: string;
  /** 转介召回 / 精确率都缺失时为 null */
  referralText: string | null;
  learned: string;
}

export interface LiveCurveModel extends ChartModel {
  rows: VersionRow[];
  rejected: string[];
  empty: boolean;
  mode: 'real' | 'mock' | null;
  experiments: number | null;
}

/** 未采纳新版本的一代：正常结果，平铺直叙 */
export function rejectedText(r: Pick<PipelineCurveRejected, 'from_version'>): string {
  return `从 ${r.from_version} 出发的一代：三份候选均未通过门禁，保留 ${r.from_version}`;
}

function learnedText(p: PipelineCurvePoint, first: boolean): string {
  const s = typeof p.learned === 'string' ? p.learned.trim() : '';
  if (s) return s;
  if (p.version === 'v1' || first) return INITIAL_LEARNED;
  return DASH;
}

function referralText(p: PipelineCurvePoint): string | null {
  const r = p.referral_recall;
  const q = p.referral_precision;
  if (!finite(r) && !finite(q)) return null;
  return `转介召回 ${pctText(r)} / 精确率 ${pctText(q)}`;
}

/**
 * 把后端的 curve 整理成图表与列表要用的样子。curve 缺失（旧后端、读取失败）或没有点时 empty=true。
 * delta_pp 优先用后端给的；后端没给（且不是第一个点）时由相邻两个 mean 相减。
 */
export function liveCurveModel(curve: PipelineCurve | null | undefined): LiveCurveModel {
  const raw = Array.isArray(curve?.points) ? [...curve!.points] : [];
  raw.sort((a, b) => versionNumber(a.version) - versionNumber(b.version));
  const points: CurvePoint[] = raw.map((p, i) => {
    const mean = finite(p.mean) ? p.mean : null;
    let deltaPp: number | null = finite(p.delta_pp) ? p.delta_pp : null;
    if (deltaPp === null && i > 0) {
      const prev = raw[i - 1].mean;
      if (finite(prev) && mean !== null) deltaPp = Math.round((mean - prev) * 1000) / 10;
    }
    return { version: p.version, mean, deltaPp };
  });
  const dots: RunDot[] = raw.flatMap((p, i) =>
    (Array.isArray(p.runs) ? p.runs : [])
      .filter((r) => finite(r?.isi_response_rate))
      .map((r, j) => ({ key: r.run_id ?? `${p.version}-${j}`, index: i, value: r.isi_response_rate as number })),
  );
  const rows: VersionRow[] = raw.map((p, i) => ({
    version: p.version,
    meanText: pctText(p.mean),
    deltaText: formatIncrement(points[i].deltaPp),
    deltaTone: incrementTone(points[i].deltaPp),
    runsText: `${finite(p.n_runs) ? p.n_runs : (p.runs ?? []).length} 次运行`,
    referralText: referralText(p),
    learned: learnedText(p, i === 0),
  }));
  const rejected = (Array.isArray(curve?.rejected) ? curve!.rejected : []).map(rejectedText);
  return {
    versions: points.map((p) => p.version),
    points,
    dots,
    thin: [],
    ceiling: null,
    axis: chartAxis(points, dots, [], null),
    rows,
    rejected,
    empty: points.length === 0,
    mode: curve?.mode ?? null,
    experiments: finite(curve?.experiments) ? curve!.experiments : null,
  };
}

// ---------- 离线复测：src/data/offlineGenerationCurve.json ----------

export interface OfflineChainPoint {
  version: string;
  mean: number;
  runs: number[];
  delta_pp: number | null;
  delta_ci: [number, number] | number[] | null;
}

export interface OfflineCurveFile {
  measured_at: string;
  cohort: string;
  n_visitors: number;
  replicates_per_version: number;
  reflector: string;
  ceiling: number | null;
  chains: { id: string; points: OfflineChainPoint[]; total_delta_pp: number | null; total_delta_ci: number[] | null }[];
  average: { version: string; mean: number; delta_pp: number | null }[];
}

export interface OfflineCurveModel extends ChartModel {
  title: string;
  subline: string;
  sentence: string;
}

export const OFFLINE_TITLE = '离线复测：两条独立进化链在留出集上的逐代成绩';

function ciText(ci: number[] | null | undefined): string {
  if (!ci || ci.length !== 2 || !ci.every(finite)) return '';
  return `［${formatIncrement(ci[0])}, ${formatIncrement(ci[1])}］`;
}

const CN_NUM = ['零', '一', '两', '三', '四', '五', '六', '七', '八', '九', '十'];

/**
 * 页面上那一句话：每条链的累计增量与区间照抄文件；后两句只在数据确实如此时才写——
 * “大多无法与 0 区分”要求过半的单步区间跨过 0；“先陡后缓，没有加速”要求平均曲线的第一步是最大的一步。
 */
export function offlineSentence(file: OfflineCurveFile): string {
  const avg = file.average;
  const first = avg[0]?.version ?? 'v1';
  const last = avg[avg.length - 1]?.version ?? first;
  const totals = file.chains.map((c) => `${formatIncrement(c.total_delta_pp)}${ciText(c.total_delta_ci)}`).join('与 ');
  const n = file.chains.length;
  const parts = [`${n === 1 ? '这条链' : `${CN_NUM[n] ?? n}条链`} ${first} → ${last} 累计 ${totals}个百分点（95% 区间）`];

  const steps = file.chains.flatMap((c) => c.points.map((p) => p.delta_ci).filter((ci): ci is number[] => Array.isArray(ci) && ci.length === 2));
  const spanZero = steps.filter(([lo, hi]) => lo <= 0 && hi >= 0).length;
  if (steps.length > 0 && spanZero * 2 > steps.length) parts.push('单步变化大多在区间内无法与 0 区分');

  const deltas = avg.map((p) => p.delta_pp).filter(finite);
  if (deltas.length >= 2 && deltas.every((d) => d <= deltas[0]) && deltas[0] > 0) parts.push('增量先陡后缓，没有加速');
  return `${parts.join('；')}。`;
}

export function offlineCurveModel(file: OfflineCurveFile): OfflineCurveModel {
  const versions = file.average.map((p) => p.version);
  const index = new Map(versions.map((v, i) => [v, i]));
  const points: CurvePoint[] = file.average.map((p) => ({ version: p.version, mean: finite(p.mean) ? p.mean : null, deltaPp: finite(p.delta_pp) ? p.delta_pp : null }));
  const thin: ThinLine[] = file.chains.map((c) => ({
    key: c.id,
    label: c.id,
    values: versions.map((v) => {
      const pt = c.points.find((p) => p.version === v);
      return pt && finite(pt.mean) ? pt.mean : null;
    }),
  }));
  // 单次运行：两条链共用同一个起点版本时，同一组测量只画一次
  const seen = new Set<string>();
  const dots: RunDot[] = [];
  for (const c of file.chains) {
    for (const p of c.points) {
      const i = index.get(p.version);
      if (i === undefined) continue;
      const sig = `${p.version}:${p.runs.join(',')}`;
      if (seen.has(sig)) continue;
      seen.add(sig);
      p.runs.filter(finite).forEach((value, j) => dots.push({ key: `${c.id}-${p.version}-${j}`, index: i, value }));
    }
  }
  const ceiling = finite(file.ceiling)
    ? { value: file.ceiling, label: `结构性上限 ${pctText(file.ceiling)}（其余来访在任何手册下都无法有效）` }
    : null;
  const subline = [
    `${file.measured_at} 实测`,
    `留出集 ${file.cohort} 组 ${file.n_visitors} 位来访`,
    `每个版本 ${file.replicates_per_version} 次`,
    `反思器 ${file.reflector}`,
  ].join(' · ');
  return {
    versions,
    points,
    dots,
    thin,
    ceiling,
    axis: chartAxis(points, dots, thin, ceiling?.value ?? null),
    title: OFFLINE_TITLE,
    subline,
    sentence: offlineSentence(file),
  };
}
