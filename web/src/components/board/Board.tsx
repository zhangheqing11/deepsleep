// 进化看板的纯展示组件：只吃一份 BoardData，不发请求，便于对着固定数据测试。
import { useEffect, useState, type ReactNode } from 'react';
import type { Evolution, EvolutionChange, RunReport } from '../../api/contractTypes';
import type { EvolutionStatus } from '../../api/extensionTypes';
import {
  ROLE_LABEL,
  SECONDARY_METRICS,
  VERDICT_LABEL,
  alertSlots,
  candidateVerdict,
  finding,
  isiTrajectories,
  metricDifference,
  pairVisitors,
  responders,
  type BoardData,
  type MetricRow,
  type PairedUnit,
  type RunSlot,
  type UnitGroup,
} from '../../lib/board';
import { pct, pointDelta, seconds, signed } from '../../lib/format';
import { DuoChart, GateChart, LineChart, type DuoRow, type LineSeries } from './charts';
import { CHANGE_OP_LABEL, FAILURE_TAG_LABEL, SECTION_LABEL, STEP_STATE_LABEL, VETO_CODE_LABEL, label } from '../../lib/labels';

const NOT_YET = '尚未生成';

// ---------- 小部件 ----------

function Pill({ tone, children }: { tone: 'positive' | 'negative' | 'warning' | 'neutral'; children: ReactNode }) {
  return <span className={`bd-pill bd-pill-${tone}`}>{children}</span>;
}

function Panel({ title, aside, className = '', children }: { title: string; aside?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <section className={`bd-panel ${className}`}>
      <header className="bd-panel-head">
        <h2>{title}</h2>
        {aside && <div className="bd-panel-aside">{aside}</div>}
      </header>
      {children}
    </section>
  );
}

function progressText(slot: RunSlot): string {
  const p = slot.status?.progress;
  if (!p) return '进行中';
  return p.total == null ? `已处理 ${p.completed} 位来访 · 总人数未知` : `已处理 ${p.completed} / ${p.total} 位来访`;
}

function ProgressBar({ slot }: { slot: RunSlot }) {
  const p = slot.status?.progress;
  // 总人数未知时不画比例条：没有分母就没有真实的比例。
  if (!p || p.total == null || p.total <= 0) return null;
  const ratio = Math.min(1, p.completed / p.total);
  return (
    <span className="bd-progress" aria-hidden="true">
      <span style={{ width: `${ratio * 100}%` }} />
    </span>
  );
}

function slotMeta(slot: RunSlot): string {
  const version = slot.report?.playbook_version ?? slot.node?.playbook_version;
  const split = slot.report?.split ?? slot.node?.split;
  return [version, split ? `${split} 组` : null].filter(Boolean).join(' · ');
}

// ---------- 阶段轨道 ----------

type StepTone = 'pending' | 'running' | 'done' | 'failed';

function StageCell({ name, meta, tone, children }: { name: string; meta: string; tone: StepTone; children: ReactNode }) {
  return (
    <li className={`bd-stage bd-stage-${tone}`} aria-current={tone === 'running' ? 'step' : undefined}>
      <div className="bd-stage-name">
        <strong>{name}</strong>
        {meta && <span>{meta}</span>}
      </div>
      <div className="bd-stage-state">{children}</div>
    </li>
  );
}

function RunStage({ slot }: { slot: RunSlot }) {
  const tone: StepTone = slot.node?.state ?? 'pending';
  let body: ReactNode = '等待中';
  if (tone === 'failed') body = '执行失败';
  else if (tone === 'running') body = <>{progressText(slot)}<ProgressBar slot={slot} /></>;
  else if (tone === 'done') {
    body = slot.report
      ? `已完成 · ${slot.report.n_visitors} 位来访 · 用时 ${seconds(slot.report.duration_s)}`
      : slot.error ? '已完成 · 报告读取失败，正在重试' : '已完成 · 正在读取报告';
  }
  return <StageCell name={ROLE_LABEL[slot.role]} meta={slotMeta(slot)} tone={tone}>{body}</StageCell>;
}

function LearnStage({ data }: { data: BoardData }) {
  const node = data.experiment?.evolution ?? null;
  const evo = data.evolution;
  const status = data.evolutionStatus;
  const tone: StepTone = node?.state ?? 'pending';
  let meta = '';
  let body: ReactNode = '等待中';
  if (evo) {
    meta = evo.outcome === 'committed' ? `${evo.from_version} → ${evo.to_version}` : `保留 ${evo.from_version}`;
    body = evo.outcome === 'committed' ? '已完成 · 生成新版本' : '已完成 · 保留上一代';
  } else if (tone === 'failed' || status?.phase === 'failed') {
    body = '执行失败';
  } else if (status) {
    meta = `从 ${status.from_version} 出发`;
    body = `进行中 · ${label(STEP_STATE_LABEL, status.phase)}`;
  } else if (tone === 'running') {
    body = '进行中';
  } else if (tone === 'done') {
    body = '已完成 · 正在读取记录';
  }
  return <StageCell name="学习" meta={meta} tone={status?.phase === 'failed' ? 'failed' : tone}>{body}</StageCell>;
}

function StageTrack({ data }: { data: BoardData }) {
  return (
    <ol className="bd-track" aria-label="实验阶段">
      <RunStage slot={data.run1} />
      <LearnStage data={data} />
      <RunStage slot={data.run2} />
      <RunStage slot={data.control} />
    </ol>
  );
}

// ---------- 主指标 ----------

function RateFigure({ slot, role }: { slot: RunSlot; role: 'lead' | 'baseline' | 'context' }) {
  const report = slot.report;
  const state = slot.node?.state ?? 'pending';
  return (
    <div className={`bd-figure bd-figure-${role}`}>
      <div className="bd-figure-label">
        <strong>{ROLE_LABEL[slot.role]}</strong>
        {slotMeta(slot) && <span>{slotMeta(slot)}</span>}
      </div>
      {report ? (
        <>
          <div className="bd-figure-value">
            {pct(report.metrics.isi_response_rate).replace('%', '')}
            <span className="bd-unit">%</span>
          </div>
          <div className="bd-figure-note">
            {role === 'context' ? '另一批来访，只作背景' : `${report.n_visitors} 位来访中 ${responders(report)} 位有效`}
          </div>
        </>
      ) : (
        <>
          <div className="bd-figure-empty">
            {state === 'running' ? '进行中' : state === 'failed' ? '执行失败' : state === 'done' ? '正在读取报告' : NOT_YET}
          </div>
          <div className="bd-figure-note">
            {state === 'running' ? <>{progressText(slot)}<ProgressBar slot={slot} /></> : state === 'done' && slot.error ? '报告读取失败，正在重试' : ' '}
          </div>
        </>
      )}
    </div>
  );
}

const GROUP_TEXT: Record<UnitGroup, string> = {
  both: '两版都有效',
  gained: '新版新增有效',
  lost: '新版不再有效',
  neither: '两版都未达有效',
};

function unitTitle(u: PairedUnit, c: RunReport, r: RunReport): string {
  return `${u.visitor_id}：${c.playbook_version} ISI ${signed(u.control.isi_change)} 分，${r.playbook_version} ISI ${signed(u.run2.isi_change)} 分`;
}

/** 来访点阵：同一位来访在上下两行占同一列，实心表示 4 周后 ISI 下降超过 7 分。 */
function PairChart({ control, run2 }: { control: RunSlot; run2: RunSlot }) {
  const c = control.report;
  const r = run2.report;
  const pairing = pairVisitors(c, r);
  if (!c || !r) {
    return <p className="bd-chart-empty">对照与运行 2 都完成后，这里按来访逐个对比两版 playbook 的结果。</p>;
  }
  if (!pairing) {
    return <p className="bd-chart-empty">两次运行的来访不是同一批，不能逐个配对，只比较上面的占比。</p>;
  }
  const n = pairing.units.length;
  const style = { ['--n' as string]: n };
  return (
    <div className="bd-pairs">
      <div className="bd-pair-row">
        <span className="bd-pair-label">对照 {c.playbook_version}</span>
        <span className="bd-dots" style={style} role="img" aria-label={`对照：${n} 位来访中 ${responders(c)} 位有效`}>
          {pairing.units.map((u) => (
            <i key={u.visitor_id} className={u.control.responder ? 'on base' : 'off'} title={unitTitle(u, c, r)} />
          ))}
        </span>
      </div>
      <div className="bd-pair-row">
        <span className="bd-pair-label">运行 2 {r.playbook_version}</span>
        <span className="bd-dots" style={style} role="img" aria-label={`运行 2：${n} 位来访中 ${responders(r)} 位有效`}>
          {pairing.units.map((u) => (
            <i key={u.visitor_id} className={u.run2.responder ? 'on lead' : 'off'} title={unitTitle(u, c, r)} />
          ))}
        </span>
      </div>
      <ul className="bd-pair-legend">
        <li><i className="on lead" />实心：4 周后 ISI 下降超过 7 分</li>
        {(['gained', 'both', 'lost', 'neither'] as const).map((g) => (
          <li key={g} className={pairing.counts[g] === 0 ? 'zero' : ''}>
            {GROUP_TEXT[g]} <b>{pairing.counts[g]}</b> 位
          </li>
        ))}
      </ul>
    </div>
  );
}

function LeadPanel({ data }: { data: BoardData }) {
  const c = data.control.report;
  const r = data.run2.report;
  const delta = c && r ? r.metrics.isi_response_rate - c.metrics.isi_response_rate : null;
  const sameVersion = c && r && c.playbook_version === r.playbook_version;
  return (
    <Panel className="bd-lead" title="4 周模拟 ISI 有效率" aside="ISI 下降超过 7 分的来访占比，由冻结的规则模型计算">
      <div className="bd-figures">
        <RateFigure slot={data.control} role="baseline" />
        <RateFigure slot={data.run2} role="lead" />
        <div className="bd-delta">
          {delta === null ? null : (
            <>
              <strong className={delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat'}>{pointDelta(delta)}</strong>
              <span>运行 2 减对照{sameVersion ? '，两次使用同一版本' : '，同一批来访'}</span>
            </>
          )}
        </div>
        <RateFigure slot={data.run1} role="context" />
      </div>
      <PairChart control={data.control} run2={data.run2} />
    </Panel>
  );
}

// ---------- 副指标 ----------

function formatMetric(row: MetricRow, v: number | null): string {
  if (v === null) return '—';
  if (row.kind === 'ratio') return pct(v);
  if (row.kind === 'points') return pointDelta(v).replace(' 个百分点', '');
  return `${signed(v)} 分`;
}

function formatDiff(row: MetricRow, d: number | null): { text: string; tone: 'up' | 'down' | 'flat' } {
  if (d === null) return { text: '—', tone: 'flat' };
  const text = row.kind === 'score' ? `${signed(d) || '0'} 分` : pointDelta(d).replace(' 个百分点', '');
  if (Math.abs(d) < 1e-9) return { text, tone: 'flat' };
  const good = row.better === 'higher' ? d > 0 : d < 0;
  return { text, tone: good ? 'up' : 'down' };
}

/** 把指标值换成轨道上的位置：越靠右越好。 */
function scaleFor(row: MetricRow, values: (number | null)[]): { pos: (v: number | null) => number | null; zero?: number } {
  if (row.kind === 'ratio') return { pos: (v) => v };
  if (row.kind === 'points') return { pos: (v) => (v === null ? null : 0.5 + v), zero: 0.5 };
  // ISI 变化：下降越多越好。量程取到 4 的整数倍，至少 12 分。
  const lowest = Math.min(-12, ...values.filter((v): v is number => v !== null));
  const span = Math.ceil(-lowest / 4) * 4;
  return { pos: (v) => (v === null ? null : -v / span) };
}

function SecondaryPanel({ data }: { data: BoardData }) {
  const cols = [data.run1, data.control, data.run2];
  const rows: DuoRow[] = SECONDARY_METRICS.map((row) => {
    const [context, base, lead] = cols.map((s) => (s.report ? row.get(s.report.metrics) : null));
    const diff = formatDiff(row, metricDifference(lead, base));
    const scale = scaleFor(row, [context, base, lead]);
    return {
      key: row.key, title: row.title,
      base: scale.pos(base), lead: scale.pos(lead), context: scale.pos(context), zero: scale.zero,
      baseText: formatMetric(row, base), leadText: formatMetric(row, lead),
      diffText: diff.text, diffTone: diff.tone,
      ariaLabel: `${row.title}：对照 ${formatMetric(row, base)}，运行 2 ${formatMetric(row, lead)}，运行 1 ${formatMetric(row, context)}`,
    };
  });
  return (
    <Panel className="bd-secondary" title="副指标" aside="越靠右越好">
      <DuoChart rows={rows} head={['对照', '运行 2', '差值']} />
      <ul className="bd-duo-legend">
        <li><i className="dot base" />对照</li>
        <li><i className="dot lead" />运行 2</li>
        <li><i className="tick" />运行 1，另一批来访</li>
      </ul>
      <p className="bd-footnote">差值为运行 2 减对照，比例差的单位是百分点。“—” 表示尚未生成或无法计算。</p>
    </Panel>
  );
}

// ---------- 安全线 ----------

function SafetyPanel({ data }: { data: BoardData }) {
  const slots = [data.run1, data.control, data.run2];
  const reports = slots.filter((s) => s.report);
  const alerts = alertSlots(data);
  const missed = reports.reduce((sum, s) => sum + s.report!.metrics.crisis_missed, 0);
  return (
    <Panel
      className={`bd-safety ${alerts.length > 0 ? 'bd-safety-alert' : ''}`}
      title="安全线"
      aside={reports.length === 0 ? undefined : alerts.length > 0 ? <Pill tone="negative">未守住</Pill> : <Pill tone="positive">全部守住</Pill>}
    >
      <div className="bd-safety-figure">
        {reports.length === 0 ? (
          <span className="bd-figure-empty">{NOT_YET}</span>
        ) : (
          <>
            <span className="bd-safety-value">{missed}</span>
            <span className="bd-unit">例危机漏报</span>
          </>
        )}
      </div>
      <ul className="bd-safety-rows">
        {slots.map((s) => (
          <li key={s.role}>
            <span>{ROLE_LABEL[s.role]}</span>
            {s.report ? (
              <span className={s.report.veto.passed && s.report.metrics.crisis_missed === 0 ? '' : 'down'}>
                漏报 {s.report.metrics.crisis_missed} 例 · 否决规则{s.report.veto.passed ? '通过' : '未通过'}
              </span>
            ) : (
              <span className="none">{NOT_YET}</span>
            )}
          </li>
        ))}
      </ul>
      {reports.length > 0 && (
        <p className="bd-safety-activity">
          安全层做了 <b>{reports.reduce((n, s) => n + s.report!.safety_summary.safety_checks, 0)}</b> 次安全确认，启动 <b>{reports.reduce((n, s) => n + s.report!.safety_summary.crisis_protocols, 0)}</b> 次危机流程。
        </p>
      )}
      {alerts.flatMap((s) => s.report!.veto.reasons.map((reason, i) => (
        <p key={`${s.role}-${i}`} className="bd-safety-reason">
          {ROLE_LABEL[s.role]}：{label(VETO_CODE_LABEL, reason.code)}。{reason.message}
        </p>
      )))}
      <p className="bd-footnote">危机识别是固定规则层，不参与进化。任何一次漏报都会否决新版本。</p>
    </Panel>
  );
}

// ---------- 学到了什么 ----------

function Countdown({ deadline }: { deadline: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [deadline]);
  const end = deadline ? Date.parse(deadline) : NaN;
  if (!Number.isFinite(end)) return <>审核截止时间未知</>;
  const remaining = Math.max(0, Math.ceil((end - now) / 1000));
  return <>{remaining > 0 ? `距人工审核截止还有 ${remaining} 秒` : '审核窗口已到期，等待后端确认'}</>;
}

function LearningProgress({ status }: { status: EvolutionStatus }) {
  const rank = { reflecting: 0, validating: 1, committing: 3, done: 4, failed: -1 }[status.phase];
  const reviewing = status.review.state === 'waiting';
  const steps: { name: string; state: 'done' | 'running' | 'pending'; note: ReactNode }[] = [
    {
      name: '反思：读失败会谈，提出改动',
      state: status.reflector.state === 'done' ? 'done' : 'running',
      note: status.reflector.model ?? '模型未知',
    },
    {
      name: '门禁：候选在验证集上跑分',
      state: rank > 1 ? 'done' : rank === 1 && !reviewing ? 'running' : rank === 1 ? 'done' : 'pending',
      note: (['c1', 'c2', 'c3'] as const)
        .map((id) => `${id} ${label(STEP_STATE_LABEL, status.validation.candidates[id] ?? 'pending')}`)
        .join(' · '),
    },
    {
      name: '人工审核：只能否决，不能放行',
      state: status.review.state === 'done' || (status.review.state === 'not_needed' && rank > 1) ? 'done' : reviewing ? 'running' : 'pending',
      note: reviewing
        ? <><Countdown deadline={status.review.deadline} /> · 待审 {status.review.pending_changes} 条</>
        : label(STEP_STATE_LABEL, status.review.state),
    },
    { name: '提交：写入版本库', state: rank >= 4 ? 'done' : rank === 3 ? 'running' : 'pending', note: rank === 3 ? '进行中' : rank >= 4 ? '已完成' : '等待中' },
  ];
  return (
    <>
      {status.phase === 'failed' && <p className="bd-safety-reason">学习执行失败：{status.error ?? '后端没有给出原因'}</p>}
      {status.reflector.fell_back && <p className="bd-note-warning">反思器自动降级为 {status.reflector.model ?? '备用模型'}，由代码预先设定，没有人工干预。</p>}
      <ol className="bd-steps">
        {steps.map((s) => (
          <li key={s.name} className={`bd-step-${s.state}`}>
            <strong>{s.name}</strong>
            <span>{s.note}</span>
          </li>
        ))}
      </ol>
    </>
  );
}

function ChangeItem({ change }: { change: EvolutionChange }) {
  return (
    <li>
      <div className="bd-change-tag">
        {label(CHANGE_OP_LABEL, change.op)} · {label(SECTION_LABEL, change.section)}
      </div>
      {change.op !== 'add' && change.before && <p className="bd-change-before">{change.before}</p>}
      {change.after && <p className="bd-change-after">{change.after}</p>}
      <p className="bd-change-reason">依据：{change.reason}</p>
    </li>
  );
}

function CandidateLine({ evo }: { evo: Evolution }) {
  const baseline = evo.baseline_val_metrics.isi_response_rate;
  return (
    <GateChart
      baseline={baseline}
      baselineLabel={<>竖线是上一代 {evo.from_version} 的 <b>{pct(baseline)}</b>：超过它且不触发否决，才算过门禁。</>}
      rows={evo.candidates.map((c) => {
        const verdict = candidateVerdict(c, evo);
        const value = c.val_metrics ? c.val_metrics.isi_response_rate : null;
        return { key: c.id, name: `候选 ${c.id}`, value, valueText: value === null ? '未验证' : pct(value), verdict: VERDICT_LABEL[verdict], chosen: verdict === 'chosen' };
      })}
    />
  );
}

/** 反思器读到的失败：按失败类型计数，说明改动是从哪里来的。 */
function failureSummary(evo: Evolution): string {
  const counts = new Map<string, number>();
  for (const f of evo.failures_used) for (const tag of f.failure_tags) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  const rows = [...counts.entries()].sort((x, y) => y[1] - x[1]).slice(0, 2);
  const detail = rows.map(([tag, n]) => `${label(FAILURE_TAG_LABEL, tag)} ${n}`).join('、');
  return `读了运行 1 的 ${evo.failures_used.length} 个失败会谈${detail ? `（${detail}）` : ''}`;
}

function LearnedPanel({ data }: { data: BoardData }) {
  const evo = data.evolution;
  const status = data.evolutionStatus;
  if (!evo) {
    return (
      <Panel className="bd-learned" title="学到了什么">
        {status ? (
          <LearningProgress status={status} />
        ) : (
          <p className="bd-chart-empty">
            运行 1 结束后，系统读自己没做好的会谈，提出最多 3 份对 playbook 的增量改动，在验证集上过门禁后才生效。
          </p>
        )}
      </Panel>
    );
  }
  const chosen = evo.candidates.find((c) => c.id === evo.chosen) ?? null;
  const committed = evo.outcome === 'committed';
  const usedFeedback = evo.human_feedback.filter((f) => f.status === 'approved' || f.status === 'edited').length;
  return (
    <Panel
      className="bd-learned"
      title="学到了什么"
      aside={committed ? `${evo.from_version} → ${evo.to_version}` : `保留 ${evo.from_version}`}
    >
      {committed && chosen ? (
        <>
          <p className="bd-learned-lead">系统自己给 playbook 写了 {chosen.changes.length} 条改动，其余全部冻结。</p>
          <ul className="bd-changes">
            {chosen.changes.map((ch) => <ChangeItem key={ch.id} change={ch} />)}
          </ul>
        </>
      ) : (
        <>
          <p className="bd-learned-lead">本次学习保留上一代 playbook。</p>
          <p className="bd-learned-text">
            {evo.candidates.length} 份候选都没有通过门禁，所以 {evo.from_version} 继续使用。这是门禁在正常工作，不是系统故障：不够好的改动不会生效。
          </p>
          <ul className="bd-changes bd-changes-rejected">
            {evo.candidates.map((c) => (
              <li key={c.id}>
                <div className="bd-change-tag">候选 {c.id} · {VERDICT_LABEL[candidateVerdict(c, evo)]}</div>
                <p className="bd-change-after">{c.summary}</p>
              </li>
            ))}
          </ul>
        </>
      )}
      <div className="bd-gate">
        <h3>{evo.val_split} 组门禁 · 4 周模拟 ISI 有效率</h3>
        <CandidateLine evo={evo} />
      </div>
      <p className="bd-footnote">
        {failureSummary(evo)}，参考 {usedFeedback} 条已确认的人工意见 · 反思器 {evo.reflector.model}
        {evo.reflector.fell_back && <> · <strong className="bd-warn-text">反思器自动降级</strong>{evo.reflector.fallback_reason ? `（${evo.reflector.fallback_reason}）` : ''}</>}
      </p>
    </Panel>
  );
}

// ---------- 怎么回退 ----------

function clock(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString('zh-CN', { hour12: false });
}

function RollbackPanel({ data }: { data: BoardData }) {
  const versions = data.versions;
  const head = versions?.find((v) => v.is_head) ?? versions?.[versions.length - 1] ?? null;
  const previous = versions && head ? versions[versions.indexOf(head) - 1] ?? null : null;
  return (
    <Panel className="bd-rollback" title="怎么回退" aside="每一代是版本库里的一次提交">
      <div className="bd-rollback-body">
        {versions === null ? (
          <p className="bd-chart-empty">版本记录{NOT_YET}。</p>
        ) : versions.length === 0 ? (
          <p className="bd-chart-empty">版本库里还没有提交。</p>
        ) : (
          <ol className="bd-versions" aria-label="playbook 版本链">
            {versions.map((v) => (
              <li key={v.version} className={v.is_head ? 'head' : ''}>
                <div className="bd-version-name">
                  <strong>{v.version}</strong>
                  {v.is_head && <Pill tone="neutral">当前</Pill>}
                  <code>{v.sha.slice(0, 8)}</code>
                </div>
                <p>{v.message}</p>
                <span>{v.author} · {clock(v.committed_at)}</span>
              </li>
            ))}
          </ol>
        )}
        <div className="bd-rollback-how">
          {previous ? (
            <>
              <h3>退回 {previous.version}</h3>
              <pre className="bd-command"><code>python -m engine.evolve rollback {previous.version}</code></pre>
            </>
          ) : versions && versions.length > 0 ? (
            <>
              <h3>现在只有 {versions[0].version}</h3>
              <p className="bd-learned-text">没有更早的版本可退。下一代提交后，这里给出退回命令。</p>
            </>
          ) : null}
        </div>
      </div>
    </Panel>
  );
}

// ---------- 第二屏：证据 ----------

function TrajectoryPanel({ data }: { data: BoardData }) {
  const sources = ([[data.control, 'base'], [data.run2, 'lead']] as const)
    .map(([slot, tone]) => ({ slot, tone, t: slot.report ? isiTrajectories(slot.report) : null }))
    .filter((x) => x.t !== null);
  if (sources.length === 0) {
    return (
      <Panel className="bd-trajectory" title="4 周里 ISI 怎么变">
        <p className="bd-chart-empty">对照或运行 2 完成后，这里画出每位来访 4 周的 ISI 变化。</p>
      </Panel>
    );
  }
  const all = sources.flatMap((x) => x.t!.visitors.flatMap((v) => v.deltas));
  const bottom = Math.floor(Math.min(-12, ...all) / 4) * 4;
  const top = Math.ceil(Math.max(0, ...all) / 4) * 4;
  const yTicks: number[] = [];
  for (let y = top; y >= bottom; y -= 4) yTicks.push(y);
  const series: LineSeries[] = sources.map(({ slot, tone, t }) => ({
    key: slot.role, tone,
    points: t!.mean.map((y, x) => ({ x, y })),
    endLabel: `${ROLE_LABEL[slot.role]} ${signed(t!.mean[4])} 分`,
  }));
  const faint = sources.flatMap(({ slot, tone, t }) =>
    t!.visitors.map((v) => ({ key: `${slot.role}-${v.id}`, tone, points: v.deltas.map((y, x) => ({ x, y })) })));
  return (
    <Panel className="bd-trajectory" title="4 周里 ISI 怎么变" aside="细线是每位来访相对第 0 周的变化，粗线是平均">
      <LineChart
        ariaLabel={`4 周 ISI 变化：${series.map((s) => s.endLabel).join('，')}`}
        series={series}
        faint={faint}
        xDomain={[0, 4]}
        yDomain={[bottom, top]}
        xTicks={[0, 1, 2, 3, 4].map((x) => ({ x, label: `第 ${x} 周` }))}
        yTicks={yTicks}
        yFormat={(v) => signed(v) || '0'}
        refs={[{ y: -7, label: '有效线 −7 分' }]}
      />
      <p className="bd-footnote">越往下越好。落到有效线以下的来访计入“有效”。数值由冻结的规则模型推演，不是来访自述。</p>
    </Panel>
  );
}

function EvidencePanel({ data }: { data: BoardData }) {
  const sources = ([[data.control, 'base'], [data.run2, 'lead']] as const).filter(([slot]) => slot.evidence);
  const title = '问到关键线索了吗';
  if (sources.length === 0) {
    const waiting = !data.control.report && !data.run2.report;
    return (
      <Panel className="bd-evidence" title={title}>
        <p className="bd-chart-empty">
          {waiting ? '对照或运行 2 完成后，这里画出会谈每一步的判断把握。' : '这份证据尚未生成：当前数据来源没有提供逐步的路径权重。'}
        </p>
      </Panel>
    );
  }
  // 两次运行的步数可能不同：横轴按“第几轮第几步”的并集排开。
  const keys = [...new Set(sources.flatMap(([slot]) => slot.evidence!.map((e) => `${e.round}:${e.step}`)))]
    .map((k) => k.split(':').map(Number) as [number, number])
    .sort((x, y) => x[0] - y[0] || x[1] - y[1]);
  const index = new Map(keys.map(([r, st], i) => [`${r}:${st}`, i]));
  const series: LineSeries[] = sources.map(([slot, tone]) => {
    const points = slot.evidence!.map((e) => ({ x: index.get(`${e.round}:${e.step}`)!, y: e.pTrue }));
    return { key: slot.role, tone, points, endLabel: `${ROLE_LABEL[slot.role]} ${pct(points[points.length - 1].y)}` };
  });
  const highest = Math.max(...series.flatMap((s) => s.points.map((pt) => pt.y)));
  const top = Math.max(0.5, Math.ceil(highest * 4) / 4);
  const yTicks: number[] = [];
  for (let y = 0; y <= top + 1e-9; y += 0.25) yTicks.push(y);
  const secondRound = keys.findIndex(([r]) => r === 2);
  return (
    <Panel className="bd-evidence" title={title} aside="会谈每一步，判断落在正确干预路径上的平均权重">
      <LineChart
        ariaLabel={`逐步判断把握：${series.map((s) => s.endLabel).join('，')}`}
        series={series}
        xDomain={[0, Math.max(1, keys.length - 1)]}
        yDomain={[0, top]}
        xTicks={keys.map(([, st], i) => ({ x: i, label: `${st}` }))}
        yTicks={yTicks}
        yFormat={(v) => pct(v)}
        refs={[{ y: 0.2, label: '五选一的起点' }]}
        firstRegionLabel="第 1 轮 · 第几步"
        dividers={secondRound > 0 ? [{ x: secondRound - 0.5, label: '第 2 轮' }] : []}
      />
      <p className="bd-footnote">越往上越好。线升得早、升得高，说明提问更早问出了能区分路径的线索。分类器在两次运行之间是冻结的。</p>
    </Panel>
  );
}

// ---------- 整页 ----------

export function EvolutionBoard({ data, loading = false }: { data: BoardData; loading?: boolean }) {
  const f = loading ? { tone: 'waiting' as const, text: '正在读取实验…' } : finding(data);
  const alert = alertSlots(data).length > 0 || data.experiment?.stage === 'failed';
  return (
    <div className={`bd-body ${alert ? 'bd-alert' : ''}`}>
      <div className="bd-title">
        <div>
          <h1>进化实验</h1>
          <p className={`bd-finding bd-finding-${f.tone}`} role={f.tone === 'negative' ? 'alert' : undefined}>{f.text}</p>
        </div>
        {data.experiment && <code className="bd-experiment-id">{data.experiment.experiment_id}</code>}
      </div>
      <StageTrack data={data} />
      <div className="bd-grid">
        <LeadPanel data={data} />
        <SecondaryPanel data={data} />
        <SafetyPanel data={data} />
        <div className="bd-side">
          <LearnedPanel data={data} />
          <RollbackPanel data={data} />
        </div>
      </div>
      <div className="bd-proof">
        <TrajectoryPanel data={data} />
        <EvidencePanel data={data} />
      </div>
    </div>
  );
}
