import { useEffect, useState } from 'react';
import type { EvolveStatus, ExperimentManifest } from '../api/extensionTypes';
import type { EvolutionView } from '../api/validate';
import type { ExperimentData } from '../hooks/useExperimentData';
import { clock, pct } from '../lib/format';
import { CHANGE_OP_LABEL, CRITICALITY_LABEL, label, SECTION_LABEL } from '../lib/labels';
import { blockReasons, chosenCandidate, chosenChanges, secondsLeft } from '../model/overview';
import { Badge, Empty, errorText, Notice, type Tone } from './common';

/** ② 学到了什么：学习进行中显示进度；完成后显示被选候选的改动，或“保留上一代”。 */
export function LearnedPanel({ m, data }: { m: ExperimentManifest; data: ExperimentData }) {
  const status = data.status.data;
  const evo = data.evolution.data;
  const state = m.evolution.state;

  let body;
  if (evo) {
    body = evo.outcome === 'committed' ? <Committed evo={evo} /> : <KeptPrevious evo={evo} />;
  } else if (state === 'pending') {
    body = <Empty>运行 1 完成后开始学习：反思失败案例 → 生成 3 份候选 → 验证集 C 门禁 → 提交或保留上一代。</Empty>;
  } else if (state === 'failed' || status?.phase === 'failed') {
    body = (
      <>
        <Notice tone="danger" title="学习失败">
          {status?.error ?? m.error ?? '后端没有给出原因'}
        </Notice>
        {status && <Progress s={status} />}
      </>
    );
  } else {
    body = (
      <>
        {status ? <Progress s={status} /> : <Empty>学习已开始，正在读取学习状态…</Empty>}
        {state === 'done' && <Empty>学习已完成，进化记录读取中…</Empty>}
      </>
    );
  }

  const err = (data.evolution.error && !evo) ? data.evolution.error : data.status.error && !status ? data.status.error : null;
  return (
    <section className="panel" aria-labelledby="q2">
      <h2 id="q2">
        <span className="q">②</span>学到了什么
        <span className="small muted">agent 自己改写 playbook</span>
      </h2>
      {body}
      {err && err.code !== 'NOT_READY' && <p className="small error-text">{errorText(err)}</p>}
    </section>
  );
}

const PHASES: { key: EvolveStatus['phase'][]; title: string }[] = [
  { key: ['reflecting'], title: '反思失败案例' },
  { key: ['validating'], title: '候选验证（验证集 C）' },
  { key: ['committing'], title: '提交' },
];

const CAND_LABEL: Record<string, [string, Tone]> = {
  pending: ['等待', 'neutral'],
  running: ['验证中', 'info'],
  done: ['已验证', 'ok'],
  error: ['出错', 'danger'],
  blocked: ['硬规则拦下', 'warn'],
  empty: ['无可用改动', 'neutral'],
  skipped: ['跳过', 'neutral'],
};

/** 审核窗口按设计约 120 秒；明显超过时多半是两台电脑时钟不一致，不显示误导性的倒计时。 */
const MAX_REVIEW_SECONDS = 600;

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

/** 学习进度：只显示 status.json 的字段，不推算。验证与人工审核并行，分两行显示。 */
function Progress({ s }: { s: EvolveStatus }) {
  const waiting = s.review.state === 'waiting';
  const now = useNow(waiting);
  const left = secondsLeft(s.review.deadline, now);
  const order = ['reflecting', 'validating', 'committing', 'done'];
  const at = order.indexOf(s.phase);
  return (
    <div className="learn-progress">
      <ol className="steps">
        {PHASES.map((p, i) => {
          const st = s.phase === 'failed' ? (i === 0 ? 'failed' : 'pending') : at > i ? 'done' : at === i ? 'running' : 'pending';
          return (
            <li key={p.title} className={`step step-${st}`}>
              <span className="step-dot" aria-hidden="true" />
              <span>{p.title}</span>
              {i === 0 && (
                <span className="small muted">
                  {s.reflector.model ?? '模型待定'}
                  {s.reflector.fell_back && (
                    <>
                      {' '}
                      <Badge tone="warn">已降级到备用模型</Badge>
                    </>
                  )}
                </span>
              )}
              {i === 1 && (
                <span className="cands">
                  <Badge tone={CAND_LABEL[s.validation.baseline]?.[1] ?? 'neutral'}>
                    上一代基线 {CAND_LABEL[s.validation.baseline]?.[0] ?? s.validation.baseline}
                  </Badge>
                  {Object.entries(s.validation.candidates).map(([id, v]) => (
                    <Badge key={id} tone={CAND_LABEL[v]?.[1] ?? 'neutral'}>
                      {id} {CAND_LABEL[v]?.[0] ?? v}
                    </Badge>
                  ))}
                </span>
              )}
            </li>
          );
        })}
      </ol>
      <div className="review-line small">
        <strong>人工审核（只能否决）：</strong>
        {s.review.state === 'not_needed' && '本次没有需要审核的高关键度改动'}
        {s.review.state === 'done' && '审核窗口已结束'}
        {waiting && (
          <>
            {s.review.pending_changes} 条改动等待审核，截止 {clock(s.review.deadline)}
            {left !== null && left > 0 && left <= MAX_REVIEW_SECONDS && `，约剩 ${left} 秒`}
            {left !== null && left <= 0 && '，已到截止时间，等待后端更新'}
            {left !== null && left > MAX_REVIEW_SECONDS && (
              <span className="error-text">，截止时间比本机时钟晚 {Math.round(left / 60)} 分钟，请核对两台电脑的时钟</span>
            )}
            <span className="muted">（倒计时按本机时钟计算）</span>
          </>
        )}
        {!['not_needed', 'done', 'waiting'].includes(s.review.state) && s.review.state}
      </div>
      <p className="small muted">学习状态更新于 {clock(s.updated_at)}</p>
    </div>
  );
}

function Committed({ evo }: { evo: EvolutionView }) {
  const c = chosenCandidate(evo);
  const { shown, hidden } = chosenChanges(evo);
  return (
    <div className="learned">
      <p className="learned-head">
        <Badge tone="ok">已提交</Badge> playbook {evo.from_version} → <strong>{evo.to_version}</strong>，采纳候选 {evo.chosen}
        {evo.reflector.fell_back && (
          <>
            {' '}
            <Badge tone="warn">反思器已降级：{evo.reflector.model}</Badge>
          </>
        )}
      </p>
      {c && (
        <p className="small">
          <span className="chip">
            验证集 {evo.val_split ?? 'C'}：上一代 {pct(evo.baseline_isi)} → 候选 {pct(c.val_isi)}
          </span>
        </p>
      )}
      <ul className="changes">
        {shown.map((ch) => (
          <li key={ch.id} className={`change crit-${ch.criticality}`}>
            <div className="change-head">
              <strong>{label(SECTION_LABEL, ch.section)}</strong>
              <Badge>{label(CHANGE_OP_LABEL, ch.op)}</Badge>
              <Badge tone={ch.criticality === 'high' ? 'danger' : ch.criticality === 'medium' ? 'warn' : 'neutral'}>
                关键度 {label(CRITICALITY_LABEL, ch.criticality)}
              </Badge>
            </div>
            <p className="change-text">{ch.after ?? ch.before ?? ''}</p>
            {ch.reason && <p className="small muted">为什么：{ch.reason}</p>}
          </li>
        ))}
      </ul>
      {hidden > 0 && <p className="small muted">另有 {hidden} 条改动，完整 diff 见“进化记录”（后续批次）。</p>}
    </div>
  );
}

/** 保留上一代是正常结果：门禁按设计拦下了没有更好的候选。 */
function KeptPrevious({ evo }: { evo: EvolutionView }) {
  return (
    <div className="learned">
      <div className="kept">
        <strong>本次学习没有改动：候选都没过门禁，继续使用 {evo.from_version}</strong>
        <p className="small">这是门禁的正常结果，不是故障。没有通过验证的改动不会进入 playbook。</p>
      </div>
      <ul className="cand-reasons">
        {evo.candidates.map((c) => (
          <li key={c.id}>
            <strong>{c.id}</strong> {c.summary && <span className="small muted">{c.summary}</span>}
            <ul className="small">
              {blockReasons(c, evo).map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
}
