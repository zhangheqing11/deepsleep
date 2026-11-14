// 用户端的纯展示组件：只画传进来的会谈数据，不请求、不计时。
// 教练、来访、安全层说的每一句都原样来自会谈记录；这里写的只有标签和说明。
import type { EvolutionChange, Plan, Session } from '../../api/contractTypes';
import {
  CARD_LABEL,
  CHANGE_OP_LABEL,
  COMPONENT_LABEL,
  PATH_LABEL,
  REFERRAL_LABEL,
  SAFETY_ACTION_LABEL,
  SCALE_LABEL,
  SECTION_LABEL,
  TOOL_LABEL,
  TOPIC_LABEL,
  label,
} from '../../lib/labels';
import { onlyIn, scaleResults, type Digest, type ScaleResult, type Step } from '../../lib/replay';
import { SCALE_INFO } from '../../lib/scales';

const signed = (v: number) => (v > 0 ? `+${v}` : v < 0 ? `−${Math.abs(v)}` : '0');
const hours = (min: number) => `${Math.round((min / 60) * 10) / 10} 小时`;

// ---------- 会谈 ----------

function toolSummary(result: Record<string, unknown>): string {
  const parts: string[] = [];
  if (typeof result.phq9 === 'number') parts.push(`PHQ-9 ${result.phq9} 分`);
  if (typeof result.gad7 === 'number') parts.push(`GAD-7 ${result.gad7} 分`);
  if (typeof result.stop_bang === 'number') parts.push(`STOP-Bang ${result.stop_bang} 分`);
  return parts.join('，');
}

export interface SpeakerNames { agent: string; visitor: string }
const DEFAULT_NAMES: SpeakerNames = { agent: '教练', visitor: '来访' };

function StepView({ step, names }: { step: Step; names: SpeakerNames }) {
  switch (step.kind) {
    case 'round':
      return <li className="ua-round" role="separator">第 {step.round} 轮</li>;
    case 'tool':
      return (
        <li className="ua-event">
          {names.agent}补做了一次{label(TOOL_LABEL, step.call.tool)}
          {toolSummary(step.call.result as Record<string, unknown>) && <>：{toolSummary(step.call.result as Record<string, unknown>)}</>}
        </li>
      );
    case 'turn': {
      const { speaker, text } = step.turn;
      if (speaker === 'safety') {
        return (
          <li className="ua-safety">
            <span className="ua-who">安全层 · 固定话术，不随进化改变</span>
            <p>{text}</p>
          </li>
        );
      }
      return (
        <li className={`ua-msg ${speaker}`}>
          <span className="ua-who">{speaker === 'agent' ? names.agent : names.visitor}</span>
          <p>{text}</p>
        </li>
      );
    }
    case 'end':
      return null;
  }
}

export function Transcript({ steps, shown, typing, names = DEFAULT_NAMES }: { steps: Step[]; shown: number; typing: boolean; names?: SpeakerNames }) {
  return (
    <ol className="ua-log" aria-live="polite">
      {steps.slice(0, shown).map((s, i) => <StepView key={i} step={s} names={names} />)}
      {typing && (
        <li className="ua-msg agent ua-typing" aria-label="教练正在回应">
          <span className="ua-who">教练</span>
          <p><i /><i /><i /></p>
        </li>
      )}
    </ol>
  );
}

function PlanView({ plan }: { plan: Plan }) {
  return (
    <section className="ua-plan" aria-label="教练给出的计划">
      <h3>教练给出的计划</h3>
      <dl className="ua-times">
        <div><dt>上床</dt><dd>{plan.bedtime}</dd></div>
        <div><dt>起床</dt><dd>{plan.risetime}</dd></div>
        <div><dt>卧床</dt><dd>{hours(plan.tib_minutes)}</dd></div>
      </dl>
      {plan.components.length > 0 && (
        <ul className="ua-chips" aria-label="用到的做法">
          {plan.components.map((c) => <li key={c}>{label(COMPONENT_LABEL, c)}</li>)}
        </ul>
      )}
      {plan.referral_advice && <p className="ua-referral">{plan.referral_advice}</p>}
      {plan.cards.map((c, i) => (
        <article key={i} className="ua-plancard">
          <span className="ua-who">{label(CARD_LABEL, c.type)}</span>
          <strong>{c.title}</strong>
          <p>{c.body}</p>
        </article>
      ))}
    </section>
  );
}

/** 一场会谈放完之后的收尾：计划和模拟的四周结果，或者如实说明为什么没有。 */
export function Ending({ session, digest }: { session: Session; digest: Digest }) {
  if (session.status === 'error') {
    return (
      <section className="ua-ending">
        <p className="ua-note negative" role="status">这场会谈中途出错，没有走完{session.error ? `：${session.error}` : '。'}</p>
      </section>
    );
  }
  return (
    <section className="ua-ending">
      {session.status === 'crisis_exit' && (
        <p className="ua-note safety" role="status">安全层接管后，这场会谈到此结束。睡眠的事先放一放，所以没有后面的计划。</p>
      )}
      {session.plan ? <PlanView plan={session.plan} /> : session.status === 'completed' && (
        <p className="ua-note">这场会谈没有给出计划。</p>
      )}
      {digest.isiWeek && (
        <section className="ua-outcome" aria-label="模拟的四周结果">
          <h3>照这个计划过四周（模拟）</h3>
          <p className="ua-figure">
            ISI <b>{digest.isiWeek[0]}</b> → <b>{digest.isiWeek[4]}</b>
            <span className={digest.responder ? 'good' : 'flat'}>{digest.responder ? '达到有效线' : '未达到有效线'}</span>
          </p>
          <IsiSpark before={null} after={digest.isiWeek} afterName="这场会谈" beforeName="" />
          <p className="ua-fine">分数越低，睡眠困扰越轻；下降超过 7 分记为有效。这是固定的规则模型推算的，不是真人的结果。</p>
        </section>
      )}
    </section>
  );
}

// ---------- 四周 ISI 小图 ----------

export function IsiSpark({ before, after, beforeName, afterName }: {
  before: number[] | null; after: number[] | null; beforeName: string; afterName: string;
}) {
  const all = [...(before ?? []), ...(after ?? [])];
  if (all.length === 0) return null;
  const W = 300;
  const H = 96;
  const hi = Math.max(...all) + 1;
  const lo = Math.max(0, Math.min(...all) - 1);
  const x = (i: number) => 10 + (i * (W - 20)) / 4;
  const y = (v: number) => 8 + ((hi - v) / (hi - lo || 1)) * (H - 34);
  const d = (w: number[]) => w.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
  const say = (name: string, w: number[] | null) => (w ? `${name} ${w[0]} 到 ${w[4]}` : null);
  const aria = ['四周 ISI', say(beforeName, before), say(afterName, after)].filter(Boolean).join('，');
  return (
    <svg className="ua-spark" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={aria}>
      {[0, 1, 2, 3, 4].map((i) => (
        <g key={i}>
          <line className="grid" x1={x(i)} x2={x(i)} y1={6} y2={H - 24} />
          <text x={x(i)} y={H - 6} textAnchor={i === 0 ? 'start' : i === 4 ? 'end' : 'middle'}>{i === 0 ? '开始' : `第 ${i} 周`}</text>
        </g>
      ))}
      {before && <path className="line base" d={d(before)} />}
      {after && <path className="line lead" d={d(after)} />}
      {before && <circle className="dot base" cx={x(4)} cy={y(before[4])} r={3.5} />}
      {after && <circle className="dot lead" cx={x(4)} cy={y(after[4])} r={3.5} />}
    </svg>
  );
}

// ---------- 两场会谈的对比 ----------

function Chips({ items, map, fresh }: { items: string[]; map: Record<string, string>; fresh: Set<string> }) {
  if (items.length === 0) return <span className="ua-none">没有</span>;
  return (
    <ul className="ua-chips">
      {items.map((t) => <li key={t} className={fresh.has(t) ? 'fresh' : undefined}>{label(map, t)}</li>)}
    </ul>
  );
}

function PathCell({ d }: { d: Digest }) {
  if (!d.pathR1) return <span className="ua-none">没有判断</span>;
  if (!d.pathR2 || d.pathR2 === d.pathR1) return <>{label(PATH_LABEL, d.pathR1)}</>;
  return <>{label(PATH_LABEL, d.pathR1)}<span className="ua-then">第 2 轮改为</span>{label(PATH_LABEL, d.pathR2)}</>;
}

function PlanCell({ d, other }: { d: Digest; other: Digest | null }) {
  if (!d.plan) return <span className="ua-none">{d.status === 'crisis_exit' ? '安全层接管，没有计划' : '没有计划'}</span>;
  return (
    <>
      <span className="ua-clock">{d.plan.bedtime} – {d.plan.risetime}</span>
      <Chips items={d.plan.components} map={COMPONENT_LABEL} fresh={onlyIn(d.plan.components, other?.plan?.components ?? null)} />
    </>
  );
}

function IsiCell({ d }: { d: Digest }) {
  if (!d.isiWeek || d.isiChange === null) return <span className="ua-none">尚未生成</span>;
  return (
    <>
      <span className="ua-clock">{d.isiWeek[0]} → {d.isiWeek[4]}</span>
      <span className={`ua-delta ${d.responder ? 'good' : 'flat'}`}>{signed(d.isiChange)} 分{d.responder ? '，有效' : ''}</span>
    </>
  );
}

export interface CompareProps {
  before: Digest | null;
  after: Digest | null;
  beforeName: string;
  afterName: string;
  /** 两侧是同一版手册：差别不能算在学习头上 */
  sameVersion: boolean;
  learned: EvolutionChange[];
  learnedSummary: string | null;
  outcome: 'committed' | 'kept_previous' | null;
}

export function Compare(p: CompareProps) {
  const { before: b, after: a } = p;
  const sides = [b, a] as const;
  const names = [p.beforeName, p.afterName];
  const row = (title: string, cell: (d: Digest, other: Digest | null) => JSX.Element, show = true) => show && (
    <div className="ua-row" role="row">
      <h4 role="rowheader">{title}</h4>
      {sides.map((d, i) => (
        <div key={i} role="cell" className={`ua-cell ${i === 0 ? 'base' : 'lead'}`}>
          {d ? cell(d, sides[1 - i]) : <span className="ua-none">这一场还没有</span>}
        </div>
      ))}
    </div>
  );
  const anySafety = sides.some((d) => d && d.safetyActions.length > 0);
  const anyTools = sides.some((d) => d && d.tools.length > 0);
  return (
    <div className="ua-compare">
      {p.sameVersion && b && a && (
        <p className="ua-note">两场会谈用的是同一版手册。下面的差别来自对话本身，不是学习的结果。</p>
      )}
      <div className="ua-table" role="table" aria-label="两场会谈的差别">
        <div className="ua-row ua-head" role="row">
          <span role="columnheader" className="ua-sr">项目</span>
          {sides.map((d, i) => (
            <span key={i} role="columnheader" className={i === 0 ? 'base' : 'lead'}>
              {names[i]}{d && <b>{d.version}</b>}
            </span>
          ))}
        </div>
        {row('问到的话题', (d, o) => <Chips items={d.topics} map={TOPIC_LABEL} fresh={onlyIn(d.topics, o?.topics ?? null)} />)}
        {row('补做的筛查', (d, o) => <Chips items={d.tools} map={TOOL_LABEL} fresh={onlyIn(d.tools, o?.tools ?? null)} />, anyTools)}
        {row('判断的干预路径', (d) => <PathCell d={d} />)}
        {row('就医建议', (d) => (d.referral ? <>{label(REFERRAL_LABEL, d.referral)}</> : <span className="ua-none">没有判断</span>))}
        {row('安全层', (d) => (d.safetyActions.length
          ? <>{d.safetyActions.map((s) => label(SAFETY_ACTION_LABEL, s)).join('、')}</>
          : <span className="ua-none">没有触发</span>), anySafety)}
        {row('给出的计划', (d, o) => <PlanCell d={d} other={o} />)}
        {row('四周后的 ISI（模拟）', (d) => <IsiCell d={d} />)}
      </div>
      {(b?.isiWeek || a?.isiWeek) && (
        <IsiSpark before={b?.isiWeek ?? null} after={a?.isiWeek ?? null} beforeName={p.beforeName} afterName={p.afterName} />
      )}
      <p className="ua-fine">带底色的是只在这一场出现的。ISI 越低，睡眠困扰越轻，由固定的规则模型推算。</p>
      <Learned changes={p.learned} summary={p.learnedSummary} outcome={p.outcome} />
    </div>
  );
}

export function Learned({ changes, summary, outcome }: Pick<CompareProps, 'outcome'> & { changes: EvolutionChange[]; summary: string | null }) {
  if (outcome === null) return null;
  if (outcome === 'kept_previous' || changes.length === 0) {
    return (
      <section className="ua-learned">
        <h3>教练这次没有改手册</h3>
        <p>反思器提出的修改没有通过门禁，手册保留上一代。没变好就不换，这也是设计的一部分。</p>
      </section>
    );
  }
  return (
    <section className="ua-learned">
      <h3>教练写进新手册的规则</h3>
      {summary && <p>{summary}</p>}
      <ol>
        {changes.map((c) => (
          <li key={c.id}>
            <span className="ua-who">{label(SECTION_LABEL, c.section)} · {label(CHANGE_OP_LABEL, c.op)}</span>
            <p>{c.after ?? c.before}</p>
            {c.reason && <p className="ua-reason">为什么改：{c.reason}</p>}
          </li>
        ))}
      </ol>
      <p className="ua-fine">会谈记录里没有标出哪一句话出自哪条规则，所以这里只列规则本身，不做逐句对应。</p>
    </section>
  );
}

// ---------- 来访的自评 ----------

function ScaleCard({ r }: { r: ScaleResult }) {
  const info = SCALE_INFO[r.scale];
  const items = r.items && r.items.length === info.items.length ? r.items : null;
  return (
    <article className="ua-scale">
      <header>
        <div>
          <h3>{info.name}</h3>
          <span className="ua-who">{r.source === 'prefilled' ? '会谈前自己填的' : '会谈中教练补做的筛查'}</span>
        </div>
        <p className="ua-score"><b>{r.score}</b><span>/ {info.max}</span></p>
      </header>
      <p>{info.about}</p>
      {info.stem && <p className="ua-stem">{info.stem}</p>}
      <ol className="ua-items">
        {info.items.map((text, i) => {
          const v = items ? items[i] : null;
          const flagged = r.scale === 'phq9' && i === 8 && v !== null && v > 0;
          return (
            <li key={i} className={flagged ? 'flagged' : undefined}>
              <span>{text}</span>
              {v !== null && <b>{info.options ? info.options[v] ?? v : `${v} 分`}</b>}
            </li>
          );
        })}
      </ol>
      {!items && <p className="ua-fine">这次只记录了总分，没有逐题作答。</p>}
      {!info.verbatim && <p className="ua-fine">这里列的是每一题看什么，不是量表原文。</p>}
      <p className="ua-rule">{info.rule}</p>
    </article>
  );
}

export function Scales({ session }: { session: Session }) {
  const results = scaleResults(session);
  if (results.length === 0) {
    return <p className="ua-note">这位来访会谈前没有填自评表，会谈中也没有补做筛查。</p>;
  }
  return (
    <div className="ua-scales">
      {results.map((r, i) => <ScaleCard key={`${r.scale}-${i}`} r={r} />)}
      <p className="ua-fine">
        这些是模拟来访的作答，页面上没有让真人填写的入口。量表只用来决定教练要不要建议就医，不代表任何医学结论。
        {results.some((r) => r.scale === 'isi') ? '' : ` ${SCALE_LABEL.isi} 的四周变化见“对比”。`}
      </p>
    </div>
  );
}
