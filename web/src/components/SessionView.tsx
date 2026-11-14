import type { ReactNode } from 'react';
import type { Session, SessionRound, ToolCall } from '../api/contractTypes';
import type { ExecutionMode } from '../api/draftTypes';
import { HREF } from '../hooks/useHashRoute';
import { useSession } from '../hooks/useRunData';
import type { AdapterKind } from '../config';
import { minutesToHours, pct } from '../lib/format';
import {
  CARD_LABEL,
  COMPONENT_LABEL,
  CRISIS_LABEL,
  PATH_LABEL,
  REFERRAL_LABEL,
  SAFETY_ACTION_LABEL,
  SAFETY_SOURCE_LABEL,
  SCALE_LABEL,
  SESSION_STATUS_LABEL,
  TOOL_LABEL,
  TOPIC_LABEL,
  label,
} from '../lib/labels';
import { Badge, Card, ErrorNotice, KeyValue, Notice, Spinner } from './common';
import { DataSourceBadge } from './DataSourceBanner';

function toolSummary(call: ToolCall): string {
  const r = call.result;
  if ('stop_bang' in r) return `STOP-Bang ${r.stop_bang}`;
  return `PHQ-9 ${r.phq9} · GAD-7 ${r.gad7}`;
}

type TimelineItem =
  | { kind: 'turn'; turn: number; speaker: 'agent' | 'visitor' | 'safety'; text: string }
  | { kind: 'tool'; turn: number; call: ToolCall }
  | { kind: 'safety'; turn: number; node: ReactNode };

function RoundBlock({ round, session }: { round: SessionRound; session: Session }) {
  const items: TimelineItem[] = [
    ...round.transcript.map((t) => ({ kind: 'turn' as const, turn: t.turn, speaker: t.speaker, text: t.text })),
    ...session.tool_calls.filter((c) => c.round === round.round).map((c) => ({ kind: 'tool' as const, turn: c.turn, call: c })),
    ...session.safety_events
      .filter((e) => e.round === round.round)
      .map((e) => ({
        kind: 'safety' as const,
        turn: e.turn,
        node: (
          <>
            安全层：{SAFETY_ACTION_LABEL[e.action]} · 等级 {CRISIS_LABEL[e.level]} · 来源 {label(SAFETY_SOURCE_LABEL, e.source)}
            {e.matched && <> · 命中“{e.matched}”</>}
          </>
        ),
      })),
  ].sort((a, b) => a.turn - b.turn || (a.kind === 'safety' ? 1 : 0) - (b.kind === 'safety' ? 1 : 0));

  return (
    <Card title={`第 ${round.round} 轮`} className="round">
      <ol className="chat">
        {items.map((it, i) => {
          if (it.kind === 'turn') {
            const who = it.speaker === 'agent' ? '睡眠管家' : it.speaker === 'visitor' ? '模拟来访' : '安全层固定话术';
            return (
              <li key={i} className={`bubble bubble-${it.speaker}`}>
                <span className="bubble-who">{who}</span>
                <span className="bubble-text">{it.text}</span>
              </li>
            );
          }
          if (it.kind === 'tool') {
            return (
              <li key={i} className="event event-tool">
                调用筛查工具：{label(TOOL_LABEL, it.call.tool)} → {toolSummary(it.call)}
              </li>
            );
          }
          return (
            <li key={i} className="event event-safety">
              {it.node}
            </li>
          );
        })}
      </ol>

      <KeyValue
        items={[
          [
            '干预路径判断',
            <>
              {round.path_pred} {PATH_LABEL[round.path_pred]}
              {round.path_confidence !== null && <span className="muted">（置信度 {pct(round.path_confidence, 0)}）</span>}
            </>,
          ],
          ['转介判断', `${round.referral_pred} ${REFERRAL_LABEL[round.referral_pred]}`],
          ['本轮安全层最高等级', CRISIS_LABEL[round.crisis_level]],
          [
            '问到的话题',
            round.asked_topics.length ? (
              <span className="tags">
                {round.asked_topics.map((t) => (
                  <Badge key={t}>{label(TOPIC_LABEL, t)}</Badge>
                ))}
              </span>
            ) : (
              '—'
            ),
          ],
        ]}
      />
    </Card>
  );
}

function PlanBlock({ session }: { session: Session }) {
  const plan = session.plan;
  if (!plan) {
    return (
      <Card title="建议方案">
        <p className="muted">本次会谈没有生成建议方案（会谈因危机流程结束或出错）。</p>
      </Card>
    );
  }
  return (
    <Card title="建议方案">
      <KeyValue
        items={[
          ['建议作息', `${plan.bedtime} 上床 · ${plan.risetime} 起床`],
          ['建议卧床时间', minutesToHours(plan.tib_minutes)],
          [
            '干预组件',
            <span className="tags">
              {plan.components.map((c) => (
                <Badge key={c} tone="info">
                  {label(COMPONENT_LABEL, c)}
                </Badge>
              ))}
            </span>,
          ],
          ['是否解释理由', plan.rationale_given ? '是' : '否'],
          ['睡眠限制前是否询问禁忌', plan.contraindications_checked ? '是' : '否'],
        ]}
      />
      {plan.referral_advice && (
        <Notice tone="info" title="就医建议">
          {plan.referral_advice}
        </Notice>
      )}
      {plan.cards.length > 0 && (
        <div className="cards">
          {plan.cards.map((c, i) => (
            <div key={i} className={`demo-card demo-card-${c.type}`}>
              <div className="small muted">{label(CARD_LABEL, c.type)}</div>
              <strong>{c.title}</strong>
              <p>{c.body}</p>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function SessionDetail({
  session,
  adapter,
  mode,
}: {
  session: Session;
  adapter: AdapterKind;
  mode: ExecutionMode | null;
}) {
  const b = session.behaviors;
  return (
    <>
      <Card
        title={<>会谈 · {session.visitor_id}</>}
        aside={
          <div className="btn-row">
            <DataSourceBadge adapter={adapter} mode={mode} />
            <Badge tone={session.status === 'crisis_exit' ? 'danger' : session.status === 'error' ? 'warn' : 'ok'}>
              {SESSION_STATUS_LABEL[session.status]}
            </Badge>
          </div>
        }
      >
        {session.error && <Notice tone="warn" title="会谈出错">{session.error}</Notice>}
        <KeyValue
          items={[
            ['运行编号', <span className="mono">{session.run_id}</span>],
            ['playbook 版本', <span className="mono">{session.playbook_version}</span>],
            ['模型', `会谈 ${session.models.agent} · 来访 ${session.models.visitor}`],
            [
              '会谈前自评（来访自报）',
              session.context_scales.length
                ? session.context_scales.map((s) => `${SCALE_LABEL[s.scale]} ${s.reported_score}`).join(' · ')
                : '未填写',
            ],
          ]}
        />
        {session.safety_events.some((e) => e.turn === 0) && (
          <Notice tone="warn" title="会谈前自评触发安全层">
            {session.safety_events
              .filter((e) => e.turn === 0)
              .map((e) => `${SAFETY_ACTION_LABEL[e.action]}（${CRISIS_LABEL[e.level]}）`)
              .join('；')}
          </Notice>
        )}
      </Card>

      {session.rounds.map((r) => (
        <RoundBlock key={r.round} round={r} session={session} />
      ))}

      <PlanBlock session={session} />

      <Card title="同盟相关行为计数">
        <div className="behavior-grid">
          {(
            [
              ['共同设定目标', b.goal_setting],
              ['复述确认', b.reflection],
              ['回应情绪', b.emotion_response],
              ['解释理由', b.rationale_explained],
              ['说教', b.lecturing],
              ['过早给建议', b.premature_advice],
            ] as [string, number][]
          ).map(([k, v]) => (
            <div key={k} className="behavior">
              <span className="behavior-value">{v}</span>
              <span className="small muted">{k}</span>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}

export function SessionView({
  runId,
  visitorId,
  adapter,
  mode,
}: {
  runId: string;
  visitorId: string;
  adapter: AdapterKind;
  mode: ExecutionMode | null;
}) {
  const state = useSession(runId, visitorId);
  return (
    <div className="stack">
      <a className="back-link" href={HREF.runs}>
        ‹ 返回运行
      </a>
      {state.status === 'loading' && <Spinner label="正在读取会谈记录…" />}
      {state.status === 'error' && (
        <ErrorNotice
          error={state.error}
          title="会谈记录读取失败"
          action={
            <button type="button" className="btn btn-sm" onClick={state.reload}>
              重试
            </button>
          }
        />
      )}
      {state.status === 'ok' && <SessionDetail session={state.data} adapter={adapter} mode={mode} />}
    </div>
  );
}
