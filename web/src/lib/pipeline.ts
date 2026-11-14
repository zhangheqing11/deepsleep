// 全链路演示页的纯逻辑：时间格式、整体进度、每步会谈数、结论句。只做展示推导，不计算任何指标。
import type {
  PipelineGeneration,
  PipelineLauncher,
  PipelinePreset,
  PipelineResponse,
  PipelineResult,
  PipelineSnapshot,
  PipelineStep,
  PipelineStepState,
} from '../api/extensionTypes';

export const DASH = '—';

/** 秒 → mm:ss（一小时以上 h:mm:ss）；null / 非数 → “—”；负数按 0 */
export function clock(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return DASH;
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${String(m).padStart(2, '0')}:${ss}`;
}

/** 预计时长 → “约 N 分钟”（不足 1 分钟按 1 分钟） */
export function aboutMinutes(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds <= 0) return DASH;
  return `约 ${Math.max(1, Math.round(seconds / 60))} 分钟`;
}

/**
 * 两次轮询之间在本地走表：只有进行中的才走，且总以最近一次服务端的值为起点（每次轮询都会重新对齐）。
 * direction=1 用于已用时间，-1 用于剩余时间（不小于 0）。
 */
export function tick(base: number | null | undefined, receivedAt: number, now: number, running: boolean, direction: 1 | -1 = 1): number | null {
  if (base === null || base === undefined || !Number.isFinite(base)) return null;
  if (!running) return base;
  const drift = Math.max(0, (now - receivedAt) / 1000);
  return Math.max(0, base + direction * drift);
}

/**
 * 整体进度：已用时间占预计总时长的比例。完成为 1；未完成最多 0.99（估计总会有偏差，不在结束前画满）。
 * 预计总时长 = 已用 + 剩余；没有剩余估计时退到各步骤的预计时长之和；都没有时返回 null（不画比例）。
 */
export function overallProgress(
  p: Pick<PipelineSnapshot, 'state' | 'elapsed_s' | 'eta_s'> & { steps?: Pick<PipelineStep, 'expected_s'>[] },
  elapsedOverride?: number | null,
  etaOverride?: number | null,
): number | null {
  if (p.state === 'done') return 1;
  const elapsed = elapsedOverride ?? p.elapsed_s;
  if (elapsed === null || elapsed === undefined || !Number.isFinite(elapsed)) return null;
  const eta = etaOverride !== undefined ? etaOverride : p.eta_s;
  let total: number | null = null;
  if (eta !== null && eta !== undefined && Number.isFinite(eta)) total = elapsed + eta;
  else {
    const sum = (p.steps ?? []).reduce((acc, s) => acc + (s.expected_s ?? 0), 0);
    if (sum > 0) total = sum;
  }
  if (total === null || total <= 0) return null;
  return Math.min(0.99, Math.max(0, elapsed / total));
}

export interface SessionTally {
  /** 正常写出的会谈 */
  completed: number;
  /** 出错的会谈 */
  failed: number;
  /** 该步骤已开始的批次的来访总数；还没有批次时为 null（总数未知，不画比例） */
  total: number | null;
  /** 已处理（完成 + 出错）占比；total 未知时为 null */
  ratio: number | null;
}

/** 把一步里所有批次的会谈数加起来 */
export function stepSessions(step: Pick<PipelineStep, 'batches'>): SessionTally {
  const batches = step.batches ?? [];
  if (batches.length === 0) return { completed: 0, failed: 0, total: null, ratio: null };
  let completed = 0;
  let failed = 0;
  let total = 0;
  for (const b of batches) {
    completed += b.completed ?? 0;
    failed += b.failed ?? 0;
    total += b.total ?? 0;
  }
  return { completed, failed, total, ratio: total > 0 ? Math.min(1, (completed + failed) / total) : null };
}

export function sessionsText(t: SessionTally): string {
  if (t.total === null) return '尚未开始会谈';
  return `已完成 ${t.completed} / ${t.total} 场会谈`;
}

const CN_COUNT = ['零', '一', '两', '三', '四', '五', '六', '七', '八', '九', '十'];

/** 一代学习的结论句；还没结束时为 null。保留上一代是正常结果。 */
export function outcomeSentence(g: Pick<PipelineGeneration, 'outcome' | 'chosen' | 'to_version' | 'from_version' | 'candidates'> | null | undefined): string | null {
  if (!g || !g.outcome) return null;
  if (g.outcome === 'committed') {
    return `采纳候选 ${g.chosen ?? '?'} → ${g.to_version ?? '新版本'}`;
  }
  const n = g.candidates?.length ?? 0;
  const count = n > 0 ? `${CN_COUNT[n] ?? n}份候选` : '候选';
  return `${count}${n > 1 ? '均' : ''}未通过，保留 ${g.from_version}`;
}

export type PipelineDisplayState = 'none' | 'running' | 'done' | 'failed';

export function displayState(data: PipelineResponse | null): PipelineDisplayState {
  if (!data || !data.available) return 'none';
  return data.state;
}

export const PIPELINE_STATE_LABEL: Record<PipelineDisplayState, string> = {
  none: '尚未开始',
  running: '进行中',
  done: '已完成',
  failed: '失败',
};

export const STEP_STATE_LABEL: Record<PipelineStepState, string> = {
  pending: '等待中',
  running: '进行中',
  done: '已完成',
  failed: '失败',
  skipped: '已跳过',
};

export const PHASE_LABEL: Record<string, string> = {
  reflecting: '反思中',
  validating: '门禁验证中',
  committing: '提交新版本',
  done: '已结束',
  failed: '失败',
};

export const CANDIDATE_STATE_LABEL: Record<string, string> = {
  pending: '等待',
  running: '验证中',
  done: '已验证',
};

/** 0–1 比例 → 百分比；缺失显示“—”，不显示成 0 */
export function rate(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return DASH;
  return `${(v * 100).toFixed(digits)}%`;
}

/**
 * 运行 2 相对对照的 ISI 有效率差（百分点）。两份结果都在时由比例直接算（与后端 delta_pp 同义），
 * 否则为 null。
 */
export function deltaPoints(result: PipelineResult | null | undefined): number | null {
  const a = result?.run2?.isi_response_rate;
  const b = result?.control?.isi_response_rate;
  if (a === null || a === undefined || b === null || b === undefined) return null;
  return Math.round((a - b) * 1000) / 10;
}

export function signedPoints(pp: number | null): string {
  if (pp === null || !Number.isFinite(pp)) return DASH;
  const sign = pp > 0 ? '+' : pp < 0 ? '−' : '±';
  return `${sign}${Math.abs(pp).toFixed(1)} 个百分点`;
}

/** 折叠后的一行摘要 */
export function stepSummary(step: PipelineStep): string {
  if (step.state === 'skipped') {
    // 练习只在上一代采纳了新版本时才跑；其余步骤被跳过只可能是前面的步骤没有走完
    return step.kind === 'practice' ? '上一代没有采纳新版本，跳过练习' : '前面的步骤没有走完，未执行';
  }
  if (step.state === 'pending') return step.expected_s ? `等待中 · 预计${aboutMinutes(step.expected_s)}` : '等待中';
  const parts: string[] = [];
  if (step.kind === 'generation') {
    const outcome = outcomeSentence(step.generation);
    if (outcome) parts.push(outcome);
  }
  const t = stepSessions(step);
  if (t.total !== null) parts.push(`${t.completed} / ${t.total} 场会谈${t.failed > 0 ? `（${t.failed} 场出错）` : ''}`);
  if (step.kind !== 'generation') {
    const rates = (step.batches ?? []).filter((b) => b.isi_response_rate !== null);
    if (rates.length > 0) parts.push(rates.map((b) => `${b.label} ISI 有效率 ${rate(b.isi_response_rate)}`).join(' · '));
  }
  if (step.elapsed_s !== null) parts.push(`用时 ${clock(step.elapsed_s)}`);
  return parts.join(' · ');
}

// ---------- 启动预设：续跑一代（next）与从 v1 重新开始（11/15 增补） ----------

/** 会把 playbook 重置为 v1 的预设。旧后端不发 reset 字段，它的预设都会重置。 */
export function isResetPreset(p: Pick<PipelinePreset, 'reset'>): boolean {
  return p.reset !== false;
}

/** 续跑一代（reset=false）排在最前面，其余保持后端给的顺序 */
export function orderPresets<T extends Pick<PipelinePreset, 'reset'>>(presets: readonly T[] | null | undefined): T[] {
  const list = [...(presets ?? [])];
  return [...list.filter((p) => !isResetPreset(p)), ...list.filter((p) => isResetPreset(p))];
}

/** 默认选中：排好序后的第一项（后端提供“再进化一代”时就是它） */
export function defaultPreset<T extends Pick<PipelinePreset, 'reset'>>(presets: readonly T[] | null | undefined): T | null {
  return orderPresets(presets)[0] ?? null;
}

/** 续跑从哪个版本出发：版本库不存在或还在 v1 时是 v1 */
export function continueVersion(launcher: Pick<PipelineLauncher, 'current_version'> | null | undefined): string {
  const v = launcher?.current_version;
  return v ? v : 'v1';
}

/** 续跑预设下面那一行：“从 v2 继续”；还在 v1 时是“从 v1 开始” */
export function continueFromText(launcher: Pick<PipelineLauncher, 'current_version'> | null | undefined): string {
  const v = continueVersion(launcher);
  return v === 'v1' ? '从 v1 开始' : `从 ${v} 继续`;
}

export const RESET_TAG = '从 v1 重新开始';

const MODE_NAME = { mock: '演练', real: '真实' } as const;

/**
 * 续跑时演练与真实不能接在同一条链上：返回禁用提示；不冲突（或重置类预设、或后端没给链的模式）返回 null。
 * 服务端仍会用 409 LINEAGE_MODE_MISMATCH 把关，这里只是提前提示。
 */
export function lineageConflict(
  launcher: Pick<PipelineLauncher, 'lineage_mode'> | null | undefined,
  preset: Pick<PipelinePreset, 'reset'> | null | undefined,
  mock: boolean,
): string | null {
  if (!preset || isResetPreset(preset)) return null;
  const mode = launcher?.lineage_mode;
  if (mode !== 'mock' && mode !== 'real') return null;
  if ((mode === 'mock') === mock) return null;
  return `当前进化链是${MODE_NAME[mode]}数据，演练与真实不能接在同一条链上；请先从 v1 重新开始`;
}

/** 确认框的第一段：续跑说明不重置；重置类预设保留原警告，并说明进化链与曲线从头开始 */
export function launchConfirmText(
  preset: Pick<PipelinePreset, 'label' | 'description' | 'expected_s' | 'reset'>,
  launcher: Pick<PipelineLauncher, 'current_version'> | null | undefined,
): string {
  const what = `${preset.label}（${preset.description}，${aboutMinutes(preset.expected_s)}）`;
  if (!isResetPreset(preset)) {
    const v = continueVersion(launcher);
    return `将从当前版本 ${v} 继续，不重置 playbook，开始一次新的实验：${what}。这一代在 B 组的成绩会接在逐代曲线后面。页面会改为显示新实验。`;
  }
  return `将把 playbook 重置为 v1，并开始一次新的实验：${what}。这会开始一条新的进化链，逐代曲线从头开始。页面会改为显示新实验。`;
}

/** 默认展开：进行中和失败的步骤展开，其余折叠 */
export function defaultOpen(step: Pick<PipelineStep, 'state'>): boolean {
  return step.state === 'running' || step.state === 'failed';
}
