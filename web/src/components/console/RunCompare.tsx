import { useEffect, useState, type ReactNode } from 'react';
import { api } from '../../api';
import type { Experiment } from '../../api/extensionTypes';
import type { Metrics, RunReport } from '../../api/contractTypes';
import { useResource, type ResourceState } from '../../hooks/useResource';
import { pct, pointDelta, signed } from '../../lib/format';
import type { RunHistoryEntry } from '../../lib/storage';
import { Badge, Card, ErrorNotice, Notice, Spinner } from '../common';

type Better = 'higher' | 'lower' | null;

interface Row {
  title: string;
  get: (m: Metrics) => number | null;
  fmt: (v: number | null) => ReactNode;
  better: Better;
  primary?: boolean;
}

const count = (v: number | null) => (v === null ? '暂无' : `${v} 例`);

const ROWS: Row[] = [
  { title: '4 周模拟 ISI 有效率', get: (m) => m.isi_response_rate, fmt: pct, better: 'higher', primary: true },
  { title: '平均 ISI 变化（分）', get: (m) => m.mean_isi_change, fmt: (v) => (v === null ? '暂无' : signed(v)), better: 'lower' },
  { title: '路径准确率 · 第 1 轮', get: (m) => m.path_acc_r1, fmt: pct, better: 'higher' },
  { title: '路径准确率 · 第 2 轮', get: (m) => m.path_acc_r2, fmt: pct, better: 'higher' },
  { title: '第 2 轮较第 1 轮', get: (m) => m.path_acc_gain, fmt: pointDelta, better: 'higher' },
  { title: '转介召回率', get: (m) => m.referral_recall, fmt: pct, better: 'higher' },
  { title: '转介精确率', get: (m) => m.referral_precision, fmt: pct, better: 'higher' },
  { title: '危机漏报', get: (m) => m.crisis_missed, fmt: count, better: 'lower' },
  { title: '危机召回率', get: (m) => m.crisis_recall, fmt: pct, better: 'higher' },
  { title: '补筛覆盖率', get: (m) => m.screening_coverage, fmt: pct, better: 'higher' },
  { title: '违反禁忌', get: (m) => m.contraindication_violations, fmt: count, better: 'lower' },
];

function winner(a: number | null, b: number | null, better: Better): 'left' | 'right' | null {
  if (a === null || b === null || better === null || a === b) return null;
  if (better === 'higher') return a > b ? 'left' : 'right';
  return a < b ? 'left' : 'right';
}

function useReportFor(runId: string) {
  const state = useResource<RunReport>(runId ? `compare:${runId}` : null, (signal) => api.getReport(runId, signal));
  // 切换选择时，旧报告不能短暂冒充新列的结果。
  return state.status === 'ok' && state.data.run_id !== runId
    ? { status: 'loading' as const, reload: state.reload }
    : state;
}

function ColumnHead({ state }: { state: ResourceState<RunReport> }) {
  if (state.status !== 'ok') return <span className="muted">暂无</span>;
  const r = state.data;
  return (
    <span className="compare-head">
      <strong>{r.label}</strong>
      <span className="small muted">
        {r.split} 组 · {r.playbook_version} · {r.n_visitors} 个来访
      </span>
    </span>
  );
}

/** 实验按运行 1 / 对照 / 运行 2 排列；差值只比较相邻的对照与运行 2。 */
export function RunCompare({ history, sourceNote, experiment }: {
  history: RunHistoryEntry[]; sourceNote: string; experiment?: Experiment | null;
}) {
  const candidates = history.filter((h) => h.status !== 'not_found');
  const [first, setFirst] = useState('');
  const [control, setControl] = useState('');
  const [second, setSecond] = useState('');
  useEffect(() => {
    if (experiment) {
      setFirst(experiment.run1?.run_id ?? '');
      setControl(experiment.control?.run_id ?? '');
      setSecond(experiment.run2?.run_id ?? '');
    }
  }, [experiment]);
  const a = useReportFor(first);
  const b = useReportFor(control);
  const c = useReportFor(second);
  const columns = [a, b, c];
  const titles = ['运行 1', '对照', '运行 2'];
  const both = b.status === 'ok' && c.status === 'ok';
  const sameSplit = both && b.data.split === c.data.split;
  const sameRun = both && b.data.run_id === c.data.run_id;
  return <Card title="运行对比" aside={<Badge>三方对比</Badge>}>
    <div className="compare-pickers">
      {([first, control, second]).map((value, i) => <div className="field" key={titles[i]}>
        <label htmlFor={`compare-${i}`}>{titles[i]}</label>
        <select id={`compare-${i}`} value={value} onChange={(e) => [setFirst, setControl, setSecond][i](e.target.value)}>
          <option value="">选择运行…</option>
          {value && !candidates.some((h) => h.run_id === value) && <option value={value}>{value}</option>}
          {candidates.map((h) => <option key={h.run_id} value={h.run_id}>{h.run_id} · {h.split} 组 · {h.playbook_version}</option>)}
        </select>
      </div>)}
    </div>
    {columns.map((state, i) => state.status === 'error' ? <ErrorNotice key={i} error={state.error} title={`${titles[i]}的报告读取失败`} action={<button type="button" className="btn btn-sm" onClick={state.reload}>重新读取</button>} /> : null)}
    {columns.some((state) => state.status === 'loading') && <Spinner label="正在读取报告…" />}
    {both && !sameSplit && <Notice tone="warn" title="两次运行的来访分组不同">对照与运行 2 的来访分组不同，差值不能直接说明学习效果。</Notice>}
    {sameRun && <Notice tone="warn" title="对照与运行 2 选择了同一次运行" />}
    {both && sameSplit && !sameRun && <Notice tone="info" title={`同一组来访（${b.data.split} 组）上的版本对比：${b.data.playbook_version} 与 ${c.data.playbook_version}`} />}
    {columns.some((s) => s.status === 'ok' && !s.data.veto.passed) && <Notice tone="danger" title="有运行未通过否决规则检查，请先查看该运行报告中的否决原因" />}
    <div className="table-wrap" tabIndex={0} aria-label="指标对比">
      <table className="table compare-table">
        <thead><tr><th>指标</th>{columns.map((state, i) => <th key={titles[i]}>{titles[i]}<ColumnHead state={state} /></th>)}<th>差值（运行 2 − 对照）</th></tr></thead>
        <tbody>
          {ROWS.map((row) => {
            const values = columns.map((state) => state.status === 'ok' ? row.get(state.data.metrics) : null);
            const better = sameSplit && !sameRun ? winner(values[1], values[2], row.better) : null;
            const delta = metricDifference(values[2], values[1]);
            return <tr key={row.title} className={row.primary ? 'primary-row' : ''}>
              <td>{row.title}</td>
              {values.map((value, i) => <td key={i} className={(i === 1 && better === 'left') || (i === 2 && better === 'right') ? 'better' : ''}>{value === null ? '暂无' : row.fmt(value)}</td>)}
              <td>{delta === null ? '暂无' : row.fmt === pct || row.fmt === pointDelta ? pointDelta(delta) : `${signed(delta)} ${row.fmt === count ? '例' : '分'}`}</td>
            </tr>;
          })}
          <tr><td>否决规则检查</td>{columns.map((s, i) => <td key={i}>{s.status === 'ok' ? s.data.veto.passed ? '通过' : '未通过' : '暂无'}</td>)}<td>—</td></tr>
        </tbody>
      </table>
    </div>
    <p className="small muted">数据来源：{sourceNote}。差值为运行 2 减对照；比例用百分点、ISI 用分、计数用例。任一指标缺失时显示“暂无”。运行 1 与 B 组的数值仅并排展示。</p>
    {sourceNote.startsWith('模拟数据') && <p className="small muted">模拟数据是固定示例，数值高低不代表真实学习效果。</p>}
  </Card>;
}

export function metricDifference(value: number | null | undefined, baseline: number | null | undefined): number | null {
  return value == null || baseline == null ? null : value - baseline;
}
