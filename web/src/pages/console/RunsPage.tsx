import { useEffect, useState } from 'react';
import { api } from '../../api';
import type { Experiment } from '../../api/extensionTypes';
import { useReadPoller } from '../../hooks/useReadPoller';
import { ExperimentCard } from '../../components/console/ExperimentCard';
import type { ExecutionMode, RunStatusResponse } from '../../api/draftTypes';
import { ErrorNotice, Notice, Spinner } from '../../components/common';
import { RecentRuns } from '../../components/console/RecentRuns';
import { RunCompare } from '../../components/console/RunCompare';
import { ReportView } from '../../components/ReportView';
import { RunLauncher } from '../../components/RunLauncher';
import { RunProgress } from '../../components/RunProgress';
import { SessionList } from '../../components/SessionList';
import type { ConsoleRunState } from '../../hooks/useConsoleRun';
import { isReportNotReady, type useReport } from '../../hooks/useRunData';

function sourceLabel(mode: ExecutionMode | null): string {
  if (api.adapter === 'mock') return '模拟数据（前端本地，报告与会谈取自 contracts 示例）';
  if (mode === 'mock') return '模拟数据（后端 Mock，报告与会谈取自 contracts 示例，进度为模拟）';
  if (mode === 'real') return '后端真实执行（来访仍为模拟数据）';
  return '数据来源待后端确认';
}

function subtitleFor(run: RunStatusResponse | null, hasRun: boolean, healthMode: ExecutionMode | null): string {
  const source = sourceLabel(run?.execution_mode ?? healthMode);
  if (!hasRun) return `准备一次模拟评测 · ${source}`;
  if (!run) return `正在查询运行状态 · ${source}`;
  switch (run.status) {
    case 'queued':
    case 'running':
      return `运行中，进度每秒更新 · ${source}`;
    case 'succeeded':
      return `运行已完成 · ${source}`;
    case 'failed':
      return `运行执行失败 · ${source}`;
  }
}

export function RunsPage({
  state,
  healthOk,
  healthChecked,
  healthMode,
}: {
  state: ConsoleRunState;
  healthOk: boolean;
  healthChecked: boolean;
  healthMode: ExecutionMode | null;
}) {
  const { runId, run, terminal, busy, poller, report, sessions, sessionVisitors, create, history } = state;
  const [comparison, setComparison] = useState<Experiment | null>(null);
  const experiment = useReadPoller('experiment', (signal) => api.getExperiment(signal), (data) => 'stage' in data && (data.stage === 'done' || data.stage === 'failed'));
  const stage = experiment.data && 'stage' in experiment.data ? experiment.data.stage : null;
  useEffect(() => { state.historyResource.reload(); }, [stage, state.historyResource.reload]);
  const [tab, setTab] = useState<'report' | 'compare'>('report');
  const disabledReason =
    api.adapter === 'http' && healthChecked && !healthOk ? '后端不可用，暂不能发起运行' : null;

  return (
    <div className="page">
      <RunLauncher
        adapter={api.adapter}
        healthMode={healthMode}
        subtitle={subtitleFor(run, Boolean(runId), healthMode)}
        busy={busy}
        disabledReason={disabledReason}
        submitting={create.submitting}
        error={create.error}
        pending={create.pending}
        onStart={(split, playbookVersion, backendScenario) =>
          create.start(playbookVersion ? { split, playbook_version: playbookVersion } : { split }, backendScenario)
        }
        onRetry={create.retry}
        onDiscard={create.discard}
      />

      <ExperimentCard poller={experiment} mock={api.adapter === 'mock' || healthMode === 'mock'} onCompare={(value) => { setComparison(value); setTab('compare'); }} />

      {(history.length >= 2 || comparison) && (
        <div className="tabs" role="tablist" aria-label="报告视图">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'report'}
            className={tab === 'report' ? 'tab active' : 'tab'}
            onClick={() => setTab('report')}
          >
            当前运行
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
      )}

      {tab === 'compare' ? (
        <RunCompare experiment={comparison} history={history} sourceNote={sourceLabel(run?.execution_mode ?? healthMode)} />
      ) : !runId ? (
        <p className="empty">
          还没有选中的运行。选择来访分组后点击“开始运行”{history.length > 0 ? '，或从下面的最近运行里选择' : ''}。
        </p>
      ) : (
        <>
          <RunProgress adapter={api.adapter} runId={runId} poller={poller} onClear={state.clearRun} />
          {run && <ReportSection run={run} report={report} sessionVisitors={sessionVisitors} />}
          {terminal && <SessionList runId={runId} state={sessions} onReload={sessions.reload} />}
        </>
      )}

      <div className="row">
        <button type="button" className="btn btn-sm" onClick={state.historyResource.reload}>刷新运行列表</button>
        {state.historyResource.status === 'loading' && <Spinner label="正在读取运行列表…" />}
      </div>
      {state.historyResource.status === 'error' && <ErrorNotice error={state.historyResource.error} tone="warn" title="运行列表读取失败，显示本机后备记录" />}
      {state.historyResource.status === 'ok' && history.length === 0 && <p className="muted">暂无运行记录。</p>}
      <RecentRuns
        fromServer={state.historyFromServer}
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
  // 运行中不占位，进度区已经说明
  if (run.status === 'queued' || run.status === 'running') return null;
  if (!run.report_available) {
    return run.status === 'failed' ? (
      <Notice tone="neutral" title="该运行没有可读取的报告" />
    ) : (
      <Spinner label="运行已完成，报告生成中…" />
    );
  }
  if (report.status === 'idle' || report.status === 'loading') return <Spinner label="正在读取报告…" />;
  if (report.status === 'error') {
    const notReady = isReportNotReady(report.error);
    return (
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
    );
  }
  return <ReportView report={report.data} run={run} sessionVisitors={sessionVisitors} />;
}
