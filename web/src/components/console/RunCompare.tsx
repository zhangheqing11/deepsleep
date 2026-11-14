import { useEffect, useState, type ReactNode } from 'react';
import { api } from '../../api';
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
  return useResource<RunReport>(runId ? `compare:${runId}` : null, (signal) => api.getReport(runId, signal));
}

function ColumnHead({ state }: { state: ResourceState<RunReport> }) {
  if (state.status !== 'ok') return <span className="muted">—</span>;
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

export function RunCompare({ history }: { history: RunHistoryEntry[] }) {
  const candidates = history.filter((h) => h.status !== 'not_found');
  const [left, setLeft] = useState('');
  const [right, setRight] = useState('');

  // 默认选最近的两次运行（历史按时间倒序，较早的放左边）
  useEffect(() => {
    if (!left && !right && candidates.length >= 2) {
      setLeft(candidates[1].run_id);
      setRight(candidates[0].run_id);
    }
  }, [candidates.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const a = useReportFor(left);
  const b = useReportFor(right);

  const select = (value: string, onChange: (v: string) => void, id: string, title: string) => (
    <div className="field">
      <label htmlFor={id}>{title}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">选择运行…</option>
        {candidates.map((h) => (
          <option key={h.run_id} value={h.run_id}>
            {h.run_id}
            {h.split ? ` · ${h.split} 组` : ''}
            {h.playbook_version ? ` · ${h.playbook_version}` : ''}
          </option>
        ))}
      </select>
    </div>
  );

  const both = a.status === 'ok' && b.status === 'ok';
  const sameSplit = both && a.data.split === b.data.split;

  return (
    <Card title="运行对比" aside={<Badge>并排展示</Badge>}>
      {candidates.length < 2 ? (
        <p className="muted">至少需要两次运行才能对比。可以先跑“A 组”“B 组”与“B 组 + v2”。</p>
      ) : (
        <>
          <div className="compare-pickers">
            {select(left, setLeft, 'compare-left', '左侧运行')}
            {select(right, setRight, 'compare-right', '右侧运行')}
          </div>

          {[a, b].map((s, i) =>
            s.status === 'error' ? (
              <ErrorNotice key={i} error={s.error} title={`${i === 0 ? '左侧' : '右侧'}运行的报告读取失败`} />
            ) : null,
          )}
          {(a.status === 'loading' || b.status === 'loading') && <Spinner label="正在读取报告…" />}

          {both && !sameSplit && (
            <Notice tone="warn" title="两次运行的来访分组不同">
              不同分组的来访不一样，指标高低不能直接说明版本好坏。同一组来访上的新旧版本对比（例如 B 组 v1 与 v2）更有解释力。
            </Notice>
          )}
          {both && sameSplit && a.data.playbook_version !== b.data.playbook_version && (
            <Notice tone="info" title={`同一组来访（${a.data.split} 组）上的版本对比：${a.data.playbook_version} 与 ${b.data.playbook_version}`} />
          )}
          {both && (a.data.veto.passed === false || b.data.veto.passed === false) && (
            <Notice tone="danger" title="有运行未通过否决规则检查，请先查看该运行报告中的否决原因" />
          )}

          {both && (
            <div className="table-wrap" tabIndex={0} aria-label="指标对比">
              <table className="table compare-table">
                <thead>
                  <tr>
                    <th>指标</th>
                    <th>
                      <ColumnHead state={a} />
                    </th>
                    <th>
                      <ColumnHead state={b} />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {ROWS.map((row) => {
                    const va = row.get(a.data.metrics);
                    const vb = row.get(b.data.metrics);
                    const w = winner(va, vb, row.better);
                    return (
                      <tr key={row.title} className={row.primary ? 'primary-row' : ''}>
                        <td>{row.title}</td>
                        <td className={w === 'left' ? 'better' : ''}>{row.fmt(va)}</td>
                        <td className={w === 'right' ? 'better' : ''}>{row.fmt(vb)}</td>
                      </tr>
                    );
                  })}
                  <tr>
                    <td>否决规则检查</td>
                    <td>{a.data.veto.passed ? '通过' : '未通过'}</td>
                    <td>{b.data.veto.passed ? '通过' : '未通过'}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
          <p className="small muted">
            数值均来自两份运行报告，前端只并排展示并标出较好的一侧（危机漏报、违反禁忌、平均 ISI 变化以低为好），不计算差值；是否由前端计算差值待团队确认。
          </p>
        </>
      )}
    </Card>
  );
}
