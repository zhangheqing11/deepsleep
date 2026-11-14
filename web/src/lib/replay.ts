// 用户端的数据层：把实验里同一位模拟来访的两场会谈（学习前 / 学习后）配成一对。
// 只读现有只读接口，不计算指标，不生成任何教练的话：页面上教练说的每一句都来自会谈记录。
import type { ApiClient } from '../api/client';
import type {
  Evolution,
  EvolutionChange,
  PerVisitorRow,
  Plan,
  RunReport,
  Session,
  ToolCall,
  TranscriptTurn,
} from '../api/contractTypes';
import type { SessionListItem } from '../api/draftTypes';
import type { Experiment, ExperimentRun } from '../api/extensionTypes';

export type Side = 'before' | 'after';

/** 一侧的运行：学习前取对照（同一批来访），对照还没跑完时退到运行 1；学习后取运行 2。 */
export interface RunSide {
  role: 'run1' | 'control' | 'run2';
  runId: string;
  version: string | null;
  report: RunReport | null;
  /** 有会谈记录可读的来访 */
  available: Set<string>;
  /** 会谈以危机流程结束的来访 */
  crisis: Set<string>;
}

export interface VisitorEntry {
  id: string;
  before: PerVisitorRow | null;
  after: PerVisitorRow | null;
  hasBefore: boolean;
  hasAfter: boolean;
  /** 任一侧触发过安全线：放进单独的「安全线示例」，不出现在默认路径上 */
  safety: boolean;
  /** 学习后比学习前多降的 ISI 分数（正数 = 学习后更好）；缺一侧时为 null */
  gain: number | null;
}

export interface Catalog {
  experimentId: string;
  stage: Experiment['stage'];
  before: RunSide | null;
  after: RunSide | null;
  /** 两侧用的是同一版手册（保留上一代，或学习后的版本还没跑） */
  sameVersion: boolean;
  outcome: Evolution['outcome'] | null;
  learned: EvolutionChange[];
  learnedSummary: string | null;
  visitors: VisitorEntry[];
}

export interface CatalogCache {
  reports: Map<string, RunReport>;
  lists: Map<string, SessionListItem[]>;
  evolutions: Map<string, Evolution>;
}

export function createCatalogCache(): CatalogCache {
  return { reports: new Map(), lists: new Map(), evolutions: new Map() };
}

const done = (n: ExperimentRun | null | undefined): n is ExperimentRun & { run_id: string } =>
  !!n && n.state === 'done' && typeof n.run_id === 'string';

async function readSide(
  api: ApiClient,
  cache: CatalogCache,
  role: RunSide['role'],
  node: ExperimentRun & { run_id: string },
  signal: AbortSignal,
): Promise<RunSide> {
  const runId = node.run_id;
  // 已完成运行的报告和会谈清单不会再变，读到一次就留着；读失败不缓存，下一轮再试。
  let report = cache.reports.get(runId) ?? null;
  if (!report) {
    try {
      report = await api.getReport(runId, signal);
      cache.reports.set(runId, report);
    } catch (e) {
      if (signal.aborted) throw e;
    }
  }
  let list = cache.lists.get(runId);
  if (!list) {
    list = (await api.listSessions(runId, signal)).items;
    if (list.every((s) => s.status === 'succeeded' || s.status === 'failed')) cache.lists.set(runId, list);
  }
  const available = new Set(list.filter((s) => s.session_available).map((s) => s.visitor_id));
  const crisis = new Set(list.filter((s) => s.session_status === 'crisis_exit').map((s) => s.visitor_id));
  for (const row of report?.per_visitor ?? []) if (row.crisis_pred !== 'none') crisis.add(row.visitor_id);
  return { role, runId, version: report?.playbook_version ?? node.playbook_version, report, available, crisis };
}

/** 读出「谁和哪两版教练各谈了一次」。实验不存在时返回 null。 */
export async function readCatalog(api: ApiClient, cache: CatalogCache, signal: AbortSignal): Promise<Catalog | null> {
  const exp = await api.getExperiment(signal);
  if (!('experiment_id' in exp)) return null;

  const beforeNode = done(exp.control) ? (['control', exp.control] as const) : done(exp.run1) ? (['run1', exp.run1] as const) : null;
  const [before, after] = await Promise.all([
    beforeNode ? readSide(api, cache, beforeNode[0], beforeNode[1], signal) : null,
    done(exp.run2) ? readSide(api, cache, 'run2', exp.run2, signal) : null,
  ]);

  let evolution: Evolution | null = null;
  const evoId = exp.evolution?.state === 'done' ? exp.evolution.evolution_id : null;
  if (evoId) {
    evolution = cache.evolutions.get(evoId) ?? null;
    if (!evolution) {
      try {
        evolution = await api.getEvolution(evoId, signal);
        cache.evolutions.set(evoId, evolution);
      } catch (e) {
        if (signal.aborted) throw e;
      }
    }
  }
  const chosen = evolution?.outcome === 'committed' ? evolution.candidates.find((c) => c.id === evolution.chosen) : undefined;

  return {
    experimentId: exp.experiment_id,
    stage: exp.stage,
    before,
    after,
    sameVersion: !after || !before || before.version === after.version,
    outcome: evolution?.outcome ?? null,
    learned: chosen?.changes ?? [],
    learnedSummary: chosen?.summary ?? null,
    visitors: pairVisitors(before, after),
  };
}

/** 来访配对：两侧都有的排前面，按学习后多降的分数从大到小；触发安全线的单独标记。 */
export function pairVisitors(before: RunSide | null, after: RunSide | null): VisitorEntry[] {
  const rows = (side: RunSide | null) => new Map((side?.report?.per_visitor ?? []).map((r) => [r.visitor_id, r]));
  const b = rows(before);
  const a = rows(after);
  const ids = new Set<string>([...(before?.available ?? []), ...(after?.available ?? [])]);
  const entries = [...ids].map((id): VisitorEntry => {
    const br = b.get(id) ?? null;
    const ar = a.get(id) ?? null;
    const hasBefore = before?.available.has(id) ?? false;
    const hasAfter = after?.available.has(id) ?? false;
    return {
      id,
      before: br,
      after: ar,
      hasBefore,
      hasAfter,
      safety: (before?.crisis.has(id) ?? false) || (after?.crisis.has(id) ?? false),
      gain: br && ar && hasBefore && hasAfter ? br.isi_change - ar.isi_change : null,
    };
  });
  const rank = (e: VisitorEntry) => (e.gain === null ? -Infinity : e.gain);
  return entries.sort((x, y) => rank(y) - rank(x) || x.id.localeCompare(y.id, 'en', { numeric: true }));
}

/** 首页的一句话：多少位来访在学习后四周评分降得更多 / 一样 / 更少。 */
export function tally(visitors: VisitorEntry[]): { paired: number; better: number; same: number; worse: number } {
  const paired = visitors.filter((v) => v.gain !== null);
  return {
    paired: paired.length,
    better: paired.filter((v) => (v.gain as number) > 0).length,
    same: paired.filter((v) => v.gain === 0).length,
    worse: paired.filter((v) => (v.gain as number) < 0).length,
  };
}

// ---------- 一场会谈 → 逐步回放 ----------

export type Step =
  | { kind: 'round'; round: number }
  | { kind: 'turn'; round: number; turn: TranscriptTurn }
  | { kind: 'tool'; round: number; call: ToolCall }
  | { kind: 'end'; status: Session['status']; error: string | null };

/** 把两轮会谈摊平成按顺序播放的步骤；工具调用按轮次和序号插在对话中间。 */
export function buildSteps(session: Session): Step[] {
  const steps: Step[] = [];
  for (const round of [...session.rounds].sort((x, y) => x.round - y.round)) {
    steps.push({ kind: 'round', round: round.round });
    const items: { order: number; step: Step }[] = [
      ...round.transcript.map((turn) => ({ order: turn.turn, step: { kind: 'turn', round: round.round, turn } as Step })),
      ...session.tool_calls
        .filter((c) => c.round === round.round)
        .map((call) => ({ order: call.turn, step: { kind: 'tool', round: round.round, call } as Step })),
    ];
    items.sort((x, y) => x.order - y.order);
    steps.push(...items.map((i) => i.step));
  }
  steps.push({ kind: 'end', status: session.status, error: session.error });
  return steps;
}

const isVisitorTurn = (s: Step | undefined) => s?.kind === 'turn' && s.turn.speaker === 'visitor';

/**
 * 回放的推进规则：页面上的人替来访「说」下一句，然后教练的回应（连同中间的筛查、安全层插话）一起出现，
 * 停在下一句来访发言之前。返回推进后已显示的步骤数。
 */
export function advance(steps: Step[], shown: number): number {
  let i = shown;
  // 开头不是来访发言（例如第 2 轮由教练先开口）时，先把教练这段放出来
  if (isVisitorTurn(steps[i])) i += 1;
  while (i < steps.length && !isVisitorTurn(steps[i])) i += 1;
  return i;
}

/** 刚进入一场会谈时先显示到第一句来访发言之前（通常只有「第 1 轮」的分隔）。 */
export function initialShown(steps: Step[]): number {
  let i = 0;
  while (i < steps.length && !isVisitorTurn(steps[i]) && steps[i].kind !== 'turn') i += 1;
  return i;
}

/** 下一句等着被「说出来」的来访发言；没有就是 null。 */
export function pendingLine(steps: Step[], shown: number): string | null {
  const s = steps[shown];
  return s?.kind === 'turn' && s.turn.speaker === 'visitor' ? s.turn.text : null;
}

/** 这位来访开口的第一句。 */
export function openingLine(session: Session): string | null {
  for (const round of [...session.rounds].sort((x, y) => x.round - y.round)) {
    const first = round.transcript.find((t) => t.speaker === 'visitor');
    if (first) return first.text;
  }
  return null;
}

// ---------- 两场会谈的对比 ----------

export interface Digest {
  version: string;
  model: string;
  mock: boolean;
  status: Session['status'];
  topics: string[];
  tools: string[];
  pathR1: string | null;
  pathR2: string | null;
  referral: string | null;
  plan: Plan | null;
  safetyActions: string[];
  /** 第 0–4 周 ISI；报告里没有这位来访时为 null */
  isiWeek: number[] | null;
  isiChange: number | null;
  responder: boolean | null;
}

export function digest(session: Session, row: PerVisitorRow | null): Digest {
  const rounds = [...session.rounds].sort((x, y) => x.round - y.round);
  const uniq = <T,>(xs: T[]) => [...new Set(xs)];
  const weeks = row && Array.isArray(row.isi_week) && row.isi_week.length === 5 ? row.isi_week : null;
  return {
    version: session.playbook_version,
    model: session.models.agent,
    mock: /mock/i.test(session.models.agent),
    status: session.status,
    topics: uniq(rounds.flatMap((r) => r.asked_topics)),
    tools: uniq(session.tool_calls.map((c) => c.tool)),
    pathR1: rounds[0]?.path_pred ?? null,
    pathR2: rounds[1]?.path_pred ?? null,
    referral: rounds.length ? rounds[rounds.length - 1].referral_pred : null,
    plan: session.plan,
    safetyActions: uniq(session.safety_events.map((e) => e.action).filter((a) => a !== 'none')),
    isiWeek: weeks,
    isiChange: row ? row.isi_change : null,
    responder: row ? row.responder : null,
  };
}

/** 只在其中一侧出现的条目，用来在对比里标出「学习后多问了什么」。 */
export function onlyIn(mine: string[], other: string[] | null): Set<string> {
  if (!other) return new Set();
  const o = new Set(other);
  return new Set(mine.filter((x) => !o.has(x)));
}

// ---------- 来访的自评与筛查结果 ----------

export interface ScaleResult {
  scale: 'isi' | 'phq9' | 'gad7' | 'stop_bang';
  score: number;
  items: number[] | null;
  /** 会谈前自己填的，还是会谈中教练补做的筛查 */
  source: 'prefilled' | 'screened';
}

export function scaleResults(session: Session): ScaleResult[] {
  const out: ScaleResult[] = session.context_scales.map((s) => ({
    scale: s.scale, score: s.reported_score, items: s.items, source: 'prefilled',
  }));
  for (const call of session.tool_calls) {
    const r = call.result as Record<string, unknown>;
    if (typeof r.phq9 === 'number') {
      out.push({ scale: 'phq9', score: r.phq9, items: Array.isArray(r.phq9_items) ? (r.phq9_items as number[]) : null, source: 'screened' });
    }
    if (typeof r.gad7 === 'number') out.push({ scale: 'gad7', score: r.gad7, items: null, source: 'screened' });
    if (typeof r.stop_bang === 'number') out.push({ scale: 'stop_bang', score: r.stop_bang, items: null, source: 'screened' });
  }
  return out;
}

// ---------- 文案里要用到的称呼 ----------

/** 两侧的称呼：手册版本不同才叫「学习前 / 学习后」；同一版时如实叫对照 / 运行 2。 */
export function sideName(catalog: Catalog, side: Side): string {
  if (side === 'before') {
    if (catalog.before?.role === 'run1') return '运行 1';
    return catalog.sameVersion ? '对照' : '学习前';
  }
  return catalog.sameVersion ? '运行 2' : '学习后';
}

export function sideVersion(catalog: Catalog, side: Side): string | null {
  return (side === 'before' ? catalog.before : catalog.after)?.version ?? null;
}

/** 首页那句话：现在能看到什么。 */
export function headline(catalog: Catalog | null): string {
  if (!catalog || (!catalog.before && !catalog.after)) {
    return '实验还没有跑出会谈。第一次运行结束后，这里会自动出现来访。';
  }
  const { before, after } = catalog;
  if (before && !after) {
    return before.role === 'run1'
      ? `运行 1 已经结束，教练用的是手册 ${before.version ?? ''}。学习后的版本还没有跑，先看它现在怎么谈。`
      : `对照组已经结束，教练用的是手册 ${before.version ?? ''}。运行 2 还没有结束。`;
  }
  if (after && !before) return `运行 2 已经结束，教练用的是手册 ${after.version ?? ''}。对照组还没有结束。`;
  if (before?.role === 'run1') {
    return '运行 1 和运行 2 的来访不是同一批人，这里按各自的会谈展示；对照组结束后才能看到同一位来访的两次回应。';
  }
  if (catalog.sameVersion) {
    return `这一次教练保留了上一代手册：两场会谈用的都是 ${after?.version ?? ''}，差别来自对话本身，不是学习的结果。`;
  }
  return `教练读完第一次运行里没谈好的会谈，把自己的手册从 ${before?.version ?? ''} 改写成了 ${after?.version ?? ''}。同一批来访和两版教练各谈了一次。`;
}
