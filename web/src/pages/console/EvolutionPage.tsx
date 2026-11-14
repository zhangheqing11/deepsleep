// 进化记录：静态展示契约示例 contracts/examples/evolution.v1-v2.json。
// 学习 / 版本 / 回滚接口尚未确定，这里不发请求、不提供任何操作按钮。

import evolutionExample from '../../../../contracts/examples/evolution.v1-v2.json';
import type { Evolution, EvolutionCandidate, Metrics } from '../../api/contractTypes';
import { Badge, Card, KeyValue, Notice } from '../../components/common';
import { dateTime, pct, signed } from '../../lib/format';
import {
  CHANGE_OP_LABEL,
  CRITICALITY_LABEL,
  FAILURE_TAG_LABEL,
  FEEDBACK_SOURCE_LABEL,
  FEEDBACK_STATUS_LABEL,
  REVIEW_DECISION_LABEL,
  SECTION_LABEL,
  VETO_CODE_LABEL,
  label,
} from '../../lib/labels';

const evo = evolutionExample as unknown as Evolution;

const METRIC_ROWS: { title: string; get: (m: Metrics) => number | null; fmt: (v: number | null) => string }[] = [
  { title: '4 周模拟 ISI 有效率', get: (m) => m.isi_response_rate, fmt: pct },
  { title: '平均 ISI 变化', get: (m) => m.mean_isi_change, fmt: (v) => (v === null ? '暂无' : `${signed(v)} 分`) },
  { title: '路径准确率 · 第 2 轮', get: (m) => m.path_acc_r2, fmt: pct },
  { title: '转介召回率', get: (m) => m.referral_recall, fmt: pct },
  { title: '转介精确率', get: (m) => m.referral_precision, fmt: pct },
  { title: '危机漏报', get: (m) => m.crisis_missed, fmt: (v) => (v === null ? '暂无' : `${v} 例`) },
];

function CandidateStatus({ c, chosen }: { c: EvolutionCandidate; chosen: string | null }) {
  if (c.id === chosen) return <Badge tone="ok">已选中</Badge>;
  if (c.hard_rule_violations.length > 0) return <Badge tone="danger">硬规则拦下</Badge>;
  if (!c.passed) return <Badge tone="warn">未通过门禁</Badge>;
  return <Badge tone="info">通过，未选中</Badge>;
}

function DiffView({ diff }: { diff: string }) {
  return (
    <pre className="diff" aria-label="playbook 差异">
      {diff.split('\n').map((line, i) => {
        const cls = line.startsWith('+++') || line.startsWith('---')
          ? 'diff-meta'
          : line.startsWith('@@')
            ? 'diff-hunk'
            : line.startsWith('+')
              ? 'diff-add'
              : line.startsWith('-')
                ? 'diff-del'
                : '';
        return (
          <span key={i} className={`diff-line ${cls}`}>
            {line || ' '}
          </span>
        );
      })}
    </pre>
  );
}

export function EvolutionPage() {
  const chosen = evo.candidates.find((c) => c.id === evo.chosen) ?? null;
  const reviewByChange = new Map(evo.human_review.map((r) => [r.change_id, r]));
  const committed = evo.outcome === 'committed';

  return (
    <div className="page">
      <div className="page-title-row">
        <div>
          <h1>进化记录</h1>
          <p className="muted">改了什么、为什么允许生效、如何保留或回退旧版本。</p>
        </div>
      </div>
      <p className="source-note" role="note">
        <strong>契约示例 · 静态展示</strong>
        内容来自 contracts/examples/evolution.v1-v2.json。学习任务接口尚未确定，这里没有发起学习或回滚的操作。
      </p>

      <Card
        title={
          <>
            进化记录 · {evo.from_version} → {evo.to_version ?? evo.from_version}
          </>
        }
        aside={committed ? <Badge tone="ok">生成新版本</Badge> : <Badge tone="warn">保留上一代</Badge>}
      >
        {!committed && (
          <Notice tone="info" title="所有候选都没有通过，继续使用上一代 playbook">
            这是正常的学习结果，不是系统故障。
          </Notice>
        )}
        <KeyValue
          items={[
            ['学习编号', <span className="mono">{evo.evolution_id}</span>],
            ['来源运行', <span className="mono">{evo.source_run_id}</span>],
            ['验证集', `${evo.val_split} 组`],
            ['时间', dateTime(evo.created_at)],
            [
              '反思器模型',
              <span className="tags">
                <span className="mono">{evo.reflector.model}</span>
                {evo.reflector.fell_back ? (
                  <Badge tone="warn">已自动降级</Badge>
                ) : (
                  <Badge tone="ok">未降级</Badge>
                )}
              </span>,
            ],
          ]}
        />
        {evo.reflector.fell_back && evo.reflector.fallback_reason && (
          <Notice tone="warn" title="反思器自动降级">
            {evo.reflector.fallback_reason}
          </Notice>
        )}

        <ol className="flow" aria-label="学习流程">
          <li>
            <span className="flow-step">1</span>
            <div>
              <strong>读取失败案例</strong>
              <div className="small muted">{evo.failures_used.length} 个来访</div>
            </div>
          </li>
          <li>
            <span className="flow-step">2</span>
            <div>
              <strong>参考人工意见</strong>
              <div className="small muted">
                {evo.human_feedback.filter((f) => f.status === 'approved' || f.status === 'edited').length} 条进入反思器
              </div>
            </div>
          </li>
          <li>
            <span className="flow-step">3</span>
            <div>
              <strong>提出 {evo.candidates.length} 份候选</strong>
              <div className="small muted">只做增量修改</div>
            </div>
          </li>
          <li>
            <span className="flow-step">4</span>
            <div>
              <strong>在 {evo.val_split} 组上验证</strong>
              <div className="small muted">主指标 + 否决规则 + 人工否决</div>
            </div>
          </li>
          <li>
            <span className="flow-step">5</span>
            <div>
              <strong>{committed ? `提交 ${evo.to_version}` : '保留上一代'}</strong>
              <div className="small muted">{chosen ? `选中 ${chosen.id}` : '无候选通过'}</div>
            </div>
          </li>
        </ol>
      </Card>

      <Card title="候选与验证结果">
        <div className="table-wrap" tabIndex={0} aria-label="候选验证指标">
          <table className="table">
            <thead>
              <tr>
                <th>指标（{evo.val_split} 组）</th>
                <th>基线 {evo.from_version}</th>
                {evo.candidates.map((c) => (
                  <th key={c.id}>候选 {c.id}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>门禁结果</td>
                <td>—</td>
                {evo.candidates.map((c) => (
                  <td key={c.id}>
                    <CandidateStatus c={c} chosen={evo.chosen} />
                  </td>
                ))}
              </tr>
              {METRIC_ROWS.map((row) => (
                <tr key={row.title}>
                  <td>{row.title}</td>
                  <td>{row.fmt(row.get(evo.baseline_val_metrics))}</td>
                  {evo.candidates.map((c) => (
                    <td key={c.id}>{c.val_metrics ? row.fmt(row.get(c.val_metrics)) : <span className="muted">未验证</span>}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="candidate-list">
          {evo.candidates.map((c) => (
            <details key={c.id} className="details" open={c.id === evo.chosen}>
              <summary>
                候选 {c.id} · {c.summary}
              </summary>
              {c.hard_rule_violations.map((v) => (
                <Notice key={v.change_id + v.code} tone="danger" title={`硬规则：${label(VETO_CODE_LABEL, v.code)}`}>
                  {v.message}
                </Notice>
              ))}
              {!c.veto.passed &&
                c.veto.reasons.map((r, i) => (
                  <Notice key={i} tone="warn" title={`否决规则：${label(VETO_CODE_LABEL, r.code)}`}>
                    {r.message}
                  </Notice>
                ))}
              <ul className="change-list">
                {c.changes.map((ch) => {
                  const review = reviewByChange.get(ch.id);
                  return (
                    <li key={ch.id}>
                      <div className="tags">
                        <Badge tone="info">{label(CHANGE_OP_LABEL, ch.op)}</Badge>
                        <Badge>{label(SECTION_LABEL, ch.section)}</Badge>
                        <Badge tone={ch.criticality === 'high' ? 'danger' : ch.criticality === 'medium' ? 'warn' : 'neutral'}>
                          关键度 {label(CRITICALITY_LABEL, ch.criticality)}
                        </Badge>
                        {review && (
                          <Badge tone={review.decision === 'reject' ? 'danger' : 'neutral'}>
                            人工审核：{label(REVIEW_DECISION_LABEL, review.decision)}
                          </Badge>
                        )}
                      </div>
                      {ch.before && <p className="change-before">{ch.before}</p>}
                      {ch.after && <p className="change-after">{ch.after}</p>}
                      <p className="small muted">理由：{ch.reason}</p>
                      {review?.comment && <p className="small">审核意见：{review.comment}</p>}
                    </li>
                  );
                })}
              </ul>
            </details>
          ))}
        </div>
      </Card>

      <Card title="playbook 差异" aside={chosen ? <Badge tone="ok">{`来自候选 ${chosen.id}`}</Badge> : undefined}>
        {evo.diff ? <DiffView diff={evo.diff} /> : <p className="muted">没有新版本，因此没有差异。</p>}
        {evo.commit ? (
          <KeyValue
            items={[
              ['版本库', <span className="mono">{evo.commit.repo}</span>],
              ['提交', <span className="mono">{evo.commit.sha.slice(0, 12)}</span>],
              ['提交者', evo.commit.author],
              ['说明', evo.commit.message],
            ]}
          />
        ) : (
          <p className="muted">本次没有提交新版本。</p>
        )}
        <p className="small muted">回退方式：每一代 playbook 是独立版本库里的一次提交，可以回到任一上一代。回滚操作接口确定后再接入。</p>
      </Card>

      <details className="fold">
        <summary>反思器读到的材料（{evo.failures_used.length} 个失败案例 · {evo.human_feedback.length} 条意见）</summary>
        <h3 className="h3">失败案例</h3>
        <ul className="plain-list">
          {evo.failures_used.map((f) => (
            <li key={f.visitor_id}>
              <span className="mono">{f.visitor_id}</span>：{f.failure_tags.map((t) => label(FAILURE_TAG_LABEL, t)).join('、')}
            </li>
          ))}
        </ul>
        <h3 className="h3">人工意见与自动批注</h3>
        <p className="small muted">只有“已确认”和“改写后确认”的条目会进入反思器。</p>
        <ul className="feedback-list">
          {evo.human_feedback.map((f) => (
            <li key={f.id}>
              <div className="tags">
                <Badge>{label(FEEDBACK_SOURCE_LABEL, f.source)}</Badge>
                <Badge tone={f.status === 'approved' || f.status === 'edited' ? 'ok' : 'neutral'}>
                  {label(FEEDBACK_STATUS_LABEL, f.status)}
                </Badge>
                {f.visitor_id && <span className="mono small">{f.visitor_id}</span>}
              </div>
              {f.text && <p>{f.text}</p>}
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
