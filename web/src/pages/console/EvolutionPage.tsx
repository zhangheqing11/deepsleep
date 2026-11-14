import { useEffect, useState } from 'react';
import { api } from '../../api';
import { toApiError } from '../../api/errors';
import type { EvolutionStatus } from '../../api/extensionTypes';
import { useReadPoller } from '../../hooks/useReadPoller';
import { useResource } from '../../hooks/useResource';
import type { Evolution, EvolutionCandidate, Metrics } from '../../api/contractTypes';
import { Badge, Card, ErrorNotice, KeyValue, Notice, Spinner } from '../../components/common';
import { dateTime, pct, signed } from '../../lib/format';
import {
  STEP_STATE_LABEL,
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

export function EvolutionDetail({ evo }: { evo: Evolution }) {
  const chosen = evo.candidates.find((c) => c.id === evo.chosen) ?? null;
  const reviewByChange = new Map(evo.human_review.map((r) => [r.change_id, r]));
  const committed = evo.outcome === 'committed';

  return (
    <>
      <Card
        title={
          <>
            进化记录 · {evo.from_version} → {evo.to_version ?? evo.from_version}
          </>
        }
        aside={committed ? <Badge tone="ok">生成新版本</Badge> : <Badge tone="warn">保留上一代</Badge>}
      >
        {!committed && (
          <Notice tone="info" title="本次学习保留上一代 playbook">
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
    </>
  );
}


export function EvolutionPage() {
  const list = useResource('evolutions', (signal) => api.listEvolutions(20, signal));
  const [selected, setSelected] = useState('');
  const items = list.status === 'ok' ? [...list.data.items].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)) : [];
  const id = items.some((item) => item.evolution_id === selected) ? selected : items[0]?.evolution_id ?? '';
  return <div className="page">
    <div className="page-title-row"><div><h1>进化记录</h1><p className="muted">改了什么、为什么允许生效、如何保留或回退旧版本。</p></div>
      <button type="button" className="btn btn-sm" onClick={list.reload}>刷新进化记录</button>
    </div>
    {api.adapter === 'mock' && <p className="source-note">模拟数据 · 进化来自契约示例；版本元数据为占位，正文仅含差异片段。</p>}
    {list.status === 'error' && <ErrorNotice error={list.error} title="进化列表读取失败" />}
    {list.status === 'loading' && <Spinner label="正在读取进化记录…" />}
    {list.status === 'ok' && items.length === 0 && <p className="muted">暂无进化记录。</p>}
    {items.length > 0 && <div className="field"><label htmlFor="evolution-id">选择进化记录</label>
      <select id="evolution-id" value={id} onChange={(e) => setSelected(e.target.value)}>
        {items.map((item) => <option key={item.evolution_id} value={item.evolution_id}>{item.evolution_id} · {item.from_version} → {item.to_version ?? item.from_version} · {dateTime(item.created_at)}</option>)}
      </select>
    </div>}
    {id ? <EvolutionRecord key={id} id={id} /> : <PlaybookVersions refreshKey="initial" />}
  </div>;
}

export async function readEvolution(id: string, signal: AbortSignal): Promise<{ evolution: Evolution | null; status: EvolutionStatus | null }> {
  try {
    return { evolution: await api.getEvolution(id, signal), status: null };
  } catch (e) {
    const error = toApiError(e);
    if (error.status !== 404 || error.code !== 'NOT_READY') throw e;
    return { evolution: null, status: await api.getEvolutionStatus(id, signal) };
  }
}

function EvolutionRecord({ id }: { id: string }) {
  const poller = useReadPoller(id, (signal) => readEvolution(id, signal),
    (data) => data.evolution !== null || data.status?.phase === 'failed');
  const { data, error, polling, reload } = poller;
  return <>
    {error && <ErrorNotice error={error} title={polling ? '连接中断，正在自动重试' : '进化记录读取失败'} action={<button type="button" className="btn btn-sm" onClick={reload}>重新读取</button>} />}
    {!data && !error && <Spinner label="正在读取进化记录…" />}
    {data?.status && <EvolutionProgress status={data.status} />}
    {data?.evolution && <EvolutionDetail evo={data.evolution} />}
    <PlaybookVersions refreshKey={`${id}:${data?.evolution?.outcome ?? data?.status?.phase ?? ''}`} />
  </>;
}

export function EvolutionProgress({ status }: { status: EvolutionStatus }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (status.review.state !== 'waiting') return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [status.review.state, status.review.deadline]);
  const deadline = status.review.deadline ? Date.parse(status.review.deadline) : NaN;
  const remaining = Number.isFinite(deadline) ? Math.max(0, Math.ceil((deadline - now) / 1000)) : null;
  return <Card title="学习进度" aside={<Badge>{label(STEP_STATE_LABEL, status.phase)}</Badge>}>
    {status.phase === 'failed' && <Notice tone="danger" title="学习执行失败">{status.error}</Notice>}
    {status.reflector.fell_back && <Notice tone="warn" title="反思器自动降级">{status.reflector.model}</Notice>}
    <ol className="flow" aria-label="学习流程">
      <li><span className="flow-step">1</span><div><strong>反思</strong><div>{label(STEP_STATE_LABEL, status.reflector.state)}</div><div className="small mono">{status.reflector.model}</div></div></li>
      <li><span className="flow-step">2</span><div><strong>候选验证</strong><div>基线：{label(STEP_STATE_LABEL, status.validation.baseline)}</div>
        {(['c1', 'c2', 'c3'] as const).map((id) => <div key={id}>{id}：{label(STEP_STATE_LABEL, status.validation.candidates[id] ?? 'pending')}</div>)}</div></li>
      <li><span className="flow-step">3</span><div><strong>审核窗口</strong><div>{label(STEP_STATE_LABEL, status.review.state)}</div>
        {status.review.state === 'waiting' && <>
          <div>{remaining === null ? '审核截止时间暂无' : remaining > 0 ? `距审核截止 ${remaining} 秒` : '审核窗口已到期，等待后端确认'}</div>
          {status.review.deadline && <div className="small">截止时间：{status.review.deadline}</div>}
          <div className="small">待审核改动：{status.review.pending_changes}</div>
        </>}</div></li>
      <li><span className="flow-step">4</span><div><strong>提交</strong><div>{status.phase === 'done' ? '已完成' : status.phase === 'committing' ? '进行中' : status.phase === 'failed' ? '执行失败' : '等待中'}</div></div></li>
    </ol>
  </Card>;
}

function PlaybookVersions({ refreshKey }: { refreshKey: string }) {
  const list = useResource(`versions:${refreshKey}`, (signal) => api.listPlaybookVersions(signal));
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const items = list.status === 'ok' ? [...list.data.items].sort((a, b) => Number(a.version.slice(1)) - Number(b.version.slice(1))) : [];
  const fromVersion = items.some((v) => v.version === from) ? from : items[0]?.version ?? '';
  const toVersion = items.some((v) => v.version === to) ? to : items.find((v) => v.is_head)?.version ?? items[items.length - 1]?.version ?? '';
  return <Card title="playbook 版本树" aside={<button type="button" className="btn btn-sm" onClick={list.reload}>刷新版本</button>}>
    {list.status === 'error' && <ErrorNotice error={list.error} title="版本列表读取失败" />}
    {list.status === 'loading' && <Spinner label="正在读取版本…" />}
    {list.status === 'ok' && items.length === 0 && <p className="muted">暂无版本记录。</p>}
    <ol className="plain-list" aria-label="版本历史">
      {items.map((v) => <li key={v.version}><strong>{v.version}</strong> {v.is_head && <Badge tone="ok">当前版本</Badge>} · <span className="mono">{v.sha.slice(0, 12)}</span> · {v.author} · {dateTime(v.committed_at)}<p className="small">{v.message}</p></li>)}
    </ol>
    {items.length > 0 && <>
      <div className="compare-pickers">
        {([['差异起始版本', fromVersion, setFrom], ['差异目标版本', toVersion, setTo]] as const).map(([title, value, change], i) => <div className="field" key={title}><label htmlFor={`version-${i}`}>{title}</label><select id={`version-${i}`} value={value} onChange={(e) => change(e.target.value)}>{items.map((v) => <option key={v.version}>{v.version}</option>)}</select></div>)}
      </div>
      <VersionDiff key={`${fromVersion}:${toVersion}`} from={fromVersion} to={toVersion} />
    </>}
  </Card>;
}
function VersionDiff({ from, to }: { from: string; to: string }) {
  const diff = useResource(`diff:${from}:${to}`, (signal) => api.getPlaybookDiff(from, to, signal));
  const [showText, setShowText] = useState(false);
  return <>
    {diff.status === 'loading' && <Spinner label="正在读取版本差异…" />}
    {diff.status === 'error' && <ErrorNotice error={diff.error} title="版本差异读取失败" action={<button type="button" className="btn btn-sm" onClick={diff.reload}>重新读取</button>} />}
    {diff.status === 'ok' && (diff.data.diff ? <DiffView diff={diff.data.diff} /> : <p className="muted">两个版本没有差异。</p>)}
    <details className="fold" onToggle={(e) => setShowText(e.currentTarget.open)}><summary>目标版本正文 · {to}</summary>{showText && <PlaybookText version={to} />}</details>
  </>;
}
function PlaybookText({ version }: { version: string }) {
  const text = useResource(`playbook:${version}`, (signal) => api.getPlaybook(version, signal));
  return <>
    {text.status === 'loading' && <Spinner label="正在读取版本正文…" />}
    {text.status === 'error' && <ErrorNotice error={text.error} title="版本正文读取失败" />}
    {text.status === 'ok' && <pre className="diff">{text.data.text}</pre>}
  </>;
}
