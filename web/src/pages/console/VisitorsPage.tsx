import { useMemo, useState } from 'react';
import type { SessionListItem } from '../../api/draftTypes';
import { Badge, Card, ErrorNotice, Spinner } from '../../components/common';
import type { ConsoleRunState } from '../../hooks/useConsoleRun';
import { HREF, sessionHref } from '../../hooks/useHashRoute';
import { RUN_STATUS_LABEL, SESSION_STATUS_LABEL } from '../../lib/labels';

type Filter = 'all' | 'available' | 'failed' | 'crisis';

const FILTERS: { key: Filter; label: string; test: (i: SessionListItem) => boolean }[] = [
  { key: 'all', label: '全部', test: () => true },
  { key: 'available', label: '有会谈记录', test: (i) => i.session_available },
  { key: 'failed', label: '执行失败', test: (i) => i.status === 'failed' },
  { key: 'crisis', label: '危机流程结束', test: (i) => i.session_status === 'crisis_exit' },
];

export function VisitorsPage({ state }: { state: ConsoleRunState }) {
  const { runId, run, terminal, sessions } = state;
  const [filter, setFilter] = useState<Filter>('all');

  const items = useMemo(() => (sessions.status === 'ok' ? sessions.data.items : []), [sessions]);
  const counts = useMemo(
    () => Object.fromEntries(FILTERS.map((f) => [f.key, items.filter(f.test).length])) as Record<Filter, number>,
    [items],
  );
  const shown = items.filter(FILTERS.find((f) => f.key === filter)!.test);

  if (!runId) {
    return (
      <div className="page">
      <div className="page-title-row">
        <div>
          <h1>模拟来访</h1>
          <p className="muted">来访 ID 是匿名编号。会谈记录只读展示评测过程，不是实时聊天。</p>
        </div>
      </div>
        <p className="empty">
          还没有选中的运行。请先在 <a href={HREF.runs}>运行与报告</a> 里发起或选择一次运行。
        </p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-title-row">
        <div>
          <h1>模拟来访</h1>
          <p className="muted">来访 ID 是匿名编号。会谈记录只读展示评测过程，不是实时聊天。</p>
        </div>
      </div>
    <Card
      title="来访列表"
      aside={
        <span className="tags">
          <span className="mono small">{runId}</span>
          {run && <Badge>{`${run.split} 组 · ${run.playbook_version}`}</Badge>}
        </span>
      }
    >
      {!terminal && <p className="muted">运行结束后提供完整来访列表（首版不在运行中逐个展示）。</p>}
      {terminal && (
        <>
          <div className="chips" role="group" aria-label="筛选">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                className={filter === f.key ? 'chip active' : 'chip'}
                aria-pressed={filter === f.key}
                onClick={() => setFilter(f.key)}
              >
                {f.label} <span className="chip-count">{counts[f.key] ?? 0}</span>
              </button>
            ))}
          </div>
          {sessions.status === 'loading' && <Spinner label="正在读取来访列表…" />}
          {sessions.status === 'error' && <ErrorNotice error={sessions.error} title="来访列表读取失败" />}
          {sessions.status === 'ok' && (
            <div className="table-wrap" tabIndex={0} aria-label="来访列表">
              <table className="table">
                <thead>
                  <tr>
                    <th>来访</th>
                    <th>执行状态</th>
                    <th>会谈状态</th>
                    <th>记录</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.length === 0 && (
                    <tr>
                      <td colSpan={4} className="muted">
                        没有符合条件的来访。
                      </td>
                    </tr>
                  )}
                  {shown.map((i) => (
                    <tr key={i.visitor_id}>
                      <td className="mono">{i.visitor_id}</td>
                      <td>
                        <Badge tone={i.status === 'failed' ? 'danger' : i.status === 'succeeded' ? 'ok' : 'neutral'}>
                          {RUN_STATUS_LABEL[i.status]}
                        </Badge>
                      </td>
                      <td>{i.session_status ? SESSION_STATUS_LABEL[i.session_status] : <span className="muted">—</span>}</td>
                      <td>
                        {i.session_available ? (
                          <a href={sessionHref(runId, i.visitor_id)}>查看会谈</a>
                        ) : (
                          <span className="muted">无记录</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Card>
    </div>
  );
}
