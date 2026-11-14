import { useState } from 'react';
import { api } from '../../api';
import type { RunStatusResponse } from '../../api/draftTypes';
import { Card, ErrorNotice, Notice, Spinner } from '../../components/common';
import { RecentRuns } from '../../components/console/RecentRuns';
import { RunCompare } from '../../components/console/RunCompare';
import { ReportView } from '../../components/ReportView';
import { RunLauncher } from '../../components/RunLauncher';
import { RunProgress } from '../../components/RunProgress';
import { SessionList } from '../../components/SessionList';
import type { ConsoleRunState } from '../../hooks/useConsoleRun';
import { isReportNotReady, type useReport } from '../../hooks/useRunData';

export function RunsPage({
  state,
  healthOk,
  healthChecked,
}: {
  state: ConsoleRunState;
  healthOk: boolean;
  healthChecked: boolean;
}) {
  const { runId, run, terminal, busy, poller, report, sessions, sessionVisitors, create, history } = state;
  const [tab, setTab] = useState<'report' | 'compare'>('report');
  const disabledReason =
    api.adapter === 'http' && healthChecked && !healthOk ? '后端不可用，暂不能发起运行' : null;

  return (
    <div className="stack">
      <div className="grid-top">
        <div className="stack">
          <RunLauncher
            adapter={api.adapter}
            busy={busy}
            disabledReason={disabledReason}
            submitting={create.submitting}
            error={create.error}
            pending={create.pending}
            onStart={(split, playbookVersion) =>
              create.start(playbookVersion ? { split, playbook_version: playbookVersion } : { split })
            }
            onRetry={create.retry}
            onDiscard={create.discard}
          />
        </div>
        <div className="stack">
          {runId ? (
            <RunProgress adapter={api.adapter} runId={runId} poller={poller} onClear={state.clearRun} />
          ) : (
            <Card title="当前运行">
              <p className="muted">还没有选中的运行。发起一次新运行，或从“最近运行”里选择。</p>
            </Card>
          )}
          <RecentRuns
            history={history}
            currentRunId={runId}
            disabled={busy}
            onSelect={(id) => {
              state.selectRun(id);
              setTab('report');
            }}
            onForget={state.forgetRun}
          />
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="报告视图">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'report'}
          className={tab === 'report' ? 'tab active' : 'tab'}
          onClick={() => setTab('report')}
        >
          本次报告
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'compare'}
          className={tab === 'compare' ? 'tab active' : 'tab'}
          onClick={() => setTab('compare')}
        >
          对比
        </button>
      </div>

      {tab === 'report' ? (
        <>
          {!runId && (
            <Card title="运行报告">
              <p className="muted">选中一个运行后在这里显示报告。</p>
            </Card>
          )}
          {runId && run && (
            <ReportSection run={run} report={report} sessionVisitors={sessionVisitors} />
          )}
          {runId && terminal && <SessionList runId={runId} state={sessions} onReload={sessions.reload} />}
        </>
      ) : (
        <RunCompare history={history} />
      )}
    </div>
  );
}

function ReportSection({
  run,
  report,
  sessionVisitors,
}: {
  run: RunStatusResponse;
  report: ReturnType<typeof useReport>;
  sessionVisitors: Set<string>;
}) {
  if (run.status === 'queued' || run.status === 'running') {
    return (
      <Card title="运行报告">
        <p className="muted">运行结束后在这里显示报告。</p>
      </Card>
    );
  }
  if (!run.report_available) {
    return (
      <Card title="运行报告">
        {run.status === 'failed' ? (
          <Notice tone="neutral" title="该运行没有可读取的报告" />
        ) : (
          <Spinner label="运行已完成，报告生成中…" />
        )}
      </Card>
    );
  }
  if (report.status === 'idle' || report.status === 'loading') {
    return (
      <Card title="运行报告">
        <Spinner label="正在读取报告…" />
      </Card>
    );
  }
  if (report.status === 'error') {
    const notReady = isReportNotReady(report.error);
    return (
      <Card title="运行报告">
        <ErrorNotice
          error={report.error}
          tone={notReady ? 'warn' : 'danger'}
          title={notReady ? '报告生成中，暂时还不能读取' : '报告读取失败'}
          action={
            <button type="button" className="btn btn-sm" onClick={report.reload}>
              重新读取
            </button>
          }
        />
      </Card>
    );
  }
  return <ReportView report={report.data} run={run} sessionVisitors={sessionVisitors} />;
}
