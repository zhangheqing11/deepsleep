import type { ReactNode } from 'react';
import type { Metrics, RunReport } from '../api/contractTypes';
import type { RunStatusResponse } from '../api/draftTypes';
import { sessionHref } from '../hooks/useHashRoute';
import { dateTime, pct, pointDelta, seconds, signed } from '../lib/format';
import {
  CRISIS_LABEL,
  FAILURE_TAG_LABEL,
  PATH_LABEL,
  REFERRAL_LABEL,
  VETO_CODE_LABEL,
  label,
} from '../lib/labels';
import { Badge, KeyValue, Notice } from './common';

function Metric({
  title,
  value,
  hint,
  tone,
}: {
  title: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: 'danger' | 'ok';
}) {
  return (
    <div className={`metric ${tone ? `metric-${tone}` : ''}`}>
      <div className="metric-title">{title}</div>
      <div className="metric-value">{value}</div>
      {hint && <div className="metric-hint">{hint}</div>}
    </div>
  );
}

/** 结论：主指标、路径准确率、危机漏报，放在报告最上面 */
function Headline({ m }: { m: Metrics }) {
  return (
    <div className="headline">
      <Metric
        title="4 周模拟 ISI 有效率"
        value={pct(m.isi_response_rate)}
        hint={<>ISI 下降 &gt; 7 分的来访占比</>}
      />
      <Metric
        title="路径准确率 · 第 2 轮"
        value={pct(m.path_acc_r2)}
        hint={<>第 1 轮 {pct(m.path_acc_r1)} · 提升 {pointDelta(m.path_acc_gain)}</>}
      />
      <Metric
        title="危机漏报"
        value={`${m.crisis_missed} 例`}
        tone={m.crisis_missed > 0 ? 'danger' : undefined}
        hint={`危机召回率 ${pct(m.crisis_recall)}`}
      />
    </div>
  );
}

/** 其余指标：默认收起 */
function MoreMetrics({ m }: { m: Metrics }) {
  return (
    <div className="metric-grid">
      <Metric title="平均 ISI 变化" value={`${signed(m.mean_isi_change)} 分`} />
      <Metric title="转介召回率" value={pct(m.referral_recall)} />
      <Metric title="转介精确率" value={pct(m.referral_precision)} />
      <Metric
        title="分类召回率"
        value={
          <span className="metric-split">
            <span>R1 {pct(m.referral_recall_by_label.R1)}</span>
            <span>R2 {pct(m.referral_recall_by_label.R2)}</span>
            <span>R3 {pct(m.referral_recall_by_label.R3)}</span>
          </span>
        }
      />
      <Metric title="补筛覆盖率" value={pct(m.screening_coverage)} hint="未自评的转介阳性来访中，agent 补做筛查的占比" />
      <Metric
        title="违反禁忌"
        value={`${m.contraindication_violations} 例`}
        tone={m.contraindication_violations > 0 ? 'danger' : undefined}
      />
    </div>
  );
}

function VetoPanel({ veto }: { veto: RunReport['veto'] }) {
  if (veto.passed) {
    return <Notice tone="ok" title="安全与否决规则检查：通过" />;
  }
  return (
    <Notice tone="danger" title="安全与否决规则检查：未通过（业务检查结果，不是请求错误）">
      <ul className="plain-list">
        {veto.reasons.map((r, i) => (
          <li key={i}>
            <strong>{label(VETO_CODE_LABEL, r.code)}</strong>：{r.message}
          </li>
        ))}
      </ul>
    </Notice>
  );
}

function PerVisitorTable({ report, sessionVisitors }: { report: RunReport; sessionVisitors: Set<string> }) {
  return (
    <div className="table-wrap" tabIndex={0} aria-label="逐个来访结果，可横向滚动">
      <table className="table">
        <thead>
          <tr>
            <th>来访</th>
            <th>参考路径</th>
            <th>第 1 轮判断</th>
            <th>第 2 轮判断</th>
            <th>参考转介</th>
            <th>转介判断</th>
            <th>危机（参考 / 判断）</th>
            <th>ISI 第 0 → 4 周</th>
            <th>有效</th>
            <th>问题标签</th>
            <th>会谈</th>
          </tr>
        </thead>
        <tbody>
          {report.per_visitor.map((r) => (
            <tr key={r.visitor_id}>
              <td className="mono">{r.visitor_id}</td>
              <td title={PATH_LABEL[r.main_path]}>{r.main_path}</td>
              <td className={r.path_pred_r1 === r.main_path ? 'hit' : 'miss'} title={PATH_LABEL[r.path_pred_r1]}>
                {r.path_pred_r1}
              </td>
              <td className={r.path_pred_r2 === r.main_path ? 'hit' : 'miss'} title={PATH_LABEL[r.path_pred_r2]}>
                {r.path_pred_r2}
              </td>
              <td title={REFERRAL_LABEL[r.referral_true]}>{r.referral_true}</td>
              <td className={r.referral_pred === r.referral_true ? 'hit' : 'miss'} title={REFERRAL_LABEL[r.referral_pred]}>
                {r.referral_pred}
              </td>
              <td>
                {CRISIS_LABEL[r.crisis_true]} / {CRISIS_LABEL[r.crisis_pred]}
              </td>
              <td className="nowrap">
                {r.isi_week[0]} → {r.isi_week[r.isi_week.length - 1]}（{signed(r.isi_change, 0)}）
              </td>
              <td>{r.responder ? '是' : '否'}</td>
              <td>
                {r.failure_tags.length === 0 ? (
                  <span className="muted">—</span>
                ) : (
                  <span className="tags">
                    {r.failure_tags.map((t) => (
                      <Badge key={t} tone="warn">
                        {label(FAILURE_TAG_LABEL, t)}
                      </Badge>
                    ))}
                  </span>
                )}
              </td>
              <td>
                {sessionVisitors.has(r.visitor_id) ? (
                  <a href={sessionHref(report.run_id, r.visitor_id)}>查看</a>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ReportView({
  report,
  run,
  sessionVisitors,
}: {
  report: RunReport;
  run: RunStatusResponse | null;
  sessionVisitors: Set<string>;
}) {
  const incomplete = run?.status === 'failed';
  const m = report.metrics;
  // 有风险时把相关内容默认展开，不靠折叠“制造简洁”
  const hasRisk = m.contraindication_violations > 0 || !report.veto.passed;
  return (
    <section className="section report">
      <div className="section-head">
        <h2>报告 · {report.label}</h2>
        <span className="row small muted">
          <span>
            {report.split} 组 · {report.playbook_version} · {report.n_visitors} 个来访
          </span>
          <Badge>{`契约 ${report.schema_version}`}</Badge>
        </span>
      </div>

      {incomplete && (
        <Notice tone="warn" title="不完整报告，不可用于正式比较">
          该运行以失败结束，后端保留了部分结果。是否计入比较由评分规则决定，这里仅供查看。
        </Notice>
      )}

      <Headline m={m} />
      <VetoPanel veto={report.veto} />

      <details className="fold" open={hasRisk}>
        <summary>其余指标</summary>
        <MoreMetrics m={m} />
      </details>

      <details className="fold">
        <summary>逐个来访结果与评测参考答案（{report.per_visitor.length} 个，运行后分析）</summary>
        <p className="small muted">
          “参考路径 / 参考转介”是模拟来访的评测标签，只在运行结束后的分析中展示，会谈中的 agent 看不到。
        </p>
        <PerVisitorTable report={report} sessionVisitors={sessionVisitors} />
      </details>

      <details className="fold">
        <summary>运行信息与安全层统计</summary>
        <KeyValue
          items={[
            ['运行编号', <span className="mono">{report.run_id}</span>],
            ['耗时', seconds(report.duration_s)],
            ['生成时间', dateTime(report.created_at)],
            ['模型', `会谈 ${report.models.agent} · 来访 ${report.models.visitor} · 判断器 ${report.models.judge}`],
            ['判断器', report.safety_summary.judge_provider],
            ['判断器调用', `${report.safety_summary.judge_calls} 次（降级 ${report.safety_summary.judge_fallbacks} 次）`],
            ['安全确认', `${report.safety_summary.safety_checks} 次`],
            ['危机流程', `${report.safety_summary.crisis_protocols} 次`],
          ]}
        />
      </details>
    </section>
  );
}
