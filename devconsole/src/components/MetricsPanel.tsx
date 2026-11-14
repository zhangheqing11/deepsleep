import type { ExperimentManifest } from '../api/extensionTypes';
import type { ReportView } from '../api/validate';
import type { ExperimentData, RunData } from '../hooks/useExperimentData';
import { pct, pointDelta } from '../lib/format';
import { label, VETO_CODE_LABEL } from '../lib/labels';
import { pointDiff, redLineFailed, redLines, ROLE_TITLE, type RunKey } from '../model/overview';
import { Badge, errorText } from './common';

/** ① 比什么指标：对照与运行 2 紧挨着作主要对比（同一批 B 组来访），运行 1 只作背景。 */
export function MetricsPanel({ m, data }: { m: ExperimentManifest; data: ExperimentData }) {
  const r = (k: RunKey) => data.runs[k].report.data;
  const control = r('control');
  const run2 = r('run2');
  const diff = pointDiff(control?.metrics.isi_response_rate, run2?.metrics.isi_response_rate);

  return (
    <section className="panel" aria-labelledby="q1">
      <h2 id="q1">
        <span className="q">①</span>比什么指标
        <span className="small muted">主指标：4 周模拟 ISI 有效率</span>
      </h2>

      <div className="headline">
        <BigNumber k="control" m={m} run={data.runs.control} />
        <div className="delta" aria-label="运行 2 相对对照">
          <span className={`delta-value ${diff === null ? 'delta-empty' : ''}`}>{diff === null ? '暂无' : pointDelta(diff / 100)}</span>
          <span className="small muted">运行 2 − 对照</span>
        </div>
        <BigNumber k="run2" m={m} run={data.runs.run2} />
      </div>
      <div className="background-run">
        <SmallNumber k="run1" m={m} run={data.runs.run1} />
        <p className="small muted">
          对照与运行 2 用的是同一批 B 组模拟来访，只换了 playbook 版本，差值才是学习带来的变化。运行 1 用的是另一批（A 组）来访，只作背景，不能当成同一批人的前后对比。
        </p>
      </div>

      <table className="metric-table">
        <caption className="sr-only">副指标</caption>
        <thead>
          <tr>
            <th scope="col">副指标</th>
            {(['run1', 'control', 'run2'] as const).map((k) => (
              <th scope="col" key={k} className={`role-${k}`}>
                {ROLE_TITLE[k]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <MetricRow name="路径准确率（第 2 轮）" get={(x) => pct(x.metrics.path_acc_r2)} r={r} />
          <MetricRow name="路径准确率增幅（第 1→2 轮）" get={(x) => pointDelta(x.metrics.path_acc_gain)} r={r} />
          <MetricRow name="转介召回率" get={(x) => pct(x.metrics.referral_recall)} r={r} />
          <MetricRow name="转介精确率" get={(x) => pct(x.metrics.referral_precision)} r={r} />
        </tbody>
      </table>

      <RedLines r={r} />

      <p className="caliber small muted">
        口径：模拟 4 周 ISI 下降 &gt; 7 分的来访占比；来访为模拟数据，非真实用户；4 周 ISI 由规则状态模型模拟。样本量较小，差异未做显著性检验。
      </p>
    </section>
  );
}

function sub(m: ExperimentManifest, k: RunKey, report: ReportView | null): string {
  const split = report?.split ?? m[k].split;
  const version = report?.playbook_version ?? m[k].playbook_version ?? '版本待定';
  return `${split} 组 · ${version}`;
}

function pendingText(run: RunData, state: string): string {
  if (run.report.error && !run.report.data) return errorText(run.report.error);
  if (state === 'failed') return '运行失败，没有报告';
  if (state === 'done') return '报告读取中…';
  return '尚未生成';
}

function BigNumber({ k, m, run }: { k: RunKey; m: ExperimentManifest; run: RunData }) {
  const report = run.report.data;
  const partial = run.state.data?.partial_metrics?.isi_response_rate;
  const progress = run.state.data?.progress;
  return (
    <div className={`big role-${k}`}>
      <div className="big-label">
        <strong>{ROLE_TITLE[k]}</strong>
        <span className="small muted">{sub(m, k, report)}</span>
      </div>
      {report ? (
        <>
          <div className="big-value">{pct(report.metrics.isi_response_rate)}</div>
          <div className="small muted">n = {report.n_visitors} 个模拟来访</div>
        </>
      ) : (
        <>
          <div className="big-value big-empty">{pendingText(run, m[k].state)}</div>
          {partial !== undefined && progress && (
            <div className="small">
              <Badge tone="warn">阶段统计</Badge> 已完成 {progress.completed ?? '—'} / {progress.total}：{pct(partial)}（不是最终指标）
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SmallNumber({ k, m, run }: { k: RunKey; m: ExperimentManifest; run: RunData }) {
  const report = run.report.data;
  return (
    <div className={`small-number role-${k}`}>
      <strong>{ROLE_TITLE[k]}</strong>
      <span className="small muted">{sub(m, k, report)}</span>
      <span className="small-number-value">{report ? pct(report.metrics.isi_response_rate) : pendingText(run, m[k].state)}</span>
      {report && <span className="small muted">n = {report.n_visitors}</span>}
    </div>
  );
}

function MetricRow({
  name,
  get,
  r,
}: {
  name: string;
  get: (x: ReportView) => string;
  r: (k: RunKey) => ReportView | null;
}) {
  return (
    <tr>
      <th scope="row">{name}</th>
      {(['run1', 'control', 'run2'] as const).map((k) => {
        const x = r(k);
        return <td key={k}>{x ? get(x) : <span className="muted">尚未生成</span>}</td>;
      })}
    </tr>
  );
}

/** 红线：危机漏报、违反禁忌、否决规则。任何一项不过都醒目显示并列出原因，不隐藏。 */
function RedLines({ r }: { r: (k: RunKey) => ReportView | null }) {
  const keys = ['run1', 'control', 'run2'] as const;
  const failing = keys.filter((k) => {
    const x = r(k);
    return x !== null && redLineFailed(x);
  });
  return (
    <div className={`redlines ${failing.length ? 'redlines-fail' : ''}`} role={failing.length ? 'alert' : undefined}>
      <div className="redlines-head">
        <strong>安全红线</strong>
        <span className="small muted">危机识别是冻结规则层，不参与进化</span>
      </div>
      <table className="metric-table">
        <caption className="sr-only">安全红线</caption>
        <tbody>
          {(['crisis_missed', 'contraindication_violations', 'veto'] as const).map((key, i) => (
            <tr key={key}>
              <th scope="row">{['危机漏报（须为 0）', '违反禁忌（须为 0）', '否决规则'][i]}</th>
              {keys.map((k) => {
                const x = r(k);
                if (!x) return <td key={k} className="muted">尚未生成</td>;
                const line = redLines(x).find((l) => l.key === key)!;
                return (
                  <td key={k}>
                    {line.ok === null ? (
                      <span className="muted">暂无</span>
                    ) : (
                      <Badge tone={line.ok ? 'ok' : 'danger'}>{line.ok ? `✓ ${line.value}` : `✗ ${line.value}`}</Badge>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {failing.map((k) => {
        const x = r(k)!;
        return (
          <p key={k} className="redline-reason small">
            <strong>{ROLE_TITLE[k]}未通过红线：</strong>
            {x.veto.reasons.length
              ? x.veto.reasons.map((v) => `${label(VETO_CODE_LABEL, v.code)}${v.message ? `（${v.message}）` : ''}`).join('；')
              : redLines(x)
                  .filter((l) => l.ok === false)
                  .map((l) => `${l.label}：${l.value}`)
                  .join('；')}
          </p>
        );
      })}
    </div>
  );
}
