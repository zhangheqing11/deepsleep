import { useCallback, useMemo, useState } from 'react';
import { api } from './api';
import type { CreateRunResponse } from './api/draftTypes';
import { ErrorNotice, Card, Notice, Spinner } from './components/common';
import { DataSourceBanner } from './components/DataSourceBanner';
import { HealthBar } from './components/HealthBar';
import { ReportView } from './components/ReportView';
import { RunLauncher } from './components/RunLauncher';
import { RunProgress } from './components/RunProgress';
import { SessionList } from './components/SessionList';
import { SessionView } from './components/SessionView';
import { useCreateRun } from './hooks/useCreateRun';
import { useHashRoute } from './hooks/useHashRoute';
import { isReportNotReady, useHealth, useReport, useSessionList } from './hooks/useRunData';
import { useRunPoller } from './hooks/useRunPoller';
import { currentRunStore, type SavedRun } from './lib/storage';

function loadSavedRun(): SavedRun | null {
  const saved = currentRunStore.get();
  // 不同数据来源的运行编号互不通用
  return saved && saved.adapter === api.adapter ? saved : null;
}

function Home({ healthOk, healthChecked }: { healthOk: boolean; healthChecked: boolean }) {
  const [saved, setSaved] = useState<SavedRun | null>(loadSavedRun);
  const runId = saved?.run_id ?? null;

  const poller = useRunPoller(runId, () => currentRunStore.clear());
  const run = poller.run;
  const terminal = run?.status === 'succeeded' || run?.status === 'failed';

  const report = useReport(runId, Boolean(run?.report_available));
  const sessions = useSessionList(runId, terminal);

  const onCreated = useCallback((res: CreateRunResponse) => {
    const next: SavedRun = { run_id: res.run_id, adapter: api.adapter, saved_at: new Date().toISOString() };
    currentRunStore.set(next);
    setSaved(next);
  }, []);
  const create = useCreateRun(onCreated);

  const clearRun = useCallback(() => {
    currentRunStore.clear();
    setSaved(null);
  }, []);

  const busy = Boolean(runId) && poller.stop === null && !terminal;
  const disabledReason =
    api.adapter === 'http' && healthChecked && !healthOk ? '后端不可用，暂不能发起运行' : null;

  const sessionVisitors = useMemo(() => {
    if (sessions.status !== 'ok') return new Set<string>();
    return new Set(sessions.data.items.filter((i) => i.session_available).map((i) => i.visitor_id));
  }, [sessions]);

  return (
    <div className="stack">
      <div className="grid-top">
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
        {runId ? (
          <RunProgress adapter={api.adapter} runId={runId} poller={poller} onClear={clearRun} />
        ) : (
          <Card title="当前运行">
            <p className="muted">还没有运行。选择来访分组后点击“开始运行”。</p>
          </Card>
        )}
      </div>

      {runId && run && <ReportSection runStatus={run.status} reportAvailable={run.report_available} report={report} run={run} sessionVisitors={sessionVisitors} />}

      {runId && terminal && <SessionList runId={runId} state={sessions} onReload={sessions.reload} />}
    </div>
  );
}

function ReportSection({
  runStatus,
  reportAvailable,
  report,
  run,
  sessionVisitors,
}: {
  runStatus: string;
  reportAvailable: boolean;
  report: ReturnType<typeof useReport>;
  run: NonNullable<ReturnType<typeof useRunPoller>['run']>;
  sessionVisitors: Set<string>;
}) {
  if (runStatus === 'queued' || runStatus === 'running') {
    return (
      <Card title="运行报告">
        <p className="muted">运行结束后在这里显示报告。</p>
      </Card>
    );
  }
  if (!reportAvailable) {
    return (
      <Card title="运行报告">
        {runStatus === 'failed' ? (
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

export function App() {
  const route = useHashRoute();
  const health = useHealth();
  const mode = health.status === 'ok' ? health.data.execution_mode : null;

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="#/">
          <svg viewBox="0 0 32 32" width="22" height="22" aria-hidden="true">
            <path d="M20 4a12 12 0 1 0 8 20A10 10 0 0 1 20 4z" fill="currentColor" />
          </svg>
          <span>
            deepsleep <span className="brand-sub">评测台</span>
          </span>
        </a>
        <HealthBar adapter={api.adapter} health={health} onRetry={health.reload} />
      </header>

      <DataSourceBanner adapter={api.adapter} mode={mode} />

      <main className="main">
        {route.name === 'session' ? (
          <SessionView runId={route.runId} visitorId={route.visitorId} adapter={api.adapter} mode={mode} />
        ) : (
          <Home healthOk={health.status === 'ok'} healthChecked={health.status === 'ok' || health.status === 'error'} />
        )}
      </main>

      <footer className="footer">
        所有来访均为模拟数据。页面展示的是干预路径与生活方式建议，不能替代专业医疗意见；如有需要，请建议就医。
      </footer>
    </div>
  );
}
