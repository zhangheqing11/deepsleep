// 进化总览的视图推导（纯函数，可测试）。只做比较、排序和取值，不计算任何新指标；
// 唯一的算术是两个比例相减（百分点），任一为 null 结果就是 null。

import type { EvolveStatus, ExperimentManifest, ManifestRun, RunState, StageState } from '../api/extensionTypes';
import type { CandidateView, ChangeView, EvolutionView, ReportView } from '../api/validate';
import { label, REVIEW_DECISION_LABEL, VETO_CODE_LABEL } from '../lib/labels';

export type RunKey = 'run1' | 'run2' | 'control';

export const ROLE_TITLE: Record<RunKey, string> = { run1: '运行 1', control: '对照', run2: '运行 2' };

/** 两个比例之差，单位百分点，保留一位；任一缺失 → null（页面显示“暂无”）。 */
export function pointDiff(from: number | null | undefined, to: number | null | undefined): number | null {
  if (from === null || from === undefined || to === null || to === undefined) return null;
  if (!Number.isFinite(from) || !Number.isFinite(to)) return null;
  return Math.round((to - from) * 1000) / 10;
}

// ---------- 红线 ----------

export interface RedLine {
  key: 'crisis_missed' | 'contraindication_violations' | 'veto';
  label: string;
  /** null = 报告没给这个值 */
  ok: boolean | null;
  value: string;
}

export function redLines(r: ReportView): RedLine[] {
  const count = (v: number | null) => (v === null ? { ok: null, value: '暂无' } : { ok: v === 0, value: String(v) });
  return [
    { key: 'crisis_missed', label: '危机漏报（必须为 0）', ...count(r.metrics.crisis_missed) },
    { key: 'contraindication_violations', label: '违反禁忌（必须为 0）', ...count(r.metrics.contraindication_violations) },
    { key: 'veto', label: '否决规则', ok: r.veto.passed, value: r.veto.passed ? '通过' : '未通过' },
  ];
}

export function redLineFailed(r: ReportView): boolean {
  return redLines(r).some((l) => l.ok === false);
}

// ---------- 学到了什么 ----------

const CRIT_ORDER = { high: 0, medium: 1, low: 2 } as const;

export function chosenCandidate(e: EvolutionView): CandidateView | null {
  if (e.chosen === null) return null;
  return e.candidates.find((c) => c.id === e.chosen) ?? null;
}

/** 被选候选的改动：按关键度排序，最多展示 limit 条，其余计数。 */
export function chosenChanges(e: EvolutionView, limit = 3): { shown: ChangeView[]; hidden: number } {
  const c = chosenCandidate(e);
  if (!c) return { shown: [], hidden: 0 };
  const sorted = c.changes
    .map((ch, i) => ({ ch, i }))
    .sort((a, b) => CRIT_ORDER[a.ch.criticality] - CRIT_ORDER[b.ch.criticality] || a.i - b.i)
    .map((x) => x.ch);
  return { shown: sorted.slice(0, limit), hidden: Math.max(sorted.length - limit, 0) };
}

/** 候选没被采纳的原因：全部来自数据字段，不重算门禁。 */
export function blockReasons(c: CandidateView, e: EvolutionView): string[] {
  const reasons: string[] = [];
  for (const h of c.hard_rule_violations) reasons.push(`硬规则拦下：${h.message || h.code}`);
  if (!c.validated && c.hard_rule_violations.length === 0) reasons.push('未在验证集上验证');
  if (c.validated && c.val_isi !== null && e.baseline_isi !== null && c.val_isi <= e.baseline_isi) {
    reasons.push(`验证集主指标没有高于上一代（${fmtPct(c.val_isi)}，上一代 ${fmtPct(e.baseline_isi)}）`);
  }
  for (const v of c.veto.reasons) reasons.push(`否决规则：${label(VETO_CODE_LABEL, v.code)}${v.message ? `（${v.message}）` : ''}`);
  const changeIds = new Set(c.changes.map((ch) => ch.id));
  for (const r of e.human_review) {
    if (changeIds.has(r.change_id) && r.decision === 'reject') {
      reasons.push(`人工审核：${label(REVIEW_DECISION_LABEL, r.decision)}${r.comment ? `（${r.comment}）` : ''}`);
    }
  }
  if (reasons.length === 0 && !c.passed) reasons.push('门禁未通过（数据没有给出具体原因）');
  return reasons;
}

function fmtPct(v: number): string {
  return `${Math.round(v * 1000) / 10}%`;
}

// ---------- 当前版本 ----------

export interface VersionInfo {
  /** 当前生效版本；不知道时为 null */
  current: string | null;
  /** 上一代（学习的起点）；不知道时为 null */
  previous: string | null;
  /** 当前版本的来源说明 */
  source: string;
}

export function versionInfo(
  m: ExperimentManifest,
  status: EvolveStatus | null,
  evo: EvolutionView | null,
): VersionInfo {
  if (evo) {
    if (evo.outcome === 'committed') return { current: evo.to_version, previous: evo.from_version, source: '进化记录（已提交）' };
    return { current: evo.from_version, previous: null, source: '进化记录（保留上一代）' };
  }
  if (status && status.phase === 'done' && status.outcome) {
    const prev = status.from_version;
    if (status.outcome === 'committed') return { current: status.to_version, previous: prev, source: '学习状态（已提交）' };
    return { current: prev, previous: null, source: '学习状态（保留上一代）' };
  }
  const v = m.run1.playbook_version ?? status?.from_version ?? null;
  return { current: v, previous: null, source: v ? '实验清单（学习尚未完成）' : '暂无' };
}

// ---------- 时间线 ----------

export interface TimelineNode {
  key: RunKey | 'evolution';
  title: string;
  sub: string;
  state: StageState;
  progress: { completed: number | null; failed: number | null; total: number | null } | null;
}

function runSub(r: ManifestRun): string {
  return `${r.split} 组 · ${r.playbook_version ?? '版本待定'}`;
}

export function timeline(
  m: ExperimentManifest,
  runStates: Partial<Record<RunKey, RunState | null>>,
  status: EvolveStatus | null,
): TimelineNode[] {
  const run = (key: RunKey): TimelineNode => ({
    key,
    title: ROLE_TITLE[key],
    sub: runSub(m[key]),
    state: m[key].state,
    progress: runStates[key]?.progress ?? null,
  });
  const from = status?.from_version ?? m.run1.playbook_version;
  const to = status?.to_version ?? m.run2.playbook_version;
  return [
    run('run1'),
    {
      key: 'evolution',
      title: '学习',
      sub: status?.outcome === 'kept_previous' ? `${from ?? '版本待定'} → 保留上一代` : `${from ?? '版本待定'} → ${to ?? '待定'}`,
      state: m.evolution.state,
      progress: null,
    },
    run('run2'),
    run('control'),
  ];
}

/** 审核窗口剩余秒数（按后端给的截止时间与本机时钟）；无法解析 → null */
export function secondsLeft(deadline: string | null, now: number): number | null {
  if (!deadline) return null;
  const t = Date.parse(deadline);
  if (Number.isNaN(t)) return null;
  return Math.round((t - now) / 1000);
}
